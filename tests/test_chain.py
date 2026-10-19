"""On-chain anchoring (OpenTimestamps → Bitcoin) with a fake calendar server; no network needed."""
import hashlib
import os
import unittest
import urllib.error

from tests.helpers import STU_BD  # noqa: F401  (sets test environment)
from sudoroute.chain import anchor
from sudoroute.chain.anchor import Anchors, OTS_MAGIC, canonical, cert_hash


class FakeCalendar:
    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def __call__(self, url, data):
        self.calls.append((url, data))
        if any(f in url for f in self.fail):
            raise urllib.error.URLError("down")
        return b"\xf0\x10" + b"\x11" * 16 + b"\x08\xf1\x04" + b"\x00" * 8  # opaque timestamp bytes


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("TS_ANCHOR")
        os.environ["TS_ANCHOR"] = "1"

    def tearDown(self):
        os.environ["TS_ANCHOR"] = self._env or "0"

    def test_record_hash_and_ots_file(self):
        cal = FakeCalendar()
        a = Anchors(post=cal)
        pub = a.record("SR1.abc.def", "f" * 64, 12, "kid1")
        h = pub["cert_sha256"]
        self.assertEqual(h, hashlib.sha256(b"SR1.abc.def").hexdigest())
        self.assertEqual(pub["status"], "queued")
        out = a.submit(h)
        self.assertEqual(out["status"], "submitted")
        digest = hashlib.sha256(a.record_bytes(h)).digest()
        self.assertEqual(digest.hex(), out["digest"])                       # the downloadable record IS what was stamped
        self.assertEqual(cal.calls[0][1], digest)                           # only the 32-byte hash leaves the server
        ots = a.ots(h)
        self.assertTrue(ots.startswith(OTS_MAGIC + b"\x01\x08" + digest))   # valid DetachedTimestampFile header
        self.assertEqual(len(out["calendars"]), len(anchor.CALENDARS))

    def test_one_calendar_down_still_anchors(self):
        a = Anchors(post=FakeCalendar(fail=("a.pool",)))
        h = a.record("SR1.x.y", None, 0, "k")["cert_sha256"]
        self.assertEqual(a.submit(h)["status"], "submitted")

    def test_offline_is_reported_not_faked(self):
        a = Anchors(post=FakeCalendar(fail=("http",)))
        h = a.record("SR1.x.y", None, 0, "k")["cert_sha256"]
        out = a.submit(h)
        self.assertEqual(out["status"], "not_submitted"); self.assertIsNone(a.ots(h)); self.assertTrue(out["error"])

    def test_disabled(self):
        os.environ["TS_ANCHOR"] = "0"
        a = Anchors(post=FakeCalendar())
        h = a.record("SR1.x.y", None, 0, "k")["cert_sha256"]
        self.assertEqual(a.submit(h)["status"], "disabled")

    def test_record_contains_no_personal_data(self):
        a = Anchors(post=FakeCalendar())
        h = a.record("SR1.secret-claims.sig", "a" * 64, 3, "k")["cert_sha256"]
        rec = a.record_bytes(h).decode()
        self.assertNotIn("secret-claims", rec)
        self.assertEqual(set(canonical_keys(rec)), {"v", "cert_sha256", "audit_head", "audit_entries", "issuer_kid", "created"})

    def test_persistence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "anchors.json")
            a = Anchors(p, post=FakeCalendar())
            h = a.record("SR1.p.q", None, 0, "k")["cert_sha256"]; a.submit(h)
            self.assertEqual(Anchors(p).public(h)["status"], "submitted")


def canonical_keys(text):
    import json
    return json.loads(text).keys()


class AnchorHttpTests(unittest.TestCase):
    def test_certificate_issue_creates_anchor_and_endpoints_work(self):
        from tests.test_v3 import _ServerCase
        case = type("C", (_ServerCase,), {})
        case.setUpClass()
        try:
            c, st, out = case.register(case, "chain@example.test", university_name="Meridian University of Technology",
                                       guardian_name="Ashraful Islam", guardian_email="chain-dad@example.test")
            self.assertEqual(st, 200, out)
            st, cert, _ = c.req("/api/certificates/issue", {"kind": "funds", "at_least": 100, "currency": "USD"})
            self.assertEqual(st, 200, cert)
            h = cert["anchor"]; self.assertEqual(h, cert_hash(cert["code"]))
            p = case.Client(case.port)
            st, a, _ = p.req("/api/public/anchor?h=" + h)
            self.assertIn(a["status"], ("queued", "disabled")); self.assertEqual(a["record"]["cert_sha256"], h)
            st, a2, _ = p.req("/api/public/anchor?code=" + cert["code"])
            self.assertEqual(a2["cert_sha256"], h)
            st, _, _ = p.req("/api/public/anchor/ots?h=" + h)
            self.assertEqual(st, 404)                                      # no proof without a calendar
            st, _, _ = p.req("/api/public/anchor?h=nothex")
            self.assertEqual(st, 400)
            other, st, _ = case.register(case, "chain2@example.test", university_name="Meridian University of Technology",
                                         guardian_name="X Y", guardian_email="chain2-dad@example.test")
            st, out, _ = other.req("/api/chain/retry", {"h": h})
            self.assertEqual(st, 404)                                      # can't touch someone else's anchor
            st, s, _ = p.req("/api/public/chain")
            self.assertGreaterEqual(s["anchors"], 1)
        finally:
            case.tearDownClass()


if __name__ == "__main__":
    unittest.main()
