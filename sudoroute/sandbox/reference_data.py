"""Static sandbox reference data.

All universities, banks, accounts, providers and people here are FICTIONAL.
Country rule packs are simplified illustrations of real-world requirements and must be
validated with the relevant regulator / authorised bank before any production use.
"""

# ---------------------------------------------------------------- currencies
# Units of currency per 1 USD. REFERENCE snapshot of real market rates published by
# open.er-api.com on 17 Oct 2026 00:02 UTC (rounded). When the server can reach the live feed
# it replaces these at start-up (see sudoroute/sandbox/fx_live.py) and labels rates LIVE.
REFERENCE_AS_OF = "2026-10-17T00:02:32Z"
REFERENCE_SOURCE = "open.er-api.com (ExchangeRate-API open access), snapshot"
UNITS_PER_USD = {
    "USD": 1.0, "BDT": 123.04, "INR": 95.11, "NGN": 1332.43, "PKR": 277.0, "NPR": 152.18,
    "VND": 25868.9, "MYR": 4.0815, "GBP": 0.7508, "EUR": 0.8895, "AUD": 1.4396, "CAD": 1.4147,
    # added from the 18 Oct 2026 00:02 UTC snapshot of the same feed
    "JPY": 158.0, "CNY": 6.7029, "SGD": 1.2799, "NZD": 1.7684, "KRW": 1334.77, "CHF": 0.8246, "SEK": 9.9113,
}
# Annualised volatility of each currency against USD.
ANNUAL_VOL = {
    "USD": 0.0, "BDT": 0.06, "INR": 0.05, "NGN": 0.24, "PKR": 0.09, "NPR": 0.05,
    "VND": 0.04, "MYR": 0.07, "GBP": 0.08, "EUR": 0.08, "AUD": 0.10, "CAD": 0.06,
    "JPY": 0.10, "CNY": 0.04, "SGD": 0.05, "NZD": 0.10, "KRW": 0.09, "CHF": 0.07, "SEK": 0.09,
}
# Annual drift of units-per-USD (positive = the currency tends to weaken vs USD).
ANNUAL_DRIFT = {
    "USD": 0.0, "BDT": 0.05, "INR": 0.03, "NGN": 0.18, "PKR": 0.06, "NPR": 0.03,
    "VND": 0.02, "MYR": 0.0, "GBP": 0.0, "EUR": 0.0, "AUD": 0.0, "CAD": 0.0,
    "JPY": 0.0, "CNY": 0.0, "SGD": 0.0, "NZD": 0.0, "KRW": 0.0, "CHF": 0.0, "SEK": 0.0,
}

# ---------------------------------------------------------------- study destinations
# Used when a student types a university that is not yet in the verified registry.
# fee_range = typical yearly/semester tuition band for international students (sanity checks only).
STUDY_COUNTRIES = {
    "MY": {"name": "Malaysia", "currency": "MYR", "fee_range": [8000, 40000]},
    "UK": {"name": "United Kingdom", "currency": "GBP", "fee_range": [4000, 40000]},
    "US": {"name": "United States", "currency": "USD", "fee_range": [5000, 60000]},
    "AU": {"name": "Australia", "currency": "AUD", "fee_range": [8000, 50000]},
    "CA": {"name": "Canada", "currency": "CAD", "fee_range": [8000, 50000]},
    "DE": {"name": "Germany", "currency": "EUR", "fee_range": [150, 30000]},
    "IE": {"name": "Ireland", "currency": "EUR", "fee_range": [5000, 35000]},
    "NL": {"name": "Netherlands", "currency": "EUR", "fee_range": [2000, 25000]},
    "FR": {"name": "France", "currency": "EUR", "fee_range": [200, 25000]},
    "JP": {"name": "Japan", "currency": "JPY", "fee_range": [250000, 3000000]},
    "CN": {"name": "China", "currency": "CNY", "fee_range": [10000, 150000]},
    "KR": {"name": "South Korea", "currency": "KRW", "fee_range": [2000000, 20000000]},
    "SG": {"name": "Singapore", "currency": "SGD", "fee_range": [8000, 60000]},
    "NZ": {"name": "New Zealand", "currency": "NZD", "fee_range": [10000, 50000]},
    "CH": {"name": "Switzerland", "currency": "CHF", "fee_range": [500, 30000]},
    "SE": {"name": "Sweden", "currency": "SEK", "fee_range": [40000, 300000]},
}

# ---------------------------------------------------------------- universities
# The verified-beneficiary registry. Payment details ALWAYS come from here,
# never from an invoice or an email (control-plane / data-plane separation).
UNIVERSITIES = {
    "MUT": {
        "id": "MUT",
        "name": "Meridian University of Technology",
        "aliases": ["meridian university", "meridian utech", "mut"],
        "country": "MY", "city": "Kuala Lumpur", "currency": "MYR",
        "official_domains": ["meridian-utech.edu.my"],
        "beneficiary": {"bank": "Sandbox Maybank Berhad", "account": "MY-MBB-5140-2290-8837", "swift": "SBXMMYKL"},
        "fee_range": [12000, 26000],
        "allows_installments": True, "max_installments": 3,
        "late_fee": 500,
        "edu_partners": ["edupay"],
    },
    "NBU": {
        "id": "NBU",
        "name": "Northbridge University London",
        "aliases": ["northbridge university", "northbridge", "nbu"],
        "country": "UK", "city": "London", "currency": "GBP",
        "official_domains": ["northbridge.ac.uk"],
        "beneficiary": {"bank": "Sandbox Barclays", "account": "GB-SBX-20-45-77-11908834", "swift": "SBXBGB2L"},
        "fee_range": [4000, 25000],
        "allows_installments": True, "max_installments": 3,
        "late_fee": 150,
        "edu_partners": ["edupay"],
    },
    "PCSU": {
        "id": "PCSU",
        "name": "Pacific Coast State University",
        "aliases": ["pacific coast state", "pcsu"],
        "country": "US", "city": "Oakland", "currency": "USD",
        "official_domains": ["pcsu.edu"],
        "beneficiary": {"bank": "Sandbox Bank of the West Coast", "account": "US-SBX-021000021-55320918", "swift": "SBXWUS6S"},
        "fee_range": [9000, 32000],
        "allows_installments": False, "max_installments": 1,
        "late_fee": 100,
        "edu_partners": ["edupay"],
    },
    "SRU": {
        "id": "SRU",
        "name": "Southern Reef University",
        "aliases": ["southern reef", "sru"],
        "country": "AU", "city": "Brisbane", "currency": "AUD",
        "official_domains": ["southernreef.edu.au"],
        "beneficiary": {"bank": "Sandbox Westpac", "account": "AU-SBX-032-000-88104421", "swift": "SBXWAU2S"},
        "fee_range": [14000, 30000],
        "allows_installments": True, "max_installments": 2,
        "late_fee": 200,
        "edu_partners": [],
    },
}

# ---------------------------------------------------------------- payment channels
PROVIDERS = {
    "bank_swift": {
        "id": "bank_swift", "name": "Bank wire (SWIFT via authorised bank)", "type": "bank",
        "licensed": True, "fee_usd": 35.0, "fx_markup": 0.025, "days": [3, 5], "reliability": 0.98,
        "max_usd": 100000, "partner_only": False, "reconciliation": "manual (student must email proof)",
    },
    "edupay": {
        "id": "edupay", "name": "EduPay (education payment platform)", "type": "edu_platform",
        "licensed": True, "fee_usd": 0.0, "fx_markup": 0.012, "days": [2, 3], "reliability": 0.995,
        "max_usd": 60000, "partner_only": True, "reconciliation": "automatic (student ID matched by university)",
    },
    "remitlite": {
        "id": "remitlite", "name": "RemitLite (licensed money transfer operator)", "type": "licensed_mto",
        "licensed": True, "fee_usd": 4.99, "fx_markup": 0.007, "days": [1, 2], "reliability": 0.99,
        "max_usd": 10000, "partner_only": False, "reconciliation": "manual (student must email proof)",
    },
    "debit_card": {
        "id": "debit_card", "name": "International debit card", "type": "card",
        "licensed": True, "fee_usd": 0.0, "fx_markup": 0.045, "days": [0, 1], "reliability": 0.97,
        "max_usd": 3000, "partner_only": False, "reconciliation": "automatic (card portal)",
    },
    "informal": {
        "id": "informal", "name": "Informal channel (hundi / hawala)", "type": "informal",
        "licensed": False, "fee_usd": 0.0, "fx_markup": -0.01, "days": [1, 1], "reliability": 0.85,
        "max_usd": 1000000, "partner_only": False, "reconciliation": "none",
    },
}

# ---------------------------------------------------------------- country rule packs
# ILLUSTRATIVE ONLY — simplified from public guidance; verify before production.
COUNTRY_RULES = {
    "BD": {
        "name": "Bangladesh",
        "allowed_channel_types": ["bank", "edu_platform"],
        "documents": [
            "Student file opened with an Authorised Dealer (AD) bank",
            "Offer letter / tuition invoice from the university",
            "Passport and student visa copy",
        ],
        "annual_cap_usd": None,
        "note": "Outward tuition remittance must go through an AD bank or an approved education channel.",
    },
    "NG": {
        "name": "Nigeria",
        "allowed_channel_types": ["bank", "edu_platform", "licensed_mto"],
        "documents": ["Form A submitted through your bank", "Admission letter", "Tuition invoice", "Passport"],
        "annual_cap_usd": None,
        "note": "Education remittances are processed against Form A with supporting documents.",
    },
    "IN": {
        "name": "India",
        "allowed_channel_types": ["bank", "edu_platform", "licensed_mto"],
        "documents": ["Form A2 and LRS declaration", "Admission letter", "Tuition invoice", "PAN card"],
        "annual_cap_usd": 250000,
        "note": "Remittances count towards the annual Liberalised Remittance Scheme limit.",
    },
    "PK": {
        "name": "Pakistan",
        "allowed_channel_types": ["bank", "edu_platform"],
        "documents": ["Bank education remittance form", "Admission letter", "Tuition invoice"],
        "annual_cap_usd": None,
        "note": "Education payments are made through authorised banks.",
    },
}

# ---------------------------------------------------------------- screening
SANCTIONED_COUNTRIES = {"KP", "IR", "SY", "CU"}
SANCTIONED_NAMES = ["blocked entity ltd", "sanctioned trading co", "darkpool exchange"]
