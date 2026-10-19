#!/usr/bin/env python3
"""Check on-chain anchoring from your own computer (needs internet, no wallet, no key).

    python scripts/anchor_check.py

Creates a test anchor record, submits its SHA-256 to the OpenTimestamps calendars (which commit it to
the Bitcoin blockchain within a few hours) and saves two files in evidence/onchain/:
    anchor-test.json       the record that was timestamped
    anchor-test.json.ots   the OpenTimestamps proof
Drop both on https://opentimestamps.org to see the proof (pending → confirmed in a Bitcoin block).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["TS_ANCHOR"] = "1"
from sudoroute.chain.anchor import Anchors, CALENDARS  # noqa: E402

a = Anchors()
h = a.record("SR1.sudoroute-anchor-check", None, 0, "check")["cert_sha256"]
print("Submitting to:", ", ".join(CALENDARS))
out = a.submit(h)
if out["status"] != "submitted":
    sys.exit(f"✗ Not submitted: {out['error']}\n  Check your internet connection and try again.")
d = os.path.join(ROOT, "evidence", "onchain")
os.makedirs(d, exist_ok=True)
with open(os.path.join(d, "anchor-test.json"), "wb") as f:
    f.write(a.record_bytes(h))
with open(os.path.join(d, "anchor-test.json.ots"), "wb") as f:
    f.write(a.ots(h))
print(f"✓ Accepted by {len(out['calendars'])} calendar(s): {', '.join(out['calendars'])}")
print(f"✓ Saved evidence/onchain/anchor-test.json and anchor-test.json.ots")
print("  Open https://opentimestamps.org and drop both files there to verify.")
