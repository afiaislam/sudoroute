#!/usr/bin/env python3
"""Compare SudoRoute with a bank wire and a cheapest-fee AI assistant, and save evidence.

    python scripts/benchmark_baselines.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sudoroute.benchmark.baselines import run, to_markdown  # noqa: E402

r = run()
os.makedirs(os.path.join(ROOT, "evidence"), exist_ok=True)
with open(os.path.join(ROOT, "evidence", "baseline_comparison.json"), "w", encoding="utf-8") as f:
    json.dump(r, f, indent=2, ensure_ascii=False)
with open(os.path.join(ROOT, "evidence", "baseline_comparison.md"), "w", encoding="utf-8") as f:
    f.write(to_markdown(r))
print(to_markdown(r))
