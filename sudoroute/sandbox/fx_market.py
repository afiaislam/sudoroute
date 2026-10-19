"""Simulated FX market.

Each currency follows a geometric Brownian motion against USD. A 180-day history is
generated backwards from today's reference level so the current rate always equals the
reference rate, while the history has realistic volatility for risk estimation.
"""

import math
import random

from .reference_data import ANNUAL_DRIFT, ANNUAL_VOL, UNITS_PER_USD

DAYS_PER_YEAR = 365.0


class FXMarket:
    def __init__(self, seed: int = 2026, history_days: int = 180, spots: dict | None = None):
        self.seed = seed
        self.spots = dict(spots or UNITS_PER_USD)
        self._rng = random.Random(seed)
        self.history: dict[str, list[float]] = {}
        for ccy, spot in self.spots.items():
            if ccy == "USD":
                self.history[ccy] = [1.0] * (history_days + 1)
                continue
            vol = ANNUAL_VOL[ccy] / math.sqrt(DAYS_PER_YEAR)
            drift = ANNUAL_DRIFT.get(ccy, 0.0) / DAYS_PER_YEAR
            path = [spot]
            for _ in range(history_days):
                z = self._rng.gauss(0.0, 1.0)
                path.append(path[-1] / math.exp(drift - 0.5 * vol * vol + vol * z))
            self.history[ccy] = list(reversed(path))

    # ------------------------------------------------------------ quotes
    def currencies(self) -> list[str]:
        return sorted(self.history)

    def units_per_usd(self, ccy: str) -> float:
        return self.history[ccy][-1]

    def mid(self, src: str, dst: str) -> float:
        """Units of `dst` received for 1 unit of `src` at the mid-market rate."""
        return self.units_per_usd(dst) / self.units_per_usd(src)

    def to_usd(self, amount: float, ccy: str) -> float:
        return amount / self.units_per_usd(ccy)

    def convert(self, amount: float, src: str, dst: str) -> float:
        return amount * self.mid(src, dst)

    def pair_history(self, src: str, dst: str) -> list[float]:
        return [d / s for s, d in zip(self.history[src], self.history[dst])]

    # ------------------------------------------------------------ dynamics
    def advance(self, days: int = 1) -> None:
        """Move the sandbox market forward by `days` daily steps."""
        for _ in range(days):
            for ccy, path in self.history.items():
                if ccy == "USD":
                    path.append(1.0)
                    continue
                vol = ANNUAL_VOL[ccy] / math.sqrt(DAYS_PER_YEAR)
                drift = ANNUAL_DRIFT.get(ccy, 0.0) / DAYS_PER_YEAR
                z = self._rng.gauss(0.0, 1.0)
                path.append(path[-1] * math.exp(drift - 0.5 * vol * vol + vol * z))
