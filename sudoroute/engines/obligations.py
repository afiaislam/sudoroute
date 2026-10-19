"""Semester bills planner.

Tuition is not the only thing due in a semester. This engine lines up every bill (open tuition
invoices plus typical living obligations: next month's hostel rent, student medical insurance,
student-pass renewal), sorts them by due date, and checks whether the money the student has now
plus the family support scheduled before each due date covers it — bill by bill, in order.

All figures are in the study currency. Home-currency savings are converted at today's mid rate
less a typical licensed-channel markup, so the plan never assumes a better rate than is
realistically available. Living-cost bills are for planning only; the agent pays tuition.
"""

from datetime import datetime, timedelta

LICENSED_MARKUP = 0.012  # education-platform spread used for planning conversions
LIVING_BILLS_USD = [  # label, approximate USD amount, days from now
    ("Hostel rent (next month)", 420, 6),
    ("Student medical insurance", 160, 21),
    ("Student pass / visa renewal", 250, 40),
]


def make_obligations(study_ccy: str, market, now: datetime) -> list[dict]:
    out = []
    for i, (label, usd, days) in enumerate(LIVING_BILLS_USD, 1):
        amt = usd * market.units_per_usd(study_ccy)
        amt = round(amt, -1) if amt > 1000 else round(amt, 2)
        out.append({"id": f"BILL-{i}", "label": label, "amount": float(amt), "currency": study_ccy,
                    "due": (now + timedelta(days=days)).isoformat(), "kind": "living", "paid": False})
    return out


def _to_study(market, amount: float, ccy: str, study: str, markup: float = LICENSED_MARKUP) -> float:
    if ccy == study:
        return amount
    return amount * market.mid(ccy, study) * (1 - markup)


def semester_plan(student: dict, tuition: list[dict], market, now: datetime, days_elapsed: int) -> dict:
    """tuition: [{"id", "amount" (outstanding), "currency", "due"}] in the study currency."""
    study = student["study_currency"]
    bills = [{"id": t["id"], "label": f"Tuition ({t['id']})", "amount": round(t["amount"], 2), "currency": study,
              "due": t["due"], "kind": "tuition"} for t in tuition if t["amount"] > 0.01]
    bills += [dict(b) for b in student.get("obligations", []) if not b.get("paid")]
    bills.sort(key=lambda b: b["due"])

    available = sum(_to_study(market, a, c, study) for c, a in student["balances"].items() if a > 0)

    def inflows_until(due_iso: str) -> float:
        days = max(0, (datetime.fromisoformat(due_iso) - now).days)
        total = 0.0
        for f in student.get("inflows", []):
            k = f["every_days"]
            hits = (days_elapsed + days) // k - days_elapsed // k
            total += hits * _to_study(market, f["amount"], f["currency"], study)
        return total

    needed_before = 0.0
    for b in bills:
        funds = available + inflows_until(b["due"])
        left = funds - needed_before
        ratio = max(0.0, min(1.0, left / b["amount"])) if b["amount"] else 1.0
        b["funded_pct"] = round(ratio * 100, 1)
        b["status"] = "covered" if ratio >= 0.999 else "partly" if ratio > 0 else "short"
        b["days_left"] = (datetime.fromisoformat(b["due"]) - now).days
        needed_before += b["amount"]
    total = sum(b["amount"] for b in bills)
    last_due = bills[-1]["due"] if bills else now.isoformat()
    funds_total = available + inflows_until(last_due)
    return {"currency": study, "bills": bills, "total_needed": round(total, 2), "available_now": round(available, 2),
            "funded_pct": round(min(1.0, funds_total / total) * 100, 1) if total else 100.0,
            "note": "Planning view. Home savings converted at today's rate less a typical licensed-channel markup; "
                    "family support counted only if it is scheduled before each due date."}
