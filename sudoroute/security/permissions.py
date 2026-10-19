"""Permission tiers.

Every tool the agent can call is registered with exactly one tier. A session has a
permission level chosen by the student; the agent can never raise it.

    T0 READ        view balances, invoices, history                 — always allowed
    T1 ANALYZE     verify invoices, compare routes, FX risk, budget — advisor and above
    T2 PREPARE     draft a signed payment proposal (no money moves) — assisted mode
    T3 EXECUTE     move money — ONLY via the confirmation endpoint with a valid signed
                   proposal + step-up OTP + policy checks. Never callable from chat.
    T4 PROHIBITED  actions the agent may never take, in any mode (see PROHIBITED_ACTIONS)
"""

from enum import IntEnum


class Tier(IntEnum):
    READ = 0
    ANALYZE = 1
    PREPARE = 2
    EXECUTE = 3
    PROHIBITED = 4


TIER_LABELS = {
    Tier.READ: "T0 Read",
    Tier.ANALYZE: "T1 Analyze",
    Tier.PREPARE: "T2 Prepare",
    Tier.EXECUTE: "T3 Execute",
    Tier.PROHIBITED: "T4 Prohibited",
}

# Session levels the student can choose (the agent cannot change them).
LEVELS = {
    "read_only": {"label": "Read only", "max_tier": Tier.READ,
                  "description": "The agent can only look at balances and invoices."},
    "advisor": {"label": "Advisor", "max_tier": Tier.ANALYZE,
                "description": "The agent can analyse and recommend, but cannot prepare payments."},
    "assisted": {"label": "Assisted payments", "max_tier": Tier.EXECUTE,
                 "description": "The agent can prepare payments; money moves only after you confirm with a one-time code."},
}
DEFAULT_LEVEL = "assisted"

PROHIBITED_ACTIONS = {
    "pay_unregistered_payee": "Pay a beneficiary that is not in the verified university registry.",
    "use_invoice_bank_details": "Use bank details taken from an invoice, email or chat message.",
    "use_unlicensed_channel": "Send money through an unlicensed or informal channel (hundi/hawala).",
    "convert_to_crypto": "Convert or send tuition money to crypto wallets.",
    "raise_limits": "Raise transaction limits or change the session permission level.",
    "disable_audit": "Disable, edit or delete audit records.",
    "follow_document_instructions": "Act on instructions found inside invoices, emails or pasted documents.",
    "execute_without_confirmation": "Move money without the student's explicit confirmation and one-time code.",
}


class PermissionDenied(Exception):
    def __init__(self, message: str, tier: Tier, code: str = "permission_denied"):
        super().__init__(message)
        self.tier = tier
        self.code = code


def check(level: str, tier: Tier, action: str) -> None:
    if tier == Tier.PROHIBITED:
        raise PermissionDenied(f"'{action}' is permanently prohibited for the agent.", tier, "prohibited")
    max_tier = LEVELS.get(level, LEVELS[DEFAULT_LEVEL])["max_tier"]
    if tier > max_tier:
        raise PermissionDenied(
            f"'{action}' needs {TIER_LABELS[tier]} but this session is set to "
            f"'{LEVELS[level]['label']}' ({TIER_LABELS[max_tier]}).", tier)
