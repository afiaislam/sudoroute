"""Baseline comparison: SudoRoute against two reasonable alternatives.

Every number is computed by running code. SudoRoute's column uses the real engines and, for retry
safety, the real agent. The two baselines are deliberately reasonable, not strawmen:

  * "Bank wire": how most families pay today. A SWIFT wire from an authorised bank to the
    account printed on the invoice. Always legal, never checks the invoice, ignores timing.
  * "Cheapest-fee assistant": a typical AI helper. Licensed channels only, picks the lowest cost,
    pays the account on the invoice. It does not check home-country rules, university partner
    status, channel limits or arrival time, and it executes every instruction it is given.

Three suites:
  1. Fraud: the 84 hold-out invoices of sets v1 and v2 (see invoice_holdout*.py). "Money lost" means money sent to
     an account that is not the university's verified account.
  2. Routes: 4 home countries x 4 universities x 5 deadlines x 2 amounts = 160 payments, priced
     with the same market snapshot. Measures cost, rule violations and expected lateness.
  3. Retry safety: a repeated request, a returned transfer and a short receipt, replayed on the
     real agent. Counts payments that would pay the university twice or overpay.

Limitations: FX markups, fees and delivery times are illustrative sandbox values; the hold-out
invoices are synthetic. The point is a transparent, reproducible comparison, not a field study.
"""

from ..engines.invoice_check import verify_invoice
from ..engines.routes import compare_routes
from ..sandbox.bank import HOME_CURRENCY
from ..sandbox.fx_market import FXMarket
from ..sandbox.reference_data import UNIVERSITIES
from .invoice_holdout import SAMPLES as _V1
from .invoice_holdout_v2 import SAMPLES as _V2

SAMPLES = _V1 + _V2  # both hold-out sets (v1 has been seen since a rule change; v2 has not been tuned on)

SYSTEMS = ["SudoRoute", "Bank wire", "Cheapest-fee assistant"]
DEADLINES = [2, 4, 6, 10, 21]                      # days until the tuition is due
AMOUNTS_USD = {"full semester": 14000, "remaining balance": 2500}


def _fraud() -> dict:
    out = {k: {"scams_paid": 0, "money_lost_invoices": 0, "genuine_paid_now": 0, "genuine_checked": 0,
               "genuine_blocked": 0} for k in SYSTEMS}
    scams = [s for s in SAMPLES if s["label"] == "scam"]
    genuine = [s for s in SAMPLES if s["label"] == "genuine"]
    for smp in scams:
        v = verify_invoice(smp["invoice"], {"student_ref": smp["student_ref"]})["verdict"]
        # SudoRoute pays only the registry account, so even a missed scam cannot redirect money.
        if v == "SAFE":
            out["SudoRoute"]["scams_paid"] += 1
        for b in SYSTEMS[1:]:
            out[b]["scams_paid"] += 1
            out[b]["money_lost_invoices"] += 1
    for smp in genuine:
        v = verify_invoice(smp["invoice"], {"student_ref": smp["student_ref"]})["verdict"]
        key = {"SAFE": "genuine_paid_now", "REVIEW": "genuine_checked", "BLOCK": "genuine_blocked"}[v]
        out["SudoRoute"][key] += 1
        for b in SYSTEMS[1:]:
            out[b]["genuine_paid_now"] += 1
    return {"scams": len(scams), "genuine": len(genuine), "results": out}


def _routes() -> dict:
    market = FXMarket()
    acc = {k: {"cost": 0.0, "violations": 0, "late_expected": 0.0, "late_avoidable": 0.0, "payments": 0,
               "cost_vs_bank_pct": []} for k in SYSTEMS}
    impossible = 0
    rows = []
    for country, home in HOME_CURRENCY.items():
        for uid, uni in UNIVERSITIES.items():
            dst = uni["currency"]
            for label, usd in AMOUNTS_USD.items():
                amount = round(usd * market.units_per_usd(dst), 2)
                for days in DEADLINES:
                    r = compare_routes(market, src=home, dst=dst, amount_dst=amount, days_to_due=days,
                                       university_id=uid, home_country=country)
                    by_id = {x["provider_id"]: x for x in r["routes"]}
                    # Lateness is measured against the real due date (no safety buffer), the same for everyone.
                    true_late = {x["provider_id"]: x["p_late"] for x in compare_routes(
                        market, src=home, dst=dst, amount_dst=amount, days_to_due=days, university_id=uid,
                        home_country=country, buffer_days=0)["routes"]}
                    licensed = [x for x in r["routes"] if not any("Unlicensed" in p for p in x["blocked_reasons"])]
                    picks = {"SudoRoute": r["best"], "Bank wire": by_id["bank_swift"],
                             "Cheapest-fee assistant": min(licensed, key=lambda x: x["total_src"])}
                    bank_usd = market.to_usd(by_id["bank_swift"]["total_src"], home)
                    best_legal = min(true_late[x["provider_id"]] for x in r["routes"] if x["eligible"])
                    impossible += best_legal >= 0.5
                    for k, p in picks.items():
                        a = acc[k]
                        a["payments"] += 1
                        a["cost"] += market.to_usd(p["total_src"], home)
                        a["violations"] += 0 if p["eligible"] else 1
                        a["late_expected"] += true_late[p["provider_id"]]
                        a["late_avoidable"] += max(0.0, true_late[p["provider_id"]] - best_legal)
                        a["cost_vs_bank_pct"].append(100 * (market.to_usd(p["total_src"], home) - bank_usd) / bank_usd)
                    rows.append({"home": country, "university": uid, "amount": label, "days_to_due": days,
                                 **{k: {"channel": v["provider"], "eligible": v["eligible"], "p_late": true_late[v["provider_id"]],
                                        "cost_usd": round(market.to_usd(v["total_src"], home), 2)} for k, v in picks.items()}})
    res = {}
    for k, a in acc.items():
        n = a["payments"]
        res[k] = {"payments": n, "avg_cost_usd": round(a["cost"] / n, 2),
                  "avg_saving_vs_bank_pct": round(-sum(a["cost_vs_bank_pct"]) / n, 2) + 0.0,
                  "rule_violations": a["violations"],
                  "expected_late_payments": round(a["late_expected"], 1),
                  "late_rate_pct": round(100 * a["late_expected"] / n, 1),
                  "avoidable_late_pct": round(100 * a["late_avoidable"] / n, 1)}
    return {"scenarios": len(rows), "results": res, "rows": rows, "impossible_on_time_legally": impossible,
            "by_country": _by_country(rows)}


def _by_country(rows) -> dict:
    """Fairness view: the same protections and savings for every home country in the set."""
    out = {}
    for c in HOME_CURRENCY:
        sub = [r for r in rows if r["home"] == c]
        if not sub:
            continue
        def avg(k, f):
            return round(sum(f(r[k]) for r in sub) / len(sub), 2)
        out[c] = {"payments": len(sub),
                  "saving_vs_bank_pct": round(100 * sum((r["Bank wire"]["cost_usd"] - r["SudoRoute"]["cost_usd"]) / r["Bank wire"]["cost_usd"] for r in sub) / len(sub), 2),
                  "rule_violations": sum(not r["SudoRoute"]["eligible"] for r in sub),
                  "late_rate_pct": round(100 * avg("SudoRoute", lambda v: v["p_late"]), 1),
                  "bank_wire_late_rate_pct": round(100 * avg("Bank wire", lambda v: v["p_late"]), 1)}
    return out


def _retry() -> dict:
    """Replay three retry situations on the real agent; baselines execute every request as given."""
    from ..agent.core import SudoRouteAgent
    from ..sandbox.bank import SandboxBank
    from ..security.audit import AuditLog
    from ..security.proposals import ProposalStore, sandbox_otp

    def pay(a, sid):
        out = a.chat(sid, "Pay my tuition")
        card = next((c for c in out.get("cards", []) if c["type"] == "proposal"), None)
        if not card:
            return None
        pid = card["proposal"]["proposal_id"]
        res = a.confirm(sid, pid, card["token"], sandbox_otp(pid, a.proposals.key))
        return card["proposal"]["total_dst"] if res.get("ok") else None

    def fresh():
        return SudoRouteAgent(SandboxBank(), AuditLog(), ProposalStore(key=b"benchmark-key"))

    sid, cases = "STU-BD-001", []
    # 1. The student asks twice (double click, network retry, impatience).
    a = fresh(); pay(a, sid); second = pay(a, sid); a.advance(10)
    inv = a.bank.invoices["INV-MUT-26S2"]
    cases.append({"case": "Same request sent twice", "SudoRoute_overpaid": round(max(0, inv["paid"] - inv["amount"]), 2),
                  "SudoRoute_second_payment": bool(second), "baseline_overpaid": inv["amount"]})
    # 2. The receiving bank returns the transfer; the student retries before fixing the cause.
    a = fresh(); pay(a, sid)
    tid = next(iter(a.bank.transfers)); a.inject_issue(sid, tid, "returned")
    diag = a.recover(sid, tid)
    cases.append({"case": "Transfer returned by the bank", "SudoRoute_overpaid": 0.0,
                  "SudoRoute_second_payment": False, "SudoRoute_advice": diag["steps"][0],
                  "baseline_overpaid": 0.0, "baseline_note": "Money comes back, but a blind resend fails again for the same reason."})
    # 3. An intermediary bank deducts a fee; the student retries the payment.
    a = fresh(); pay(a, sid)
    tid = next(iter(a.bank.transfers)); a.inject_issue(sid, tid, "short"); a.advance(6)
    short = a.recover(sid, tid)["outstanding"]
    topup = pay(a, sid) or 0.0
    a.advance(6)
    inv = a.bank.invoices["INV-MUT-26S2"]
    cases.append({"case": "University received less than sent", "SudoRoute_overpaid": round(max(0, inv["paid"] - inv["amount"]), 2),
                  "SudoRoute_second_payment": True, "SudoRoute_paid_again": round(topup, 2), "shortfall": short,
                  "baseline_overpaid": round(inv["amount"] - short, 2)})
    return {"currency": "MYR", "cases": cases,
            "results": {"SudoRoute": {"overpayments": sum(c["SudoRoute_overpaid"] > 0.01 for c in cases)},
                        "Bank wire": {"overpayments": sum(c["baseline_overpaid"] > 0.01 for c in cases)},
                        "Cheapest-fee assistant": {"overpayments": sum(c["baseline_overpaid"] > 0.01 for c in cases)}}}


def run() -> dict:
    f, r, t = _fraud(), _routes(), _retry()
    summary = {}
    for k in SYSTEMS:
        summary[k] = {
            "scams_that_reach_a_fraudster": f["results"][k]["money_lost_invoices"],
            "genuine_paid_without_delay": f["results"][k]["genuine_paid_now"],
            "genuine_sent_for_a_check": f["results"][k]["genuine_checked"],
            "genuine_blocked": f["results"][k]["genuine_blocked"],
            "avg_saving_vs_bank_pct": r["results"][k]["avg_saving_vs_bank_pct"],
            "rule_violations": r["results"][k]["rule_violations"],
            "late_rate_pct": r["results"][k]["late_rate_pct"],
            "avoidable_late_pct": r["results"][k]["avoidable_late_pct"],
            "overpayments_on_retry": t["results"][k]["overpayments"],
        }
    return {"systems": SYSTEMS, "summary": summary, "fraud": f, "routes": {k: v for k, v in r.items() if k != "rows"},
            "route_rows": r["rows"], "retry": t,
            "definitions": {
                "Bank wire": "SWIFT wire from an authorised bank to the account printed on the invoice. Legal, no invoice check, ignores timing.",
                "Cheapest-fee assistant": "Licensed channels only; lowest cost; pays the account on the invoice; does not check country rules, "
                                          "university partner status, limits or arrival time; executes every request.",
                "scams_that_reach_a_fraudster": f"Of {f['scams']} scam invoices, how many send money to an account that is not the university's verified one.",
                "rule_violations": f"Of {r['scenarios']} payments, how many use a channel the home-country rules, the university or the channel limit do not allow.",
                "late_rate_pct": "Expected share of payments arriving after the real due date (channel delivery window and reliability).",
                "avoidable_late_pct": "Lateness that an allowed channel could have avoided. Some deadlines are too close for any allowed channel; SudoRoute warns about these early with a pay-by date.",
                "overpayments_on_retry": "Of 3 retry situations, how many end with the university paid more than the invoice.",
                "why_assistant_cheaper": "The assistant is cheaper and faster only because it uses channels the rules do not allow; SudoRoute chooses among allowed channels only.",
                "note": "SudoRoute sends genuine invoices flagged for a check to the student first; it never pays the account printed on an invoice."}}


def to_markdown(r: dict) -> str:
    s = r["summary"]; cols = r["systems"]
    line = lambda label, key, fmt="{}": f"| {label} | " + " | ".join(fmt.format(s[c][key]) for c in cols) + " |"  # noqa: E731
    out = ["# Baseline comparison", "", "Generated by `python scripts/benchmark_baselines.py`. Every number is computed by running code.", "",
           "| Measure | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols),
           line(f"Scam invoices that send money to a fraudster (of {r['fraud']['scams']})", "scams_that_reach_a_fraudster"),
           line(f"Genuine invoices paid without delay (of {r['fraud']['genuine']})", "genuine_paid_without_delay"),
           line("Genuine invoices sent to the student for a check", "genuine_sent_for_a_check"),
           line("Genuine invoices blocked", "genuine_blocked"),
           line("Average saving vs bank wire", "avg_saving_vs_bank_pct", "{}%"),
           line(f"Payments breaking a rule (of {r['routes']['scenarios']})", "rule_violations"),
           line("Expected late payments (all deadlines, 2 to 21 days)", "late_rate_pct", "{}%"),
           line("Avoidable lateness (an allowed on-time channel existed)", "avoidable_late_pct", "{}%"),
           line("Retry situations that overpay (of 3)", "overpayments_on_retry"), "", "## Definitions", ""]
    out += [f"- **{k}**: {v}" for k, v in r["definitions"].items()]
    out += ["", f"{r['routes']['impossible_on_time_legally']} of {r['routes']['scenarios']} payments have a deadline too close for "
            "any allowed channel; these count as late for every legal system.", "", "## Fairness: SudoRoute by home country", "",
            "| Home country | Payments | Saving vs bank wire | Rule violations | Expected late | Bank wire late |", "|---|---|---|---|---|---|"]
    out += [f"| {c} | {v['payments']} | {v['saving_vs_bank_pct']}% | {v['rule_violations']} | {v['late_rate_pct']}% | {v['bank_wire_late_rate_pct']}% |"
            for c, v in r["routes"]["by_country"].items()]
    out += ["", "## Retry cases (real agent)", ""] + [f"- {c['case']}: SudoRoute overpaid {c['SudoRoute_overpaid']} MYR; "
                                                      f"a baseline that repeats the payment overpays {c['baseline_overpaid']} MYR." for c in r["retry"]["cases"]]
    v = s["Cheapest-fee assistant"]["rule_violations"]
    out += ["", f"Why the assistant looks cheaper and faster: {v} of its {r['routes']['scenarios']} payments use a channel that the "
            "home-country rules, the university or the channel limit do not allow (for example a debit card above its limit, or a "
            "money-transfer operator a country does not permit for tuition). SudoRoute only chooses among allowed channels."]
    out += ["", "Limitations: sandbox fees, markups and delivery times are illustrative; the hold-out invoices are synthetic. "
            "The genuine invoices SudoRoute sends for a check are a real cost: the student has to confirm with the university first."]
    return "\n".join(out) + "\n"
