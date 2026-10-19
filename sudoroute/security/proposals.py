"""Signed payment proposals, step-up OTP and idempotency.

A proposal is the ONLY object that can lead to money moving. It binds every
security-relevant field (student, invoice, payee account from the registry, amounts,
currencies, rate, channel, installment plan, expiry) into a canonical JSON payload that is
signed with HMAC-SHA256 using a server-side key.

At execution time the server recomputes the signature over the stored proposal *and*
compares it with the token the client sends back, so neither the client, the language model
nor a malicious document can change the payee or amount between "approve" and "pay".
"""

import hashlib
import hmac
import json
import time

from .. import config


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign(payload: dict, key: bytes | None = None) -> str:
    return hmac.new(key or config.SECRET_KEY, canonical(payload), hashlib.sha256).hexdigest()


def sandbox_otp(proposal_id: str, key: bytes | None = None) -> str:
    """Deterministic 6-digit code for the sandbox 'SMS inbox'.

    Production replaces this with SMS/TOTP/passkey step-up authentication delivered on a
    separate channel the agent cannot read.
    """
    digest = hmac.new(key or config.SECRET_KEY, f"otp:{proposal_id}".encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


class ProposalError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ProposalStore:
    MAX_OTP_ATTEMPTS = 3

    def __init__(self, key: bytes | None = None, ttl_seconds: int | None = None):
        self.key = key or config.SECRET_KEY
        self.ttl = ttl_seconds or config.PROPOSAL_TTL_SECONDS
        self.proposals: dict[str, dict] = {}
        self.executed: set[str] = set()
        self.attempts: dict[str, int] = {}

    def create(self, payload: dict, ttl: int | None = None, status: str = "awaiting_confirmation") -> dict:
        payload = dict(payload)
        payload["expires_at"] = int(time.time()) + (ttl or self.ttl)
        token = sign(payload, self.key)
        self.proposals[payload["proposal_id"]] = {"payload": payload, "token": token, "status": status,
                                                  "guardian_approval": None}
        return {"payload": payload, "token": token}

    def verify_secondary_otp(self, proposal_id: str, purpose: str, otp: str) -> None:
        """Check a second party's code (e.g. a guardian) with its own lockout counter."""
        key = purpose + proposal_id
        if self.attempts.get(key, 0) >= self.MAX_OTP_ATTEMPTS:
            raise ProposalError("Too many wrong codes — approval locked.", "locked")
        if not hmac.compare_digest(sandbox_otp(key, self.key), (otp or "").strip()):
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if self.attempts[key] >= self.MAX_OTP_ATTEMPTS:
                self.proposals[proposal_id]["status"] = "locked"
                raise ProposalError("Too many wrong codes — approval locked.", "locked")
            raise ProposalError("Wrong one-time code.", "bad_otp")

    def get(self, proposal_id: str) -> dict:
        if proposal_id not in self.proposals:
            raise ProposalError("Unknown proposal.", "unknown_proposal")
        return self.proposals[proposal_id]

    def validate(self, proposal_id: str, token: str, otp: str, now: float | None = None) -> dict:
        """Run every check required before execution. Returns the trusted payload."""
        rec = self.get(proposal_id)
        payload = rec["payload"]
        if proposal_id in self.executed or rec["status"] in ("executed", "executing"):
            raise ProposalError("This proposal was already executed (idempotency protection).", "replay")
        if rec["status"] in ("cancelled", "locked", "declined", "expired"):
            raise ProposalError(f"This proposal is {rec['status']}.", rec["status"])
        expected = sign(payload, self.key)
        if not hmac.compare_digest(expected, rec["token"]) or not hmac.compare_digest(expected, token or ""):
            raise ProposalError("Signature check failed — the proposal was modified.", "bad_signature")
        if (now or time.time()) > payload["expires_at"]:
            rec["status"] = "expired"
            raise ProposalError("The quote expired. Ask SudoRoute for a fresh quote.", "expired")
        if not hmac.compare_digest(sandbox_otp(proposal_id, self.key), (otp or "").strip()):
            self.attempts[proposal_id] = self.attempts.get(proposal_id, 0) + 1
            if self.attempts[proposal_id] >= self.MAX_OTP_ATTEMPTS:
                rec["status"] = "locked"
                raise ProposalError("Too many wrong codes — proposal locked.", "locked")
            raise ProposalError("Wrong one-time code.", "bad_otp")
        return payload

    def mark(self, proposal_id: str, status: str) -> None:
        self.proposals[proposal_id]["status"] = status
        if status == "executed":
            self.executed.add(proposal_id)
