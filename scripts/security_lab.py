#!/usr/bin/env python3
"""Run the SudoRoute Security Lab (live attack suite) and save the report as evidence.

    python scripts/security_lab.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sudoroute.security.redteam import run_lab, to_markdown  # noqa: E402

rep = run_lab()
out = os.path.join(ROOT, "evidence")
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "security_lab_report.json"), "w", encoding="utf-8") as f:
    json.dump(rep, f, indent=2, ensure_ascii=False)
with open(os.path.join(out, "security_lab_report.md"), "w", encoding="utf-8") as f:
    f.write(to_markdown(rep))
for r in rep["results"]:
    print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:<7} {r['name']}")
print(f"\n{rep['passed']}/{rep['total']} passed — {rep['attacks']} attacks blocked, {rep['controls']} controls succeeded "
      f"({rep['duration_s']} s). Report: evidence/security_lab_report.md")
sys.exit(0 if rep["passed"] == rep["total"] else 1)
