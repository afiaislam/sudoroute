"""The baseline comparison must be reproducible and must keep SudoRoute's safety guarantees."""
import unittest

from sudoroute.benchmark.baselines import run, to_markdown


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_sudoroute_never_sends_money_to_a_fraudster(self):
        self.assertEqual(self.r["summary"]["SudoRoute"]["scams_that_reach_a_fraudster"], 0)
        self.assertEqual(self.r["summary"]["Bank wire"]["scams_that_reach_a_fraudster"], self.r["fraud"]["scams"])

    def test_sudoroute_never_breaks_a_channel_rule(self):
        self.assertEqual(self.r["summary"]["SudoRoute"]["rule_violations"], 0)
        self.assertEqual(self.r["routes"]["scenarios"], 160)

    def test_sudoroute_cheaper_and_more_punctual_than_bank_wire(self):
        s = self.r["summary"]
        self.assertGreater(s["SudoRoute"]["avg_saving_vs_bank_pct"], 0)
        self.assertLess(s["SudoRoute"]["late_rate_pct"], s["Bank wire"]["late_rate_pct"])
        self.assertEqual(s["SudoRoute"]["avoidable_late_pct"], 0.0)

    def test_fairness_every_country_protected_and_saving(self):
        for c, v in self.r["routes"]["by_country"].items():
            self.assertEqual(v["rule_violations"], 0, c)
            self.assertGreater(v["saving_vs_bank_pct"], 0, c)

    def test_no_overpayment_on_retry(self):
        self.assertEqual(self.r["summary"]["SudoRoute"]["overpayments_on_retry"], 0)
        short = next(c for c in self.r["retry"]["cases"] if "less" in c["case"])
        self.assertAlmostEqual(short["SudoRoute_paid_again"], short["shortfall"], places=2)

    def test_reproducible_and_reported(self):
        self.assertEqual(run()["summary"], self.r["summary"])
        self.assertIn("Why the assistant looks cheaper", to_markdown(self.r))


if __name__ == "__main__":
    unittest.main()
