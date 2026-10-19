"""Verifiable payment certificates (credit building for students with no local credit history).

After a tuition payment settles, the student can ask SudoRoute for a certificate that proves
it: who paid, which institution received it, how much, and whether it arrived before the due
date. The certificate is a compact string

    SR1.<base64url(JSON claims)>.<base64url(Ed25519 signature)>

signed with SudoRoute's issuer key. Anyone can check it with the PUBLIC key alone — on the
/verify page, with `python scripts/verify_certificate.py`, or with any Ed25519 library. Changing
a single character (an amount, a date, the name) makes verification fail.

Claims carry an `audit_anchor` (sequence number and hash of the audit-log head at issue time),
which ties the certificate to SudoRoute's tamper-evident log.
"""

import base64
import hashlib
import json
import os
import secrets

from . import ed25519

PREFIX = "SR1"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def key_id(public: bytes) -> str:
    return hashlib.sha256(public).hexdigest()[:16]


class Issuer:
    def __init__(self, key_path: str | None = None, seed: bytes | None = None):
        if seed is None and key_path and os.path.exists(key_path):
            with open(key_path) as f:
                seed = bytes.fromhex(f.read().strip())
        if seed is None:
            seed = secrets.token_bytes(32)
            if key_path:
                os.makedirs(os.path.dirname(key_path), exist_ok=True)
                with open(key_path, "w") as f:
                    f.write(seed.hex())
                try:
                    os.chmod(key_path, 0o600)
                except OSError:
                    pass
        self._seed = seed
        self.public = ed25519.public_key(seed)
        self.kid = key_id(self.public)

    def info(self) -> dict:
        return {"alg": "Ed25519", "kid": self.kid, "public_key_hex": self.public.hex(),
                "format": "SR1.<base64url(claims JSON)>.<base64url(signature)>"}

    def issue(self, claims: dict) -> str:
        body = canonical({"v": 1, "iss": "SudoRoute", "kid": self.kid, **claims})
        return f"{PREFIX}.{b64u(body)}.{b64u(ed25519.sign(self._seed, body))}"

    def verify(self, code: str) -> dict:
        return verify(code, {self.kid: self.public})


def verify(code: str, keys: dict[str, bytes]) -> dict:
    """Check a certificate string against known public keys. Never raises."""
    try:
        code = "".join((code or "").split())
        prefix, body_b64, sig_b64 = code.split(".")
        if prefix != PREFIX:
            return {"valid": False, "reason": "Not a SudoRoute certificate."}
        body, sig = unb64u(body_b64), unb64u(sig_b64)
        claims = json.loads(body)
        pub = keys.get(claims.get("kid"))
        if pub is None:
            return {"valid": False, "reason": "Signed by an unknown key.", "claims": claims}
        if not ed25519.verify(pub, body, sig):
            return {"valid": False, "reason": "Signature does not match — the certificate was changed or forged.",
                    "claims": claims}
        return {"valid": True, "claims": claims}
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return {"valid": False, "reason": "The text is not a complete certificate. Copy all of it."}
