# SudoRoute — Execution evidence (submission item 06)

Topic C is a non-on-chain topic, so the required evidence is **sandbox operation logs and the demo video**. Every file here was produced by running code in this repository; each can be regenerated with the command shown. No real money moves — accounts, banks and universities are a sandbox.

## Sandbox operation logs

| File | What it shows | Regenerate |
|---|---|---|
| `sandbox_operation_log.jsonl` | 131 hash-chained audit entries from the end-to-end run: every message, tool call, proposal, approval, code check, transfer and certificate, with simulated time and previous/own hash | `python scripts/run_demo.py` |
| `execution_summary.json` | 41 of 41 checked steps passed, audit chain valid (head hash), every transfer with amounts, channel, reference and status | `python scripts/run_demo.py` |
| `demo_transcript.md` | The same run in readable form: 9 scenarios — scam invoice with hidden AI instructions, permission tiers and prohibited actions, payment with guardian co-approval (Bangladesh → Malaysia), tampering then a 3-instalment mandate (Nigeria → UK), budget/credit/audit, attacks in four languages and the kill switch, a verifiable certificate, smart timing, authenticator app | `python scripts/run_demo.py` |

## Execution video

`execution-evidence-video.mp4` (1 min 46 s, submitted as `SudoRoute_06_Execution-Evidence-Video.mp4`) shows this evidence being produced and checked, unedited: the `run_demo.py` run in the terminal (41/41), the operation log with its hash links, the transfers in `execution_summary.json`, a live payment on the sandbox site with its activity log verified on screen, and a live Security Lab run (63/63). The log files in this folder are the ones produced by the run shown in the video. Recorded with `scripts/record_evidence.py`.

The full product demo (4 min 10 s) is item 03: `web/static/video/sudoroute-demo.mp4`, also on the home page of [sudoroute.onrender.com](https://sudoroute.onrender.com).

## Security and accuracy runs

| File | Result | Regenerate |
|---|---|---|
| `security_lab_report.md` / `.json` | 63/63 — 57 live HTTP attacks blocked (incl. a hostile AI model) + 6 controls that must succeed | `python scripts/security_lab.py` |
| `scam_shield_benchmark.md` / `.json` | 84 hold-out invoices in 4 languages: 100% of scams flagged, 0 genuine blocked | `python scripts/benchmark_scam_shield.py` |
| `baseline_comparison.md` / `.json` | vs bank wire and a cheapest-fee assistant: 0 scams paid, 0 rule breaks, 1.82% cheaper | `python scripts/benchmark_baselines.py` |
| `test_report.txt` | 230 automated tests passed | `python -m unittest discover -s tests -t . -v` |
| `live_llm_eval.md`, `live_gemini_transcript.md` | Real Gemini (gemini-3.1-flash-lite, 20 Oct 2026): 23/24 plans correct, 0 money moved, 0 leaks, reader monotonic 100% | `python scripts/eval_live_llm.py` (needs a key) |

## On-chain proof (extra)

`onchain/anchor-test.json` is a certificate anchor record; `anchor-test.json.ots` is its OpenTimestamps proof, confirmed in **Bitcoin block 972087** (`onchain_confirmed.png`). Check it with any OpenTimestamps verifier or on `/verify` of the live site. No money, wallet or personal data goes on-chain.

## Screenshots

`screenshots/` — every main screen (see `screenshots/README.md`).
