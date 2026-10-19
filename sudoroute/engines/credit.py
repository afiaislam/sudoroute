"""Credit-building planner for students who arrive with no local credit history.

The readiness score (0–100) is an illustrative, transparent heuristic — not a credit
score. It tells the student which concrete steps raise their chance of getting a first
credit line, a rental contract or a phone contract in their study country.
"""

PLAYBOOKS = {
    "UK": {
        "local_bank_account": "Open a UK current account (most banks accept a BRP/eVisa + university letter).",
        "address_proof": "Register on the electoral roll if eligible, or keep a council-tax/utility bill in your name.",
        "postpaid_phone": "Move to a low-cost pay-monthly SIM contract — it reports to UK credit agencies.",
        "rent_reporting": "Ask your landlord or a rent-reporting service to report on-time rent to credit agencies.",
        "credit_builder_product": "Get a credit-builder card with a low limit; spend < 25% and pay in full by direct debit.",
    },
    "US": {
        "local_bank_account": "Open a US checking account with your I-20, passport and university address.",
        "address_proof": "Put one utility or internet bill in your name.",
        "postpaid_phone": "A postpaid phone plan helps, but only some carriers report to credit bureaus.",
        "rent_reporting": "Use a rent-reporting service so on-time rent appears on your credit file.",
        "credit_builder_product": "Apply for a secured card (deposit = limit); some issuers accept students without an SSN.",
    },
    "MY": {
        "local_bank_account": "Open a Malaysian savings account with your student pass and offer letter.",
        "address_proof": "Keep your tenancy agreement and one utility bill in your name.",
        "postpaid_phone": "Switch to a postpaid mobile plan in your name — payment history is visible to lenders.",
        "rent_reporting": "Pay rent by bank transfer each month so you have a documented payment record.",
        "credit_builder_product": "After 6–12 months of salary/allowance history, apply for an entry-level card or BNPL with a small limit.",
    },
    "AU": {
        "local_bank_account": "Open an Australian everyday account (most banks allow this before arrival).",
        "address_proof": "Keep your lease and one utility bill in your name.",
        "postpaid_phone": "A postpaid phone plan creates repayment history.",
        "rent_reporting": "Pay rent through a tracked platform to build a rental ledger.",
        "credit_builder_product": "Consider a low-limit card after 3–6 months of account history.",
    },
}

WEIGHTS = {"local_bank_account": 20, "postpaid_phone": 15, "address_proof": 10,
           "rent_reporting": 15, "credit_builder_product": 20}
ORDER = ["local_bank_account", "address_proof", "postpaid_phone", "rent_reporting", "credit_builder_product"]


def credit_plan(student: dict) -> dict:
    country = student["study_country"]
    book = PLAYBOOKS.get(country, PLAYBOOKS["UK"])
    prof = student.get("credit_profile", {})
    score = sum(w for k, w in WEIGHTS.items() if prof.get(k))
    streak = int(prof.get("on_time_months", 0))
    score += round(min(12, streak) / 12 * 20)
    done, todo = [], []
    for k in ORDER:
        item = {"step": k.replace("_", " ").capitalize(), "action": book[k], "points": WEIGHTS[k]}
        (done if prof.get(k) else todo).append(item)
    months_to_70 = None
    if score < 70:
        gap = 70 - score
        quick = sum(t["points"] for t in todo[:2])
        remaining = max(0, gap - quick)
        months_to_70 = max(1, round(remaining / (20 / 12))) if remaining else 1
    return {
        "study_country": country, "readiness_score": score, "on_time_streak_months": streak,
        "done": done, "next_steps": todo[:3], "months_to_reach_70": months_to_70,
        "habits": [
            "Pay every bill in full and on time — set up automatic payments the day you get paid.",
            "Keep card usage below 25% of the limit.",
            "Do not apply for many credit products at once; each application can lower your score.",
        ],
        "disclaimer": "Readiness score is an educational heuristic, not an official credit score.",
    }
