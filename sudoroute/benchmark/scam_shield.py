"""Score the scam shield on the hold-out set (see invoice_holdout.py for the protocol)."""

from ..engines.invoice_check import verify_invoice
from .invoice_holdout import SAMPLES
from .invoice_holdout_v2 import SAMPLES as SAMPLES_V2

LANGS = {"en": "English", "ms": "Malay", "bn": "Bangla", "zh": "Chinese"}


def run(samples=None, with_v2: bool = True) -> dict:
    rows = []
    for smp in (samples or SAMPLES):
        v = verify_invoice(smp["invoice"], {"student_ref": smp["student_ref"]})
        rows.append({"id": smp["id"], "lang": smp["lang"], "label": smp["label"], "note": smp["note"],
                     "verdict": v["verdict"], "score": v["score"], "reasons": [r["code"] for r in v["reasons"]]})

    def stats(sub):
        gen = [r for r in sub if r["label"] == "genuine"]
        scam = [r for r in sub if r["label"] == "scam"]
        pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
        return {
            "genuine": len(gen), "scam": len(scam),
            "genuine_safe": sum(r["verdict"] == "SAFE" for r in gen),
            "genuine_review": sum(r["verdict"] == "REVIEW" for r in gen),
            "genuine_blocked": sum(r["verdict"] == "BLOCK" for r in gen),
            "scam_blocked": sum(r["verdict"] == "BLOCK" for r in scam),
            "scam_review": sum(r["verdict"] == "REVIEW" for r in scam),
            "scam_missed": sum(r["verdict"] == "SAFE" for r in scam),
            "false_block_rate_pct": pct(sum(r["verdict"] == "BLOCK" for r in gen), len(gen)),
            "false_alarm_rate_pct": pct(sum(r["verdict"] != "SAFE" for r in gen), len(gen)),
            "detection_rate_pct": pct(sum(r["verdict"] != "SAFE" for r in scam), len(scam)),
            "block_rate_pct": pct(sum(r["verdict"] == "BLOCK" for r in scam), len(scam)),
        }

    extra = {}
    if with_v2 and samples is None:
        v2 = run(SAMPLES_V2, with_v2=False)
        extra = {"v2": {"overall": v2["overall"], "by_language": v2["by_language"], "samples": v2["samples"],
                        "protocol": "Written after the negation-aware warning rule was added (which was a response to "
                                    "v1's false alarms), evaluated once. Includes scams designed to beat that rule."},
                 "v1_history": {"frozen_rules_false_alarm_pct": 13.3, "frozen_rules_detection_pct": 100.0,
                                "note": "v1 result with the original frozen rules. The current v1 numbers are measured "
                                        "after a rule change made in response to v1, so v1 is no longer unseen."}}
    return {**extra, "overall": stats(rows), "by_language": {LANGS[k]: stats([r for r in rows if r["lang"] == k]) for k in LANGS},
            "samples": rows,
            "definitions": {
                "detection_rate_pct": "Scams flagged REVIEW or BLOCK (the agent will not pay them without extra checks).",
                "block_rate_pct": "Scams flagged BLOCK (the agent refuses outright).",
                "false_block_rate_pct": "Genuine invoices wrongly BLOCKED.",
                "false_alarm_rate_pct": "Genuine invoices flagged REVIEW or BLOCK.",
                "note": "Whatever the verdict, SudoRoute only ever pays the university's registry account, never "
                        "account details printed on an invoice."}}
