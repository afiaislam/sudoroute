"""Intent understanding.

Default: a deterministic rule-based parser (English + Bangla keywords) so the system runs
offline and behaves identically for judges. Optional: an LLM can be enabled for free-form
language via `llm.classify`, but its output is restricted to the same intent schema and is
never allowed to call tools or move money directly.
"""

import re

INTENTS = ["help", "balances", "list_invoices", "verify_invoice", "pay_tuition", "smart_pay", "compare_routes",
           "fx_risk", "budget", "credit", "audit", "status", "general", "prohibited"]

PROHIBITED_RULES = [
    (r"(raise|increase|remove|change|bypass)\s+(my\s+|the\s+)?(daily\s+|transaction\s+)?limits?", "raise_limits"),
    (r"(give|grant)\s+(yourself|you)\b.*(permission|access|execute)|change\s+(the\s+)?permission", "raise_limits"),
    (r"(skip|without|no|disable|turn\s+off)\s+(the\s+)?(otp|one[- ]time\s+code|confirmation|2fa|verification)", "execute_without_confirmation"),
    (r"(delete|clear|edit|disable)\s+(the\s+)?(audit|logs?)", "disable_audit"),
    (r"\b(usdt|bitcoin|btc|crypto|ethereum|eth)\b|ক্রিপ্টো|বিটকয়েন|加密货币|比特币", "convert_to_crypto"),
    (r"\b(hundi|hawala|informal\s+channel|black\s+market)\b|হুন্ডি|地下钱庄", "use_unlicensed_channel"),
    (r"(ignore|forget)\s+(all\s+|your\s+)?(previous|prior|earlier)?\s*(instructions|rules)|developer\s+mode|jailbreak"
     r"|(আগের|পূর্বের)\s*(সব\s*)?নির্দেশ\S*\s*(উপেক্ষা|ভুলে)|忽略.{0,6}(指令|规则)", "follow_document_instructions"),
    (r"(লিমিট|সীমা)\s*(বাড়াও|বাড়িয়ে|তুলে)|提高.{0,4}(限额|额度)", "raise_limits"),
    (r"(ওটিপি|কোড)\s*(ছাড়া|ছাড়াই)|不(需要|用).{0,4}(验证码|确认)", "execute_without_confirmation"),
    (r"(pay|send|transfer)\b.*\bto\s+(this\s+|the\s+|new\s+)?account\b|\baccount\s*(no\.?|number)?\s*[:#]?\s*[A-Z]{2}-[A-Z0-9]{2,5}-", "use_invoice_bank_details"),
]

KEYWORDS = [
    ("smart_pay", r"\b(best|good|better|target)\s+(exchange\s+)?rate\b|\brate\s+(is\s+|gets\s+)?(good|better|improves)|smart[- ]?(pay|timing)"
                  r"|\blimit\s+order|ভালো\s*রেট|রেট\s*ভালো|汇率.{0,4}(好|合适|最佳)"),
    ("verify_invoice", r"\b(verify|legit|real|fake|scam|phish|genuine|authentic|suspicious|safe\s+to\s+pay)\b|ভুয়া|আসল|যাচাই|真的|假的|诈骗|骗局|核实"),
    ("status", r"\b(status|track|where\s+is\s+my|arrived|settled|mandate)\b"),
    ("compare_routes", r"\b(compare|cheapest|routes?|providers?|channels?|remit(tance)?|send\s+money|transfer\s+options|fees?\s+compar)\b|তুলনা|সবচেয়ে\s*কম\s*খরচ|最便宜|比较|汇款方式"),
    ("fx_risk", r"\b(fx|exchange\s+rate|currency\s+risk|rate\s+risk|when\s+should\s+i\s+pay|budget[- ]at[- ]risk|wait)\b|রেট"),
    ("pay_tuition", r"\b(pay|settle|installments?|instalments?|split)\b|পরিশোধ|পেমেন্ট|জমা\s*দ|কিস্তি|付学费|付款|支付|缴费|交学费|分期|bayar"),
    ("budget", r"\b(budget|spend(ing)?|expenses?|runway|afford|savings)\b|বাজেট|খরচ|预算|开销|花费"),
    ("credit", r"\b(credit|score|credit\s+history|credit\s+card)\b|ক্রেডিট"),
    ("audit", r"\b(audit|logs?|what\s+did\s+you\s+do|activity)\b"),
    ("balances", r"\b(balances?|how\s+much\s+(money|do\s+i\s+have)|wallets?|my\s+accounts?)\b|ব্যালেন্স|余额|钱包"),
    ("list_invoices", r"\b(invoices?|bills?|what\s+do\s+i\s+owe|due)\b|বিল|ইনভয়েস"),
    ("help", r"\b(help|hi|hello|hey|what\s+can\s+you\s+do|start)\b|সাহায্য|হ্যালো"),
]


def looks_like_pasted_document(text: str) -> bool:
    return len(text) > 160 and bool(re.search(r"@|account|invoice|tuition|payment", text, re.I))


def parse(message: str) -> dict:
    text = message.strip()
    low = text.lower()
    inv = re.search(r"\bINV-[A-Z0-9-]+\b", text, re.I)
    slots = {
        "invoice_id": inv.group(0).upper() if inv else None,
        "installments": bool(re.search(r"install?ments?|split|in\s+\d\s+parts|tranche|কিস্তি", low)),
        "pay_now": bool(re.search(r"\b(now|today|immediately|full)\b", low)),
        "smart": False,
        "pasted": looks_like_pasted_document(text),
    }
    # A pasted document is analysed as untrusted data — never as instructions.
    if slots["pasted"]:
        return {"intent": "verify_invoice", "slots": slots, "source": "rules"}
    for pat, action in PROHIBITED_RULES:
        if re.search(pat, text, re.I):
            slots["prohibited_action"] = action
            return {"intent": "prohibited", "slots": slots, "source": "rules"}
    low = re.sub(r"\binv-[a-z0-9-]+\b", " ", low)  # invoice IDs must not trigger keywords
    # "Check it, and if it's fine, pay it" → the payment flow, which always verifies the invoice first.
    if re.search(r"\b(if|then)\b[^.?!]*\bpay\s+(it|for\s+it|my|the|this)\b", low) and not re.search(r"\b(best|good|better)\s+rate\b", low):
        return {"intent": "pay_tuition", "slots": slots, "source": "rules"}
    for intent, pat in KEYWORDS:
        if re.search(pat, low, re.I):
            if intent == "pay_tuition" and re.search(r"\b(compare|cheapest|routes?)\b", low):
                intent = "compare_routes"
            return {"intent": intent, "slots": slots, "source": "rules"}
    if re.search(r"tuition|fees?|টিউশন|ফি", low):
        return {"intent": "pay_tuition" if re.search(r"pay|দাও|দিতে", low) else "list_invoices",
                "slots": slots, "source": "rules"}
    if "?" in text or len(text.split()) >= 4:
        return {"intent": "general", "slots": slots, "source": "rules"}
    return {"intent": "help", "slots": slots, "source": "rules"}
