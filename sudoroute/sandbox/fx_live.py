"""Live exchange rates (optional).

At start-up the server tries to download today's rates from a free, key-less public feed.
If that works, the sandbox market is anchored to the LIVE rates; otherwise it uses the dated
REFERENCE snapshot in reference_data.py. Every screen shows which one is in use.

Safety: a live rate is accepted only if it is within 0.5x–2x of the reference value, so a
broken or spoofed feed can never make the agent quote an absurd amount.
"""

import json
import urllib.request
from datetime import datetime, timezone

from .reference_data import REFERENCE_AS_OF, REFERENCE_SOURCE, UNITS_PER_USD

FEED_URL = "https://open.er-api.com/v6/latest/USD"
STATE = {"source": "REFERENCE", "as_of": REFERENCE_AS_OF, "provider": REFERENCE_SOURCE,
         "spots": dict(UNITS_PER_USD), "rejected": []}


def sanity_filter(rates: dict) -> tuple[dict, list]:
    spots, rejected = {}, []
    for ccy, ref in UNITS_PER_USD.items():
        v = rates.get(ccy)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = None
        if v and 0.5 * ref <= v <= 2.0 * ref:
            spots[ccy] = v
        else:
            spots[ccy] = ref
            if ccy != "USD":
                rejected.append(ccy)
    spots["USD"] = 1.0
    return spots, rejected


def apply(payload: dict, provider: str = "open.er-api.com (live)") -> dict:
    """Apply a feed payload ({'rates': {...}, 'time_last_update_unix': ...}). Returns STATE."""
    rates = payload.get("rates") or {}
    spots, rejected = sanity_filter(rates)
    if len(rejected) >= len(UNITS_PER_USD) - 1:
        return STATE
    ts = payload.get("time_last_update_unix")
    as_of = (datetime.fromtimestamp(int(ts), timezone.utc).isoformat(timespec="seconds")
             if ts else datetime.now(timezone.utc).isoformat(timespec="seconds"))
    STATE.update(source="LIVE", as_of=as_of, provider=provider, spots=spots, rejected=rejected)
    return STATE


def fetch(timeout: float = 4.0, opener=None) -> dict:
    """Try the live feed once. Never raises; falls back to the reference snapshot."""
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "SudoRoute/3.0"})
        with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
            payload = json.loads(r.read(200_000))
        if payload.get("result", "success") == "success":
            return apply(payload)
    except Exception:  # offline, blocked, malformed: keep the reference snapshot
        pass
    return STATE


def public() -> dict:
    return {k: STATE[k] for k in ("source", "as_of", "provider", "rejected")} | {
        "rates": {k: round(v, 6) for k, v in STATE["spots"].items()}}
