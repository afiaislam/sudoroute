"""Compliance and risk policy engine — the last gate before money moves.

Runs at proposal time (so the student sees the checklist) and AGAIN at execution time
(so nothing that changed in between — balance, limits, rates — slips through).
Each check returns PASS / WARN / FAIL with a plain-language explanation.
"""

from datetime import datetime, timedelta

from .. import config
from ..engines.routes import eligibility
from ..sandbox.reference_data import COUNTRY_RULES, PROVIDERS, SANCTIONED_COUNTRIES, SANCTIONED_NAMES, UNIVERSITIES

REPORTING_THRESHOLD_USD = 10000.0


def _check(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail}


def usd_sent_since(bank, student_id: str, since: datetime) -> float:
    total = 0.0
    for t in bank.transfers.values():
        if t["student_id"] == student_id and datetime.fromisoformat(t["created"]) >= since:
            total += bank.market.to_usd(t["dst_amount"], t["dst_currency"])
    return total


def evaluate(bank, *, student: dict, university_id: str, provider_id: str, invoice: dict,
             invoice_verdict: str, leg_dst_amount: float, leg_src_amount: float,
             payee_account: str, acknowledged_review: bool = False,
             disclosed_installments: int = 1) -> dict:
    uni = UNIVERSITIES[university_id]
    provider = PROVIDERS[provider_id]
    checks = []

    # 1. Verified beneficiary (control-plane / data-plane separation).
    if not uni.get("verified", True) or not uni["beneficiary"].get("account"):
        checks.append(_check("Verified beneficiary", "FAIL",
                             f"{uni['name']} is still waiting for verification — no payee account is on file."))
    elif payee_account == uni["beneficiary"]["account"]:
        checks.append(_check("Verified beneficiary", "PASS",
                             f"Paying {uni['name']}'s registry account at {uni['beneficiary']['bank']}."))
    else:
        checks.append(_check("Verified beneficiary", "FAIL", "Payee account is not the registry account."))

    # 2. Invoice risk.
    if invoice_verdict == "BLOCK":
        checks.append(_check("Invoice authenticity", "FAIL", "Invoice was classified as a likely scam."))
    elif invoice_verdict == "REVIEW":
        checks.append(_check("Invoice authenticity", "PASS" if acknowledged_review else "WARN",
                             "Unusual invoice — student confirmed it with the university." if acknowledged_review
                             else "Unusual invoice — confirm with the university before paying."))
    else:
        checks.append(_check("Invoice authenticity", "PASS", "Invoice matches the verified university record."))

    # 3. No overpayment.
    outstanding = invoice["amount"] - invoice.get("paid", 0.0) - _in_transit(bank, invoice["id"])
    if leg_dst_amount <= outstanding + 0.01:
        checks.append(_check("No overpayment", "PASS",
                             f"{leg_dst_amount:,.2f} {invoice['currency']} ≤ outstanding {outstanding:,.2f}."))
    else:
        checks.append(_check("No overpayment", "FAIL",
                             f"Payment exceeds the outstanding balance ({outstanding:,.2f} {invoice['currency']})."))

    # 4. Channel licensed and allowed by home-country rules.
    amount_usd = bank.market.to_usd(leg_dst_amount, invoice["currency"])
    problems = eligibility(provider, student["home_country"], uni, amount_usd)
    checks.append(_check("Licensed & permitted channel", "FAIL" if problems else "PASS",
                         problems[0] if problems else f"{provider['name']} is licensed and allowed for "
                         f"{COUNTRY_RULES.get(student['home_country'], {}).get('name', student['home_country'])}."))

    # 5. Sanctions screening (sandbox list).
    name_hit = any(n in uni["name"].lower() for n in SANCTIONED_NAMES)
    if uni["country"] in SANCTIONED_COUNTRIES or name_hit:
        checks.append(_check("Sanctions screening", "FAIL", "Beneficiary matched the sanctions list."))
    else:
        checks.append(_check("Sanctions screening", "PASS", "No match on the sandbox sanctions list."))

    # 6. Limits.
    if amount_usd <= config.LIMIT_PER_TXN_USD:
        checks.append(_check("Per-transaction limit", "PASS",
                             f"≈USD {amount_usd:,.0f} ≤ limit USD {config.LIMIT_PER_TXN_USD:,.0f}."))
    else:
        checks.append(_check("Per-transaction limit", "FAIL",
                             f"≈USD {amount_usd:,.0f} exceeds limit USD {config.LIMIT_PER_TXN_USD:,.0f}."))
    day_start = bank.now - timedelta(hours=24)
    day_total = usd_sent_since(bank, student["id"], day_start) + amount_usd
    checks.append(_check("24-hour limit", "PASS" if day_total <= config.LIMIT_DAILY_USD else "FAIL",
                         f"24h total would be ≈USD {day_total:,.0f} (limit USD {config.LIMIT_DAILY_USD:,.0f})."))

    # 7. Annual cap from the country rule pack (e.g. India LRS).
    cap = COUNTRY_RULES.get(student["home_country"], {}).get("annual_cap_usd")
    if cap:
        year_total = usd_sent_since(bank, student["id"], bank.now - timedelta(days=365)) + amount_usd
        checks.append(_check("Annual remittance cap", "PASS" if year_total <= cap else "FAIL",
                             f"12-month total ≈USD {year_total:,.0f} of USD {cap:,.0f}."))

    # 8. Sufficient funds.
    bal = student["balances"].get(student["home_currency"], 0.0)
    checks.append(_check("Sufficient funds", "PASS" if bal + 1e-6 >= leg_src_amount else "FAIL",
                         f"Balance {bal:,.0f} {student['home_currency']}, needed {leg_src_amount:,.0f}."))

    # 9. Structuring (AML): many sub-threshold payments to one payee without disclosure.
    recent = [t for t in bank.transfers.values()
              if t["student_id"] == student["id"] and t["university_id"] == university_id
              and datetime.fromisoformat(t["created"]) >= bank.now - timedelta(days=3)]
    near = [t for t in recent if 0.8 * REPORTING_THRESHOLD_USD <= bank.market.to_usd(t["dst_amount"], t["dst_currency"]) < REPORTING_THRESHOLD_USD]
    if len(near) >= 2 and disclosed_installments <= 1:
        checks.append(_check("Structuring pattern (AML)", "FAIL",
                             "Several just-below-threshold payments to the same payee without a disclosed plan."))
    else:
        note = (f"Disclosed {disclosed_installments}-part installment plan tied to invoice {invoice['id']}."
                if disclosed_installments > 1 else "Single payment tied to an invoice reference.")
        checks.append(_check("Structuring pattern (AML)", "PASS", note))

    # 10. Required documents (informational).
    docs = COUNTRY_RULES.get(student["home_country"], {}).get("documents", [])
    if docs:
        if provider["type"] == "edu_platform":
            checks.append(_check("Documents checklist", "PASS",
                                 "Collected by the education payment platform with your student ID: " + "; ".join(docs)))
        else:
            checks.append(_check("Documents checklist", "WARN",
                                 f"{provider['name']} will ask for: " + "; ".join(docs)))

    failed = [c for c in checks if c["status"] == "FAIL"]
    blocking_warn = [c for c in checks if c["status"] == "WARN" and c["check"] == "Invoice authenticity"]
    return {"allowed": not failed and not blocking_warn, "checks": checks,
            "failed": [c["check"] for c in failed + blocking_warn]}


def _in_transit(bank, invoice_id: str) -> float:
    return sum(t["dst_amount"] for t in bank.transfers.values()
               if t["invoice_id"] == invoice_id and t["status"] == "in_transit")
