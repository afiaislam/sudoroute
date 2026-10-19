"""Small shared helpers: sample identity used by sandbox fixtures, and phone handling."""

import re

# The sandbox fixtures (scripted evidence runs and tests) use this single sample identity everywhere.
SAMPLE_NAME = "Afia Islam"
SAMPLE_PHONE = "01906032900"


def clean_phone(raw) -> str | None:
    """Return a normalised phone number ('+' optional, digits only) or None if it is not a plausible number."""
    s = re.sub(r"[ \-()]", "", str(raw or "").strip())
    if not re.fullmatch(r"\+?\d{7,15}", s):
        return None
    return s


def mask_phone(raw) -> str:
    """Keep the first three and last two digits: 01906032900 -> 019••••••00. The full number is never stored."""
    s = clean_phone(raw)
    if not s:
        return ""
    plus, d = ("+" if s.startswith("+") else ""), s.lstrip("+")
    return f"{plus}{d[:3]}{'•' * max(len(d) - 5, 0)}{d[-2:]}"
