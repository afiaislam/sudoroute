"""Contact messages, feedback and newsletter sign-ups from the public website.

Small JSON stores in the data folder. Inputs are validated and length-capped, a hidden "website" field
catches simple bots, and the caller rate-limits per network. Nothing here is ever shown publicly.
"""

import json
import os
import re
import threading
import time

EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")
TOPICS = ["general", "students", "universities", "partners", "press", "bug", "feedback", "judges"]


def _clean(v, n):
    return re.sub(r"[<>\x00-\x08\x0b-\x1f]", "", str(v or "")).strip()[:n]


class Inbox:
    def __init__(self, path: str | None, max_items: int = 5000):
        self.path, self.max = path, max_items
        self.lock = threading.Lock()
        self.items: list[dict] = []
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.items = json.load(f)
            except (OSError, ValueError):
                self.items = []

    def _save(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items[-self.max:], f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def add(self, item: dict) -> dict:
        with self.lock:
            item = {"id": f"MSG-{int(time.time() * 1000) % 10**10}", "at": int(time.time()), **item}
            self.items.append(item)
            self.items = self.items[-self.max:]
            self._save()
            return item


def contact(data: dict) -> tuple[dict | None, dict]:
    """Validate a contact / feedback form. Returns (clean item or None, field errors)."""
    if _clean(data.get("website"), 200):  # honeypot: humans never see this field
        return None, {"_bot": "rejected"}
    item = {"name": _clean(data.get("name"), 80), "email": _clean(data.get("email"), 200).lower(),
            "topic": data.get("topic") if data.get("topic") in TOPICS else "general",
            "message": _clean(data.get("message"), 3000)}
    rating = data.get("rating")
    if isinstance(rating, int) and 1 <= rating <= 5:
        item["rating"] = rating
    errors = {}
    if len(item["name"]) < 2:
        errors["name"] = "Please enter your name."
    if not EMAIL_RE.fullmatch(item["email"]):
        errors["email"] = "Please enter a valid e-mail address."
    if len(item["message"]) < 10:
        errors["message"] = "Please write at least a sentence (10 characters)."
    return (None if errors else item), errors


def newsletter(data: dict) -> tuple[dict | None, str | None]:
    if _clean(data.get("website"), 200):
        return None, "rejected"
    email = _clean(data.get("email"), 200).lower()
    if not EMAIL_RE.fullmatch(email):
        return None, "Please enter a valid e-mail address."
    return {"email": email, "lang": _clean(data.get("lang"), 5) or "en"}, None
