import unittest

from tests.helpers import STU_BD, SandboxBank
from sudoroute.engines import budget, credit, fx_risk, routes
from sudoroute.engines.invoice_check import (classify_domain, levenshtein, match_university,
                                                 parse_pasted_invoice, verify_invoice)
from sudoroute.sandbox.reference_data import UNIVERSITIES


class FXMarketTests(unittest.TestCase):
    def setUp(self):
        self.m = SandboxBank().market

    def test_cross_rates_are_consistent(self):
        direct = self.m.mid("BDT", "MYR")
        via_usd = self.m.mid("BDT", "USD") * self.m.mid("USD", "MYR")
        self.assertAlmostEqual(direct, via_usd, places=12)

    def test_history_ends_at_reference_rate(self):
        self.assertAlmostEqual(self.m.units_per_usd("BDT"), 123.04)
        self.assertEqual(len(self.m.pair_history("NGN", "GBP")), 181)

    def test_deterministic_seed(self):
        self.assertEqual(SandboxBank().market.pair_history("NGN", "GBP"), self.m.pair_history("NGN", "GBP"))


class FXRiskTests(unittest.TestCase):
    def setUp(self):
        self.m = SandboxBank().market

    def test_pay_now_has_zero_spread(self):
        r = fx_risk.budget_at_risk(self.m, "BDT", "MYR", 18500, 15, budget_src=572000, n_paths=500)
        s = r["strategies"]["pay_now"]
        self.assertEqual(s["p05"], s["p95"])
        self.assertEqual(s["prob_over_budget"], 0.0)

    def test_waiting_widens_risk(self):
        r = fx_risk.budget_at_risk(self.m, "NGN", "GBP", 6200, 30, budget_src=12.9e6, n_paths=800)
        self.assertGreater(r["strategies"]["pay_at_due"]["p95"], r["strategies"]["pay_now"]["p95"])
        self.assertLess(r["strategies"]["installments"]["p95"], r["strategies"]["pay_at_due"]["p95"])

    def test_recommends_installments_when_full_amount_unaffordable(self):
        r = fx_risk.budget_at_risk(self.m, "NGN", "GBP", 6200, 30, budget_src=12.9e6,
                                   available_src=9.4e6, n_paths=500)
        self.assertEqual(r["recommended"], "installments")

    def test_no_installments_when_university_disallows(self):
        r = fx_risk.budget_at_risk(self.m, "INR", "USD", 15000, 20, allows_installments=False, n_paths=200)
        self.assertNotIn("installments", r["strategies"])

    def test_ewma_vol_positive(self):
        self.assertGreater(fx_risk.ewma_volatility(self.m.pair_history("NGN", "GBP")), 0.1)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.m = SandboxBank().market

    def test_informal_channel_never_eligible_even_if_cheapest(self):
        r = routes.compare_routes(self.m, src="BDT", dst="MYR", amount_dst=18500, days_to_due=21,
                                  university_id="MUT", home_country="BD")
        informal = next(x for x in r["routes"] if x["provider_id"] == "informal")
        self.assertFalse(informal["eligible"])
        self.assertLess(informal["total_src"], r["best"]["total_src"])

    def test_country_rules_restrict_channels(self):
        bd = routes.compare_routes(self.m, src="BDT", dst="MYR", amount_dst=18500, days_to_due=21,
                                   university_id="MUT", home_country="BD")
        ng = routes.compare_routes(self.m, src="NGN", dst="GBP", amount_dst=6200, days_to_due=40,
                                   university_id="NBU", home_country="NG")
        self.assertFalse(next(x for x in bd["routes"] if x["provider_id"] == "remitlite")["eligible"])
        self.assertTrue(next(x for x in ng["routes"] if x["provider_id"] == "remitlite")["eligible"])

    def test_best_route_beats_bank_wire(self):
        r = routes.compare_routes(self.m, src="BDT", dst="MYR", amount_dst=18500, days_to_due=21,
                                  university_id="MUT", home_country="BD")
        self.assertEqual(r["best"]["provider_id"], "edupay")
        self.assertGreater(r["savings_vs_bank_src"], 0)

    def test_deadline_risk_is_priced(self):
        self.assertEqual(routes.late_probability(20, 3, 5, 1.0, 2), 0.0)
        self.assertEqual(routes.late_probability(1, 3, 5, 1.0, 2), 1.0)
        self.assertGreater(routes.late_probability(6, 3, 5, 1.0, 2), 0.0)

    def test_partner_only_channel_requires_partner(self):
        r = routes.compare_routes(self.m, src="BDT", dst="AUD", amount_dst=15000, days_to_due=30,
                                  university_id="SRU", home_country="BD")
        self.assertFalse(next(x for x in r["routes"] if x["provider_id"] == "edupay")["eligible"])


class InvoiceCheckTests(unittest.TestCase):
    def setUp(self):
        self.bank = SandboxBank()
        self.student = self.bank.student(STU_BD)

    def test_legit_invoice_is_safe(self):
        v = verify_invoice(self.bank.invoices["INV-MUT-26S2"], self.student)
        self.assertEqual(v["verdict"], "SAFE")
        self.assertEqual(v["score"], 0)

    def test_phishing_invoice_is_blocked_with_reasons(self):
        v = verify_invoice(self.bank.invoices["INV-PHISH-001"], self.student)
        codes = {r["code"] for r in v["reasons"]}
        self.assertEqual(v["verdict"], "BLOCK")
        self.assertTrue({"lookalike_domain", "bank_mismatch", "prompt_injection", "unusual_method"} <= codes)

    def test_lookalike_and_typosquat_detection(self):
        uni = UNIVERSITIES["MUT"]
        self.assertEqual(classify_domain("meridian-utech.edu.my", uni), "official")
        self.assertEqual(classify_domain("pay.meridian-utech.edu.my", uni), "official")
        self.assertEqual(classify_domain("meridian-utech-payments.com", uni), "lookalike")
        self.assertEqual(classify_domain("meridan-utech.edu.my", uni), "lookalike")
        self.assertEqual(classify_domain("gmail.com", uni), "unofficial")
        self.assertEqual(levenshtein("kitten", "sitting"), 3)

    def test_unknown_payee(self):
        v = verify_invoice({"id": "X", "university_name": "Totally Real College", "sender_email": "a@b.com",
                            "amount": 5000, "currency": "USD", "text": ""})
        self.assertIn("unknown_payee", {r["code"] for r in v["reasons"]})

    def test_review_band(self):
        inv = dict(self.bank.invoices["INV-MUT-26S2"])
        inv["sender_email"] = "bursary.meridian@gmail.com"
        v = verify_invoice(inv, self.student)
        self.assertEqual(v["verdict"], "REVIEW")

    def test_amount_anomaly(self):
        inv = dict(self.bank.invoices["INV-MUT-26S2"], amount=95000)
        self.assertIn("amount_anomaly", {r["code"] for r in verify_invoice(inv, self.student)["reasons"]})

    def test_parse_pasted_email(self):
        p = parse_pasted_invoice("From: fees@northbridge-uni-pay.com Northbridge University tuition "
                                 "GBP 6,200 pay to account GB-SBX-99-11-22-00001111 in bitcoin")
        self.assertEqual(p["currency"], "GBP")
        self.assertEqual(p["amount"], 6200.0)
        self.assertEqual(p["university_name"], "Northbridge University London")
        self.assertEqual(verify_invoice(p)["verdict"], "BLOCK")

    def test_university_matching(self):
        self.assertEqual(match_university("Meridian University of Technology - Finance")["id"], "MUT")
        self.assertIsNone(match_university("Random Institute"))


class BudgetCreditTests(unittest.TestCase):
    def test_budget_flags_spending_spike(self):
        b = SandboxBank()
        s = b.student(STU_BD)
        out = budget.budget_overview(b.market, s, b.transactions[STU_BD],
                                     [b.invoices["INV-MUT-26S2"]], b.now.date())
        food = next(c for c in out["categories"] if c["category"] == "Food")
        self.assertGreater(food["change_pct"], 30)
        self.assertTrue(any("Food" in i for i in out["insights"]))
        self.assertIsNotNone(out["runway_months"])

    def test_credit_plan(self):
        s = SandboxBank().student(STU_BD)
        c = credit.credit_plan(s)
        self.assertTrue(0 <= c["readiness_score"] <= 100)
        self.assertTrue(c["next_steps"])
        self.assertNotIn("local_bank_account", [x["step"] for x in c["next_steps"]])


if __name__ == "__main__":
    unittest.main()
