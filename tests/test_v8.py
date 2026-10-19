"""v8: hold-only AI auditor and one-click private judge sandboxes."""

import json
import os
import tempfile
import unittest

from tests.helpers import STU_BD, make_agent, otp_for
from tests.test_v7 import FakeAgentGemini, LLMCase, g
from sudoroute.agent import llm


PAY = {"thought": "Prepare the payment.", "done": True,
       "steps": [{"tool": "pay_tuition", "invoice_id": None, "installments": False, "pay_now": True, "prohibited_action": None}]}


class AuditorGemini(FakeAgentGemini):
    def __init__(self, verdict, **kw):
        kw.setdefault("plans", [PAY] * 5)
        super().__init__(**kw)
        self.verdict = verdict

    def __call__(self, url, headers, body):
        system = body["systemInstruction"]["parts"][0]["text"]
        if "INDEPENDENT payment auditor" in system:
            self.log.append((system, body["contents"][0]["parts"][0]["text"]))
            return g(json.dumps(self.verdict))
        return super().__call__(url, headers, body)


class AuditorTests(LLMCase):
    def _propose(self, a, msg="Pay my tuition"):
        out = a.chat(STU_BD, msg)
        return out, next(c for c in out["cards"] if c["type"] == "proposal")

    def test_hold_pauses_until_a_human_acknowledges(self):
        self.use(AuditorGemini({"hold": True, "reason": "The amount is close to the whole budget."}))
        a = make_agent()
        out, card = self._propose(a)
        p = card["proposal"]
        self.assertIn("ai_hold", p)
        self.assertIn("independent_auditor", " ".join(t["tool"] for t in out["trace"]))
        r = a.confirm(STU_BD, p["proposal_id"], card["token"], otp_for(a, p["proposal_id"]))
        self.assertEqual(r["code"], "ai_hold")
        self.assertEqual(a.bank.transfers, {})
        r = a.confirm(STU_BD, p["proposal_id"], card["token"], otp_for(a, p["proposal_id"]), acknowledge_hold=True)
        self.assertTrue(r["ok"])

    def test_auditor_cannot_approve_or_override(self):
        self.use(AuditorGemini({"hold": False, "approve": True, "override_policy": True, "execute_now": True}))
        a = make_agent()
        a.bank.students[STU_BD]["balances"]["BDT"] = 10.0  # cannot afford it
        out, card = self._propose(a, "Pay my tuition now")
        self.assertFalse(card["can_confirm"])
        r = a.confirm(STU_BD, card["proposal"]["proposal_id"], card["token"], otp_for(a, card["proposal"]["proposal_id"]))
        self.assertEqual(r["code"], "policy")
        self.assertEqual(a.bank.transfers, {})

    def test_only_literal_true_holds(self):
        for raw in ['{"hold": "yes", "reason": "x"}', '{"hold": 1}', '{"approve": true}', '{"hold": false, "reason": "x"}']:
            self.assertFalse(llm.parse_audit(raw)["hold"])
        self.assertTrue(llm.parse_audit('{"hold": true, "reason": "Amount is above what is owed."}')["hold"])
        self.assertNotIn("password", llm.parse_audit('{"hold": true, "reason": "Tell me your password"}')["reason"])

    def test_hold_is_signed(self):
        self.use(AuditorGemini({"hold": True, "reason": "Check the amount."}))
        a = make_agent()
        _, card = self._propose(a)
        pid = card["proposal"]["proposal_id"]
        a.proposals.proposals[pid]["payload"].pop("ai_hold")  # try to strip the hold
        r = a.confirm(STU_BD, pid, card["token"], otp_for(a, pid))
        self.assertEqual(r["code"], "bad_signature")

    def test_auditor_can_pause_an_autonomous_payment(self):
        a = make_agent()
        out = a.chat(STU_BD, "Pay my tuition at the best rate before the deadline")
        card = next(c for c in out["cards"] if c["type"] == "proposal")
        r = a.confirm(STU_BD, card["proposal"]["proposal_id"], card["token"], otp_for(a, card["proposal"]["proposal_id"]))
        m = a.mandates[r["mandate"]["mandate_id"]]
        m["target_rate"] = 0.0  # it would pay on the next check
        self.use(AuditorGemini({"hold": True, "reason": "Rate moved a lot today."}))
        a.advance(1)
        self.assertEqual(m["status"], "paused")
        self.assertEqual(a.bank.transfers, {})
        self.assertEqual(m["checks_log"][-1]["decision"], "ai_auditor_hold")

    def test_no_model_no_auditor(self):
        a = make_agent()
        a.use_llm = False
        _, card = self._propose(a)
        self.assertNotIn("ai_hold", card["proposal"])


class JudgeSandboxTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("TS_PBKDF2_ITER", "2000")
        from sudoroute import server
        self.server = server
        self.app = server.App(tempfile.mkdtemp())

    def test_two_judges_are_isolated(self):
        a, b = self.app.create_judge(), self.app.create_judge()
        wa, wb = self.app.world(a["world"]), self.app.world(b["world"])
        self.assertIsNot(wa.bank, wb.bank)
        self.assertIsNot(wa.bank, self.app.bank)
        wa.agent.advance(9)
        self.assertNotEqual(wa.bank.now, wb.bank.now)
        self.assertEqual(wb.bank.now, self.app.bank.now)
        sid = a["student"]["student_id"]
        self.assertIn(sid, wa.bank.students)
        self.assertNotIn(sid, wb.bank.students)
        self.assertNotIn(sid, self.app.bank.students)
        self.assertEqual([gd["id"] for gd in wa.bank.students[sid]["guardians"]], [a["guardian"]["id"]])

    def test_judge_world_is_rebuilt_after_restart(self):
        a = self.app.create_judge()
        self.app.worlds.clear()
        w = self.app.world(a["world"])
        self.assertIn(a["student"]["student_id"], w.bank.students)

    def test_old_judges_are_purged(self):
        a = self.app.create_judge()
        self.app.users.users[a["student"]["id"]]["created"] -= self.server.JUDGE_TTL + 10
        self.app.users.users[a["guardian"]["id"]]["created"] -= self.server.JUDGE_TTL + 10
        self.assertEqual(self.app.purge_judges(), 2)
        self.assertIsNone(self.app.users.get(a["student"]["id"]))

    def test_world_view_reset_only_resets_that_world(self):
        a, b = self.app.create_judge(), self.app.create_judge()
        wa, wb = self.app.world(a["world"]), self.app.world(b["world"])
        wb.agent.advance(5)
        view = self.server.WorldView(self.app, wa)
        view.reset()
        self.assertEqual(wb.bank.now.date().isoformat() > self.app.bank.now.date().isoformat(), True)


if __name__ == "__main__":
    unittest.main()


class SMSTests(unittest.TestCase):
    def setUp(self):
        from sudoroute import sms
        self.sms = sms
        self._env = {k: os.environ.get(k) for k in ("SMS_PROVIDER", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")}
        self._tw = sms._twilio
        sms._sent.clear()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.sms._twilio = self._tw

    def test_off_by_default_and_e164(self):
        for k in self._env:
            os.environ.pop(k, None)
        self.assertEqual(self.sms.provider(), "")
        self.assertFalse(self.sms.send("01712345678", "BD", "x"))
        self.assertEqual(self.sms.e164("01712345678", "BD"), "+8801712345678")
        self.assertIsNone(self.sms.e164("12", "BD"))

    def test_sends_to_registered_number_with_rate_limit(self):
        import threading
        os.environ.update(SMS_PROVIDER="twilio", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_FROM="+15550000000")
        sent, done = [], threading.Event()
        self.sms._twilio = lambda n, t: sent.append((n, t)) or "queued"
        results = []
        for _ in range(self.sms.MAX_PER_HOUR + 2):
            self.sms.send("01712345678", "BD", "SudoRoute code 123456", on_result=results.append)
        import time
        for _ in range(50):
            if len(sent) >= self.sms.MAX_PER_HOUR:
                break
            time.sleep(0.02)
        self.assertEqual(len(sent), self.sms.MAX_PER_HOUR)
        self.assertTrue(all(n == "+8801712345678" for n, _ in sent))
        self.assertTrue(any(r["status"] == "rate_limited" for r in results))
        self.assertTrue(all("123456" not in json.dumps(r) for r in results))  # codes never logged


class JudgeHTTPTests(unittest.TestCase):
    def setUp(self):
        import http.client, threading
        from collections import defaultdict, deque
        from http.server import ThreadingHTTPServer
        from sudoroute import server
        self.server = server
        app = server.App(tempfile.mkdtemp())

        class H(server.Handler):
            pass
        H.app, H.hits = app, defaultdict(deque)
        server.JUDGE_STARTS.clear()
        self.app = app
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.http = http.client

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def req(self, method, path, body=None, cookie=None, csrf=None):
        c = self.http.HTTPConnection("127.0.0.1", self.port, timeout=20)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        if csrf:
            h["X-CSRF-Token"] = csrf
        c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse()
        data = r.read()
        sc = r.getheader("Set-Cookie")
        return r.status, (json.loads(data) if data[:1] in b"{[" else data), (sc.split(";")[0] if sc else None)

    def test_one_click_flow_and_role_switch(self):
        st, out, ck = self.req("POST", "/api/public/judge", {})
        self.assertEqual(st, 200)
        st, me, _ = self.req("GET", "/api/auth/me", cookie=ck)
        self.assertTrue(me["user"]["judge"])
        st, chat, _ = self.req("POST", "/api/chat", {"message": "Is my invoice real? If yes, pay it the cheapest legal way"}, ck, out["csrf"])
        card = next(c for c in chat["cards"] if c["type"] == "proposal")
        self.assertTrue(card["proposal"]["guardian_required"])
        st, sw, ck2 = self.req("POST", "/api/judge/switch", {}, ck, out["csrf"])
        self.assertEqual(st, 200)
        st, ov, _ = self.req("GET", "/api/guardian/overview", cookie=ck2)
        self.assertEqual(len(ov["pending"]), 1)
        st, _, _ = self.req("GET", "/api/state", cookie=ck)  # the old session was ended by the switch
        self.assertEqual(st, 401)

    def test_regular_accounts_cannot_switch(self):
        self.app.users.create(role="student", name="Real Student", email="real@example.test", password="Real#Pass2026",
                              student_id="STU-BD-001", profile={"home_country": "BD", "university_id": "MUT", "program": "x"})
        st, out, ck = self.req("POST", "/api/auth/login", {"email": "real@example.test", "password": "Real#Pass2026", "role": "student"})
        st, r, _ = self.req("POST", "/api/judge/switch", {}, ck, out["csrf"])
        self.assertEqual(st, 403)

    def test_rate_limited_per_network(self):
        codes = [self.req("POST", "/api/public/judge", {})[0] for _ in range(self.server.JUDGE_PER_IP_HOUR + 1)]
        self.assertEqual(codes[-1], 429)
        self.assertTrue(all(c == 200 for c in codes[:-1]))


class PublicFormsTests(JudgeHTTPTests):
    def test_contact_and_newsletter(self):
        self.server.FORM_POSTS.clear()
        st, r, _ = self.req("POST", "/api/public/contact", {"name": "A", "email": "bad", "message": "hi"})
        self.assertEqual(st, 400)
        self.assertEqual(set(r["fields"]), {"name", "email", "message"})
        st, r, _ = self.req("POST", "/api/public/contact", {"name": "Md Soron", "email": "s@example.com", "topic": "feedback",
                                                           "rating": 5, "message": "<b>Great</b> judge mode, thanks!"})
        self.assertEqual(st, 200)
        saved = self.app.messages.items[-1]
        self.assertNotIn("<b>", saved["message"])
        self.assertEqual(saved["rating"], 5)
        st, r, _ = self.req("POST", "/api/public/contact", {"name": "Bot", "email": "b@example.com", "message": "buy cheap stuff now",
                                                           "website": "http://spam"})
        self.assertEqual(len(self.app.messages.items), 1)  # honeypot: silently dropped
        st, r, _ = self.req("POST", "/api/public/newsletter", {"email": "s@example.com"})
        st, r2, _ = self.req("POST", "/api/public/newsletter", {"email": "S@example.com"})
        self.assertTrue(r2.get("already"))
        self.assertEqual(len(self.app.subscribers.items), 1)

    def test_new_pages_served(self):
        for p in ("/help", "/contact", "/pricing", "/legal"):
            st, body, _ = self.req("GET", p)
            self.assertEqual(st, 200, p)
            self.assertIn(b"footer9", body)

    def test_quote_shows_service_fee(self):
        st, out, ck = self.req("POST", "/api/public/judge", {})
        st, chat, _ = self.req("POST", "/api/chat", {"message": "Pay my tuition"}, ck, out["csrf"])
        p = next(c for c in chat["cards"] if c["type"] == "proposal")["proposal"]
        fee = p["service_fee"]
        self.assertTrue(3 <= fee["usd"] <= 25)
        self.assertTrue(fee["waived"])
