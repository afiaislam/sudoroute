"""On-chain anchoring of certificates and the audit log (challenge bonus: on-chain exploration).

When SudoRoute signs a certificate it also writes a small ANCHOR RECORD:

    {"v": 1, "cert_sha256": sha256(certificate), "audit_head": <hash of the audit chain>,
     "audit_entries": n, "issuer_kid": ..., "created": ...}

The SHA-256 of that record is timestamped on the **Bitcoin blockchain** through OpenTimestamps, a
free public timestamping service: calendar servers aggregate many hashes into one Merkle tree and
commit its root in a Bitcoin transaction (usually within a few hours). The result is an `.ots` proof
file that anyone can check at https://opentimestamps.org together with the anchor record — without
trusting SudoRoute's server.

Why this design:
  * No wallet, coins or private keys are needed, and no money or personal data goes on-chain —
    only a 32-byte hash. It fits SudoRoute's rule of never paying in crypto.
  * It makes two things tamper-evident beyond SudoRoute itself: the certificate, and the state of
    the audit log when it was issued (rewriting history later would break the anchored hash).
  * If the network is unavailable (sandbox, offline demo) the record is kept as "not submitted"
    and can be retried; nothing else in the payment flow depends on it.
"""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

CALENDARS = [c.strip() for c in os.environ.get(
    "TS_OTS_CALENDARS",
    "https://a.pool.opentimestamps.org,https://b.pool.opentimestamps.org,https://a.pool.eternitywall.com"
).split(",") if c.strip()]
def enabled() -> bool:
    return os.environ.get("TS_ANCHOR", "1") != "0"
TIMEOUT = float(os.environ.get("TS_ANCHOR_TIMEOUT", 8))

# DetachedTimestampFile header (OpenTimestamps format, version 1) + SHA-256 file-hash op tag.
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OTS_VERSION = b"\x01"
OP_SHA256 = b"\x08"


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def cert_hash(code: str) -> str:
    return hashlib.sha256("".join((code or "").split()).encode()).hexdigest()


def _post(url: str, data: bytes) -> bytes:
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Accept": "application/vnd.opentimestamps.v1", "User-Agent": "SudoRoute-anchor/1.0",
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


class Anchors:
    def __init__(self, path: str | None = None, post=None):
        self.path, self.post = path, post or _post
        self.lock = threading.Lock()
        self.rows: dict[str, dict] = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.rows = json.load(f)
            except (OSError, ValueError):
                self.rows = {}

    # ---------------------------------------------------------------- write
    def record(self, code: str, audit_head: str | None, audit_entries: int | None, issuer_kid: str) -> dict:
        """Create the anchor record for a certificate (instant) — submission happens separately."""
        h = cert_hash(code)
        rec = {"v": 1, "cert_sha256": h, "audit_head": audit_head, "audit_entries": audit_entries,
               "issuer_kid": issuer_kid, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        digest = hashlib.sha256(canonical(rec)).hexdigest()
        with self.lock:
            self.rows[h] = {"record": rec, "digest": digest, "status": "queued", "calendars": [], "ots_hex": None,
                            "error": None}
            self._save()
        return self.public(h)

    def submit(self, h: str) -> dict:
        """Send the record's digest to OpenTimestamps calendars and build the .ots proof."""
        row = self.rows.get(h)
        if not row:
            return {"status": "unknown"}
        if not enabled():
            row.update(status="disabled", error="Anchoring is turned off (TS_ANCHOR=0).")
            return self.public(h)
        digest = bytes.fromhex(row["digest"])
        ok, errors = [], []
        for cal in CALENDARS:
            try:
                resp = self.post(cal.rstrip("/") + "/digest", digest)
                if not resp or len(resp) > 10_000:
                    raise ValueError("unexpected calendar response")
                ok.append((cal, resp))
            except (urllib.error.URLError, OSError, ValueError) as e:
                errors.append(f"{cal}: {type(e).__name__}")
        with self.lock:
            if ok:
                # One calendar's timestamp is enough for a valid proof; keep the first, list all that accepted.
                cal, resp = ok[0]
                ots = OTS_MAGIC + OTS_VERSION + OP_SHA256 + digest + resp
                row.update(status="submitted", calendars=[c for c, _ in ok], ots_hex=ots.hex(), error=None,
                           submitted=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            else:
                row.update(status="not_submitted", error="; ".join(errors)[:300] or "no calendar reachable")
            self._save()
        return self.public(h)

    def submit_async(self, h: str) -> None:
        threading.Thread(target=self.submit, args=(h,), daemon=True).start()

    # ---------------------------------------------------------------- read
    def public(self, h: str) -> dict:
        row = self.rows.get(h)
        if not row:
            return {"status": "unknown", "cert_sha256": h}
        return {"status": row["status"], "cert_sha256": h, "record": row["record"], "digest": row["digest"],
                "calendars": row["calendars"], "submitted": row.get("submitted"), "error": row["error"],
                "chain": "Bitcoin (via OpenTimestamps)", "has_proof": bool(row["ots_hex"]),
                "how_to_check": "Download the anchor record and the .ots proof, then open https://opentimestamps.org "
                                "and drop both files there. Bitcoin confirmation usually takes a few hours."}

    def ots(self, h: str) -> bytes | None:
        row = self.rows.get(h)
        return bytes.fromhex(row["ots_hex"]) if row and row["ots_hex"] else None

    def record_bytes(self, h: str) -> bytes | None:
        row = self.rows.get(h)
        return canonical(row["record"]) if row else None

    def summary(self) -> dict:
        st = [r["status"] for r in self.rows.values()]
        return {"anchors": len(st), "submitted": st.count("submitted"), "not_submitted": st.count("not_submitted"),
                "queued": st.count("queued"), "chain": "Bitcoin (via OpenTimestamps)", "calendars": CALENDARS,
                "enabled": enabled()}

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.rows, f, indent=1)
        os.replace(tmp, self.path)
