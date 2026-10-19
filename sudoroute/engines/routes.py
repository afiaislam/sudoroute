"""Payment-route optimiser.

Ranks every payment channel by *true landed cost* in the student's home currency:

    landed cost = amount / (mid * (1 - FX markup))   # includes the hidden FX spread
                + fixed fee
                + P(late) * (university late fee + LATE_HARM_USD)   # deadline risk, priced in

and marks a channel ineligible when it breaks a hard rule (unlicensed, not allowed by the
home-country rule pack, over the channel limit, or not a partner of the university).
"""

from .. import config
from ..sandbox.reference_data import COUNTRY_RULES, PROVIDERS, UNIVERSITIES


def late_probability(days_to_due: float, min_days: int, max_days: int, reliability: float,
                     buffer_days: int) -> float:
    usable = days_to_due - buffer_days
    if max_days <= usable:
        timing = 0.0
    elif min_days > days_to_due:
        timing = 1.0
    else:
        span = max(1, max_days - min_days + 1)
        timing = min(1.0, max(0.0, (max_days - usable) / span))
    return round(min(1.0, timing + (1.0 - reliability) * 0.5), 4)


def eligibility(provider: dict, home_country: str, university: dict, amount_usd: float) -> list[str]:
    problems = []
    rules = COUNTRY_RULES.get(home_country)
    if not provider["licensed"]:
        problems.append("Unlicensed channel — illegal for tuition payments and offers no consumer protection.")
    if rules and provider["type"] not in rules["allowed_channel_types"]:
        problems.append(f"{rules['name']} rules do not allow tuition remittance through this channel type "
                        f"({provider['type'].replace('_', ' ')}).")
    if provider["partner_only"] and provider["id"] not in university.get("edu_partners", []):
        problems.append(f"{university['name']} is not a partner of {provider['name']}.")
    if amount_usd > provider["max_usd"]:
        problems.append(f"Amount (≈USD {amount_usd:,.0f}) is above this channel's limit of USD {provider['max_usd']:,.0f}.")
    return problems


def compare_routes(market, *, src: str, dst: str, amount_dst: float, days_to_due: float,
                   university_id: str, home_country: str, buffer_days: int | None = None) -> dict:
    buffer_days = config.ARRIVAL_BUFFER_DAYS if buffer_days is None else buffer_days
    uni = UNIVERSITIES[university_id]
    mid = market.mid(src, dst)
    mid_cost = amount_dst / mid
    amount_usd = market.to_usd(amount_dst, dst)
    late_fee_src = uni.get("late_fee", 0) / mid + config.LATE_HARM_USD * market.units_per_usd(src)

    rows = []
    for p in PROVIDERS.values():
        rate = mid * (1.0 - p["fx_markup"])
        fx_cost = amount_dst / rate
        fee_src = p["fee_usd"] * market.units_per_usd(src)
        total = fx_cost + fee_src
        p_late = late_probability(days_to_due, p["days"][0], p["days"][1], p["reliability"], buffer_days)
        expected_penalty = p_late * late_fee_src
        problems = eligibility(p, home_country, uni, amount_usd)
        rows.append({
            "provider_id": p["id"], "provider": p["name"], "type": p["type"],
            "rate": rate, "fx_markup_pct": round(p["fx_markup"] * 100, 2),
            "fee_src": round(fee_src, 2), "hidden_fx_cost_src": round(fx_cost - mid_cost, 2),
            "total_src": round(total, 2), "arrival_days": p["days"],
            "p_late": p_late, "expected_late_penalty_src": round(expected_penalty, 2),
            "score_src": round(total + expected_penalty, 2),
            "reconciliation": p["reconciliation"],
            "eligible": not problems, "blocked_reasons": problems,
        })

    rows.sort(key=lambda r: (not r["eligible"], r["score_src"]))
    eligible = [r for r in rows if r["eligible"]]
    best = eligible[0] if eligible else None
    bank = next((r for r in rows if r["provider_id"] == "bank_swift"), None)
    savings = round(bank["score_src"] - best["score_src"], 2) if best and bank and bank["eligible"] else None

    explanation = []
    if best:
        explanation.append(f"{best['provider']} has the lowest landed cost: {best['total_src']:,.0f} {src} "
                           f"including {best['hidden_fx_cost_src']:,.0f} {src} of hidden FX spread and "
                           f"{best['fee_src']:,.0f} {src} in fees.")
        if best["p_late"] == 0:
            explanation.append(f"It arrives in {best['arrival_days'][0]}–{best['arrival_days'][1]} days, "
                               f"safely before the due date with a {buffer_days}-day buffer.")
        if savings and savings > 0:
            explanation.append(f"That saves {savings:,.0f} {src} compared with a standard bank wire.")
    cheap_blocked = [r for r in rows if not r["eligible"] and best and r["total_src"] < best["total_src"]]
    for r in cheap_blocked:
        explanation.append(f"{r['provider']} looks cheaper but was excluded: {r['blocked_reasons'][0]}")

    return {
        "src": src, "dst": dst, "amount_dst": amount_dst, "mid_rate": mid, "mid_cost_src": round(mid_cost, 2),
        "days_to_due": round(days_to_due, 1), "buffer_days": buffer_days,
        "routes": rows, "best": best, "savings_vs_bank_src": savings, "explanation": explanation,
    }
