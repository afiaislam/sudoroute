"""AI assistance beyond the chat: money brief, verification e-mails, guardian Q&A, public Q&A.

Every function follows the same pattern:
  1. Deterministic code computes the facts (amounts, dates, verdicts) from the sandbox state.
  2. Gemini, when connected, turns those facts into friendly text in the user's language.
  3. The model's text is accepted only if it keeps every number and ID and adds none
     (llm.rewrite / llm.grounded). Otherwise the template text is shown.
The model never sees raw invoices or e-mails, never sees full account numbers, and cannot act.
"""

import re
import time

from . import llm
from ..engines.invoice_check import verify_invoice
from ..sandbox.reference_data import UNIVERSITIES
from ..security.guardrails import mask_account


def _src(text_ai: str | None, draft: str) -> dict:
    if text_ai:
        return {"text": text_ai, "source": llm.provider(), "draft": draft}
    return {"text": draft, "source": "template", "draft": None}


def _day(iso: str) -> str:
    from datetime import date
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d:%b %Y}"


def _fmt(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}"


# ------------------------------------------------------------------ student money brief
def brief(agent, sid: str, lang: str | None = None) -> dict:
    s = agent.bank.student(sid)
    d = agent.dashboard(sid)
    k, plan = d["kpis"], d["plan"]
    lines = []
    if k.get("next_invoice"):
        lines.append(f"Next tuition: {k['next_invoice']}, {k['currency']} {_fmt(k['due_amount'])}, due on {_day(k['due_date'])} "
                     f"({k['days_to_due']} days from today).")
        lines.append(f"Paid today through {k['best_route']}, the chance it arrives on time is {k['on_time_pct']}%.")
        if k.get("pay_by_days") is not None:
            lines.append(f"Latest safe day to pay: {_day(k['pay_by'])}." if k["pay_by_days"] > 0 else
                         "It is already tight: pay today to arrive before the due date.")
        lines.append(f"If you wait until the due date, the risk that it costs more than your budget is "
                     f"{k['shortfall_if_wait_pct']}%.")
    else:
        lines.append("You have no tuition left to pay right now.")
    short = [b for b in plan["bills"] if b["status"] != "covered"]
    lines.append(f"This semester is {plan['funded_pct']}% funded across {len(plan['bills'])} bills"
                 + (f"; {len(short)} bill(s) are not fully covered yet." if short else "; every bill is covered."))
    if s.get("frozen"):
        lines.append("The kill switch is on, so no payment can be made until it is released.")
    if k.get("next_invoice"):
        action = ("Suggested next step: ask the assistant to pay now." if k["shortfall_if_wait_pct"] >= 10 or k.get("pay_by_days", 99) <= 3
                  else "Suggested next step: no rush, but do not pass the latest safe day.")
        lines.append(action)
    draft = " ".join(lines)
    ai = None
    if agent._llm():
        t0 = time.perf_counter()
        ai = llm.rewrite(draft, purpose="a short personal money brief (2–4 sentences) for the student", lang=lang, words=90)
        agent.audit.append("ai_brief", actor="agent", sim_time=agent._now(), student_id=sid, ok=ai is not None,
                           ms=round((time.perf_counter() - t0) * 1000))
    return _src(ai, draft)


# ------------------------------------------------------------------ verification e-mail drafts
def draft_email(agent, sid: str, *, invoice_id: str | None = None, transfer_id: str | None = None,
                lang: str | None = None) -> dict:
    """A message the student can send to the university's finance office. SudoRoute never sends it."""
    s = agent.bank.student(sid)
    uni = UNIVERSITIES[s["university_id"]]
    domain = (uni.get("official_domains") or ["the university's official website"])[0]
    to = f"the finance office contact published on {domain}"
    if transfer_id:
        t = agent.bank.transfers.get(transfer_id)
        if not t or t["student_id"] != sid:
            return {"ok": False, "error": "No such transfer in your account."}
        subject = f"Tuition payment {t['reference']}: please confirm your bank details"
        status = ("was returned by the receiving bank" if t["status"] == "returned" else
                  "arrived short" if t["status"] == "credited_short" else "is on its way")
        facts = (f"Dear {uni['name']} finance office,\n"
                 f"My tuition payment {t['id']} for student reference {t['reference']} "
                 f"({t['dst_currency']} {_fmt(t['dst_amount'])}, sent through {t['provider_name']}) {status}.\n"
                 f"Before I pay again, please confirm the exact account holder name and the bank account ending "
                 f"{t['beneficiary_account'][-4:]} for tuition payments, and tell me the amount still due on my account.\n"
                 f"Kind regards,\n{s['name']}, {s['program']}")
    else:
        inv = agent.bank.invoices.get(invoice_id or "")
        if not inv or inv["student_id"] != sid:
            return {"ok": False, "error": "No such invoice in your account."}
        v = verify_invoice(inv, s)
        signals = "; ".join(r["message"].rstrip(".") for r in v["reasons"][:2]) or "no specific warning signs"
        subject = f"Please confirm invoice {inv['id']} for student reference {s['student_ref']}"
        facts = (f"Dear {uni['name']} finance office,\n"
                 f"I received a tuition invoice {inv['id']} for {inv['currency']} {_fmt(inv['amount'])}, due on "
                 f"{_day(inv['due'])}, from {inv['sender_email']}. It asks for payment to an account ending "
                 f"{inv['bank_account'][-4:]}.\n"
                 f"My payment assistant flagged it ({signals}). Could you confirm whether you sent it, and the correct "
                 f"account for tuition payments? I will not pay until I hear from you.\n"
                 f"Kind regards,\n{s['name']}, student reference {s['student_ref']}")
    ai = None
    if agent._llm():
        ai = llm.rewrite(facts, purpose="a short, polite e-mail from the student to the university finance office "
                                        "(keep the greeting and sign-off lines)", lang=lang, words=140)
    agent.audit.append("ai_email_drafted", actor="agent", sim_time=agent._now(), student_id=sid,
                       invoice_id=invoice_id, transfer_id=transfer_id, ai=ai is not None)
    out = _src(ai, facts)
    return {"ok": True, "to": to, "subject": subject, "body": out["text"], "source": out["source"],
            "note": "SudoRoute never sends e-mails for you. Use the contact on the university's official website, "
                    "never the address or phone number printed on a suspicious invoice."}


# ------------------------------------------------------------------ guardian questions
def guardian_facts(agent, guardian: dict) -> str:
    rows = []
    for sid in guardian.get("students", []):
        try:
            v = agent.guardian_view(sid)
        except LookupError:
            continue
        uname = v["university"]["name"] if isinstance(v["university"], dict) else v["university"]
        rows.append(f"Student {v['name']} ({v['program']}, {uname}), home currency {v['home_currency']}, "
                    f"study currency {v['study_currency']}. Sandbox date {v['sim_date']}.")
        bal = ", ".join(f"{c} {_fmt(a)}" for c, a in v["balances"].items() if a)
        rows.append(f"Wallet balances: {bal or 'none'}.")
        rows.append(f"Tuition still to pay (not counting money on its way): {v['study_currency']} {_fmt(v['outstanding'])}.")
        for i in v["invoices"]:
            rows.append(f"Invoice {i['id']}: {i['currency']} {_fmt(i['amount'])}, paid {_fmt(i['paid'])}, due {i['due'][:10]}, "
                        f"status {i['status']}, scam check {i['verdict']} (score {i['score']}).")
        for t in v["transfers"][-4:]:
            rows.append(f"Payment {t['id']}: {t['dst_currency']} {_fmt(t['dst_amount'])} via {t['provider_name']}, "
                        f"status {t['status'].replace('_', ' ')}, expected {t['eta'][:10]}.")
        pend = [p for p in agent.pending_for_guardian(guardian["id"]) if p["proposal"]["student_id"] == sid]
        rows.append(f"Payments waiting for this guardian's approval: {len(pend)}."
                    + "".join(f" {p['proposal']['proposal_id']}: {p['proposal']['dst_currency']} "
                              f"{_fmt(p['proposal']['total_dst'])} to {p['proposal']['university_name']}." for p in pend))
        rows.append("Kill switch: " + ("ON — no payments can be made." if v.get("frozen") else "off."))
    return "\n".join(rows) if rows else "No student is linked to this guardian account yet."


_G_RULES = [
    (r"approv|waiting|pending|অনুমোদন|批准", "Payments waiting for this guardian"),
    (r"owe|due|left|remaining|outstanding|বাকি|欠|应付", "Tuition still to pay"),
    (r"balance|wallet|money|ব্যালেন্স|টাকা|余额", "Wallet balances"),
    (r"where|arriv|status|sent|transfer|কোথায়|পৌঁছ|到账", "Payment "),
    (r"scam|fake|real|safe|invoice|প্রতারণা|ভুয়া|诈骗|发票", "Invoice "),
    (r"freeze|kill|stop|বন্ধ|冻结", "Kill switch"),
]


def guardian_answer(agent, guardian: dict, question: str, lang: str | None = None) -> dict:
    facts = guardian_facts(agent, guardian)
    ai = None
    if agent._llm():
        ai = llm.grounded(question, facts, lang=lang)
    agent.audit.append("guardian_question", actor="guardian", sim_time=agent._now(), user_id=guardian["id"],
                       ai=ai is not None, text=question[:200])
    if ai:
        return {"text": ai, "source": llm.provider()}
    q = question.lower()
    picked = []
    for pat, prefix in _G_RULES:
        if re.search(pat, q):
            picked += [ln for ln in facts.splitlines() if ln.startswith(prefix) and ln not in picked]
    text = "\n".join(picked) if picked else facts
    return {"text": text, "source": "template"}


# ------------------------------------------------------------------ public questions (home page)
PUBLIC_FACTS = """SudoRoute is an AI agent that pays international students' tuition safely. It runs in a sandbox: no real money moves.
Who it is for: international students and their parents or guardians.
How a payment works: the agent checks the invoice against the university's verified record, compares licensed channels on true cost (fees plus hidden exchange-rate markup), prices currency risk, runs 10 compliance checks, and prepares a signed proposal. Nothing moves until the student types a one-time code. If family money is used, the guardian approves first with their own code.
The one-time code is a 6-digit code texted to the registered phone. In this sandbox no real SMS is sent; the code appears on the phone icon at the top of the portal.
Scam check: every invoice is scored 0 to 100 for look-alike domains, changed bank details, pressure, crypto requests and hidden instructions for AI assistants, in English, Malay, Bangla and Chinese. SudoRoute only ever pays the university's verified account, never the account printed on an invoice.
Universities: students type their university. If it is not yet verified, it is added as pending verification and cannot receive money until its bank account is confirmed with the university.
Guardians: the student enters the guardian's name and e-mail at sign-up; the guardian is linked automatically when they register with that e-mail.
Kill switch: the student or guardian can freeze every payment with one press.
Certificates: a paid-on-time tuition payment can become an Ed25519-signed certificate that anyone can check on the Verify page; a proof-of-funds certificate shows a balance is above a threshold without revealing the balance.
If a transfer is returned or arrives short, SudoRoute explains why and pays only the shortfall, never the full amount twice.
Languages: English, Simplified Chinese and Bangla.
Proof pages: the Security Lab runs 47 live attacks plus 4 controls; the accuracy page shows the scam check on 84 test invoices and a comparison with a bank wire and a basic AI assistant.
Cost: the sandbox is free to try. Sign up at the Get started button. Built for the 2026 Shenzhen International FinTech Competition."""

PUBLIC_FAQ = [
    (r"code|otp|sms|digit|কোড|验证码", "The one-time code is a 6-digit code texted to your registered phone. Typing it proves that you — not the AI — approve this exact payment. In this sandbox no real SMS is sent: the code appears on the phone icon at the top of the portal."),
    (r"scam|fake|fraud|phish|প্রতারণা|ভুয়া|诈骗", "Every invoice is scored 0–100 for look-alike domains, changed bank details, pressure, crypto requests and hidden instructions for AI assistants, in four languages. SudoRoute only ever pays the university's verified account, never the account printed on an invoice."),
    (r"guardian|parent|father|mother|অভিভাবক|বাবা|মা|家长|父母", "Students enter a guardian's name and e-mail at sign-up. When the guardian registers with that e-mail, they are linked automatically and approve every payment that uses family money with their own code."),
    (r"universit|college|school|বিশ্ববিদ্যালয়|大学", "Type your university when you sign up. If it isn't verified yet, it's added as pending verification and can't receive money until its bank account is confirmed with the university itself."),
    (r"safe|secure|trust|security|নিরাপদ|安全", "Nothing moves without your one-time code, family money also needs the guardian's code, proposals are signed and single-use, every step is in a tamper-evident log, and a kill switch freezes everything. Try 47 live attacks yourself on the Security Lab page."),
    (r"cost|fee|price|cheap|খরচ|ফি|费用", "SudoRoute compares licensed channels on true cost — fees plus the hidden exchange-rate markup — and picks the cheapest one that arrives before the due date and is allowed in your country."),
    (r"real money|sandbox|demo|আসল টাকা|真钱|沙盒", "This is a sandbox: universities, banks and accounts are simulated and no real money moves. Exchange rates are real (live or a dated snapshot)."),
    (r"certificate|proof|verify|প্রমাণ|সার্টিফিকেট|证明", "After an on-time payment you can create a signed certificate, or a proof-of-funds certificate for a visa or landlord. Anyone can check it on the Verify page — one changed character fails."),
]


def public_answer(question: str, lang: str | None = None) -> dict:
    ai = llm.grounded(question, PUBLIC_FACTS, lang=lang, words=90) if llm.enabled() else None
    if ai:
        return {"text": ai, "source": llm.provider()}
    q = question.lower()
    for pat, text in PUBLIC_FAQ:
        if re.search(pat, q):
            return {"text": text, "source": "template"}
    return {"text": "I can explain how SudoRoute pays tuition safely: one-time codes, guardian approval, the scam check, "
                    "certificates, costs and universities. Try asking “What is the 6-digit code?” or “How do you stop scams?”",
            "source": "template"}


__all__ = ["brief", "draft_email", "guardian_answer", "guardian_facts", "public_answer", "mask_account"]
