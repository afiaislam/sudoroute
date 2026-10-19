"""Tuition-invoice verification (scam shield).

Tuition-payment scams usually combine a few tell-tale signs: a look-alike sender domain,
"our bank details have changed", extreme urgency, unusual payment methods (crypto, gift
cards, personal accounts) — and, increasingly, hidden text aimed at AI assistants.

Each check adds weighted points; the total (capped at 100) gives a verdict:
SAFE (< 25), REVIEW (25–59) or BLOCK (>= 60). Every point is explained in plain language.
"""

import re

from .. import config
from ..sandbox.reference_data import UNIVERSITIES
from ..security.guardrails import mask_account, scan_untrusted_text

WEIGHTS = {
    "unknown_payee": 40,
    "lookalike_domain": 35,
    "unofficial_domain": 25,
    "bank_mismatch": 45,
    "urgency": 10,
    "threat": 10,
    "unusual_method": 30,
    "amount_anomaly": 15,
    "currency_mismatch": 15,
    "prompt_injection": 30,
    "hidden_content": 10,
    "reference_mismatch": 10,
}

# Pressure, threat and payment-method cues in English, Malay, Bangla and Chinese. Non-Latin
# patterns avoid \b because word boundaries are unreliable for those scripts.
URGENCY = (r"\b(urgent|immediately|within\s+\d+\s*hours?|final\s+notice|last\s+chance|today\s+only|asap"
           r"|segera|serta[- ]?merta|notis\s+terakhir|dalam\s+(masa\s+)?\d+\s*jam)\b"
           r"|জরুরি|অবিলম্বে|এখনই|\d+\s*ঘণ্টার\s*মধ্যে|শেষ\s*সুযোগ|紧急|立即|马上|\d+\s*小时内|最后通知")
THREATS = (r"\b(cancel(l)?ed|cancel(l)?ation|deport|visa\s+(will\s+be\s+)?(revoked|reported|cancel)|legal\s+action|arrest"
           r"|dibatalkan|pembatalan|dihantar\s+pulang|tindakan\s+undang|ditangkap)\b"
           r"|বাতিল\s*(করা\s*)?হবে|ভিসা.{0,20}(বাতিল|রিপোর্ট)|আইনি\s*ব্যবস্থা|গ্রেফতার|取消.{0,6}(学籍|签证|注册)|驱逐|法律行动|逮捕")
UNUSUAL_METHODS = {"usdt", "bitcoin", "btc", "crypto", "gift_card", "giftcard", "western_union_personal",
                   "personal_account", "cash", "paypal_friends"}
UNUSUAL_TEXT = (r"\b(usdt|bitcoin|btc|crypto(currency)?|gift\s*cards?|wallet\s+address|personal\s+account"
                r"|kripto|kad\s+hadiah|akaun\s+peribadi)\b"
                r"|ক্রিপ্টো|বিটকয়েন|গিফট\s*কার্ড|ব্যক্তিগত\s*(অ্যাকাউন্ট|একাউন্ট)|বিকাশ\s*পার্সোনাল"
                r"|加密货币|比特币|泰达币|礼品卡|个人账户|钱包地址")

# A university warning ("we will NEVER ask for crypto") mentions the same words as a scam. A sentence is
# treated as a warning only if it negates the method and contains no instruction to pay that way.
NEGATION = (r"\b(never|not|no|don'?t|do\s+not|will\s+not|won'?t|beware|warning|tidak|jangan|bukan|tak)\b"
            r"|কখনও|কখনো|না\b|নয়|সতর্ক|绝不|不会|不要|从不|切勿|谨防|提醒")
PAY_CUE = (r"\b(only|must|please\s+(pay|send|transfer)|pay\s+(via|by|in|to|with)|send\s+(it|the|your|to)|transfer\s+to"
           r"|instead|hanya|sila\s+(bayar|hantar)|bayar\s+(melalui|ke|dengan))\b"
           r"|শুধু|পাঠান|পাঠাও|পরিশোধ\s*করুন|只|请(支付|汇|转)|改用|转账至|汇至")


def _asks_unusual_method(text: str) -> bool:
    """True if any sentence mentions crypto/gift cards/personal accounts without being a plain warning."""
    for sentence in re.split(r"(?<=[.!?।。！？])\s*|\n+", text):
        if not re.search(UNUSUAL_TEXT, sentence, re.I):
            continue
        warning = re.search(NEGATION, sentence, re.I) and not _active_pay_cue(sentence)
        if not warning:
            return True
    return False


def _active_pay_cue(sentence: str) -> bool:
    """An instruction to pay that is not itself negated within its clause ('never ask you to pay in …')."""
    for m in re.finditer(PAY_CUE, sentence, re.I):
        clause = re.split(r"[,;:，；：—–]|\s-\s|\bbut\b|\btetapi\b|কিন্তু|但是?", sentence[:m.start()])[-1]
        if not re.search(NEGATION, clause, re.I):
            return True
    return False


# Letters from other scripts that look like Latin ones (IDN homograph attacks: "meridiаn" with a Cyrillic а).
CONFUSABLES = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
                             "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ս": "u",
                             "α": "a", "ο": "o", "ρ": "p", "ν": "v", "τ": "t", "ι": "i", "κ": "k",
                             "0": "o", "1": "l"})


def skeleton(domain: str) -> str:
    try:
        if "xn--" in domain:
            domain = domain.encode().decode("idna")
    except UnicodeError:
        pass
    return domain.lower().translate(CONFUSABLES)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).strip()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_university(name: str) -> dict | None:
    n = _norm(name)
    if not n:
        return None
    best, best_score = None, 0.0
    toks = set(n.split())
    for uni in UNIVERSITIES.values():
        candidates = [uni["name"]] + uni.get("aliases", [])
        for c in candidates:
            cn = _norm(c)
            if cn and (cn == n or cn in n):
                score = 1.0
            else:
                ct = set(cn.split())
                score = len(toks & ct) / max(1, len(ct))
            if score > best_score:
                best, best_score = uni, score
    return best if best_score >= 0.6 else None


def domain_of(email: str) -> str:
    return (email or "").split("@")[-1].lower().strip()


def classify_domain(domain: str, uni: dict | None) -> str:
    """Return 'official', 'lookalike' or 'unofficial'."""
    if not uni or not domain:
        return "unofficial"
    for official in uni["official_domains"]:
        if domain == official or domain.endswith("." + official):
            return "official"
    if not domain.isascii() or "xn--" in domain:
        return "lookalike"  # internationalised look-alike of a Latin university domain
    for official in uni["official_domains"]:
        if skeleton(domain) == official or skeleton(domain).endswith("." + official):
            return "lookalike"
    for official in uni["official_domains"]:
        brand = official.split(".")[0]
        sld = domain.split(".")[0]
        if brand in domain or levenshtein(sld, brand) <= 2 or levenshtein(domain, official) <= 3:
            return "lookalike"
    return "unofficial"


def verify_invoice(invoice: dict, student: dict | None = None) -> dict:
    reasons: list[dict] = []

    def add(code: str, message: str):
        reasons.append({"code": code, "points": WEIGHTS[code], "message": message})

    uni = match_university(invoice.get("university_name", ""))
    if uni is None:
        add("unknown_payee", "The payee is not in the verified university registry.")

    domain = domain_of(invoice.get("sender_email", ""))
    dclass = classify_domain(domain, uni)
    if domain and dclass == "lookalike":
        add("lookalike_domain", f"Sender domain '{domain}' imitates the official domain "
                                f"'{uni['official_domains'][0]}'.")
    elif domain and dclass == "unofficial" and uni is not None:
        add("unofficial_domain", f"Sender domain '{domain}' is not an official domain of {uni['name']}.")

    acct = (invoice.get("bank_account") or "").strip()
    if uni and acct and acct != uni["beneficiary"]["account"]:
        add("bank_mismatch", f"Bank account on the invoice ({mask_account(acct)}) does not match the "
                             f"verified account of {uni['name']} ({mask_account(uni['beneficiary']['account'])}).")

    text = " ".join([invoice.get("subject", ""), invoice.get("text", "")])
    if re.search(URGENCY, text, re.I):
        add("urgency", "Uses pressure language (e.g. 'urgent', 'within 24 hours', 'final notice').")
    if re.search(THREATS, text, re.I):
        add("threat", "Threatens enrolment cancellation, visa problems or legal action.")

    methods = {m.lower() for m in invoice.get("payment_methods", [])}
    if methods & UNUSUAL_METHODS or _asks_unusual_method(text):
        add("unusual_method", "Asks for crypto, gift cards or a personal account — universities do not do this.")

    if uni:
        if invoice.get("currency") and invoice["currency"] != uni["currency"]:
            add("currency_mismatch", f"Invoice currency {invoice['currency']} differs from {uni['name']}'s "
                                     f"billing currency {uni['currency']}.")
        lo, hi = uni["fee_range"]
        amt = float(invoice.get("amount") or 0)
        if amt and not (lo * 0.25 <= amt <= hi * 1.1):
            add("amount_anomaly", f"Amount {amt:,.0f} is outside the usual range for this university "
                                  f"({lo:,.0f}–{hi:,.0f} {uni['currency']} per semester).")

    if student and invoice.get("student_ref") and invoice["student_ref"] != student.get("student_ref"):
        add("reference_mismatch", "Student reference on the invoice does not match your student ID.")

    scan = scan_untrusted_text(invoice.get("text", ""))
    if scan["suspicious"]:
        add("prompt_injection", "Contains hidden instructions aimed at AI assistants: "
                                + "; ".join(f["detail"] for f in scan["findings"] if f["type"] == "injection") + ".")
    if scan["has_hidden_content"]:
        add("hidden_content", "Contains hidden content (" +
            ", ".join(f["detail"] for f in scan["findings"] if f["type"] == "hidden") + ").")

    score = min(100, sum(r["points"] for r in reasons))
    verdict = "BLOCK" if score >= config.RISK_BLOCK else "REVIEW" if score >= config.RISK_REVIEW else "SAFE"
    advice = {
        "SAFE": "This invoice matches the verified university record. SudoRoute will still pay only to the "
                "registry account, never to details typed on the invoice.",
        "REVIEW": "Some details are unusual. Confirm with the university through its official website or phone "
                  "number before paying.",
        "BLOCK": "Do not pay. This has the hallmarks of a tuition scam. Report it to your university's finance "
                 "office using contact details from the official website — never the ones in this message.",
    }[verdict]
    return {
        "invoice_id": invoice.get("id"), "score": score, "verdict": verdict, "reasons": reasons,
        "university_id": uni["id"] if uni else None, "university_name": uni["name"] if uni else None,
        "domain_class": dclass if domain else None, "injection_scan": scan, "advice": advice,
    }


def parse_pasted_invoice(text: str) -> dict:
    """Extract invoice-like fields from free text pasted by the user (email body etc.)."""
    email = re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", text)
    amt = re.search(r"\b(MYR|GBP|USD|AUD|CAD|EUR|RM|£|\$)\s?([\d,]+(?:\.\d+)?)", text, re.I)
    acct = re.search(r"\b([A-Z]{2}-[A-Z0-9]{2,5}-[0-9A-Z-]{6,})\b", text)
    uni_name = ""
    for uni in UNIVERSITIES.values():
        for c in [uni["name"]] + uni["aliases"]:
            if c.lower() in text.lower():
                uni_name = uni["name"]
                break
        if uni_name:
            break
    ccy = None
    if amt:
        sym = amt.group(1).upper()
        ccy = {"RM": "MYR", "£": "GBP", "$": "USD"}.get(sym, sym)
    methods = []
    if _asks_unusual_method(text):
        methods.append("crypto")
    return {
        "id": "PASTED", "university_name": uni_name or "unknown",
        "sender_email": email.group(0) if email else "",
        "amount": float(amt.group(2).replace(",", "")) if amt else 0.0,
        "currency": ccy, "bank_account": acct.group(1) if acct else "",
        "payment_methods": methods, "subject": "", "text": text,
    }
