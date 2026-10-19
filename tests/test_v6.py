"""HTTP tests for the v6 features: AI endpoints, proof of funds, recovery, pilot feedback, installable app."""
import json
import urllib.request

from tests.test_v3 import _ServerCase


class V6HttpTests(_ServerCase):
    def setUp(self):
        self.app.guard.fails.clear()  # sign-up throttling is tested elsewhere

    def family(self, tag):
        self.app.guard.fails.clear()
        c, st, out = self.register(f"{tag}@example.test", university_name="Meridian University of Technology",
                                   guardian_name="Ashraful Islam", guardian_email=f"{tag}-dad@example.test")
        self.assertEqual(st, 200, out)
        g = self.Client(self.port)
        st, gout, _ = g.req("/api/auth/register", {"role": "guardian", "name": "Ashraful Islam", "email": f"{tag}-dad@example.test",
                                                   "password": "Family8Pass", "relationship": "Father"}, csrf=False)
        self.assertEqual(st, 200, gout)
        g.csrf = gout["csrf"]
        return c, g, out["user"]["student_id"]

    def raw(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.headers, r.read()

    def test_brief_and_language(self):
        c, _, _ = self.family("brief")
        st, out, _ = c.req("/api/brief", {"lang": "bn"})
        self.assertEqual(st, 200, out)
        self.assertIn("Next tuition", out["text"]); self.assertEqual(out["source"], "template")

    def test_email_draft_only_for_own_documents(self):
        c, _, sid = self.family("mail")
        inv = next(iter(i for i in self.app.bank.invoices.values() if i["student_id"] == sid))
        st, out, _ = c.req("/api/email-draft", {"invoice_id": inv["id"]})
        self.assertEqual(st, 200, out); self.assertIn("finance office", out["body"])
        other, _, _ = self.family("mail2")
        st, out, _ = other.req("/api/email-draft", {"invoice_id": inv["id"]})
        self.assertEqual(st, 404)

    def test_guardian_ask_is_read_only_and_scoped(self):
        c, g, sid = self.family("ask")
        st, out, _ = g.req("/api/guardian/ask", {"question": "How much tuition is left?"})
        self.assertEqual(st, 200, out); self.assertIn("Tuition still to pay", out["text"])
        st, out, _ = c.req("/api/guardian/ask", {"question": "hi"})
        self.assertIn(st, (403, 404))

    def test_public_ask_and_rate_limit(self):
        p = self.Client(self.port)
        st, out, _ = p.req("/api/public/ask", {"question": "What is the 6-digit code?"}, csrf=False)
        self.assertEqual(st, 200, out); self.assertIn("one-time code", out["text"])
        st, out, _ = p.req("/api/public/ask", {"question": "again"}, csrf=False)
        self.assertEqual(st, 429)

    def test_proof_of_funds_certificate_round_trip(self):
        c, _, _ = self.family("funds")
        st, out, _ = c.req("/api/certificates/issue", {"kind": "funds", "at_least": 1000, "currency": "USD", "purpose": "Visa"})
        self.assertEqual(st, 200, out)
        self.assertEqual(set(out["claims"]["funds"]), {"at_least", "currency", "as_of", "valid_until", "purpose", "method"})
        st, v, _ = self.Client(self.port).req("/api/public/verify", {"code": out["code"]}, csrf=False)
        self.assertTrue(v["valid"]); self.assertEqual(v["claims"]["type"], "proof_of_funds")
        st, out, _ = c.req("/api/certificates/issue", {"kind": "funds", "at_least": 10 ** 12, "currency": "USD"})
        self.assertEqual(st, 400); self.assertIn("can't sign", out["error"])
        st, out, _ = c.req("/api/certificates/issue", {"kind": "funds", "at_least": "nan", "currency": "USD"})
        self.assertEqual(st, 400)

    def test_recovery_endpoints_scoped(self):
        c, g, sid = self.family("recov")
        other, _, _ = self.family("recov2")
        t = self.app.bank.transfer(student_id=sid, src_currency="BDT", src_amount=1000.0, dst_currency="MYR", dst_amount=38.0,
                                   provider={"id": "edupay", "name": "EduPay", "days": [2, 3]}, university_id="MUT",
                                   reference="X", invoice_id="none", proposal_id="p", leg=1)
        st, out, _ = other.req("/api/sandbox/transfer-issue", {"transfer_id": t["id"], "kind": "returned"})
        self.assertEqual(st, 400)
        st, out, _ = c.req("/api/sandbox/transfer-issue", {"transfer_id": t["id"], "kind": "returned"})
        self.assertEqual(st, 200, out)
        st, out, _ = c.req("/api/transfer/recover", {"transfer_id": t["id"]})
        self.assertEqual(out["kind"], "returned")
        st, out, _ = c.req("/api/email-draft", {"transfer_id": t["id"]})
        self.assertIn("returned", out["body"])

    def test_pilot_feedback_aggregates_only(self):
        c, g, _ = self.family("pilot")
        st, out, _ = c.req("/api/feedback", {"useful": 5, "trust": 4, "would_use": "yes", "comment": "secret note"})
        self.assertEqual(st, 200, out)
        st, out, _ = g.req("/api/feedback", {"useful": 9, "trust": 4, "would_use": "yes"})
        self.assertEqual(st, 400)
        st, out, _ = g.req("/api/feedback", {"useful": 3, "trust": 3, "would_use": "maybe"})
        st, s, _ = self.Client(self.port).req("/api/pilot".replace("/api/", "/api/public/"))
        self.assertGreaterEqual(s["responses"], 2); self.assertNotIn("secret note", json.dumps(s))
        st, out, _ = self.Client(self.port).req("/api/feedback", {"useful": 5, "trust": 5, "would_use": "yes"}, csrf=False)
        self.assertEqual(st, 401)

    def test_installable_app(self):
        st, h, body = self.raw("/manifest.webmanifest")
        self.assertEqual(json.loads(body)["short_name"], "SudoRoute")
        st, h, body = self.raw("/sw.js")
        self.assertIn("no-cache", h["Cache-Control"]); self.assertIn(b"never caches API", body)
        st, h, body = self.raw("/offline")
        self.assertIn(b"offline", body)
        st, h, body = self.raw("/")
        self.assertIn(b'rel="manifest"', body); self.assertIn(b"aichat.js", body)
