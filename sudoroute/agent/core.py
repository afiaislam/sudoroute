"""SudoRoute agent: plans multi-step financial tasks, calls tier-gated tools, prepares
signed proposals, and executes only after explicit confirmation (or within a signed,
bounded installment mandate).
"""

import copy
import math
import re
import time
from datetime import datetime, timedelta

from .. import config
from ..engines import budget as budget_engine
from ..engines import credit as credit_engine
from ..engines import fx_risk, fx_timing, routes
from ..engines.invoice_check import apply_ai_reading, parse_pasted_invoice, verify_invoice
from ..sandbox.reference_data import COUNTRY_RULES, PROVIDERS, UNIVERSITIES
from ..security import permissions, policy, totp
from ..security.audit import AuditLog
from ..security.guardrails import mask_account
from ..security.permissions import PROHIBITED_ACTIONS, TIER_LABELS, PermissionDenied, Tier
from ..security.proposals import ProposalError, ProposalStore, sandbox_otp
from . import intents, llm


def redact_obs(text: str) -> str:
    """Observations fed back to the planner: verified tool replies only, trimmed and with PII redacted."""
    from ..security.guardrails import redact
    return redact((text or "")[:600])



def script_lang(text: str) -> str | None:
    """'bn' or 'zh' when the message is written in Bengali or Chinese script; None otherwise (keep the UI language)."""
    bn = sum(1 for ch in text or "" if "\u0980" <= ch <= "\u09ff")
    zh = sum(1 for ch in text or "" if "\u4e00" <= ch <= "\u9fff")
    if bn >= 2 and bn >= zh:
        return "bn"
    if zh >= 2:
        return "zh"
    return None


_PREFIXES = {"md", "mst", "mosammat", "mohd", "mr", "mrs", "ms", "miss", "dr", "prof"}


def short_name(name: str) -> str:
    """First name for greetings; honorific prefixes such as "Md" or "Mst" are skipped."""
    parts = (name or "").split()
    while len(parts) > 1 and parts[0].rstrip(".").lower() in _PREFIXES:
        parts.pop(0)
    return parts[0] if parts else ""

class Context:
    def __init__(self, student_id: str, level: str):
        self.student_id = student_id
        self.level = level
        self.trace: list[dict] = []


class SudoRouteAgent:
    def __init__(self, bank, audit: AuditLog | None = None, proposals: ProposalStore | None = None):
        self.bank = bank
        self.audit = audit or AuditLog()
        self.proposals = proposals or ProposalStore()
        self.sessions: dict[str, dict] = {}
        self.mandates: dict[str, dict] = {}
        self.guardian_inbox: dict[str, list] = {}
        self.guardian_funding: dict[str, list] = {}
        self.use_llm = True  # the Security Lab runs an offline copy with this off
        self.llm = llm  # swappable: the Security Lab plugs in a deliberately hostile model here
        self.issuer = None  # set by the server (security.certificates.Issuer)
        self.certificates: dict[str, list] = {}
        # Students who linked an authenticator app: sid -> {"secret": base32, "last_step": int | None}.
        # When present, payment approval needs the app's code; the sandbox SMS code no longer works.
        self.totp: dict[str, dict] = {}
        # Second opinions from the quarantined AI reader, per (student, invoice). They can only add risk.
        self.ai_readings: dict[tuple, dict] = {}
        # Optional real SMS (sudoroute/sms.py): set by the server; called as sms_out(kind, ref, text)
        self.sms_out = None

    # ================================================================ sessions
    def session(self, sid: str) -> dict:
        self.bank.student(sid)  # validates id
        return self.sessions.setdefault(sid, {"level": permissions.DEFAULT_LEVEL, "sms_inbox": [],
                                              "notifications": []})

    def set_level(self, sid: str, level: str, actor: str = "student (settings UI)") -> dict:
        if level not in permissions.LEVELS:
            raise ValueError("unknown level")
        s = self.session(sid)
        old = s["level"]
        s["level"] = level
        self.audit.append("permission_level_changed", actor=actor, sim_time=self._now(),
                          student_id=sid, old=old, new=level)
        return {"level": level, **permissions.LEVELS[level]}

    def _now(self) -> str:
        return self.bank.now.isoformat()

    # ================================================================ tool gate
    def _call(self, ctx: Context, tool: str, tier: Tier, fn, *args, **kwargs):
        t0 = time.perf_counter()
        step = {"tool": tool, "tier": TIER_LABELS[tier], "status": "ok"}
        try:
            permissions.check(ctx.level, tier, tool)
        except PermissionDenied as e:
            step.update(status="denied", detail=str(e))
            ctx.trace.append(step)
            self.audit.append("permission_denied", actor="agent", sim_time=self._now(),
                              student_id=ctx.student_id, tool=tool, tier=TIER_LABELS[tier], reason=str(e))
            raise
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            step.update(status="error", detail=str(e))
            ctx.trace.append(step)
            self.audit.append("tool_error", actor="agent", sim_time=self._now(),
                              student_id=ctx.student_id, tool=tool, error=str(e))
            raise
        step["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        ctx.trace.append(step)
        self.audit.append("tool_call", actor="agent", sim_time=self._now(), student_id=ctx.student_id,
                          tool=tool, tier=TIER_LABELS[tier], ms=step["ms"])
        return result

    # ================================================================ chat entry
    def chat(self, sid: str, message: str, lang: str | None = None) -> dict:
        sess = self.session(sid)
        ctx = Context(sid, sess["level"])
        lang = script_lang(message) or lang   # reply in the language the student wrote in
        ctx.lang = lang
        parsed = intents.parse(message)
        pasted = parsed["slots"]["pasted"]
        # 1. Agentic planning. Rule-based refusals and pasted documents never go to the planner.
        if parsed["intent"] != "prohibited" and not pasted and self._llm():
            planned = self._plan_and_act(ctx, sid, message, lang)
            if planned is not None:
                return planned
        # 1b. Fallback: single-intent language understanding.
        if parsed["intent"] != "prohibited" and not pasted and self._llm():
            t0 = time.perf_counter()
            ai = self.llm.classify(message)
            self._ai_step(ctx, "classify_intent", t0, ai is not None,
                          f"→ {ai['intent']}" if ai else "fallback to rules")
            if ai:
                if ai["intent"] == "prohibited":
                    if ai["prohibited_action"]:  # the model may only make things stricter
                        parsed["intent"] = "prohibited"
                        parsed["slots"]["prohibited_action"] = ai["prohibited_action"]
                else:
                    parsed["intent"] = ai["intent"]
                    for k in ("installments", "pay_now"):
                        parsed["slots"][k] = parsed["slots"][k] or ai[k]
                    parsed["slots"]["invoice_id"] = parsed["slots"]["invoice_id"] or ai["invoice_id"]
                parsed["source"] = self.llm.provider()
        self.audit.append("user_message", actor="student", sim_time=self._now(), student_id=sid,
                          intent=parsed["intent"], intent_source=parsed["source"], text=message[:300])
        # 2. Deterministic, tier-gated tools.
        handler = getattr(self, f"_h_{parsed['intent']}")
        try:
            out = handler(ctx, parsed["slots"], message)
        except PermissionDenied as e:
            out = {"reply": f"I can't do that in the current mode. {e} You can change the mode in "
                            "Settings — I can't change it myself.", "cards": []}
        except LookupError as e:
            out = {"reply": str(e).strip("'\""), "cards": []}
        out.setdefault("cards", [])
        out.setdefault("reply_source", "template")
        # 3. Natural-language reply. Facts come from the draft; numbers are verified after rewriting.
        if out["reply_source"] == "template" and parsed["intent"] != "prohibited" and self._llm():
            t0 = time.perf_counter()
            shown = "[the student pasted an email/invoice for checking]" if pasted else message
            polished = self.llm.compose(shown, out["reply"], parsed["intent"], lang)
            self._ai_step(ctx, "write_reply", t0, polished is not None,
                          "numbers verified" if polished else "template kept")
            if polished:
                out["reply_draft"], out["reply"], out["reply_source"] = out["reply"], polished, self.llm.provider()
        out["intent"] = parsed["intent"]
        out["intent_source"] = parsed["source"]
        out["trace"] = ctx.trace
        out["level"] = ctx.level
        out["ai"] = self.llm.status()
        return out

    MAX_PLAN_ROUNDS = 3
    MAX_PLAN_TOOLS = 5

    def _plan_and_act(self, ctx, sid, message, lang):
        """Plan → act → observe loop. The model picks tools from a fixed list; every tool still goes through
        the permission gate, the policy engine and the audit log. Payment tools can only PREPARE a proposal.
        Returns None if the planner is unavailable (the caller falls back to single-intent handling)."""
        s = self._student(sid)
        context = (f"home {s['home_currency']}, study {s['study_currency']} in {s['study_country']}; "
                   f"open invoices: {', '.join(i['id'] for i in self.bank.student_invoices(sid) if self._outstanding(i) > 0.01) or 'none'}; "
                   f"assistant mode: {ctx.level}")
        hist = self.session(sid).setdefault("history", [])
        if hist:  # follow-ups ("ok, do it in installments") — the student's own recent messages, never pasted documents
            context += "\nRecent conversation (oldest first):\n" + "\n".join(
                f"- student: {redact_obs(h['msg'])[:160]} → tools: {', '.join(h['tools']) or 'none'}" for h in hist[-3:])
        observations, results, done_keys, plan_log = [], [], set(), []
        paid = False
        for rnd in range(self.MAX_PLAN_ROUNDS):
            t0 = time.perf_counter()
            p = self.llm.plan(message, context, observations or None)
            names = [x["tool"] for x in p["steps"]] if p else []
            self._ai_step(ctx, f"plan_round_{rnd + 1}", t0, p is not None,
                          (("→ " + ", ".join(names)) if names else "done") if p else "fallback to rules")
            if p is None:
                if rnd == 0:
                    return None
                break
            plan_log.append({"round": rnd + 1, "thought": p["thought"], "steps": names})
            new = [x for x in p["steps"] if (x["tool"], x["invoice_id"]) not in done_keys]
            for st in new:
                if len(results) >= self.MAX_PLAN_TOOLS or paid:
                    break
                done_keys.add((st["tool"], st["invoice_id"]))
                if st["tool"] == "prohibited":
                    if not st["prohibited_action"]:
                        continue  # the model may only make things stricter, with a concrete rule
                    slots = {"prohibited_action": st["prohibited_action"]}
                    out = self._h_prohibited(ctx, slots, message)
                    self.audit.append("user_message", actor="student", sim_time=self._now(), student_id=sid,
                                      intent="prohibited", intent_source=self.llm.provider() + "-planner", text=message[:300])
                    return self._finish(ctx, {**out, "plan": plan_log}, "prohibited", self.llm.provider() + "-planner",
                                        message, lang, pasted=False)
                slots = {"invoice_id": st["invoice_id"], "installments": st["installments"], "pay_now": st["pay_now"],
                         "pasted": False, "smart": st["tool"] == "smart_pay"}
                try:
                    out = getattr(self, f"_h_{st['tool']}")(ctx, slots, message)
                except PermissionDenied as e:
                    out = {"reply": f"I can't do that in the current mode. {e} You can change the mode in Settings — "
                                    "I can't change it myself.", "cards": []}
                except LookupError as e:
                    out = {"reply": str(e).strip("'\""), "cards": []}
                results.append((st["tool"], out))
                observations.append(f"[{st['tool']}] " + redact_obs(out.get("reply", "")))
                paid = paid or st["tool"] in self.llm.PAYMENT_TOOLS
            if p["done"] or paid or not new or len(results) >= self.MAX_PLAN_TOOLS:
                break
        if not results:
            return None
        intents_run = [r[0] for r in results]
        hist.append({"msg": message[:300], "tools": intents_run})
        del hist[:-6]
        self.audit.append("user_message", actor="student", sim_time=self._now(), student_id=sid,
                          intent="+".join(intents_run), intent_source=self.llm.provider() + "-planner", text=message[:300])
        self.audit.append("agent_plan", actor="ai-planner", sim_time=self._now(), student_id=sid,
                          rounds=len(plan_log), tools=intents_run)
        cards, replies, sources = [], [], set()
        for _, out in results:
            cards += out.get("cards", [])
            replies.append(out.get("reply", ""))
            sources.add(out.get("reply_source", "template"))
        primary = next((t for t in intents_run if t in self.llm.PAYMENT_TOOLS), intents_run[0])
        combined = {"reply": "\n\n".join(r for r in replies if r), "cards": cards, "plan": plan_log,
                    "reply_source": "template" if "template" in sources else sources.pop()}
        return self._finish(ctx, combined, primary, self.llm.provider() + "-planner", message, lang, pasted=False)

    def _finish(self, ctx, out, intent, source, message, lang, pasted):
        out.setdefault("cards", [])
        out.setdefault("reply_source", "template")
        if out["reply_source"] == "template" and intent != "prohibited" and self._llm():
            t0 = time.perf_counter()
            shown = "[the student pasted an email/invoice for checking]" if pasted else message
            polished = self.llm.compose(shown, out["reply"], intent, lang)
            self._ai_step(ctx, "write_reply", t0, polished is not None,
                          "numbers verified" if polished else "template kept")
            if polished:
                out["reply_draft"], out["reply"], out["reply_source"] = out["reply"], polished, self.llm.provider()
        out["intent"] = intent
        out["intent_source"] = source
        out["trace"] = ctx.trace
        out["level"] = ctx.level
        out["ai"] = self.llm.status()
        return out

    def _llm(self) -> bool:
        return self.use_llm and self.llm.enabled()

    def _ai_step(self, ctx, name: str, t0: float, ok: bool, detail: str) -> None:
        st = self.llm.status()
        ctx.trace.append({"tool": f"{st['provider']}.{name}", "tier": f"AI · {st['model'] or 'language'}",
                          "status": "ok" if ok else "fallback", "detail": detail,
                          "ms": round((time.perf_counter() - t0) * 1000, 1)})

    def _h_general(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        uni = UNIVERSITIES[s["university_id"]]
        context = (f"{COUNTRY_RULES.get(s['home_country'], {}).get('name', s['home_country'])} student "
                   f"({s['home_currency']}) studying {s['program']} at {uni['name']} in {uni['city']}, "
                   f"{s['study_country']} ({s['study_currency']}).")
        t0 = time.perf_counter()
        ans = self.llm.answer(msg, context, getattr(ctx, "lang", None)) if self._llm() else None
        if self._llm():
            self._ai_step(ctx, "answer_question", t0, ans is not None, "answered" if ans else "unavailable")
        if ans:
            return {"reply": ans, "reply_source": self.llm.provider(), "cards": [{"type": "suggestions", "items": [
                "Pay my tuition", "Compare transfer options", "When should I pay?"]}]}
        out = self._h_help(ctx, slots, msg)
        out["reply"] = ("I'm best at your tuition and money tasks — paying tuition, checking invoices for scams, "
                        "comparing transfer channels, exchange-rate risk, budgeting and credit. "
                        + ("" if self._llm() else "Open questions are answered when Gemini is connected. ")
                        + "Try one of these:")
        return out

    # ================================================================ helpers
    def _student(self, sid):
        return self.bank.student(sid)

    def _unverified_reply(self, sid) -> str | None:
        uni = UNIVERSITIES[self._student(sid)["university_id"]]
        if uni.get("verified", True):
            return None
        return (f"{uni['name']} isn't verified yet, so I won't prepare any payment to it. Before the first payment, "
                "SudoRoute confirms the university's official bank account directly with its finance office — never "
                "from an invoice or an e-mail. You can still paste an invoice e-mail and I'll check it for scams.")

    def _pick_invoice(self, ctx, slots, require_safe=True):
        invs = self._call(ctx, "list_invoices", Tier.READ, self.bank.student_invoices, ctx.student_id)
        if not invs and self._unverified_reply(ctx.student_id):
            raise LookupError(self._unverified_reply(ctx.student_id))
        if slots.get("invoice_id"):
            match = [i for i in invs if i["id"] == slots["invoice_id"]]
            if not match:
                raise LookupError(f"I couldn't find invoice {slots['invoice_id']} in your account.")
            return match[0]
        open_invs = [i for i in invs if self._outstanding(i) > 0.01]
        if require_safe:
            student = self._student(ctx.student_id)
            open_invs = [i for i in open_invs if verify_invoice(i, student)["verdict"] != "BLOCK"]
        if not open_invs:
            raise LookupError("You have nothing left to pay — all your tuition invoices are paid or already "
                              "on their way. Ask 'Where is my payment?' to track them.")
        return sorted(open_invs, key=lambda i: i["due"])[0]

    def _outstanding(self, inv) -> float:
        return round(inv["amount"] - inv["paid"] - policy._in_transit(self.bank, inv["id"]), 2)

    def _nothing_due(self, inv):
        if self._outstanding(inv) <= 0.01:
            return {"reply": f"{inv['id']} is already fully paid or the payment is on its way — nothing left to "
                             "optimise. Ask 'Where is my payment?' to track it."}
        return None

    def _days_to_due(self, invoice) -> float:
        return (datetime.fromisoformat(invoice["due"]) - self.bank.now).total_seconds() / 86400

    # ================================================================ intents
    def _h_help(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        phish = next((i["id"] for i in self.bank.student_invoices(ctx.student_id) if "PHISH" in i["id"]), None)
        return {"reply": (f"Hi {short_name(s['name'])}! I'm SudoRoute. I can pay your tuition safely and cheaply, "
                          "check whether an invoice is a scam, compare transfer channels, show how exchange-rate "
                          "moves could affect your tuition, review your budget and plan your credit history. "
                          "Money only moves after you confirm with a one-time code."),
                "cards": [{"type": "suggestions", "items": [
                    "Pay my tuition", f"Is {phish} real?" if phish else "Check an invoice e-mail", "Compare transfer options",
                    "When should I pay? (FX risk)", "Show my budget", "How do I build credit?"]}]}

    def _h_balances(self, ctx, slots, msg):
        s = self._call(ctx, "get_balances", Tier.READ, lambda: copy.deepcopy(self._student(ctx.student_id)))
        study = s["study_currency"]
        rows = [{"currency": c, "amount": a, "in_study": round(self.bank.market.convert(a, c, study), 2)}
                for c, a in s["balances"].items()]
        total = sum(r["in_study"] for r in rows)
        return {"reply": f"Your wallets are worth about {total:,.0f} {study} in total.",
                "cards": [{"type": "balances", "rows": rows, "study_currency": study}]}

    def _h_list_invoices(self, ctx, slots, msg):
        invs = self._call(ctx, "list_invoices", Tier.READ, self.bank.student_invoices, ctx.student_id)
        s = self._student(ctx.student_id)
        rows = []
        for i in invs:
            v = verify_invoice(i, s)
            rows.append({"id": i["id"], "from": i["sender_email"], "amount": i["amount"], "currency": i["currency"],
                         "due": i["due"][:10], "status": i["status"], "verdict": v["verdict"], "score": v["score"]})
        return {"reply": f"You have {len(rows)} invoice(s). I've pre-screened each one for scam signals.",
                "cards": [{"type": "invoices", "rows": rows}]}

    def _h_verify_invoice(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        if slots.get("pasted"):
            inv = self._call(ctx, "parse_untrusted_document", Tier.READ, parse_pasted_invoice, msg)
            targets = [inv]
        elif slots.get("invoice_id"):
            targets = [self._pick_invoice(ctx, slots, require_safe=False)]
        else:
            targets = [i for i in self._call(ctx, "list_invoices", Tier.READ, self.bank.student_invoices,
                                             ctx.student_id) if i["status"] != "paid"]
        cards, lines = [], []
        for inv in targets:
            v = self._call(ctx, "verify_invoice", Tier.ANALYZE, verify_invoice, inv, s)
            v = self._ai_second_opinion(ctx, inv, v, read=len(targets) == 1)
            self.audit.append("invoice_verified", actor="agent", sim_time=self._now(), student_id=ctx.student_id,
                              invoice_id=inv["id"], verdict=v["verdict"], score=v["score"],
                              reasons=[r["code"] for r in v["reasons"]])
            if v["injection_scan"]["suspicious"]:
                self.audit.append("prompt_injection_blocked", actor="guardrail", sim_time=self._now(),
                                  student_id=ctx.student_id, invoice_id=inv["id"],
                                  findings=[f["detail"] for f in v["injection_scan"]["findings"]])
            cards.append({"type": "risk", "invoice": {"id": inv["id"], "from": inv.get("sender_email"),
                                                      "amount": inv.get("amount"), "currency": inv.get("currency")},
                          **v})
            emoji = {"SAFE": "✅", "REVIEW": "⚠️", "BLOCK": "⛔"}[v["verdict"]]
            lines.append(f"{emoji} {inv['id']}: {v['verdict']} (risk {v['score']}/100). {v['advice']}")
        return {"reply": "\n".join(lines), "cards": cards}

    def _ai_second_opinion(self, ctx, inv, v, read=True):
        """Quarantined AI reader (dual-LLM pattern): a model with no tools reads the untrusted text and returns
        typed fields only. The result can add risk points, never remove them, and never reaches the planner."""
        key = (ctx.student_id, inv.get("id"))
        reading = self.ai_readings.get(key) if inv.get("id") != "PASTED" else None
        if reading is None and read and self._llm() and inv.get("text"):
            t0 = time.perf_counter()
            reading = self.llm.read_document(inv["text"] if inv.get("id") == "PASTED"
                                        else f"From: {inv.get('sender_email', '')}\nSubject: {inv.get('subject', '')}\n\n{inv['text']}")
            self._ai_step(ctx, "quarantined_reader", t0, reading is not None,
                          "typed fields only · can add risk, never remove" if reading else "rules only")
            if reading and inv.get("id") != "PASTED":
                self.ai_readings[key] = reading
        merged = apply_ai_reading(v, reading, inv)
        if reading and merged["ai_reader"].get("added"):
            self.audit.append("ai_reader_raised_risk", actor="ai-quarantined", sim_time=self._now(),
                              student_id=ctx.student_id, invoice_id=inv.get("id"), added=merged["ai_reader"]["added"],
                              rule_score=v["score"], score=merged["score"])
        return merged

    def _h_compare_routes(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        inv = self._pick_invoice(ctx, slots)
        if self._nothing_due(inv):
            return self._nothing_due(inv)
        uni = UNIVERSITIES[s["university_id"]]
        r = self._call(ctx, "compare_routes", Tier.ANALYZE, routes.compare_routes, self.bank.market,
                       src=s["home_currency"], dst=inv["currency"], amount_dst=self._outstanding(inv),
                       days_to_due=self._days_to_due(inv), university_id=uni["id"], home_country=s["home_country"])
        return {"reply": " ".join(r["explanation"]), "cards": [{"type": "routes", "invoice_id": inv["id"], **r}]}

    def _h_fx_risk(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        inv = self._pick_invoice(ctx, slots)
        if self._nothing_due(inv):
            return self._nothing_due(inv)
        plan = self._analyse(ctx, s, inv)
        f = plan["fx"]
        rec = f["strategies"][f["recommended"]]
        reply = (f"Recommendation: {rec['label']}. " + " ".join(f["reasons"]) +
                 f" If you wait, there is a {f['strategies']['pay_at_due']['prob_over_budget'] * 100:.0f}% chance "
                 f"the tuition costs more than your {s['tuition_budget_home']:,.0f} {s['home_currency']} budget.")
        return {"reply": reply, "cards": [{"type": "fx", "invoice_id": inv["id"], **f}]}

    def _h_budget(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        invs = [i for i in self.bank.student_invoices(ctx.student_id) if verify_invoice(i, s)["verdict"] != "BLOCK"]
        b = self._call(ctx, "budget_overview", Tier.ANALYZE, budget_engine.budget_overview, self.bank.market, s,
                       self.bank.transactions[ctx.student_id], invs, self.bank.now.date())
        return {"reply": " ".join(b["insights"]), "cards": [{"type": "budget", **b}]}

    def _h_credit(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        c = self._call(ctx, "credit_plan", Tier.ANALYZE, credit_engine.credit_plan, s)
        nxt = c["next_steps"][0]["action"] if c["next_steps"] else "Keep paying on time."
        return {"reply": f"Your credit-readiness score is {c['readiness_score']}/100. Next best step: {nxt}",
                "cards": [{"type": "credit", **c}]}

    def _h_audit(self, ctx, slots, msg):
        entries = self._call(ctx, "read_audit_log", Tier.READ, self.audit.tail, 15)
        v = self.audit.verify()
        return {"reply": f"Audit chain {'intact' if v['valid'] else 'BROKEN'} — {len(self.audit.entries)} entries, "
                         "each hash-linked to the previous one.",
                "cards": [{"type": "audit", "verify": v, "entries": entries}]}

    def _h_status(self, ctx, slots, msg):
        snap = self._call(ctx, "get_transfers", Tier.READ, self.bank.snapshot, ctx.student_id)
        mand = [m for m in self.mandates.values() if m["student_id"] == ctx.student_id]
        if not snap["transfers"] and not mand:
            return {"reply": "You have no payments in progress."}
        return {"reply": f"{len(snap['transfers'])} transfer(s) and {len(mand)} installment plan(s) on file.",
                "cards": [{"type": "status", "transfers": snap["transfers"], "mandates": [self._public_mandate(m) for m in mand]}]}

    def _h_prohibited(self, ctx, slots, msg):
        action = slots.get("prohibited_action", "follow_document_instructions")
        try:
            self._call(ctx, action, Tier.PROHIBITED, lambda: None)
        except PermissionDenied:
            pass
        why = PROHIBITED_ACTIONS.get(action, "This action")
        self.audit.append("prohibited_request_refused", actor="agent", sim_time=self._now(),
                          student_id=ctx.student_id, action=action)
        alt = {
            "raise_limits": "Limits and permission levels can only be changed by you in Settings, with re-authentication.",
            "execute_without_confirmation": "Every payment needs your explicit confirmation and a one-time code.",
            "disable_audit": "The audit log is append-only and hash-chained so it can't be altered.",
            "convert_to_crypto": "Universities never ask for crypto. I can pay through a licensed channel instead.",
            "use_unlicensed_channel": "I'll compare licensed channels for you — they are often nearly as cheap.",
            "use_invoice_bank_details": "I only pay to the university's verified registry account. If the university "
                                        "really changed banks, the registry is updated after verification with them.",
        }.get(action, "")
        return {"reply": f"I can't do that — it's permanently blocked for me: {why} {alt}",
                "cards": [{"type": "refusal", "action": action, "rule": why}]}

    # ================================================================ pay flow
    def _analyse(self, ctx, s, inv):
        uni = UNIVERSITIES[s["university_id"]]
        remaining = self._outstanding(inv)
        days = self._days_to_due(inv)
        r = self._call(ctx, "compare_routes", Tier.ANALYZE, routes.compare_routes, self.bank.market,
                       src=s["home_currency"], dst=inv["currency"], amount_dst=remaining, days_to_due=days,
                       university_id=uni["id"], home_country=s["home_country"])
        best = r["best"]
        if best is None:
            raise LookupError("No licensed channel can deliver this payment on time.")
        provider = PROVIDERS[best["provider_id"]]
        horizon = max(1, math.floor(days - config.ARRIVAL_BUFFER_DAYS - provider["days"][1]))
        f = self._call(ctx, "fx_budget_at_risk", Tier.ANALYZE, fx_risk.budget_at_risk, self.bank.market,
                       s["home_currency"], inv["currency"], remaining, horizon,
                       budget_src=s["tuition_budget_home"], available_src=s["balances"].get(s["home_currency"], 0.0),
                       fx_markup=provider["fx_markup"], installments=uni["max_installments"],
                       allows_installments=uni["allows_installments"])
        return {"routes": r, "fx": f, "provider": provider, "remaining": remaining, "horizon": horizon, "uni": uni}

    def _h_pay_tuition(self, ctx, slots, msg):
        s = self._student(ctx.student_id)
        if s.get("frozen"):
            self.audit.append("payment_refused_frozen", actor="agent", sim_time=self._now(), student_id=s["id"])
            who = (f"Your guardian {s['frozen']['name']} switched it on, so only they can release it."
                   if s["frozen"]["by"] == "guardian" else "You can release it from the top bar (it needs your password).")
            return {"reply": f"⏸ The kill switch is on, so I can't prepare any payment. {who}", "cards": []}
        if self._unverified_reply(s["id"]):
            self.audit.append("payment_refused_unverified_university", actor="agent", sim_time=self._now(),
                              student_id=s["id"], university_id=s["university_id"])
            return {"reply": "⏳ " + self._unverified_reply(s["id"]), "cards": []}
        inv = self._pick_invoice(ctx, slots, require_safe=not slots.get("invoice_id"))
        v = self._call(ctx, "verify_invoice", Tier.ANALYZE, verify_invoice, inv, s)
        v = apply_ai_reading(v, self.ai_readings.get((ctx.student_id, inv["id"])), inv)  # an earlier AI flag still counts
        if v["verdict"] == "BLOCK":
            self.audit.append("payment_refused_scam", actor="agent", sim_time=self._now(), student_id=ctx.student_id,
                              invoice_id=inv["id"], score=v["score"])
            return {"reply": f"⛔ I won't pay {inv['id']}. It scored {v['score']}/100 on scam risk. {v['advice']}",
                    "cards": [{"type": "risk", "invoice": {"id": inv["id"], "from": inv["sender_email"],
                                                           "amount": inv["amount"], "currency": inv["currency"]}, **v}]}
        if self._nothing_due(inv):
            return self._nothing_due(inv)

        plan = self._analyse(ctx, s, inv)
        f, provider, uni = plan["fx"], plan["provider"], plan["uni"]

        strategy = f["recommended"]
        if slots.get("installments") and "installments" in f["strategies"]:
            strategy = "installments"
        elif slots.get("pay_now") and f["strategies"]["pay_now"]["affordable_now"]:
            strategy = "pay_now"
        st = f["strategies"][strategy]

        quoted_rate = self.bank.market.mid(s["home_currency"], inv["currency"]) * (1 - provider["fx_markup"])
        fee_src = provider["fee_usd"] * self.bank.market.units_per_usd(s["home_currency"])
        timing, smart_note = None, ""
        if slots.get("smart"):
            # Smart timing: one payment, executed by the agent on the first day the target rate is reached,
            # or on the latest safe day at the market rate. Needs at least 2 days of room to be useful.
            pay_by = datetime.fromisoformat(inv["due"]) - timedelta(days=config.ARRIVAL_BUFFER_DAYS + provider["days"][1])
            horizon = (pay_by.date() - self.bank.now.date()).days
            if horizon >= 2:
                timing = self._call(ctx, "fx_smart_timing", Tier.ANALYZE, fx_timing.plan, self.bank.market,
                                    s["home_currency"], inv["currency"], plan["remaining"], quoted_rate,
                                    provider["fx_markup"], fee_src, horizon)
                timing["deadline"] = pay_by.date().isoformat()
                strategy, st = "smart_timing", {"legs": [{"day": horizon, "fraction": 1.0}]}
            else:
                smart_note = ("There isn't enough time before the latest safe day to wait for a better rate, "
                              "so I've prepared a payment for today instead. ")
                strategy, st = "pay_now", f["strategies"]["pay_now"]
        legs = []
        leg_specs = st["legs"] if strategy != "pay_at_due" else [{"day": 0, "fraction": 1.0}]
        for i, leg in enumerate(leg_specs):
            if i == len(leg_specs) - 1:
                dst_amt = round(plan["remaining"] - sum(l["dst_amount"] for l in legs), 2)
            else:
                dst_amt = round(plan["remaining"] * leg["fraction"], 2)
            src_amt = round(dst_amt / quoted_rate + fee_src, 2)
            legs.append({"leg": i + 1, "day_offset": leg["day"],
                         "execute_on": (self.bank.now + timedelta(days=leg["day"])).date().isoformat(),
                         "dst_amount": dst_amt, "src_amount_quote": src_amt})
        if strategy == "pay_at_due":
            strategy = "pay_now"  # never auto-defer a payment: waiting only adds risk to an approved plan

        checks = self._call(ctx, "policy_precheck", Tier.ANALYZE, policy.evaluate, self.bank, student=s,
                            university_id=uni["id"], provider_id=provider["id"], invoice=inv,
                            invoice_verdict=v["verdict"], leg_dst_amount=legs[0]["dst_amount"],
                            leg_src_amount=legs[0]["src_amount_quote"], payee_account=uni["beneficiary"]["account"],
                            disclosed_installments=len(legs))

        payload = {
            "proposal_id": self.bank.new_id("PRP"), "student_id": s["id"], "invoice_id": inv["id"],
            "university_id": uni["id"], "university_name": uni["name"],
            "payee_account": uni["beneficiary"]["account"], "payee_bank": uni["beneficiary"]["bank"],
            "reference": s["student_ref"], "provider_id": provider["id"], "provider_name": provider["name"],
            "src_currency": s["home_currency"], "dst_currency": inv["currency"],
            "quoted_rate": round(quoted_rate, 8), "strategy": strategy, "legs": legs,
            "total_dst": round(sum(l["dst_amount"] for l in legs), 2),
            "total_src_quote": round(sum(l["src_amount_quote"] for l in legs), 2),
            "max_slippage": config.MANDATE_MAX_SLIPPAGE, "invoice_verdict": v["verdict"],
            "created_sim": self._now(),
            "second_factor": "totp" if s["id"] in self.totp else "sms",
        }
        # How SudoRoute would earn money (see /pricing): one visible service fee, never a hidden FX markup.
        # 0.5% of the payment, at least USD 3 and at most USD 25 — shown on every quote, waived during the pilot.
        fee_usd = min(config.SERVICE_FEE_CAP_USD, max(config.SERVICE_FEE_MIN_USD,
                                                      config.SERVICE_FEE_RATE * self.bank.market.to_usd(payload["total_dst"], inv["currency"])))
        payload["service_fee"] = {"rate": config.SERVICE_FEE_RATE, "min_usd": config.SERVICE_FEE_MIN_USD,
                                  "cap_usd": config.SERVICE_FEE_CAP_USD, "usd": round(fee_usd, 2),
                                  "amount_src": round(fee_usd * self.bank.market.units_per_usd(s["home_currency"]), 2),
                                  "waived": config.SERVICE_FEE_WAIVED}
        if timing:
            payload["timing"] = {k: timing[k] for k in ("target_rate", "floor_rate", "deadline", "p_target_hit",
                                                         "target_improvement_pct", "expected_saving_src",
                                                         "max_cost_src", "best_case_src")}
        # Only one live approval per invoice: a new quote supersedes older pending ones.
        for old_id, old in self.proposals.proposals.items():
            if old["payload"]["invoice_id"] == inv["id"] and old["status"] in ("awaiting_guardian", "awaiting_confirmation"):
                old["status"] = "cancelled"
                self.audit.append("proposal_superseded", actor="agent", sim_time=self._now(), student_id=s["id"],
                                  proposal_id=old_id, replaced_by=payload["proposal_id"])
        audit_ai = self._audit_ai(ctx, self._proposal_facts(s, inv, payload, checks, v), "proposal")
        if audit_ai and audit_ai["hold"]:
            payload["ai_hold"] = {"reason": audit_ai["reason"]}  # signed with the proposal; only a human can clear it
        guardians = s.get("guardians", [])
        need_guardian = bool(guardians) and s.get("guardian_approval", True)
        payload["guardian_required"] = need_guardian
        payload["guardian_ids"] = [g["id"] for g in guardians] if need_guardian else []
        signed = self._call(ctx, "create_signed_proposal", Tier.PREPARE, self.proposals.create, payload,
                            ttl=2 * 3600 if need_guardian else None,
                            status="awaiting_guardian" if need_guardian else "awaiting_confirmation")
        if need_guardian:
            for g in guardians:
                gotp = sandbox_otp("guardian:" + payload["proposal_id"], self.proposals.key)
                gtext = (f"SudoRoute guardian code {gotp}: {s['name']} asks you to approve "
                         f"{payload['total_dst']:,.2f} {payload['dst_currency']} to {uni['name']}. Never share this code.")
                self.guardian_inbox.setdefault(g["id"], []).append({
                    "to": g.get("phone_masked") or "guardian sandbox phone", "proposal_id": payload["proposal_id"],
                    "text": gtext})
                if self.sms_out:
                    self.sms_out("guardian", g["id"], gtext)
        sess = self.session(ctx.student_id)
        if payload["second_factor"] == "sms":
            otp = sandbox_otp(payload["proposal_id"], self.proposals.key)
            stext = (f"SudoRoute code {otp}: approve {payload['total_dst']:,.2f} "
                     f"{payload['dst_currency']} to {uni['name']}. Never share this code.")
            sess["sms_inbox"].append({"to": s["phone_masked"] or "your sandbox phone", "proposal_id": payload["proposal_id"],
                                      "text": stext})
            if self.sms_out:
                self.sms_out("student", s["id"], stext)
        self.audit.append("proposal_created", actor="agent", sim_time=self._now(), student_id=s["id"],
                          proposal_id=payload["proposal_id"], invoice_id=inv["id"], provider=provider["id"],
                          strategy=strategy, legs=len(legs), total_dst=payload["total_dst"],
                          total_src_quote=payload["total_src_quote"], payee=mask_account(payload["payee_account"]),
                          policy_allowed=checks["allowed"])

        code_where = "from your authenticator app" if payload["second_factor"] == "totp" else "sent to your phone"
        if timing:
            reply = (f"{smart_note}I've prepared a smart-timing payment of {payload['total_dst']:,.2f} {inv['currency']} to "
                     f"{uni['name']} via {provider['name']}. After you approve, I'll check the rate every day and pay as soon "
                     f"as it reaches {timing['target_rate']:.6f} ({timing['target_improvement_pct']}% better than today), "
                     f"or on {timing['deadline']} at the market rate so it still arrives on time. Chance the target is "
                     f"reached: {timing['p_target_hit'] * 100:.0f}%. You'll never pay more than "
                     f"{timing['max_cost_src']:,.0f} {s['home_currency']} — if the rate falls further, I pause and ask you. ")
        else:
            leg_txt = (f"in {len(legs)} installments ({', '.join(l['execute_on'] for l in legs)})"
                       if len(legs) > 1 else "today")
            reply = (f"{smart_note}I've prepared a payment of {payload['total_dst']:,.2f} {inv['currency']} to {uni['name']} via "
                     f"{provider['name']}, {leg_txt}. Estimated cost {payload['total_src_quote']:,.0f} "
                     f"{s['home_currency']}. ")
        if plan["routes"]["savings_vs_bank_src"]:
            reply += f"That's {plan['routes']['savings_vs_bank_src']:,.0f} {s['home_currency']} cheaper than a bank wire. "
        if payload.get("ai_hold"):
            reply += f"⚠ The independent AI auditor put this on hold: {payload['ai_hold']['reason']} You can still decide to pay. "
        if checks["allowed"] and need_guardian:
            names = " and ".join(short_name(g["name"]) for g in guardians)
            reply += (f"All compliance checks passed. Because family funds are involved, {names} must approve it "
                      f"first; after that, confirm with the one-time code {code_where}.")
        elif checks["allowed"]:
            reply += f"All compliance checks passed. Enter the one-time code {code_where} to confirm."
        else:
            reply += "Some checks need attention before this can be confirmed: " + ", ".join(checks["failed"]) + "."
        card = {"type": "proposal", "proposal": signed["payload"], "token": signed["token"], "checks": checks,
                "can_confirm": checks["allowed"], "otp_hint": "Sandbox: the code is in the SMS inbox panel.",
                "fx_summary": {k: {"label": x["label"], "expected": x["expected"], "p95": x["p95"],
                                   "prob_over_budget": x["prob_over_budget"]} for k, x in f["strategies"].items()},
                "route_explanation": plan["routes"]["explanation"],
                "documents": COUNTRY_RULES.get(s["home_country"], {}).get("documents", []),
                "status": "awaiting_guardian" if need_guardian else "awaiting_confirmation",
                "guardians": [g["name"] for g in guardians] if need_guardian else [],
                "timing": timing}
        self.proposals.proposals[payload["proposal_id"]]["card"] = {k: v for k, v in card.items() if k != "token"}
        return {"reply": reply, "cards": [card]}

    def _audit_ai(self, ctx, facts: str, where: str) -> dict | None:
        """Independent AI auditor: may only put a payment on hold for a human to look again. It cannot approve,
        unblock, change or execute anything; without a model it simply does not run."""
        if not self._llm():
            return None
        t0 = time.perf_counter()
        a = self.llm.audit_proposal(facts)
        if ctx is not None:
            self._ai_step(ctx, "independent_auditor", t0, a is not None,
                          ("HOLD — " + a["reason"]) if a and a["hold"] else ("no concerns" if a else "unavailable"))
        if a and a["hold"]:
            self.audit.append("ai_auditor_hold", actor="ai-auditor", sim_time=self._now(),
                              student_id=ctx.student_id if ctx else None, where=where, reason=a["reason"])
        return a

    def _proposal_facts(self, s, inv, payload, checks, v) -> str:
        paid_before = [t for t in self.bank.transfers.values() if t["invoice_id"] == inv["id"]]
        return (f"Student home currency {s['home_currency']}, tuition budget {s['tuition_budget_home']:,.0f}, "
                f"wallet {s['balances'].get(s['home_currency'], 0):,.0f} {s['home_currency']}.\n"
                f"Invoice {inv['id']}: {inv['amount']:,.2f} {inv['currency']}, already paid {inv['paid']:,.2f}, due {inv['due'][:10]}, "
                f"scam check {v['verdict']} ({v['score']}/100; {', '.join(r['code'] for r in v['reasons']) or 'no warnings'}).\n"
                f"Earlier transfers for this invoice: {len(paid_before)} ({', '.join(t['status'] for t in paid_before) or 'none'}).\n"
                f"Prepared payment: {payload['total_dst']:,.2f} {payload['dst_currency']} to the verified registry account of "
                f"{payload['university_name']} via {payload['provider_name']}, strategy {payload['strategy']}, "
                f"{len(payload['legs'])} leg(s), estimated cost {payload['total_src_quote']:,.0f} {payload['src_currency']}.\n"
                f"Compliance checks: {'all passed' if checks['allowed'] else 'failed: ' + ', '.join(checks['failed'])}.")

    def _h_smart_pay(self, ctx, slots, msg):
        return self._h_pay_tuition(ctx, {**slots, "smart": True, "installments": False, "pay_now": False}, msg)

    # ================================================================ execution (T3)
    def confirm(self, sid: str, proposal_id: str, token: str, otp: str, acknowledge_review: bool = False,
                acknowledge_hold: bool = False) -> dict:
        sess = self.session(sid)
        ctx = Context(sid, sess["level"])
        try:
            permissions.check(ctx.level, Tier.EXECUTE, "execute_payment")
            if self._student(sid).get("frozen"):
                raise ProposalError("The kill switch is on. Nothing can be paid until it is released.", "frozen")
            rec = self.proposals.get(proposal_id)
            if rec["payload"]["student_id"] != sid:
                raise ProposalError("This proposal belongs to a different student.", "wrong_owner")
            if rec["status"] == "declined":
                raise ProposalError("Your guardian declined this payment.", "declined")
            if rec["payload"].get("guardian_required") and not rec.get("guardian_approval"):
                raise ProposalError("Waiting for your guardian to approve this payment first.", "awaiting_guardian")
            if rec["payload"].get("ai_hold") and not acknowledge_hold:
                raise ProposalError("The AI auditor put this payment on hold. Read its concern and tick the box if you "
                                    "still want to pay.", "ai_hold")
            app = self.totp.get(sid)
            matched = {}

            def _totp_ok(code, _app=app):
                step = totp.verify(_app["secret"], code, _app.get("last_step"))
                matched["step"] = step
                return step is not None

            payload = self.proposals.validate(proposal_id, token, otp, otp_check=_totp_ok if app else None)
            if app:
                app["last_step"] = matched["step"]  # each authenticator code works only once
        except (PermissionDenied, ProposalError) as e:
            code = getattr(e, "code", "denied")
            self.audit.append("execution_rejected", actor="security", sim_time=self._now(), student_id=sid,
                              proposal_id=proposal_id, code=code, reason=str(e))
            return {"ok": False, "code": code, "error": str(e)}

        self.proposals.mark(proposal_id, "executing")
        s = self._student(sid)
        inv = self.bank.invoices[payload["invoice_id"]]
        leg = payload["legs"][0]
        checks = policy.evaluate(self.bank, student=s, university_id=payload["university_id"],
                                 provider_id=payload["provider_id"], invoice=inv,
                                 invoice_verdict=payload["invoice_verdict"], leg_dst_amount=leg["dst_amount"],
                                 leg_src_amount=leg["src_amount_quote"], payee_account=payload["payee_account"],
                                 acknowledged_review=acknowledge_review, disclosed_installments=len(payload["legs"]))
        if not checks["allowed"]:
            self.proposals.mark(proposal_id, "cancelled")
            self.audit.append("execution_rejected", actor="policy", sim_time=self._now(), student_id=sid,
                              proposal_id=proposal_id, code="policy", failed=checks["failed"])
            return {"ok": False, "code": "policy", "error": "Policy checks failed: " + ", ".join(checks["failed"]),
                    "checks": checks}
        if payload.get("strategy") == "smart_timing":
            return self._start_smart_mandate(sid, proposal_id, payload, inv, checks)
        try:
            txn = self.bank.transfer(student_id=sid, src_currency=payload["src_currency"],
                                     src_amount=leg["src_amount_quote"], dst_currency=payload["dst_currency"],
                                     dst_amount=leg["dst_amount"], provider=PROVIDERS[payload["provider_id"]],
                                     university_id=payload["university_id"], reference=payload["reference"],
                                     invoice_id=payload["invoice_id"], proposal_id=proposal_id, leg=1)
        except ValueError as e:
            self.proposals.mark(proposal_id, "cancelled")
            self.audit.append("execution_rejected", actor="bank", sim_time=self._now(), student_id=sid,
                              proposal_id=proposal_id, code="bank", reason=str(e))
            return {"ok": False, "code": "bank", "error": str(e)}
        self.proposals.mark(proposal_id, "executed")
        self.audit.append("payment_executed", actor="student-confirmed", sim_time=self._now(), student_id=sid,
                          proposal_id=proposal_id, transfer_id=txn["id"], leg=1, provider=txn["provider"],
                          src_amount=txn["src_amount"], src_currency=txn["src_currency"],
                          dst_amount=txn["dst_amount"], dst_currency=txn["dst_currency"],
                          beneficiary=txn["beneficiary_account"], eta=txn["eta"])
        mandate = None
        if len(payload["legs"]) > 1:
            mandate = {
                "mandate_id": self.bank.new_id("MDT"), "proposal_id": proposal_id, "student_id": sid,
                "invoice_id": payload["invoice_id"], "university_id": payload["university_id"],
                "payee_account": payload["payee_account"], "provider_id": payload["provider_id"],
                "src_currency": payload["src_currency"], "dst_currency": payload["dst_currency"],
                "quoted_rate": payload["quoted_rate"], "max_slippage": payload["max_slippage"],
                "legs": copy.deepcopy(payload["legs"][1:]), "reference": payload["reference"],
                "status": "active", "executed_legs": [txn["id"]], "created_sim": self._now(),
                "invoice_verdict": payload["invoice_verdict"], "total_legs": len(payload["legs"]),
                "expires": inv["due"],
            }
            self.mandates[mandate["mandate_id"]] = mandate
            self.audit.append("mandate_created", actor="student-confirmed", sim_time=self._now(), student_id=sid,
                              mandate_id=mandate["mandate_id"], proposal_id=proposal_id,
                              remaining_legs=len(mandate["legs"]), max_slippage=mandate["max_slippage"],
                              expires=mandate["expires"])
        return {"ok": True, "transfer": txn, "checks": checks,
                "mandate": self._public_mandate(mandate) if mandate else None,
                "message": (f"Sent {txn['dst_amount']:,.2f} {txn['dst_currency']} via {txn['provider_name']}. "
                            f"Expected to arrive by {txn['eta'][:10]}." +
                            (f" The remaining {len(mandate['legs'])} installment(s) will run automatically on "
                             f"schedule within the limits you approved; you can cancel any time." if mandate else ""))}

    def _start_smart_mandate(self, sid, proposal_id, payload, inv, checks) -> dict:
        """Approved smart-timing payment: nothing moves now; the agent executes it later by itself,
        only to the approved payee and invoice, only between the target rate and the floor, and only
        until the deadline."""
        t = payload["timing"]
        self.proposals.mark(proposal_id, "executed")  # the approval is used up; no second payment from it
        mandate = {
            "mandate_id": self.bank.new_id("MDT"), "kind": "smart_timing", "proposal_id": proposal_id,
            "student_id": sid, "invoice_id": payload["invoice_id"], "university_id": payload["university_id"],
            "payee_account": payload["payee_account"], "provider_id": payload["provider_id"],
            "src_currency": payload["src_currency"], "dst_currency": payload["dst_currency"],
            "quoted_rate": payload["quoted_rate"], "max_slippage": payload["max_slippage"],
            "target_rate": t["target_rate"], "floor_rate": t["floor_rate"], "deadline": t["deadline"],
            "legs": copy.deepcopy(payload["legs"]), "reference": payload["reference"], "status": "active",
            "executed_legs": [], "created_sim": self._now(), "invoice_verdict": payload["invoice_verdict"],
            "total_legs": 1, "expires": t["deadline"], "checks_log": [],
        }
        self.mandates[mandate["mandate_id"]] = mandate
        self.audit.append("mandate_created", actor="student-confirmed", sim_time=self._now(), student_id=sid,
                          mandate_id=mandate["mandate_id"], proposal_id=proposal_id, kind="smart_timing",
                          target_rate=t["target_rate"], floor_rate=t["floor_rate"], deadline=t["deadline"])
        return {"ok": True, "transfer": None, "checks": checks, "mandate": self._public_mandate(mandate),
                "message": (f"Approved. I'll watch the {payload['src_currency']}/{payload['dst_currency']} rate every day and pay "
                            f"{payload['total_dst']:,.2f} {payload['dst_currency']} as soon as it reaches {t['target_rate']:.6f}, "
                            f"or on {t['deadline']} at the market rate. Nothing has moved yet; you can cancel any time.")}

    def cancel_mandate(self, sid: str, mandate_id: str) -> dict:
        m = self.mandates.get(mandate_id)
        if not m or m["student_id"] != sid:
            return {"ok": False, "error": "unknown mandate"}
        m["status"] = "revoked"
        self.audit.append("mandate_revoked", actor="student", sim_time=self._now(), student_id=sid, mandate_id=mandate_id)
        return {"ok": True, "mandate": self._public_mandate(m)}

    def _public_mandate(self, m):
        if not m:
            return None
        out = {k: m[k] for k in ("mandate_id", "proposal_id", "invoice_id", "provider_id", "status",
                                 "quoted_rate", "max_slippage", "legs", "executed_legs", "total_legs", "expires")}
        out["kind"] = m.get("kind", "installments")
        if out["kind"] == "smart_timing":
            out.update({k: m[k] for k in ("target_rate", "floor_rate", "deadline")})
            out["dst_currency"], out["src_currency"] = m["dst_currency"], m["src_currency"]
            out["last_check"] = (m.get("checks_log") or [None])[-1]
        out["payee_account"] = mask_account(m["payee_account"])
        return out

    # ================================================================ payment certificates
    def payment_records(self, sid: str) -> list[dict]:
        """Settled tuition transfers with an on-time flag (credited on or before the invoice due date)."""
        out = []
        for t in self.bank.transfers.values():
            if t["student_id"] != sid or t["status"] not in ("credited", "credited_short"):
                continue
            inv = self.bank.invoices.get(t["invoice_id"], {})
            due = (inv.get("due") or "")[:10]
            paid = t["credited"][:10]
            days_early = (datetime.fromisoformat(due) - datetime.fromisoformat(paid)).days if due else None
            issued = next((c for c in self.certificates.get(sid, []) if c.get("transfer_id") == t["id"]), None)
            out.append({"transfer_id": t["id"], "invoice_id": t["invoice_id"], "amount": t.get("received_amount", t["dst_amount"]),
                        "currency": t["dst_currency"], "paid_on": paid, "due": due,
                        "on_time": days_early is not None and days_early >= 0, "days_early": days_early,
                        "institution": UNIVERSITIES[t["university_id"]]["name"], "channel": t["provider_name"],
                        "certificate": issued})
        return sorted(out, key=lambda r: r["paid_on"])

    # ------------------------------------------------------------ failed-transfer recovery
    def inject_issue(self, sid: str, transfer_id: str, kind: str) -> dict:
        t = self.bank.transfers.get(transfer_id)
        if not t or t["student_id"] != sid:
            return {"ok": False, "error": "No such transfer in your account."}
        try:
            rec = self.bank.inject_issue(transfer_id, kind)
        except (ValueError, LookupError) as e:
            return {"ok": False, "error": str(e)}
        if kind == "returned":
            self.audit.append("transfer_returned", actor="sandbox", sim_time=self._now(), student_id=sid,
                              transfer_id=transfer_id, invoice_id=t["invoice_id"], reason=rec["return_reason"],
                              refunded=rec["refunded_amount"], currency=rec["src_currency"])
            self.session(sid)["notifications"].append(
                f"{transfer_id} was returned by the receiving bank. {rec['refunded_amount']:,.0f} "
                f"{rec['src_currency']} is back in your wallet. Nothing was resent.")
        else:
            self.audit.append("intermediary_deduction_scheduled", actor="sandbox", sim_time=self._now(),
                              student_id=sid, transfer_id=transfer_id, deduction=rec["intermediary_deduction"],
                              currency=rec["dst_currency"])
        return {"ok": True, "transfer": rec}

    def recover(self, sid: str, transfer_id: str) -> dict:
        """Diagnose a returned or short-paid transfer and give the one safe next step.

        Never resends automatically: a resend while the original might still arrive can pay twice.
        The old approval is single-use, so any new payment needs a fresh proposal and fresh codes.
        """
        t = self.bank.transfers.get(transfer_id)
        if not t or t["student_id"] != sid:
            return {"ok": False, "error": "No such transfer in your account."}
        inv = self.bank.invoices.get(t["invoice_id"]) or {}
        outstanding = self._outstanding(inv) if inv else 0.0
        uni = UNIVERSITIES[t["university_id"]]
        reg_ok = t["beneficiary_account"] == uni["beneficiary"]["account"]
        steps, action = [], None
        if t["status"] == "returned":
            diagnosis = (f"The receiving bank sent the money back ({t['return_reason']}). "
                         f"{t['refunded_amount']:,.2f} {t['src_currency']} is already back in your wallet, "
                         f"so the invoice is still open for {outstanding:,.2f} {t['dst_currency']}.")
            steps = ["Do not resend the same transfer: the cause has not been fixed yet.",
                     ("The account we used matches the university's verified record, so the mismatch is on the bank's side. "
                      if reg_ok else "The account we used does NOT match the verified record — report this. ")
                     + f"Call {uni['name']} finance on the number published on its official website and confirm the "
                       "account holder name.",
                     "Then ask the assistant to pay again. It will build a new signed proposal; the old approval and codes "
                     "can't be reused."]
            action = {"label": f"Pay {inv.get('id', 'the invoice')} again (after confirming)",
                      "message": f"Pay {inv.get('id', '')}"} if outstanding > 0.01 else None
            kind = "returned"
        elif t["status"] == "credited_short":
            short = round(t["dst_amount"] - t.get("received_amount", t["dst_amount"]), 2)
            diagnosis = (f"The university received {t['received_amount']:,.2f} {t['dst_currency']}, "
                         f"{short:,.2f} less than was sent. An intermediary bank deducted a fee on the way.")
            steps = [f"Your invoice now shows {outstanding:,.2f} {t['dst_currency']} still to pay. "
                     "Pay only this shortfall, never the full amount again.",
                     "SudoRoute's overpayment check caps any new payment at the outstanding balance, so a double payment "
                     "is blocked even if you ask for one.",
                     "To avoid this next time, prefer a route that guarantees the full amount arrives (fees paid by sender)."]
            action = {"label": f"Pay the shortfall ({t['dst_currency']} {outstanding:,.2f})",
                      "message": f"Pay {inv.get('id', '')}"} if outstanding > 0.01 else None
            kind = "short"
        elif t["status"] == "in_transit":
            diagnosis = f"This payment is still on its way. It's expected by {t['eta'][:10]}."
            steps = ["Don't send it again: if both arrive, the university is paid twice. Wait for the expected date first."]
            kind = "in_transit"
        else:
            diagnosis = f"This payment arrived in full ({t['dst_amount']:,.2f} {t['dst_currency']}). Nothing to fix."
            kind = "ok"
        self.audit.append("transfer_diagnosed", actor="agent", sim_time=self._now(), student_id=sid,
                          transfer_id=transfer_id, kind=kind, outstanding=outstanding)
        return {"ok": True, "kind": kind, "transfer_id": transfer_id, "invoice_id": t["invoice_id"],
                "diagnosis": diagnosis, "steps": steps, "outstanding": outstanding,
                "currency": t["dst_currency"], "action": action}

    def issue_certificate(self, sid: str, kind: str, transfer_id: str | None = None, *, at_least: float | None = None,
                          currency: str | None = None, purpose: str | None = None) -> dict:
        if not self.issuer:
            return {"ok": False, "error": "Certificates are not available on this server."}
        s = self._student(sid)
        recs = self.payment_records(sid)
        uni = UNIVERSITIES[s["university_id"]]
        head = self.audit.verify()
        base = {"cert_id": self.bank.new_id("CRT"), "holder": s["name"],
                "holder_ref": "•••" + s["student_ref"][-4:], "issued_at": self._now(),
                "audit_anchor": {"seq": head.get("entries"), "hash": head.get("head")},
                "sandbox": True}
        if kind == "payment":
            r = next((x for x in recs if x["transfer_id"] == transfer_id), None)
            if not r:
                return {"ok": False, "error": "Only settled tuition payments can be certified."}
            claims = {**base, "type": "tuition_payment",
                      "payment": {k: r[k] for k in ("transfer_id", "amount", "currency", "paid_on", "due", "on_time",
                                                    "days_early", "institution", "channel")},
                      "institution_country": uni["country"]}
        elif kind == "history":
            if not recs:
                return {"ok": False, "error": "You have no settled payments yet. Pay a tuition invoice first."}
            totals: dict[str, float] = {}
            for r in recs:
                totals[r["currency"]] = round(totals.get(r["currency"], 0) + r["amount"], 2)
            claims = {**base, "type": "payment_history",
                      "history": {"payments": len(recs), "on_time": sum(r["on_time"] for r in recs),
                                  "first": recs[0]["paid_on"], "last": recs[-1]["paid_on"], "totals": totals,
                                  "institutions": sorted({r["institution"] for r in recs})}}
        elif kind == "funds":
            # Proof of funds without a bank statement: states only that the holder had AT LEAST the
            # requested amount on a date. The actual balance is never written into the certificate.
            ccy = (currency or s["study_currency"]).upper()
            if ccy not in self.bank.market.currencies():
                return {"ok": False, "error": "Choose a supported currency."}
            try:
                need = round(float(at_least), 2)
            except (TypeError, ValueError):
                return {"ok": False, "error": "Enter the amount you need to prove."}
            if not math.isfinite(need) or need <= 0:
                return {"ok": False, "error": "Enter an amount above zero."}
            held = sum(a * self.bank.market.mid(c, ccy) for c, a in s["balances"].items() if a > 0)
            if held + 1e-6 < need:
                self.audit.append("funds_proof_refused", actor="agent", sim_time=self._now(), student_id=sid,
                                  currency=ccy, at_least=need)
                return {"ok": False, "error": f"Your wallets don't hold {ccy} {need:,.2f} today, so SudoRoute can't sign this. "
                                              "It never signs a claim it cannot back."}
            as_of = self.bank.now.date()
            clean = re.sub(r"[^\w .,'()/-]", "", str(purpose or ""))[:60].strip() or "General proof of funds"
            claims = {**base, "type": "proof_of_funds",
                      "funds": {"at_least": need, "currency": ccy, "as_of": as_of.isoformat(),
                                "valid_until": (as_of + timedelta(days=30)).isoformat(), "purpose": clean,
                                "method": "Wallet balances converted at the mid-market rate of the day; balance not disclosed."}}
        else:
            return {"ok": False, "error": "Unknown certificate type."}
        code = self.issuer.issue(claims)
        entry = {"cert_id": claims["cert_id"], "type": claims["type"], "transfer_id": transfer_id,
                 "issued_at": claims["issued_at"], "code": code}
        anchors = getattr(self, "anchors", None)
        if anchors is not None:  # timestamp a hash of the certificate + audit-log state on Bitcoin (OpenTimestamps)
            a = anchors.record(code, head.get("head"), head.get("entries"), self.issuer.kid)
            entry["anchor"] = a["cert_sha256"]
            anchors.submit_async(a["cert_sha256"])
        self.certificates.setdefault(sid, []).append(entry)
        self.audit.append("certificate_issued", actor="agent", sim_time=self._now(), student_id=sid,
                          cert_id=claims["cert_id"], cert_type=claims["type"], transfer_id=transfer_id)
        return {"ok": True, **entry, "claims": claims}

    # ================================================================ kill switch
    def frozen(self, sid: str) -> dict | None:
        return self._student(sid).get("frozen")

    def freeze(self, sid: str, by_role: str, user: dict) -> dict:
        """Emergency stop: the agent can prepare or move nothing until released."""
        s = self._student(sid)
        if s.get("frozen"):
            return {"ok": True, "already": True, "frozen": s["frozen"]}
        s["frozen"] = {"by": by_role, "user_id": user["id"], "name": short_name(user["name"]), "at": self._now()}
        cancelled = []
        for pid, rec in self.proposals.proposals.items():
            if rec["payload"]["student_id"] == sid and rec["status"] in ("awaiting_guardian", "awaiting_confirmation"):
                rec["status"] = "cancelled"
                cancelled.append(pid)
        paused = []
        for m in self.mandates.values():
            if m["student_id"] == sid and m["status"] == "active":
                m["status"] = "frozen"
                paused.append(m["mandate_id"])
        self.session(sid)["notifications"].append(
            f"Kill switch ON ({by_role}). {len(cancelled)} pending payment(s) cancelled, "
            f"{len(paused)} installment plan(s) stopped. Nothing can move until it is released.")
        self.audit.append("kill_switch_engaged", actor=by_role, sim_time=self._now(), student_id=sid,
                          user_id=user["id"], cancelled=cancelled, mandates_stopped=paused)
        return {"ok": True, "frozen": s["frozen"], "cancelled": cancelled, "mandates_stopped": paused}

    def unfreeze(self, sid: str, by_role: str, user: dict) -> dict:
        s = self._student(sid)
        f = s.get("frozen")
        if not f:
            return {"ok": True, "already": True}
        if f["by"] == "guardian" and by_role != "guardian":
            return {"ok": False, "code": "guardian_hold",
                    "error": f"{f['name']} (guardian) switched this on. Only a guardian can release it."}
        s["frozen"] = None
        self.session(sid)["notifications"].append(
            "Kill switch released. Stopped installment plans stay stopped — ask for a fresh quote to continue.")
        self.audit.append("kill_switch_released", actor=by_role, sim_time=self._now(), student_id=sid,
                          user_id=user["id"])
        return {"ok": True}

    # ================================================================ guardians
    def guardian_decide(self, guardian: dict, proposal_id: str, otp: str, approve: bool) -> dict:
        gid = guardian["id"]
        try:
            rec = self.proposals.get(proposal_id)
            payload = rec["payload"]
            if gid not in payload.get("guardian_ids", []):
                raise ProposalError("You are not a guardian on this payment.", "forbidden")
            if approve and self._student(payload["student_id"]).get("frozen"):
                raise ProposalError("The kill switch is on for this student.", "frozen")
            if rec["status"] != "awaiting_guardian":
                raise ProposalError(f"This payment is no longer waiting for approval ({rec['status']}).", "not_pending")
            if time.time() > payload["expires_at"]:
                rec["status"] = "expired"
                raise ProposalError("This request expired. The student can ask for a fresh quote.", "expired")
            self.proposals.verify_secondary_otp(proposal_id, "guardian:", otp)
        except ProposalError as e:
            self.audit.append("guardian_decision_rejected", actor="security", sim_time=self._now(),
                              student_id=rec["payload"]["student_id"] if "rec" in locals() else None,
                              user_id=gid, proposal_id=proposal_id, code=e.code)
            return {"ok": False, "code": e.code, "error": str(e)}
        sid = payload["student_id"]
        if approve:
            rec["guardian_approval"] = {"by": gid, "name": guardian["name"], "at": self._now()}
            rec["status"] = "awaiting_confirmation"
            note = (f"{guardian['name']} approved your payment of {payload['total_dst']:,.2f} "
                    f"{payload['dst_currency']}. Confirm it with your one-time code.")
        else:
            rec["status"] = "declined"
            note = f"{guardian['name']} declined your payment of {payload['total_dst']:,.2f} {payload['dst_currency']}."
        self.session(sid)["notifications"].append(note)
        self.audit.append("guardian_approved" if approve else "guardian_declined", actor="guardian",
                          sim_time=self._now(), student_id=sid, user_id=gid, proposal_id=proposal_id)
        return {"ok": True, "status": rec["status"], "message": note}

    def _public_proposal(self, pid: str, rec: dict, with_token: bool) -> dict:
        card = dict(rec.get("card") or {"proposal": rec["payload"]})
        card.update(status=rec["status"], guardian_approval=rec.get("guardian_approval"),
                    expired=time.time() > rec["payload"]["expires_at"])
        if with_token:
            card["token"] = rec["token"]
        return card

    def pending_for_student(self, sid: str) -> list[dict]:
        return [self._public_proposal(pid, r, True) for pid, r in self.proposals.proposals.items()
                if r["payload"]["student_id"] == sid and r["status"] in ("awaiting_guardian", "awaiting_confirmation")
                and time.time() <= r["payload"]["expires_at"]]

    def pending_for_guardian(self, gid: str) -> list[dict]:
        return [self._public_proposal(pid, r, False) for pid, r in self.proposals.proposals.items()
                if gid in r["payload"].get("guardian_ids", []) and r["status"] == "awaiting_guardian"
                and time.time() <= r["payload"]["expires_at"]]

    def guardian_fund(self, guardian: dict, sid: str, amount: float) -> dict:
        if sid not in guardian.get("students", []):
            return {"ok": False, "error": "You are not linked to this student.", "code": "forbidden"}
        s = self._student(sid)
        ccy = s["home_currency"]
        if not (amount > 0):
            return {"ok": False, "error": "Enter an amount above zero.", "code": "invalid"}
        usd = self.bank.market.to_usd(amount, ccy)
        sent = [f for f in self.guardian_funding.get(guardian["id"], [])
                if f["date"] == self.bank.now.date().isoformat()]
        if usd + sum(f["usd"] for f in sent) > 10000:
            return {"ok": False, "code": "limit",
                    "error": "Family transfers are limited to about USD 10,000 per day in the sandbox."}
        ev = self.bank.top_up(sid, round(amount, 2), ccy, f"Family support from {guardian['name']}")
        self.guardian_funding.setdefault(guardian["id"], []).append({**ev, "usd": usd})
        self.session(sid)["notifications"].append(f"{guardian['name']} sent you {amount:,.0f} {ccy}.")
        self.audit.append("guardian_funding", actor="guardian", sim_time=self._now(), student_id=sid,
                          user_id=guardian["id"], amount=round(amount, 2), currency=ccy)
        return {"ok": True, "balance": s["balances"][ccy], "currency": ccy}

    def guardian_view(self, sid: str) -> dict:
        snap = self.bank.snapshot(sid)
        for inv in snap["invoices"]:
            v = verify_invoice(inv, self.bank.student(sid))
            inv["verdict"], inv["score"] = v["verdict"], v["score"]
            inv["bank_account"] = mask_account(inv["bank_account"])
            inv.pop("text", None)
        keep = ("id", "name", "program", "university", "home_currency", "study_currency", "home_country",
                "study_country", "balances", "invoices", "transfers", "sim_date", "student_ref", "guardian_approval",
                "frozen")
        out = {k: snap.get(k) for k in keep}
        out["mandates"] = [self._public_mandate(m) for m in self.mandates.values() if m["student_id"] == sid]
        out["level"] = self.session(sid)["level"]
        out["outstanding"] = round(sum(max(0.0, self._outstanding(i)) for i in self.bank.student_invoices(sid)
                                       if verify_invoice(i, self.bank.student(sid))["verdict"] != "BLOCK"), 2)
        return out

    def audit_for(self, sid: str | None = None, user_id: str | None = None, n: int = 40) -> list[dict]:
        rows = [e for e in self.audit.entries
                if (sid and e["data"].get("student_id") == sid) or (user_id and e["data"].get("user_id") == user_id)]
        return rows[-n:]

    def insights(self, sid: str) -> dict:
        """Dashboard analytics without going through chat (tools still tier-checked and audited)."""
        sess = self.session(sid)
        ctx = Context(sid, sess["level"])
        s = self._student(sid)
        out = {}
        try:
            invs = [i for i in self.bank.student_invoices(sid) if verify_invoice(i, s)["verdict"] != "BLOCK"]
            out["budget"] = self._call(ctx, "budget_overview", Tier.ANALYZE, budget_engine.budget_overview,
                                       self.bank.market, s, self.bank.transactions[sid], invs, self.bank.now.date())
            out["credit"] = self._call(ctx, "credit_plan", Tier.ANALYZE, credit_engine.credit_plan, s)
            open_inv = [i for i in invs if self._outstanding(i) > 0.01]
            if open_inv:
                inv = sorted(open_inv, key=lambda i: i["due"])[0]
                plan = self._analyse(ctx, s, inv)
                out["fx"] = {"invoice_id": inv["id"], **plan["fx"]}
                out["routes"] = {"invoice_id": inv["id"], **plan["routes"]}
        except PermissionDenied as e:
            out["denied"] = str(e)
        out["trace"] = ctx.trace
        return out

    # ================================================================ dashboard metrics
    def dashboard(self, sid: str) -> dict:
        """Headline numbers for the overview, computed by the same tested engines (cached per sandbox day)."""
        from ..engines.obligations import semester_plan
        s = self._student(sid)
        invs = [i for i in self.bank.student_invoices(sid)
                if verify_invoice(i, s)["verdict"] != "BLOCK" and self._outstanding(i) > 0.01]
        key = (sid, self.bank.now.isoformat(), tuple((i["id"], self._outstanding(i)) for i in invs),
               tuple(sorted(s["balances"].items())))
        cache = self.__dict__.setdefault("_dash_cache", {})
        if key in cache:
            return cache[key]
        tuition = [{"id": i["id"], "amount": self._outstanding(i), "currency": i["currency"], "due": i["due"]} for i in invs]
        plan = semester_plan(s, tuition, self.bank.market, self.bank.now, self.bank.days_elapsed)
        out = {"plan": plan, "kpis": {"semester_funded_pct": plan["funded_pct"]}, "whatif": None}
        if invs and UNIVERSITIES[s["university_id"]].get("verified", True):
            inv = sorted(invs, key=lambda i: i["due"])[0]
            ctx = Context(sid, self.session(sid)["level"])  # read-only mode stays read-only here too
            try:
                a = self._analyse(ctx, s, inv)
                best = a["routes"]["best"]
                out["kpis"].update({
                    "next_invoice": inv["id"], "days_to_due": max(0, math.floor(self._days_to_due(inv))),
                    "due_amount": a["remaining"], "currency": inv["currency"], "due_date": inv["due"][:10],
                    "on_time_pct": round((1 - best["p_late"]) * 100, 1), "best_route": best["provider"],
                    "shortfall_if_wait_pct": round(a["fx"]["strategies"]["pay_at_due"]["prob_over_budget"] * 100, 1)})
                prov = PROVIDERS[best["provider_id"]]
                pay_by = datetime.fromisoformat(inv["due"]) - timedelta(days=config.ARRIVAL_BUFFER_DAYS + prov["days"][1])
                out["kpis"]["pay_by"] = pay_by.date().isoformat()
                out["kpis"]["pay_by_days"] = (pay_by.date() - self.bank.now.date()).days
                out["whatif"] = {"home": s["home_currency"], "study": inv["currency"], "outstanding": a["remaining"],
                                 "mid": self.bank.market.mid(s["home_currency"], inv["currency"]),
                                 "markup": prov["fx_markup"], "fee_home": round(best["fee_src"], 2),
                                 "budget_home": s["tuition_budget_home"],
                                 "balance_home": s["balances"].get(s["home_currency"], 0.0)}
            except (LookupError, PermissionDenied):
                pass
        if len(cache) > 500:
            cache.clear()
        cache[key] = out
        return out

    # ================================================================ scheduler
    def advance(self, days: int = 1) -> dict:
        events = []
        for _ in range(int(days)):
            events += self.bank.advance(1)
            events += self._run_mandates()
        for e in events:
            self.audit.append(f"sandbox_{e['type']}", actor="sandbox", sim_time=self._now(), **e)
        return {"sim_date": self.bank.now.date().isoformat(), "events": events}

    def _run_mandates(self) -> list[dict]:
        events = []
        today = self.bank.now.date().isoformat()
        for m in self.mandates.values():
            if m["status"] != "active" or self._student(m["student_id"]).get("frozen"):
                continue
            if today > m["expires"][:10]:
                m["status"] = "expired"
                continue
            if m.get("kind") == "smart_timing":
                events += self._run_smart(m, today)
                continue
            for leg in m["legs"]:
                if leg.get("done") or leg["execute_on"] > today:
                    continue
                s = self._student(m["student_id"])
                provider = PROVIDERS[m["provider_id"]]
                rate = self.bank.market.mid(m["src_currency"], m["dst_currency"]) * (1 - provider["fx_markup"])
                slippage = m["quoted_rate"] / rate - 1.0
                if slippage > m["max_slippage"]:
                    m["status"] = "paused"
                    note = (f"Installment {leg['leg']} paused: {m['src_currency']} weakened {slippage * 100:.1f}% "
                            f"since you approved (limit {m['max_slippage'] * 100:.0f}%). Please re-confirm.")
                    self.session(s["id"])["notifications"].append(note)
                    events.append({"type": "mandate_paused", "mandate_id": m["mandate_id"], "leg": leg["leg"],
                                   "slippage": round(slippage, 4)})
                    break
                fee_src = provider["fee_usd"] * self.bank.market.units_per_usd(m["src_currency"])
                src_amt = round(leg["dst_amount"] / rate + fee_src, 2)
                inv = self.bank.invoices[m["invoice_id"]]
                checks = policy.evaluate(self.bank, student=s, university_id=m["university_id"],
                                         provider_id=m["provider_id"], invoice=inv,
                                         invoice_verdict=m["invoice_verdict"], leg_dst_amount=leg["dst_amount"],
                                         leg_src_amount=src_amt, payee_account=m["payee_account"],
                                         disclosed_installments=m["total_legs"])
                if not checks["allowed"]:
                    m["status"] = "paused"
                    note = f"Installment {leg['leg']} paused — failed checks: {', '.join(checks['failed'])}."
                    self.session(s["id"])["notifications"].append(note)
                    events.append({"type": "mandate_paused", "mandate_id": m["mandate_id"], "leg": leg["leg"],
                                   "failed": checks["failed"]})
                    break
                txn = self.bank.transfer(student_id=s["id"], src_currency=m["src_currency"], src_amount=src_amt,
                                         dst_currency=m["dst_currency"], dst_amount=leg["dst_amount"],
                                         provider=provider, university_id=m["university_id"],
                                         reference=m["reference"], invoice_id=m["invoice_id"],
                                         proposal_id=m["proposal_id"], leg=leg["leg"])
                leg["done"] = True
                leg["src_amount_actual"] = src_amt
                leg["transfer_id"] = txn["id"]
                m["executed_legs"].append(txn["id"])
                self.session(s["id"])["notifications"].append(
                    f"Installment {leg['leg']}/{m['total_legs']} sent: {leg['dst_amount']:,.2f} {m['dst_currency']} "
                    f"for {src_amt:,.0f} {m['src_currency']} (rate moved {-slippage * 100:+.2f}%).")
                events.append({"type": "mandate_leg_executed", "mandate_id": m["mandate_id"], "leg": leg["leg"],
                               "transfer_id": txn["id"], "src_amount": src_amt, "dst_amount": leg["dst_amount"],
                               "slippage": round(slippage, 4)})
            if all(l.get("done") for l in m["legs"]) and m["status"] == "active":
                m["status"] = "completed"
        return events

    def _run_smart(self, m, today: str) -> list[dict]:
        """One daily decision of a smart-timing mandate. The agent acts on its own, inside the approval."""
        s = self._student(m["student_id"])
        provider = PROVIDERS[m["provider_id"]]
        rate = self.bank.market.mid(m["src_currency"], m["dst_currency"]) * (1 - provider["fx_markup"])
        leg = m["legs"][0]
        reason = None
        if rate >= m["target_rate"]:
            reason = "target_reached"
        elif today >= m["deadline"]:
            if rate < m["floor_rate"]:
                m["status"] = "paused"
                note = (f"Smart payment paused: on the last safe day the rate ({rate:.6f}) is below the limit you "
                        f"approved ({m['floor_rate']:.6f}). Please decide now — pay at today's rate or ask your guardian.")
                self.session(s["id"])["notifications"].append(note)
                m["checks_log"].append({"date": today, "rate": round(rate, 8), "decision": "paused_below_floor"})
                return [{"type": "mandate_paused", "mandate_id": m["mandate_id"], "leg": 1, "rate": round(rate, 8),
                         "reason": "below_floor_at_deadline"}]
            reason = "deadline"
        if reason is None:
            m["checks_log"].append({"date": today, "rate": round(rate, 8), "decision": "wait"})
            m["checks_log"] = m["checks_log"][-30:]
            return [{"type": "smart_check", "mandate_id": m["mandate_id"], "rate": round(rate, 8),
                     "target": m["target_rate"], "decision": "wait"}]
        fee_src = provider["fee_usd"] * self.bank.market.units_per_usd(m["src_currency"])
        src_amt = round(leg["dst_amount"] / rate + fee_src, 2)
        inv = self.bank.invoices[m["invoice_id"]]
        checks = policy.evaluate(self.bank, student=s, university_id=m["university_id"], provider_id=m["provider_id"],
                                 invoice=inv, invoice_verdict=m["invoice_verdict"], leg_dst_amount=leg["dst_amount"],
                                 leg_src_amount=src_amt, payee_account=m["payee_account"], disclosed_installments=1)
        if checks["allowed"]:
            a = self._audit_ai(None, (f"AUTOMATIC smart-timing payment about to run by itself ({reason}).\n"
                                      f"Approved quote rate {m['quoted_rate']:.6f}, target {m['target_rate']:.6f}, floor "
                                      f"{m['floor_rate']:.6f}, today's rate {rate:.6f}.\nInvoice {inv['id']}: "
                                      f"{inv['amount']:,.2f} {inv['currency']}, paid {inv['paid']:,.2f}, due {inv['due'][:10]}.\n"
                                      f"Payment {leg['dst_amount']:,.2f} {m['dst_currency']} for about {src_amt:,.0f} "
                                      f"{m['src_currency']} to the approved registry account. Compliance checks passed."),
                               "smart_mandate")
            if a and a["hold"]:
                m["status"] = "paused"
                self.session(s["id"])["notifications"].append(
                    f"Smart payment paused by the independent AI auditor: {a['reason']} Nothing was sent; please decide.")
                m["checks_log"].append({"date": today, "rate": round(rate, 8), "decision": "ai_auditor_hold"})
                return [{"type": "mandate_paused", "mandate_id": m["mandate_id"], "leg": 1, "reason": "ai_auditor_hold"}]
        if not checks["allowed"]:
            m["status"] = "paused"
            self.session(s["id"])["notifications"].append(
                f"Smart payment paused — failed checks: {', '.join(checks['failed'])}.")
            m["checks_log"].append({"date": today, "rate": round(rate, 8), "decision": "paused_policy"})
            return [{"type": "mandate_paused", "mandate_id": m["mandate_id"], "leg": 1, "failed": checks["failed"]}]
        txn = self.bank.transfer(student_id=s["id"], src_currency=m["src_currency"], src_amount=src_amt,
                                 dst_currency=m["dst_currency"], dst_amount=leg["dst_amount"], provider=provider,
                                 university_id=m["university_id"], reference=m["reference"], invoice_id=m["invoice_id"],
                                 proposal_id=m["proposal_id"], leg=1)
        leg.update(done=True, src_amount_actual=src_amt, transfer_id=txn["id"], executed_on=today)
        m["executed_legs"].append(txn["id"])
        m["status"] = "completed"
        m["checks_log"].append({"date": today, "rate": round(rate, 8), "decision": reason})
        saved = round(leg["src_amount_quote"] - src_amt, 2)
        why = ("the target rate was reached" if reason == "target_reached"
               else "it was the last safe day to pay on time")
        self.session(s["id"])["notifications"].append(
            f"Smart payment sent because {why}: {leg['dst_amount']:,.2f} {m['dst_currency']} for {src_amt:,.0f} "
            f"{m['src_currency']} ({'saved' if saved >= 0 else 'cost'} {abs(saved):,.0f} {m['src_currency']} vs. the day you approved).")
        return [{"type": "mandate_leg_executed", "mandate_id": m["mandate_id"], "leg": 1, "transfer_id": txn["id"],
                 "src_amount": src_amt, "dst_amount": leg["dst_amount"], "reason": reason, "rate": round(rate, 8),
                 "saved_src": saved}]

    # ================================================================ state for UI
    def state(self, sid: str) -> dict:
        sess = self.session(sid)
        snap = self.bank.snapshot(sid)
        for inv in snap["invoices"]:
            v = verify_invoice(inv, self.bank.student(sid))
            inv["verdict"], inv["score"] = v["verdict"], v["score"]
            inv["bank_account"] = mask_account(inv["bank_account"])
        snap["level"] = sess["level"]
        snap["levels"] = {k: {"label": v["label"], "description": v["description"]} for k, v in permissions.LEVELS.items()}
        snap["sms_inbox"] = sess["sms_inbox"][-5:]
        snap["pending"] = self.pending_for_student(sid)
        snap["guardians"] = [{"name": g["name"], "relationship": g.get("relationship", ""), "id": g["id"]}
                             for g in self.bank.student(sid).get("guardians", [])]
        snap["guardian_approval"] = self.bank.student(sid).get("guardian_approval", True)
        snap["frozen"] = self.bank.student(sid).get("frozen")
        snap["notifications"] = sess["notifications"][-8:]
        snap["mandates"] = [self._public_mandate(m) for m in self.mandates.values() if m["student_id"] == sid]
        snap["rates"] = {f"{snap['home_currency']}/{snap['study_currency']}":
                         self.bank.market.mid(snap["home_currency"], snap["study_currency"])}
        snap["audit"] = self.audit.verify()
        snap["ai"] = self.llm.status()
        snap["university_ledger"] = self.bank.university_ledger.setdefault(snap["university_id"], {}).get(snap["student_ref"], 0.0)
        return snap
