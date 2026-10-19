"""Failed-transfer recovery and reconciliation: returned transfers and short receipts."""
import unittest

from tests.helpers import STU_BD, make_agent, otp_for, propose


def paid_transfer(a):
    out, card = propose(a)
    pid = card["proposal"]["proposal_id"]
    res = a.confirm(STU_BD, pid, card["token"], otp_for(a, pid))
    assert res["ok"], res
    return next(t for t in a.bank.transfers.values() if t["proposal_id"] == pid)


class RecoveryTests(unittest.TestCase):
    def test_no_double_payment_while_in_transit(self):
        a = make_agent()
        paid_transfer(a)
        out = a.chat(STU_BD, "Pay my tuition")
        self.assertFalse(any(c["type"] == "proposal" for c in out.get("cards", [])))
        self.assertEqual(len(a.bank.transfers), 1)
        r = a.recover(STU_BD, next(iter(a.bank.transfers)))
        self.assertEqual(r["kind"], "in_transit")
        self.assertIn("paid twice", r["steps"][0])

    def test_returned_transfer_refunds_and_reopens_invoice(self):
        a = make_agent()
        t = paid_transfer(a)
        bal_after_send = a.bank.student(STU_BD)["balances"]["BDT"]
        res = a.inject_issue(STU_BD, t["id"], "returned")
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(a.bank.student(STU_BD)["balances"]["BDT"], bal_after_send + t["src_amount"], places=2)
        a.advance(10)  # a returned transfer must never be credited later
        self.assertEqual(a.bank.transfers[t["id"]]["status"], "returned")
        self.assertEqual(a.bank.invoices[t["invoice_id"]]["paid"], 0.0)
        r = a.recover(STU_BD, t["id"])
        self.assertEqual(r["kind"], "returned")
        self.assertAlmostEqual(r["outstanding"], 18500.0, places=2)
        self.assertTrue(any("Do not resend" in s for s in r["steps"]))
        # the old approval is single-use: replaying it fails
        self.assertFalse(a.confirm(STU_BD, t["proposal_id"], "x", "000000").get("ok"))
        # a fresh payment goes through the full flow again
        out, card = propose(a)
        self.assertAlmostEqual(card["proposal"]["total_dst"], 18500.0, places=2)

    def test_short_receipt_pays_only_the_shortfall(self):
        a = make_agent()
        t = paid_transfer(a)
        a.inject_issue(STU_BD, t["id"], "short")
        a.advance(6)
        tr = a.bank.transfers[t["id"]]
        self.assertEqual(tr["status"], "credited_short")
        short = round(tr["dst_amount"] - tr["received_amount"], 2)
        self.assertGreater(short, 0)
        inv = a.bank.invoices[t["invoice_id"]]
        self.assertEqual(inv["status"], "partially_paid")
        r = a.recover(STU_BD, t["id"])
        self.assertEqual(r["kind"], "short")
        self.assertAlmostEqual(r["outstanding"], short, places=2)
        out, card = propose(a)
        self.assertAlmostEqual(card["proposal"]["total_dst"], short, places=2)
        pid = card["proposal"]["proposal_id"]
        self.assertTrue(a.confirm(STU_BD, pid, card["token"], otp_for(a, pid))["ok"])
        a.advance(6)
        self.assertEqual(a.bank.invoices[t["invoice_id"]]["status"], "paid")
        self.assertAlmostEqual(a.bank.invoices[t["invoice_id"]]["paid"], inv["amount"], places=2)

    def test_cannot_touch_someone_elses_transfer(self):
        a = make_agent()
        t = paid_transfer(a)
        self.assertFalse(a.inject_issue("STU-NG-002", t["id"], "returned")["ok"])
        self.assertFalse(a.recover("STU-NG-002", t["id"])["ok"])

    def test_only_in_transit_can_fail(self):
        a = make_agent()
        t = paid_transfer(a)
        a.advance(6)
        self.assertFalse(a.inject_issue(STU_BD, t["id"], "returned")["ok"])


if __name__ == "__main__":
    unittest.main()
