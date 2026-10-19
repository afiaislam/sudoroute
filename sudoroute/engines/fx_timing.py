"""Smart-timing engine: "pay when the rate is good — but never late".

The student approves ONE payment with a target exchange rate and a hard deadline (the latest
safe day to pay: due date − delivery time − buffer). Every sandbox day the agent checks the
rate by itself and executes as soon as the target is reached; if it never is, it pays on the
deadline day at the market rate, provided the rate has not fallen by more than the approved
slippage limit (otherwise it pauses and asks again — it never pays at any price).

This module prices that plan with the same EWMA volatility and Monte Carlo approach as the
FX budget-at-risk engine, so the student sees the chance the target is reached and what the
plan is expected to save or cost compared with paying today.
"""

import math
import random

from .. import config
from .fx_risk import _percentile, ewma_volatility, shrunk_drift

MIN_IMPROVEMENT = 0.0025
MAX_IMPROVEMENT = 0.02
PATHS = 3000


def plan(market, src: str, dst: str, amount_dst: float, quoted_rate: float, fx_markup: float,
         fee_src: float, horizon_days: int, max_slippage: float | None = None, seed: int | None = None) -> dict:
    """quoted_rate = dst units per src unit after the channel markup (what the student gets today)."""
    max_slippage = config.MANDATE_MAX_SLIPPAGE if max_slippage is None else max_slippage
    hist = market.pair_history(src, dst)
    vol = ewma_volatility(hist[-120:])
    drift = shrunk_drift(hist[-120:])
    h = max(1, int(horizon_days))
    improvement = min(MAX_IMPROVEMENT, max(MIN_IMPROVEMENT, 0.5 * vol * math.sqrt(h / 365.0)))
    target = quoted_rate * (1 + improvement)
    floor = quoted_rate / (1 + max_slippage)  # below this the deadline payment pauses instead of paying

    rng = random.Random(config.MC_SEED if seed is None else seed)
    dt = 1.0 / 365.0
    mu, sd = (drift - 0.5 * vol * vol) * dt, vol * math.sqrt(dt)
    cost_now = amount_dst / quoted_rate + fee_src
    costs, hits, hit_days, paused = [], 0, [], 0
    for _ in range(PATHS):
        r = quoted_rate
        done = False
        for d in range(1, h + 1):
            r *= math.exp(mu + sd * rng.gauss(0.0, 1.0))
            if r >= target:
                hits += 1
                hit_days.append(d)
                costs.append(amount_dst / target + fee_src)
                done = True
                break
        if not done:
            if r < floor:
                paused += 1
                costs.append(amount_dst / floor + fee_src)  # bounded: it would pause rather than pay more
            else:
                costs.append(amount_dst / r + fee_src)
    costs.sort()
    expected = sum(costs) / len(costs)
    return {
        "pair": f"{src}/{dst}", "horizon_days": h, "annual_vol": round(vol, 4),
        "quoted_rate": round(quoted_rate, 8), "target_rate": round(target, 8),
        "target_improvement_pct": round(improvement * 100, 2), "floor_rate": round(floor, 8),
        "p_target_hit": round(hits / PATHS, 3), "p_pause": round(paused / PATHS, 3),
        "median_days_to_hit": sorted(hit_days)[len(hit_days) // 2] if hit_days else None,
        "cost_now_src": round(cost_now, 2), "expected_cost_src": round(expected, 2),
        "expected_saving_src": round(cost_now - expected, 2),
        "best_case_src": round(amount_dst / target + fee_src, 2),
        "p95_cost_src": round(_percentile(costs, 0.95), 2),
        "max_cost_src": round(amount_dst / floor + fee_src, 2),
        "paths": PATHS,
    }
