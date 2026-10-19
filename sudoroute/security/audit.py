"""Tamper-evident audit log.

Every agent step, permission decision and money movement is appended as one JSON line.
Each entry stores the SHA-256 hash of the previous entry, so editing or deleting any
record breaks the chain and `verify()` reports exactly where. PII is redacted first.
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

from .guardrails import redact

GENESIS = "0" * 64


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: str | None = None):
        self.path = path
        self.entries: list[dict] = []
        self._lock = threading.Lock()
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):  # never truncate: the chain continues across restarts and resets
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                self.entries.append(json.loads(line))
                            except ValueError:  # a damaged line breaks the chain, so verify() reports it
                                self.entries.append({"corrupt": line.strip()[:80]})
            else:
                open(path, "w").close()

    def append(self, event: str, *, actor: str, sim_time: str | None = None, **data) -> dict:
        with self._lock:
            prev = self.entries[-1]["hash"] if self.entries else GENESIS
            entry = {
                "seq": len(self.entries) + 1,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sim_time": sim_time,
                "event": event,
                "actor": actor,
                "data": redact(data),
                "prev_hash": prev,
            }
            entry["hash"] = _digest(entry)
            self.entries.append(entry)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return entry

    def verify(self) -> dict:
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.get("prev_hash") != prev:
                return {"valid": False, "broken_at": e.get("seq", i + 1), "reason": "previous-hash link broken"}
            if _digest(e) != e.get("hash"):
                return {"valid": False, "broken_at": e.get("seq", i + 1), "reason": "entry content was modified"}
            prev = e["hash"]
        return {"valid": True, "entries": len(self.entries), "head": prev}

    def tail(self, n: int = 50) -> list[dict]:
        return self.entries[-n:]
