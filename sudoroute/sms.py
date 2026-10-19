"""Optional real SMS delivery of one-time codes (off by default).

The sandbox shows every code on the in-app phone. To ALSO send it as a real text message to the number the
student or guardian registered, set (for example on Render, never in the repository):

    SMS_PROVIDER=twilio
    TWILIO_ACCOUNT_SID=AC...
    TWILIO_AUTH_TOKEN=...
    TWILIO_FROM=+1...            # a Twilio number or an approved alphanumeric sender ID

Safety rules:
* Only the account's own registered number receives a code, never a number typed in chat.
* At most SMS_MAX_PER_HOUR messages per number per hour (stops SMS-bombing and cost abuse).
* Sending happens in a background thread; a failed SMS never blocks or changes a payment.
* The audit log records only the masked number and the provider's status, never the code.

A Twilio trial account can only text numbers you have verified in its console. Students who want a free
second factor that needs no SMS at all can link an authenticator app instead (Security → Authenticator app).
"""

import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque

from .util import clean_phone, mask_phone

DIAL = {"BD": "880", "NG": "234", "IN": "91", "PK": "92", "NP": "977", "LK": "94", "VN": "84", "ID": "62",
        "PH": "63", "CN": "86", "KE": "254", "GH": "233", "EG": "20", "MY": "60", "GB": "44", "US": "1"}
MAX_PER_HOUR = int(os.environ.get("SMS_MAX_PER_HOUR", 5))
_sent: dict = defaultdict(deque)
_lock = threading.Lock()


def provider() -> str:
    p = os.environ.get("SMS_PROVIDER", "").lower()
    if p == "twilio" and all(os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")):
        return "twilio"
    return ""


def e164(phone: str | None, country: str | None) -> str | None:
    s = clean_phone(phone)
    if not s:
        return None
    if s.startswith("+"):
        return s
    if s.startswith("00"):
        return "+" + s[2:]
    code = DIAL.get((country or "").upper())
    if not code:
        return None
    return "+" + code + s.lstrip("0")


def _allowed(number: str) -> bool:
    now = time.time()
    with _lock:
        q = _sent[number]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= MAX_PER_HOUR:
            return False
        q.append(now)
        return True


def _twilio(number: str, text: str) -> str:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    body = urllib.parse.urlencode({"To": number, "From": os.environ["TWILIO_FROM"], "Body": text}).encode()
    auth = base64.b64encode(f"{sid}:{os.environ['TWILIO_AUTH_TOKEN']}".encode()).decode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("status", "sent")


def send(phone: str | None, country: str | None, text: str, on_result=None) -> bool:
    """Queue a real SMS if a provider is configured. Returns True if it was queued."""
    p = provider()
    number = e164(phone, country)
    if not p or not number or not _allowed(number):
        if on_result and p and number:
            on_result({"to": mask_phone(number), "status": "rate_limited"})
        return False

    def run():
        try:
            status = _twilio(number, text)
        except Exception as e:  # never let SMS failures affect payments
            status = f"failed: {type(e).__name__}"
        if on_result:
            on_result({"to": mask_phone(number), "status": status, "provider": p})
    threading.Thread(target=run, daemon=True).start()
    return True
