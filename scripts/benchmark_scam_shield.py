#!/usr/bin/env python3
"""Score the invoice scam shield on the multilingual hold-out set and save evidence.

    python scripts/benchmark_scam_shield.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sudoroute.benchmark.scam_shield import run  # noqa: E402

r = run()
o = r["overall"]
lines = ["# Scam shield hold-out benchmark", "",
         "Protocol: rules frozen first, then 60 invoices (30 genuine, 30 scam) written in English, Malay, Bangla "
         "and Chinese. Not tuned on this set. Synthetic samples — see sudoroute/benchmark/invoice_holdout.py.", "",
         "| | Detection (REVIEW or BLOCK) | Hard block | False block (genuine) | False alarm (genuine) |",
         "|---|---|---|---|---|",
         f"| **All** | {o['detection_rate_pct']}% | {o['block_rate_pct']}% | {o['false_block_rate_pct']}% | {o['false_alarm_rate_pct']}% |"]
for k, v in r["by_language"].items():
    lines.append(f"| {k} | {v['detection_rate_pct']}% | {v['block_rate_pct']}% | {v['false_block_rate_pct']}% | "
                 f"{v['false_alarm_rate_pct']}% |")
v2 = r["v2"]["overall"]
lines += ["", "## Hold-out v2 (unseen; includes scams built to beat the negation rule)", "",
          r["v2"]["protocol"], "",
          f"Detection {v2['detection_rate_pct']}% · hard block {v2['block_rate_pct']}% · false block {v2['false_block_rate_pct']}% · "
          f"false alarm {v2['false_alarm_rate_pct']}% ({v2['genuine_review']}/{v2['genuine']} genuine sent to review)", "",
          f"History: with the original frozen rules, set v1 had {r['v1_history']['frozen_rules_false_alarm_pct']}% false alarms. "
          + r["v1_history"]["note"], "",
          "| ID | Lang | Label | Verdict | Score | Signals | Note |", "|---|---|---|---|---|---|---|"]
for x in r["v2"]["samples"]:
    lines.append(f"| {x['id']} | {x['lang']} | {x['label']} | {x['verdict']} | {x['score']} | {', '.join(x['reasons']) or '—'} | {x['note']} |")
lines += ["", "## Set v1 samples", "", "| ID | Lang | Label | Verdict | Score | Signals | Note |", "|---|---|---|---|---|---|---|"]
for s in r["samples"]:
    lines.append(f"| {s['id']} | {s['lang']} | {s['label']} | {s['verdict']} | {s['score']} | "
                 f"{', '.join(s['reasons']) or '—'} | {s['note']} |")
os.makedirs(os.path.join(ROOT, "evidence"), exist_ok=True)
with open(os.path.join(ROOT, "evidence", "scam_shield_benchmark.json"), "w", encoding="utf-8") as f:
    json.dump(r, f, indent=2, ensure_ascii=False)
with open(os.path.join(ROOT, "evidence", "scam_shield_benchmark.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines[:12]))
