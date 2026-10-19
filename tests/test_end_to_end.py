import unittest

from tests.helpers import STU_BD, STU_NG, make_agent, otp_for, propose
from sudoroute.agent import intents


class TaskCompletionTests(unittest.TestCase):
    """The core tasks the agent must complete end-to-end in the sandbox."""

    def test_task1_pay_tuition_full_cycle(self):
        a = make_agent()
        before = a.bank.student(STU_BD)["balances"]["BDT"]
        out, card = propose(a)
        self.assertEqual([t["tool"] for t in out["trace"]],
                         ["list_invoices", "verify_invoice", "compare_routes", "fx_budget_at_risk",
                          "policy_precheck", "create_signed_proposal"])
        pid = card["proposal"]["proposal_id"]
        res = a.confirm(STU_BD, pid, card["token"], otp_for(a, pid))
        self.assertTrue(res["ok"])
        self.assertLess(a.bank.student(STU_BD)["balances"]["BDT"], before)
        a.advance(5)
        self.assertEqual(a.bank.invoices["INV-MUT-26S2"]["status"], "paid")
        self.assertEqual(a.bank.university_ledger["MUT"]["MUT-2026-04417"], 18500.0)

    def test_task2_installments_run_autonomously_under_mandate(self):
        a = make_agent()
        out, card = propose(a, STU_NG)
        self.assertEqual(len(card["proposal"]["legs"]), 3)
        self.assertAlmostEqual(sum(l["dst_amount"] for l in card["proposal"]["legs"]), 6200.0, places=2)
        pid = card["proposal"]["proposal_id"]
        res = a.confirm(STU_NG, pid, card["token"], otp_for(a, pid))
        self.assertIsNotNone(res["mandate"])
        a.advance(40)
        self.assertEqual(a.bank.invoices["INV-NBU-26T1"]["status"], "paid")
        self.assertEqual(len(a.bank.transfers), 3)
        self.assertEqual(next(iter(a.mandates.values()))["status"], "completed")

    def test_task3_scam_detected_and_refused(self):
        a = make_agent()
        out = a.chat(STU_BD, "Is INV-PHISH-001 real?")
        self.assertEqual(out["cards"][0]["verdict"], "BLOCK")
        out = a.chat(STU_BD, "Pay INV-PHISH-001")
        self.assertIn("won't pay", out["reply"])

    def test_task4_analysis_tools(self):
        a = make_agent()
        for msg, ctype in [("Compare transfer options", "routes"), ("When should I pay?", "fx"),
                           ("Show my budget", "budget"), ("How do I build credit?", "credit"),
                           ("my balance", "balances"), ("what invoices do I have", "invoices"),
                           ("show the audit log", "audit")]:
            out = a.chat(STU_BD, msg)
            self.assertEqual(out["cards"][0]["type"], ctype, msg)

    def test_bangla_request(self):
        self.assertEqual(intents.parse("আমার টিউশন ফি পরিশোধ করো")["intent"], "pay_tuition")


if __name__ == "__main__":
    unittest.main()
