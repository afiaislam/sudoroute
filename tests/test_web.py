"""Website and account security tests over real HTTP (no browser needed)."""

import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from tests import helpers  # noqa: F401  (sets fast hashing + test secret)
from sudoroute.security import auth
from sudoroute.security.proposals import sandbox_otp
from sudoroute.server import App, Handler

STU_BD = ("student.bd@example.test", "Student#2026")
STU_NG = ("student.ng@example.test", "Student#2026")
GUARD_BD = ("guardian.bd@example.test", "Guardian#2026")


class Client:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.cookie = None
        self.csrf = None

    def req(self, path, body=None, headers=None, csrf=True):
        h = {"Content-Type": "application/json"}
        if self.cookie:
            h["Cookie"] = self.cookie
        if body is not None and csrf and self.csrf:
            h["X-CSRF-Token"] = self.csrf
        h.update(headers or {})
        if path == "/api/auth/register" and isinstance(body, dict) and "phone" not in body:
            body = {**body, "phone": "01906032900"}  # phone is required at sign-up
        if path == "/api/auth/register" and isinstance(body, dict) and body.get("role") == "student" \
                and "guardian_email" not in body:
            body = {**body, "guardian_name": "Test Guardian", "guardian_email": "guardian-of-" + str(body.get("email", "x"))}
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers=h)
        opener = urllib.request.build_opener(NoRedirect)
        try:
            resp = opener.open(r)
            status, raw, hdrs = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            status, raw, hdrs = e.code, e.read(), e.headers
        sc = hdrs.get("Set-Cookie")
        if sc:
            m = re.match(r"ts_session=([^;]*)", sc)
            self.cookie = f"ts_session={m.group(1)}" if m and m.group(1) else None
        try:
            payload = json.loads(raw) if raw and hdrs.get("Content-Type", "").startswith("application/json") else raw
        except ValueError:
            payload = raw
        return status, payload, hdrs

    def login(self, creds, role):
        status, out, hdrs = self.req("/api/auth/login", {"email": creds[0], "password": creds[1], "role": role})
        if status == 200:
            self.csrf = out["csrf"]
        return status, out, hdrs


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class WebTestCase(unittest.TestCase):
    def setUp(self):
        Handler.app = App(None, samples=True)  # scripted sample students exist in tests only
        helpers.seed_accounts(Handler.app)
        Handler.hits.clear()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def client(self):
        return Client(self.port)


class PagesAndHeaders(WebTestCase):
    def test_public_pages(self):
        c = self.client()
        for path in ("/", "/login", "/register?role=guardian", "/static/site.css", "/static/common.js"):
            status, body, _ = c.req(path)
            self.assertEqual(status, 200, path)

    def test_portals_require_sign_in(self):
        c = self.client()
        for path in ("/app", "/guardian"):
            status, _, hdrs = c.req(path)
            self.assertEqual(status, 302)
            self.assertIn("/login", hdrs["Location"])

    def test_wrong_role_cannot_open_other_portal(self):
        c = self.client()
        c.login(STU_BD, "student")
        status, _, hdrs = c.req("/guardian")
        self.assertEqual(status, 302)

    def test_security_headers(self):
        _, _, h = self.client().req("/")
        csp = h["Content-Security-Policy"]
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_static_path_traversal_blocked(self):
        c = self.client()
        for path in ("/static/../sudoroute/config.py", "/static/..%2f..%2fREADME.md", "/static/x.py"):
            self.assertEqual(c.req(path)[0], 404, path)

    def test_api_requires_session(self):
        self.assertEqual(self.client().req("/api/state")[0], 401)


class Authentication(WebTestCase):
    def test_login_sets_hardened_cookie(self):
        c = self.client()
        status, out, hdrs = c.login(STU_BD, "student")
        self.assertEqual(status, 200)
        cookie = hdrs["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(out["redirect"], "/app")
        self.assertNotIn('"password":', json.dumps(out))
        self.assertNotIn("pbkdf2", json.dumps(out))

    def test_generic_error_for_wrong_password_unknown_email_and_wrong_role(self):
        c = self.client()
        a = c.req("/api/auth/login", {"email": STU_BD[0], "password": "wrong-pass-1", "role": "student"})
        b = c.req("/api/auth/login", {"email": "nobody@x.com", "password": "wrong-pass-1", "role": "student"})
        d = c.req("/api/auth/login", {"email": STU_BD[0], "password": STU_BD[1], "role": "guardian"})
        self.assertEqual({a[0], b[0], d[0]}, {401})
        self.assertEqual(a[1]["error"], b[1]["error"])
        self.assertEqual(a[1]["error"], d[1]["error"])

    def test_lockout_after_five_failures(self):
        c = self.client()
        for _ in range(5):
            c.req("/api/auth/login", {"email": STU_BD[0], "password": "nope-nope-1", "role": "student"})
        status, out, _ = c.login(STU_BD, "student")
        self.assertEqual(status, 429)
        self.assertEqual(out["code"], "locked")

    def test_csrf_required_for_state_changes(self):
        c = self.client()
        c.login(STU_BD, "student")
        status, out, _ = c.req("/api/chat", {"message": "Pay my tuition"}, csrf=False)
        self.assertEqual((status, out["code"]), (403, "csrf"))
        status, out, _ = c.req("/api/chat", {"message": "hi"}, headers={"X-CSRF-Token": "forged"})
        self.assertEqual(status, 403)

    def test_cross_origin_post_blocked(self):
        c = self.client()
        c.login(STU_BD, "student")
        status, out, _ = c.req("/api/chat", {"message": "hi"}, headers={"Origin": "https://evil.example"})
        self.assertEqual((status, out["code"]), (403, "bad_origin"))

    def test_logout_invalidates_session(self):
        c = self.client()
        c.login(STU_BD, "student")
        old = c.cookie
        self.assertEqual(c.req("/api/auth/logout", {})[0], 200)
        c.cookie = old
        self.assertEqual(c.req("/api/state")[0], 401)

    def test_session_idle_timeout(self):
        c = self.client()
        c.login(STU_BD, "student")
        for s in Handler.app.sessions.sessions.values():
            s["last"] -= auth.SESSION_IDLE + 5
        self.assertEqual(c.req("/api/state")[0], 401)

    def test_password_change_revokes_other_sessions(self):
        a, b = self.client(), self.client()
        a.login(STU_BD, "student")
        b.login(STU_BD, "student")
        status, out, _ = a.req("/api/auth/password", {"current": STU_BD[1], "new": "NewPassword2026x"})
        self.assertEqual(status, 200)
        self.assertEqual(out["revoked_sessions"], 1)
        self.assertEqual(b.req("/api/state")[0], 401)
        self.assertEqual(a.req("/api/state")[0], 200)
        self.assertEqual(a.req("/api/auth/password", {"current": "wrong", "new": "Another2026xx"})[0], 403)

    def test_passwords_hashed_not_stored(self):
        u = Handler.app.users.by_email(STU_BD[0])
        self.assertTrue(u["password"].startswith("pbkdf2_sha256$"))
        self.assertNotIn(STU_BD[1], json.dumps(Handler.app.users.users))
        self.assertTrue(auth.verify_password(STU_BD[1], u["password"]))
        self.assertFalse(auth.verify_password("Student#2027", u["password"]))

    def test_password_policy(self):
        self.assertTrue(auth.password_problems("short1"))
        self.assertTrue(auth.password_problems("onlyletterslong"))
        self.assertTrue(auth.password_problems("alllower1"))
        self.assertTrue(auth.password_problems("ALLUPPER1"))
        self.assertFalse(auth.password_problems("Tuition8"))
        self.assertTrue(auth.password_problems("password123"))
        self.assertTrue(auth.password_problems("priyanair2026", "priyanair@x.com"))
        self.assertFalse(auth.password_problems("Blue-River-2026", "p@x.com", "Priya"))


class Registration(WebTestCase):
    def test_student_registration_opens_wallet_and_invoice(self):
        c = self.client()
        status, out, _ = c.req("/api/auth/register", {
            "role": "student", "name": "Priya Nair", "email": "priya@example.com", "password": "Blue-River-2026",
            "home_country": "IN", "university_id": "NBU", "program": "MSc AI"})
        self.assertEqual(status, 200, out)
        c.csrf = out["csrf"]
        st = c.req("/api/state")[1]
        self.assertEqual(st["home_currency"], "INR")
        self.assertEqual(len(st["invoices"]), 2)   # one real tuition invoice and one suspicious sample e-mail to try the scam shield
        self.assertEqual(sum("PHISH" in i["id"] for i in st["invoices"]), 1)
        self.assertGreater(st["balances"]["INR"], 0)
        chat = c.req("/api/chat", {"message": "Pay my tuition"})[1]
        self.assertTrue(any(card["type"] == "proposal" for card in chat["cards"]))

    def test_validation_errors_are_per_field(self):
        status, out, _ = self.client().req("/api/auth/register", {
            "role": "student", "name": "<script>", "email": "bad", "password": "short", "home_country": "XX",
            "university_id": "NOPE"})
        self.assertEqual(status, 400)
        self.assertEqual(set(out["fields"]), {"name", "email", "password", "home_country", "university_name", "guardian_email"})

    def test_duplicate_email_rejected(self):
        status, out, _ = self.client().req("/api/auth/register", {
            "role": "guardian", "name": "Someone Else", "email": STU_BD[0], "password": "Blue-River-2026",
            "relationship": "Parent"})
        self.assertEqual(status, 400)
        self.assertIn("email", out["fields"])

    def test_guardian_link_code_is_single_use(self):
        s = self.client()
        s.login(STU_NG, "student")
        code = s.req("/api/guardian/invite", {})[1]["code"]
        g1 = self.client()
        status, out, _ = g1.req("/api/auth/register", {
            "role": "guardian", "name": "Afia Islam", "email": "afia.guardian@example.com", "password": "Green-Field-2026",
            "relationship": "Father", "link_code": code})
        self.assertEqual(status, 200)
        g1.csrf = out["csrf"]
        ov = g1.req("/api/guardian/overview")[1]
        self.assertEqual([x["id"] for x in ov["students"]], ["STU-NG-002"])
        g2 = self.client()
        g2.req("/api/auth/register", {"role": "guardian", "name": "Other Person", "email": "other@example.com",
                                      "password": "Green-Field-2026", "relationship": "Parent"})
        me = g2.req("/api/auth/me")[1]
        g2.csrf = me["csrf"]
        status, out, _ = g2.req("/api/guardian/link", {"code": code})
        self.assertEqual((status, out["code"]), (400, "bad_code"))


class RolesAndApprovals(WebTestCase):
    def test_role_separation(self):
        s, g = self.client(), self.client()
        s.login(STU_BD, "student")
        g.login(GUARD_BD, "guardian")
        self.assertEqual(s.req("/api/guardian/overview")[0], 403)
        self.assertEqual(s.req("/api/guardian/decide", {"proposal_id": "x", "otp": "1", "approve": True})[0], 404)
        self.assertEqual(g.req("/api/state")[0], 403)
        self.assertEqual(g.req("/api/chat", {"message": "Pay my tuition"})[0], 404)

    def test_student_id_in_request_is_ignored(self):
        c = self.client()
        c.login(STU_NG, "student")
        out = c.req("/api/chat", {"message": "my balance", "student_id": "STU-BD-001"})[1]
        self.assertIn("NGN", [r["currency"] for r in out["cards"][0]["rows"]])
        self.assertEqual(c.req("/api/state?student_id=STU-BD-001")[1]["id"], "STU-NG-002")

    def test_guardian_cannot_see_unlinked_student(self):
        g = self.client()
        g.login(GUARD_BD, "guardian")
        ov = g.req("/api/guardian/overview")[1]
        self.assertEqual([x["id"] for x in ov["students"]], ["STU-BD-001"])
        out = g.req("/api/guardian/fund", {"student_id": "STU-NG-002", "amount": 1000})
        self.assertEqual(out[1]["code"], "forbidden")

    def test_two_party_approval_flow(self):
        s, g = self.client(), self.client()
        s.login(STU_BD, "student")
        g.login(GUARD_BD, "guardian")
        card = next(x for x in s.req("/api/chat", {"message": "Pay my tuition"})[1]["cards"] if x["type"] == "proposal")
        pid = card["proposal"]["proposal_id"]
        key = Handler.app.agent.proposals.key
        self.assertEqual(card["status"], "awaiting_guardian")
        status, out, _ = s.req("/api/confirm", {"proposal_id": pid, "token": card["token"], "otp": sandbox_otp(pid, key)})
        self.assertEqual((status, out["code"]), (403, "awaiting_guardian"))
        pend = g.req("/api/guardian/overview")[1]["pending"]
        self.assertEqual(len(pend), 1)
        self.assertNotIn("token", pend[0])
        self.assertEqual(g.req("/api/guardian/decide", {"proposal_id": pid, "otp": "000000", "approve": True})[1]["code"], "bad_otp")
        ok = g.req("/api/guardian/decide", {"proposal_id": pid, "otp": sandbox_otp("guardian:" + pid, key), "approve": True})[1]
        self.assertTrue(ok["ok"])
        status, out, _ = s.req("/api/confirm", {"proposal_id": pid, "token": card["token"], "otp": sandbox_otp(pid, key)})
        self.assertEqual(status, 200)
        self.assertTrue(out["ok"])

    def test_guardian_decline_blocks_payment(self):
        s, g = self.client(), self.client()
        s.login(STU_BD, "student")
        g.login(GUARD_BD, "guardian")
        card = next(x for x in s.req("/api/chat", {"message": "Pay my tuition"})[1]["cards"] if x["type"] == "proposal")
        pid, key = card["proposal"]["proposal_id"], Handler.app.agent.proposals.key
        g.req("/api/guardian/decide", {"proposal_id": pid, "otp": sandbox_otp("guardian:" + pid, key), "approve": False})
        out = s.req("/api/confirm", {"proposal_id": pid, "token": card["token"], "otp": sandbox_otp(pid, key)})[1]
        self.assertEqual(out["code"], "declined")

    def test_raising_permission_needs_password(self):
        c = self.client()
        c.login(STU_BD, "student")
        self.assertTrue(c.req("/api/settings", {"level": "read_only"})[1]["ok"])
        status, out, _ = c.req("/api/settings", {"level": "assisted"})
        self.assertEqual((status, out["code"]), (403, "reauth_required"))
        self.assertTrue(c.req("/api/settings", {"level": "assisted", "password": STU_BD[1]})[1]["ok"])

    def test_turning_off_guardian_approval_needs_password(self):
        c = self.client()
        c.login(STU_BD, "student")
        self.assertEqual(c.req("/api/settings", {"guardian_approval": False})[1]["code"], "reauth_required")
        self.assertFalse(c.req("/api/settings", {"guardian_approval": False, "password": STU_BD[1]})[1]["guardian_approval"])

    def test_new_quote_supersedes_old(self):
        c = self.client()
        c.login(STU_BD, "student")
        c.req("/api/chat", {"message": "Pay my tuition"})
        c.req("/api/chat", {"message": "Pay my tuition"})
        self.assertEqual(len(c.req("/api/state")[1]["pending"]), 1)

    def test_audit_is_scoped_to_the_user(self):
        a, b = self.client(), self.client()
        a.login(STU_BD, "student")
        b.login(STU_NG, "student")
        b.req("/api/chat", {"message": "Pay my tuition"})
        rows = a.req("/api/audit")[1]["entries"]
        self.assertTrue(rows)
        self.assertFalse(any(e["data"].get("student_id") == "STU-NG-002" for e in rows))


if __name__ == "__main__":
    unittest.main()


class NoDemoAccounts(WebTestCase):
    """The shipped application has no built-in accounts, and phone numbers are stored masked only."""

    NEW_STUDENT = {"role": "student", "name": "Afia Islam", "email": "afia.new@example.test", "password": "Green-Field-2026",
                   "home_country": "BD", "university_id": "MUT", "program": "BSc Computer Science", "phone": "01906032900"}

    def test_public_meta_lists_no_accounts(self):
        status, out, _ = self.client().req("/api/public/meta")
        self.assertEqual(status, 200)
        self.assertNotIn("demo_accounts", out)

    def test_pages_do_not_advertise_demo_accounts(self):
        for path in ("/", "/login", "/register"):
            body = self.client().req(path)[1]
            text = body.decode() if isinstance(body, bytes) else str(body)
            for bad in ("Demo accounts", "demo account", "sudoroute.demo", "Student#2026"):
                self.assertNotIn(bad, text, f"{bad!r} found on {path}")

    def test_fresh_app_has_no_users(self):
        self.assertEqual(App(None).users.users, {})

    def test_legacy_demo_users_are_removed_on_start(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            first = App(d)
            first.users.create(role="student", name="Old Demo", email="old@sudoroute.demo", password="Student#2026", student_id="STU-BD-001", demo=True)
            first.users.create(role="student", name="Real Person", email="real@example.test", password="Student#2026", student_id="STU-NG-002")
            self.assertIsNone(App(d).users.by_email("old@sudoroute.demo"))
            self.assertIsNotNone(App(d).users.by_email("real@example.test"))

    def test_owner_sees_own_phone_but_audit_log_and_others_do_not(self):
        c = self.client()
        status, out, _ = c.req("/api/auth/register", dict(self.NEW_STUDENT))
        self.assertEqual(status, 200, out)
        c.csrf = out["csrf"]
        state = c.req("/api/state")[1]
        self.assertEqual(state["phone"], "01906032900")
        self.assertEqual(state["phone_masked"], "019••••••00")
        self.assertNotIn("01906032900", json.dumps(Handler.app.audit.entries))   # PII never reaches the audit chain
        code = c.req("/api/guardian/invite", {})[1]["code"]
        g = self.client()
        gs, gout, _ = g.req("/api/auth/register", {"role": "guardian", "name": "Parent Person", "email": "parent@example.test", "password": "Green-Field-2026",
                                                   "relationship": "Father", "link_code": code, "phone": "+8801711000000"})
        self.assertEqual(gs, 200, gout)
        g.csrf = gout["csrf"]
        self.assertNotIn("01906032900", json.dumps(g.req("/api/guardian/overview")[1]))  # the guardian never gets the student's number

    def test_phone_is_required_and_validated(self):
        for bad in ("", "abc", "12"):
            status, out, _ = self.client().req("/api/auth/register", {**self.NEW_STUDENT, "phone": bad})
            self.assertEqual(status, 400, bad)
            self.assertIn("phone", out["fields"])

    def test_guardian_registers_with_masked_phone(self):
        status, out, _ = self.client().req("/api/auth/register", {"role": "guardian", "name": "Afia Islam", "email": "afia.g@example.test",
                                                                  "password": "Green-Field-2026", "relationship": "Mother", "phone": "+8801906032900"})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["user"]["phone_masked"], "+880••••••••00")
        self.assertEqual(out["user"]["phone"], "+8801906032900")


class AuditSurvivesRestartAndReset(unittest.TestCase):
    def test_audit_chain_is_persistent_and_reset_cannot_erase_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a = App(d, samples=True); helpers.seed_accounts(a)
            a.audit.append("probe_event", actor="test")
            n = len(a.audit.entries)
            b = App(d)  # a restart must keep the existing chain
            self.assertGreaterEqual(len(b.audit.entries), n)
            self.assertTrue(b.audit.verify()["valid"])
            b.reset()   # a sandbox reset must only add to it
            self.assertGreater(len(b.audit.entries), n)
            self.assertTrue(b.audit.verify()["valid"])

    def test_damaged_audit_file_is_reported_not_hidden(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            a = App(d); a.audit.append("probe_event", actor="test")
            path = os.path.join(d, "audit_log.jsonl")
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            lines[0] = lines[0].replace("sandbox_reset", "edited")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            self.assertFalse(App(d).audit.verify()["valid"])


class SandboxResetNeedsPassword(WebTestCase):
    def test_reset_requires_reauthentication(self):
        c = self.client(); c.login(STU_BD, "student")
        self.assertEqual(c.req("/api/sandbox/reset", {})[0], 403)
        self.assertEqual(c.req("/api/sandbox/reset", {"password": "wrong-password-1"})[0], 403)
        before = len(Handler.app.audit.entries)
        self.assertEqual(c.req("/api/sandbox/reset", {"password": STU_BD[1]})[0], 200)
        self.assertGreater(len(Handler.app.audit.entries), before - 1)


class NameAndPhoneFollowTheSignedInUser(WebTestCase):
    """Whoever signs in sees their own name and number everywhere. No fixed person exists in the live app."""

    def test_live_app_contains_no_pre_made_people(self):
        live = App(None)
        self.assertEqual(live.users.users, {})
        self.assertEqual(live.bank.students, {})
        self.assertEqual(live.bank.invoices, {})
        self.assertNotIn("Afia", json.dumps(live.bank.students) + json.dumps(live.bank.invoices))

    def test_another_person_gets_their_own_name_phone_and_sample_email(self):
        c = self.client()
        status, out, _ = c.req("/api/auth/register", {"role": "student", "name": "Priya Sharma", "email": "priya@example.test", "password": "Green-Field-2026",
                                                      "home_country": "BD", "university_id": "MUT", "program": "BSc Data Science", "phone": "+8801711223344"})
        self.assertEqual(status, 200, out)
        c.csrf = out["csrf"]
        state = c.req("/api/state")[1]
        self.assertEqual(state["name"], "Priya Sharma")
        self.assertEqual(state["phone"], "+8801711223344")
        everything = json.dumps(state)
        self.assertNotIn("Afia", everything)
        phish = [i for i in state["invoices"] if "PHISH" in i["id"]]
        self.assertEqual(len(phish), 1)
        self.assertIn("Priya Sharma", phish[0]["text"])
        status, reply, _ = c.req("/api/chat", {"message": "hello"})
        self.assertEqual(status, 200, reply)
        text = json.dumps(reply)
        self.assertIn("Priya", text)
        self.assertNotIn("Afia", text)
        self.assertIn(phish[0]["id"], text)   # the suggestion chip points at her own sample e-mail
