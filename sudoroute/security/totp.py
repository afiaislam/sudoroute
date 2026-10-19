"""Authenticator-app one-time codes (TOTP, RFC 6238 on top of HOTP, RFC 4226).

Why: in the sandbox a payment code arrives on a simulated phone. A student can instead link
an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password, Authy...).
Then payment approval needs a code that only exists on the student's own device, so neither
the server's SMS channel, the AI agent nor someone who got into the account can produce it.

Standard library only; checked against the official RFC 6238 Appendix B test vectors.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

STEP = 30
DIGITS = 6
WINDOW = 1  # accept one 30-second step of clock drift either side


def new_secret() -> str:
    """160-bit random secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS, algo=hashlib.sha1) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), algo).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{code:0{digits}d}"


def code_at(secret_b32: str, t: float | None = None) -> str:
    return hotp(_key(secret_b32), int((time.time() if t is None else t) // STEP))


def verify(secret_b32: str, code: str, last_step: int | None = None, t: float | None = None) -> int | None:
    """Return the matched time step, or None.

    A step at or before `last_step` is refused, so a code can be used only once (replay protection).
    """
    code = (code or "").strip().replace(" ", "")
    if not (len(code) == DIGITS and code.isdigit()):
        return None
    now = int((time.time() if t is None else t) // STEP)
    key = _key(secret_b32)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(hotp(key, step), code):
            return step
    return None


def provisioning_uri(secret_b32: str, account: str, issuer: str = "SudoRoute") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}")
    q = urllib.parse.urlencode({"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1",
                                "digits": DIGITS, "period": STEP})
    return f"otpauth://totp/{label}?{q}"
