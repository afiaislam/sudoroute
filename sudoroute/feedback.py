"""Pilot feedback from real testers.

Signed-in students and guardians can rate SudoRoute once (they may update their answer). The public
pilot page shows only aggregates — never names, e-mails or comments — so the team can report real
user evidence honestly: if nobody has answered yet, the page says so.
"""

import json
import os
import threading
import time

QUESTIONS = {
    "useful": "How useful would SudoRoute be for paying tuition? (1–5)",
    "trust": "How much would you trust it with a real payment? (1–5)",
    "would_use": "Would you use it for a real tuition payment?",
}


class FeedbackStore:
    def __init__(self, path: str | None = None):
        self.path, self.lock, self.rows = path, threading.Lock(), {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.rows = json.load(f)
            except (OSError, ValueError):
                self.rows = {}

    def submit(self, user: dict, data: dict) -> dict:
        try:
            useful, trust = int(data.get("useful")), int(data.get("trust"))
        except (TypeError, ValueError):
            raise ValueError("Choose a rating from 1 to 5 for both questions.")
        if not (1 <= useful <= 5 and 1 <= trust <= 5):
            raise ValueError("Choose a rating from 1 to 5 for both questions.")
        would = data.get("would_use")
        if would not in ("yes", "maybe", "no"):
            raise ValueError("Answer whether you would use it: yes, maybe or no.")
        comment = " ".join(str(data.get("comment", "")).split())[:500]
        with self.lock:
            self.rows[user["id"]] = {"role": user["role"], "useful": useful, "trust": trust, "would_use": would,
                                     "comment": comment, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            self._save()
        return {"ok": True}

    def mine(self, user_id: str) -> dict | None:
        r = self.rows.get(user_id)
        return {k: r[k] for k in ("useful", "trust", "would_use")} if r else None

    def summary(self) -> dict:
        rows = list(self.rows.values())
        n = len(rows)
        avg = lambda k, sub: round(sum(r[k] for r in sub) / len(sub), 2) if sub else None  # noqa: E731
        by = {role: [r for r in rows if r["role"] == role] for role in ("student", "guardian")}
        return {"responses": n, "students": len(by["student"]), "guardians": len(by["guardian"]),
                "useful_avg": avg("useful", rows), "trust_avg": avg("trust", rows),
                "would_use_pct": round(100 * sum(r["would_use"] == "yes" for r in rows) / n, 1) if n else None,
                "maybe_pct": round(100 * sum(r["would_use"] == "maybe" for r in rows) / n, 1) if n else None,
                "questions": QUESTIONS,
                "note": "Collected inside the app from signed-in testers. Only totals are shown; comments stay private."}

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.rows, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
