"""FX budget-at-risk engine.

Question it answers for a student: "If I pay now, later, or in installments, how much will
my tuition cost in my home currency — and how likely is it to exceed the money my family
set aside?"

Method
------
1. Volatility of the pair (dst per src) is estimated from its daily log returns with an
   EWMA (RiskMetrics, lambda = 0.94), annualised with sqrt(365).
2. Drift is the historical mean log return shrunk 50% towards zero (robust to short samples).
3. 4,000 Monte Carlo paths of geometric Brownian motion are simulated to the payment horizon.
4. Each strategy's home-currency cost is computed on every path, giving the mean, the 95th
   percentile ("budget-at-risk") and the probability of exceeding the tuition budget.
"""

import math
import random
import statistics

from .. import config

LAMBDA = 0.94


def ewma_volatility(series: list[float]) -> float:
    rets = [math.log(b / a) for a, b in zip(series, series[1:]) if a > 0 and b > 0]
    if len(rets) < 2:
        return 0.0
    var = rets[0] ** 2
    for r in rets[1:]:
        var = LAMBDA * var + (1 - LAMBDA) * r * r
    return math.sqrt(var * 365.0)


def shrunk_drift(series: list[float]) -> float:
    rets = [math.log(b / a) for a, b in zip(series, series[1:]) if a > 0 and b > 0]
    if not rets:
        return 0.0
    return 0.5 * statistics.fmean(rets) * 365.0


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def simulate_paths(spot: float, vol: float, drift: float, horizon_days: int,
                   n_paths: int, seed: int) -> list[list[float]]:
    rng = random.Random(seed)
    dt = 1.0 / 365.0
    step_mu = (drift - 0.5 * vol * vol) * dt
    step_sd = vol * math.sqrt(dt)
    paths = []
    for _ in range(n_paths):
        r = spot
        path = [r]
        for _ in range(horizon_days):
            r *= math.exp(step_mu + step_sd * rng.gauss(0.0, 1.0))
            path.append(r)
        paths.append(path)
    return paths


def _stats(costs: list[float], budget: float | None) -> dict:
    s = sorted(costs)
    out = {
        "expected": round(statistics.fmean(s), 2),
        "p05": round(_percentile(s, 0.05), 2),
        "p95": round(_percentile(s, 0.95), 2),
    }
    out["prob_over_budget"] = (round(sum(1 for c in s if c > budget) / len(s), 4) if budget else None)
    return out


def budget_at_risk(market, src: str, dst: str, amount_dst: float, horizon_days: int,
                   budget_src: float | None = None, available_src: float | None = None,
                   fx_markup: float = 0.0, installments: int = 3,
                   allows_installments: bool = True,
                   n_paths: int | None = None, seed: int | None = None) -> dict:
    """Compare pay-now, pay-at-due and equal installments for one invoice."""
    n_paths = n_paths or config.MC_PATHS
    seed = config.MC_SEED if seed is None else seed
    horizon_days = max(1, int(horizon_days))
    hist = market.pair_history(src, dst)
    spot = market.mid(src, dst)
    vol = ewma_volatility(hist)
    drift = shrunk_drift(hist)
    paths = simulate_paths(spot, vol, drift, horizon_days, n_paths, seed)
    eff = 1.0 - fx_markup  # provider rate = mid * (1 - markup)

    def cost_at(rate: float, amt: float) -> float:
        return amt / (rate * eff)

    pay_now = cost_at(spot, amount_dst)
    strategies = {
        "pay_now": {"label": "Pay now (rate locked today)", "legs": [{"day": 0, "fraction": 1.0}],
                    "costs": [pay_now] * len(paths)},
        "pay_at_due": {"label": f"Wait and pay on day {horizon_days}",
                       "legs": [{"day": horizon_days, "fraction": 1.0}],
                       "costs": [cost_at(p[-1], amount_dst) for p in paths]},
    }
    if allows_installments and installments > 1:
        days = [round(i * horizon_days / (installments - 1)) for i in range(installments)]
        frac = 1.0 / installments
        strategies["installments"] = {
            "label": f"{installments} equal installments (days {', '.join(map(str, days))})",
            "legs": [{"day": d, "fraction": frac} for d in days],
            "costs": [sum(cost_at(p[d], amount_dst * frac) for d in days) for p in paths],
        }

    results = {}
    for key, st in strategies.items():
        res = {"label": st["label"], "legs": st["legs"]}
        res.update(_stats(st["costs"], budget_src))
        first_leg = st["legs"][0]["fraction"] * pay_now if st["legs"][0]["day"] == 0 else 0.0
        res["upfront_needed"] = round(first_leg, 2)
        res["affordable_now"] = (available_src is None) or (first_leg <= available_src + 1e-6)
        results[key] = res

    # Recommendation: lowest 95th-percentile cost among strategies affordable today.
    affordable = {k: v for k, v in results.items() if v["affordable_now"]}
    pool = affordable or results
    best = min(pool, key=lambda k: (pool[k]["p95"], pool[k]["expected"]))
    wait_extra = results["pay_at_due"]["expected"] - results["pay_now"]["expected"]

    reasons = []
    if best == "pay_now":
        reasons.append("Paying now removes all exchange-rate risk and has the lowest worst-case cost.")
    elif best == "installments":
        if not results["pay_now"]["affordable_now"]:
            reasons.append("Your current balance cannot cover the full amount today, so installments "
                           "spread the payment across your expected family transfers.")
        reasons.append("Installments average the exchange rate and cut the worst-case cost versus waiting.")
    else:
        reasons.append("Waiting has the lowest worst-case cost under the current market trend.")
    if wait_extra > 0:
        reasons.append(f"Waiting until the due date is expected to cost {wait_extra:,.0f} {src} more "
                       f"because {src} has been weakening against {dst}.")

    # Fan chart: percentiles of the home-currency cost of the full invoice over time.
    step = max(1, horizon_days // 30)
    fan = []
    for d in range(0, horizon_days + 1, step):
        col = sorted(cost_at(p[d], amount_dst) for p in paths)
        fan.append({"day": d, "p05": round(_percentile(col, 0.05), 2), "p50": round(_percentile(col, 0.5), 2),
                    "p95": round(_percentile(col, 0.95), 2)})

    return {
        "pair": f"{src}/{dst}", "spot_mid": spot, "annual_vol": round(vol, 4), "annual_drift": round(drift, 4),
        "horizon_days": horizon_days, "paths": n_paths, "amount_dst": amount_dst, "currency_dst": dst,
        "currency_src": src, "budget_src": budget_src, "available_src": available_src,
        "strategies": results, "recommended": best, "reasons": reasons, "fan": fan,
        "method": "EWMA volatility (lambda 0.94) + GBM Monte Carlo",
    }
