"""University registry: verified payees, plus universities that students typed in themselves.

Students may type ANY university at sign-up. If it is already in the verified registry it is
used as is. Otherwise it is added as PENDING VERIFICATION: the agent can analyse costs, but it
will not prepare or execute a payment until the university's official bank account has been
confirmed out-of-band (production: SudoRoute operations call the bursary on the number published
on the university's own website and receive a signed bank letter; sandbox: a clearly labelled
"simulate verification" button). This keeps the core rule intact — payee bank details never
come from the student, an invoice or an e-mail.
"""

import json
import os
import re
import threading

from .reference_data import STUDY_COUNTRIES, UNIVERSITIES

_lock = threading.Lock()
_path: str | None = None
BUILTIN = set(UNIVERSITIES)


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())).strip()


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[<>{}\[\]\\|@#$%^*=+]", "", str(name or ""))).strip()[:120]


def clean_domain(website: str) -> str:
    w = str(website or "").strip().lower()
    w = re.sub(r"^[a-z]+://", "", w).split("/")[0].split("?")[0]
    w = w[4:] if w.startswith("www.") else w
    return w if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", w) and len(w) <= 80 else ""


def find_exact(name: str) -> dict | None:
    """Exact (normalised) match on a registry name or alias — never a fuzzy guess at sign-up."""
    n = norm(name)
    if not n:
        return None
    for u in UNIVERSITIES.values():
        if n == norm(u["name"]) or n in {norm(a) for a in u.get("aliases", [])}:
            return u
    return None


def load(path: str | None) -> None:
    global _path
    _path = path
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for u in json.load(f):
                UNIVERSITIES.setdefault(u["id"], u)


def _save() -> None:
    if not _path:
        return
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    rows = [u for k, u in UNIVERSITIES.items() if k not in BUILTIN]
    tmp = _path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path)


def request(name: str, country: str, website: str = "", city: str = "", requested_by: str = "") -> dict:
    """Add a student-typed university as PENDING VERIFICATION (or return the existing entry)."""
    name = clean_name(name)
    if len(name) < 3:
        raise ValueError("Type the full name of your university.")
    if country not in STUDY_COUNTRIES:
        raise ValueError("Choose the country where you study.")
    with _lock:
        existing = find_exact(name)
        if existing:
            return existing
        n = 1 + sum(1 for k in UNIVERSITIES if k not in BUILTIN)
        uid = f"U{n:04d}"
        while uid in UNIVERSITIES:
            n += 1
            uid = f"U{n:04d}"
        c = STUDY_COUNTRIES[country]
        domain = clean_domain(website)
        u = {"id": uid, "name": name, "aliases": [], "country": country,
             "city": clean_name(city)[:60] or c["name"], "currency": c["currency"],
             "official_domains": [domain] if domain else [],
             "beneficiary": {"bank": None, "account": None, "swift": None},
             "fee_range": list(c["fee_range"]), "allows_installments": True, "max_installments": 2,
             "late_fee": 0, "edu_partners": [], "verified": False, "requested_by": requested_by}
        UNIVERSITIES[uid] = u
        _save()
        return u


def verify_sandbox(uid: str) -> dict:
    """SANDBOX ONLY: mark a pending university as verified and give it a sandbox payee account."""
    with _lock:
        u = UNIVERSITIES[uid]
        if u.get("verified", True):
            return u
        digits = "".join(str(ord(ch) % 10) for ch in uid + u["name"])[:12].ljust(12, "0")
        u["beneficiary"] = {"bank": f"Sandbox bank ({STUDY_COUNTRIES[u['country']]['name']})",
                            "account": f"{u['country']}-SBX-{digits[:4]}-{digits[4:8]}-{digits[8:12]}",
                            "swift": f"SBX{u['country']}XXX"}
        if not u["official_domains"]:
            u["official_domains"] = [re.sub(r"[^a-z0-9]+", "-", norm(u["name"])).strip("-")[:40] + ".edu.sandbox"]
        u["edu_partners"] = ["edupay"]
        u["verified"] = True
        _save()
        return u


def public(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "city": u["city"], "country": u["country"],
            "currency": u["currency"], "verified": u.get("verified", True)}
