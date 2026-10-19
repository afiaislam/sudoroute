"""Multi-currency budget, runway and spending insights for a student."""

from collections import defaultdict
from datetime import date, timedelta


def budget_overview(market, student: dict, transactions: list[dict], open_invoices: list[dict],
                    today: date) -> dict:
    study = student["study_currency"]
    home = student["home_currency"]

    # Spend per category in rolling 30-day periods (period 0 = the last 30 days).
    by_month: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    # Anchor periods to the latest recorded spending so the sandbox clock moving ahead
    # doesn't create artificial "empty" months.
    dates = [date.fromisoformat(t["date"]) for t in transactions if t["direction"] == "out"]
    anchor = min(today, max(dates) + timedelta(days=1)) if dates else today
    for t in transactions:
        if t["direction"] != "out":
            continue
        amt = market.convert(t["amount"], t["currency"], study)
        period = max(0, (anchor - date.fromisoformat(t["date"])).days) // 30
        by_month[period][t["category"]] += amt
    months = sorted(by_month)
    if not months:
        return {"error": "no transactions"}
    latest = months[0]
    previous = months[1:] or months
    cats = sorted({c for m in by_month.values() for c in m})
    categories = []
    for c in cats:
        avg_prev = sum(by_month[m].get(c, 0.0) for m in previous) / len(previous)
        cur = by_month[latest].get(c, 0.0)
        change = (cur - avg_prev) / avg_prev if avg_prev else 0.0
        categories.append({"category": c, "latest": round(cur, 2), "average": round(avg_prev, 2),
                           "change_pct": round(change * 100, 1)})
    monthly_burn = sum(c["average"] for c in categories)

    # Balances valued in study currency.
    balances = []
    total_study = 0.0
    for ccy, amt in student["balances"].items():
        val = market.convert(amt, ccy, study)
        total_study += val
        balances.append({"currency": ccy, "amount": round(amt, 2), "value_in_study_ccy": round(val, 2)})

    tuition_due = sum(inv["amount"] - inv["paid"] for inv in open_invoices
                      if inv["status"] != "paid" and inv["currency"] == study)
    inflow_monthly = 0.0
    for inf in student.get("inflows", []):
        inflow_monthly += market.convert(inf["amount"], inf["currency"], study) * 30.0 / inf["every_days"]

    after_tuition = total_study - tuition_due
    net_burn = monthly_burn - inflow_monthly
    runway = None if net_burn <= 0 else round(max(0.0, after_tuition) / net_burn, 1)

    insights = []
    for c in sorted(categories, key=lambda c: -c["change_pct"]):
        if c["change_pct"] >= 20:
            insights.append(f"{c['category']} spending is up {c['change_pct']:.0f}% this month "
                            f"({c['latest']:,.0f} vs usual {c['average']:,.0f} {study}).")
    if tuition_due > 0:
        insights.append(f"After setting aside {tuition_due:,.0f} {study} for tuition, you have "
                        f"{max(0.0, after_tuition):,.0f} {study} of savings left.")
    if runway is not None:
        insights.append(f"With {inflow_monthly:,.0f} {study}/month from home and {monthly_burn:,.0f} {study}/month "
                        f"spending, your savings last about {runway} months.")
    else:
        insights.append("Your monthly support covers your usual spending — no runway risk.")
    top = max(categories, key=lambda c: c["average"])
    if top["category"] != "Rent" and top["average"] > 0.3 * monthly_burn:
        insights.append(f"{top['category']} is your largest cost; a 10% cut saves {0.1 * top['average']:,.0f} {study}/month.")
    hint = next((c for c in categories if c["category"] == "Food" and c["change_pct"] >= 20), None)
    if hint:
        insights.append("Tip: a weekly grocery list and the campus meal plan usually bring food costs back to normal.")

    return {
        "study_currency": study, "home_currency": home, "latest_period": "last 30 days",
        "categories": categories, "monthly_burn": round(monthly_burn, 2),
        "monthly_inflow": round(inflow_monthly, 2), "balances": balances,
        "total_value_study": round(total_study, 2), "tuition_outstanding": round(tuition_due, 2),
        "runway_months": runway, "insights": insights, "as_of": today.isoformat(),
    }
