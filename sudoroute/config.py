"""Central configuration. Every value can be overridden with an environment variable."""

import os
import secrets
from datetime import datetime, timezone


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a .env file in the project root (never overrides real env vars)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Server-side secret used to sign payment proposals and derive sandbox OTPs.
# In production this lives in an HSM / KMS and is never in source code.
SECRET_KEY: bytes = (os.environ.get("TS_SECRET") or secrets.token_hex(32)).encode()

# Sandbox clock starts at a fixed date so demos and tests are reproducible.
SIM_START = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)

# A signed quote is valid for this many seconds of *wall-clock* time.
PROPOSAL_TTL_SECONDS = int(os.environ.get("TS_PROPOSAL_TTL", 600))

# Transaction limits (USD equivalent). Agent can never raise these itself.
LIMIT_PER_TXN_USD = _env_float("TS_LIMIT_PER_TXN_USD", 30000)
LIMIT_DAILY_USD = _env_float("TS_LIMIT_DAILY_USD", 40000)

# Scheduled installment legs pause if the rate moved against the student by more than this.
MANDATE_MAX_SLIPPAGE = _env_float("TS_MANDATE_MAX_SLIPPAGE", 0.05)

# Business days kept as a safety buffer between expected arrival and the due date.
ARRIVAL_BUFFER_DAYS = int(os.environ.get("TS_ARRIVAL_BUFFER_DAYS", 2))
# A late tuition payment costs more than the university's late fee: enrolment holds, blocked
# results, visa letters delayed. Route choice prices that harm in (USD) so it prefers on-time channels.
LATE_HARM_USD = float(os.environ.get("TS_LATE_HARM_USD", 400.0))

# Monte Carlo settings for FX budget-at-risk.
MC_PATHS = int(os.environ.get("TS_MC_PATHS", 4000))
MC_SEED = int(os.environ.get("TS_MC_SEED", 7))

# Invoice risk thresholds (0-100).
RISK_BLOCK = 60
RISK_REVIEW = 25

# Where audit and evidence logs are written.
DATA_DIR = os.environ.get("TS_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

# Optional LLM for language understanding and reply writing — never for execution decisions.
# Auto-selects Gemini when GEMINI_API_KEY (or GOOGLE_API_KEY) is set.
LLM_PROVIDER = os.environ.get("TS_LLM_PROVIDER", "").lower()  # "gemini" | "anthropic" | "openai" | ""
if not LLM_PROVIDER and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    LLM_PROVIDER = "gemini"
LLM_MODEL = os.environ.get("TS_LLM_MODEL", "")
# Tried in order until one answers (Gemini 2.5 models were shut down on 16 Oct 2026).
GEMINI_MODELS = [m for m in [LLM_MODEL] if m and LLM_PROVIDER == "gemini"] + [
    "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-flash-latest"]
LLM_TIMEOUT = float(os.environ.get("TS_LLM_TIMEOUT", 15))
