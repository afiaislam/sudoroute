"""SudoRoute web server: pages, authentication and the JSON API (standard library only).

    python run.py                 # http://127.0.0.1:8000
    python run.py --port 9000 --host 0.0.0.0
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .chain.anchor import Anchors, cert_hash
from .feedback import FeedbackStore
from .util import clean_phone, mask_phone
from . import config
from .agent import llm
from .agent.core import SudoRouteAgent
from .sandbox.bank import HOME_CURRENCY, SandboxBank
from .sandbox.reference_data import COUNTRY_RULES, UNIVERSITIES
from .security import permissions, totp
from .security.audit import AuditLog
from .security.auth import (EMAIL_RE, IP_LOCK_AFTER, LoginGuard, SessionStore, UserStore, burn_time,
                            normalise_email, password_problems, verify_password)
from .security.proposals import ProposalStore
from .security.certificates import Issuer
from .sandbox import fx_live, registry
from .sandbox.reference_data import STUDY_COUNTRIES

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def _asset_version() -> str:
    """One version string for all static files, so they can be cached for a year and still never go stale."""
    h = hashlib.sha256()
    for root, _, files in os.walk(os.path.join(WEB_DIR, "static")):
        for f in sorted(files):
            with open(os.path.join(root, f), "rb") as fh:
                h.update(f.encode() + fh.read())
    return h.hexdigest()[:10]


ASSET_V = _asset_version()
COMPRESSIBLE = ("text/", "application/json", "image/svg+xml")
MAX_BODY = 64 * 1024
MAX_PHOTO_BODY = 320 * 1024  # only /api/profile/photo may send a (resized) image
RATE_WINDOW, RATE_MAX = 10.0, 120
COOKIE = "ts_session"
DEMO_MODE = os.environ.get("TS_DEMO_MODE", "1") != "0"
SECURE_COOKIES = os.environ.get("TS_SECURE_COOKIES", "0") == "1"
LAB_RUNS: dict[str, float] = {}
LAB_MIN_INTERVAL = 15
RELATIONSHIPS = ["Mother", "Father", "Parent", "Sibling", "Relative", "Sponsor", "Legal guardian"]

_BASELINES = None
PUBLIC_ASKS: dict = defaultdict(deque)
JUDGE_STARTS: dict = defaultdict(deque)
FORM_POSTS: dict = defaultdict(deque)
FORM_PER_IP_HOUR = 10
PUBLIC_ASK_PER_HOUR = 40


def _lang(data: dict) -> str:
    v = str(data.get("lang", "en"))[:2]
    return v if v in llm.LANG_NAMES else "en"


def _baselines() -> dict:
    """Computed once per process: it replays scenarios on a private agent, never on live accounts."""
    global _BASELINES
    if _BASELINES is None:
        from .benchmark.baselines import run
        r = run()
        r.pop("route_rows", None)
        _BASELINES = r
    return _BASELINES


def public_user(u: dict) -> dict:
    keys = ("id", "role", "name", "email", "created", "student_id", "relationship", "students",
            "phone", "phone_masked", "password_changed", "photo", "judge")
    return {k: u[k] for k in keys if k in u}


JUDGE_TTL = 24 * 3600      # judge accounts and their private sandboxes are removed after a day
MAX_WORLDS = 150           # private sandboxes kept in memory (least recently used are rebuilt on demand)
JUDGE_PER_IP_HOUR = 8


class World:
    """A private sandbox (bank, FX market, clock, agent) for one judge's student and guardian.

    Judges who press "Try as judge" each get their own world, so moving the sandbox clock, paying or
    resetting never affects anyone else. The audit chain, certificate issuer and on-chain anchors are shared.
    """

    def __init__(self, app: "App", wid: str):
        self.app, self.id = app, wid
        self.touched = time.time()
        self.lock = threading.RLock()  # each judge's sandbox has its own lock: one slow AI reply never blocks another judge
        self.build()

    def build(self):
        app = self.app
        self.bank = SandboxBank(samples=False, spots=fx_live.STATE["spots"])
        self.agent = SudoRouteAgent(self.bank, app.audit, ProposalStore())
        self.agent.issuer, self.agent.anchors = app.issuer, app.anchors
        self.agent.sms_out = _sms_hook(app, self.agent)
        for u in app.users.users.values():
            if u.get("world") == self.id and u["role"] == "student" and u.get("profile"):
                self.bank.create_student(student_id=u["student_id"], name=u["name"], **u["profile"])
                if (u.get("totp") or {}).get("secret"):
                    self.agent.totp[u["student_id"]] = {"secret": u["totp"]["secret"], "last_step": None}
        self.sync()

    def sync(self):
        for s in self.bank.students.values():
            s["guardians"] = []
        for g in self.app.users.users.values():
            if g["role"] == "guardian" and g.get("world") == self.id:
                for sid in g.get("students", []):
                    if sid in self.bank.students:
                        self.bank.students[sid]["guardians"].append(
                            {"id": g["id"], "name": g["name"], "relationship": g.get("relationship", ""),
                             "phone_masked": g.get("phone_masked", "")})


def _sms_hook(app, agent):
    """Real SMS to the account's own registered number, when SMS_PROVIDER is configured (sudoroute/sms.py)."""
    from . import sms

    def out(kind, ref, text):
        if not sms.provider():
            return
        if kind == "student":
            st = agent.bank.students.get(ref) or {}
            phone, cc = st.get("phone"), st.get("home_country")
        else:
            u = app.users.get(ref) or {}
            linked = [agent.bank.students[x] for x in u.get("students", []) if x in agent.bank.students]
            phone, cc = u.get("phone"), (linked[0]["home_country"] if linked else None)
        sms.send(phone, cc, text, on_result=lambda r: app.audit.append("sms_delivery", actor="sms", sim_time=agent.bank.now.isoformat(),
                                                                       kind=kind, **r))
    return out


class WorldView:
    """What a request handler sees as `self.app` for a judge: the shared app, with that judge's bank and agent."""

    def __init__(self, base: "App", world: World):
        self._base, self._world = base, world
        self.agent, self.bank = world.agent, world.bank
        self.lock = world.lock

    def __getattr__(self, name):
        return getattr(self._base, name)

    def reset(self):
        self._world.build()
        self.agent, self.bank = self._world.agent, self._world.bank
        self._base.audit.append("sandbox_reset", actor="system", sim_time=self.bank.now.isoformat(), world=self._world.id)

    def sync_links(self):
        self._world.sync()


class App:
    def __init__(self, data_dir: str | None = None, samples: bool = False):
        """samples=True adds the two scripted sample students (tests and evidence only; the website never does)."""
        self.samples = samples
        self.lock = threading.RLock()
        self.data_dir = data_dir
        self.users = UserStore(os.path.join(data_dir, "users.json") if data_dir else None)
        self.sessions = SessionStore()
        self.guard = LoginGuard()
        registry.load(os.path.join(data_dir, "universities.json") if data_dir else None)
        self.issuer = Issuer(os.path.join(data_dir, "issuer_ed25519.key") if data_dir else None)
        self.feedback = FeedbackStore(os.path.join(data_dir, "pilot_feedback.json") if data_dir else None)
        self.anchors = Anchors(os.path.join(data_dir, "anchors.json") if data_dir else None)
        self.worlds: dict[str, World] = {}
        from . import inbox
        self.messages = inbox.Inbox(os.path.join(data_dir, "contact_messages.json") if data_dir else None)
        self.subscribers = inbox.Inbox(os.path.join(data_dir, "newsletter.json") if data_dir else None)
        self._drop_legacy_demo_users()
        self.reset()

    # ------------------------------------------------------------ state
    def _drop_legacy_demo_users(self):
        """Older builds shipped demo accounts. Remove any that are still in a persisted user store."""
        stale = [uid for uid, u in self.users.users.items() if u.get("demo")]
        for uid in stale:
            del self.users.users[uid]
        if stale:
            self.users.save()

    def reset(self):
        with self.lock:
            self.bank = SandboxBank(samples=self.samples, spots=fx_live.STATE["spots"])
            if not hasattr(self, "audit"):  # keep one append-only audit chain for the whole life of the data folder
                self.audit = AuditLog(os.path.join(self.data_dir, "audit_log.jsonl") if self.data_dir else None)
            self.agent = SudoRouteAgent(self.bank, self.audit, ProposalStore())
            self.agent.issuer = self.issuer
            self.agent.anchors = self.anchors
            self.agent.sms_out = _sms_hook(self, self.agent)
            for u in self.users.users.values():  # authenticator apps survive restarts and sandbox resets
                if u["role"] == "student" and not u.get("world") and (u.get("totp") or {}).get("secret"):
                    self.agent.totp[u["student_id"]] = {"secret": u["totp"]["secret"], "last_step": None}
            for u in self.users.users.values():
                if u["role"] == "student" and u.get("profile") and not u.get("world") \
                        and u["student_id"] not in self.bank.students:
                    self.bank.create_student(student_id=u["student_id"], name=u["name"], **u["profile"])
            self.sync_links()
            self.audit.append("sandbox_reset", actor="system", sim_time=self.bank.now.isoformat())

    def sync_links(self):
        for s in self.bank.students.values():
            s["guardians"] = []
        for g in self.users.users.values():
            if g["role"] != "guardian":
                continue
            for sid in g.get("students", []):
                if sid in self.bank.students:
                    self.bank.students[sid]["guardians"].append(
                        {"id": g["id"], "name": g["name"], "relationship": g.get("relationship", ""),
                         "phone_masked": g.get("phone_masked", "")})

    # ------------------------------------------------------------ private judge sandboxes
    def world(self, wid: str) -> World:
        with self.lock:
            w = self.worlds.get(wid)
            if w is None:
                if len(self.worlds) >= MAX_WORLDS:
                    oldest = min(self.worlds.values(), key=lambda x: x.touched)
                    del self.worlds[oldest.id]
                w = self.worlds[wid] = World(self, wid)
            w.touched = time.time()
            return w

    def purge_judges(self) -> int:
        cutoff = time.time() - JUDGE_TTL
        with self.lock:
            old = [uid for uid, u in self.users.users.items() if u.get("judge") and u.get("created", 0) < cutoff]
            for uid in old:
                self.worlds.pop(self.users.users[uid].get("world"), None)
                del self.users.users[uid]
            if old:
                self.users.save()
        return len(old)

    def create_judge(self) -> dict:
        """One click: a private sandbox with a student (with tuition due) and a linked guardian."""
        self.purge_judges()
        wid = "J" + secrets.token_hex(5)
        pw = lambda: "Judge#" + secrets.token_urlsafe(9)  # noqa: E731
        with self.lock:
            n = 900 + sum(1 for u in self.users.users.values() if u.get("judge") and u["role"] == "student")
            sid = f"STU-BD-{n}"
            while self.users.student_user(sid):
                n += 1
                sid = f"STU-BD-{n}"
            profile = {"home_country": "BD", "university_id": "MUT", "program": "BSc Computer Science, Year 2",
                       "phone": "01700000000", "phone_masked": mask_phone("01700000000")}
            student = self.users.create(role="student", name="Md Soron", email=f"student.{wid.lower()}@judge.invalid",
                                        password=pw(), student_id=sid, profile=profile, world=wid, judge=True,
                                        guardian_invite={"name": "Mst Nishi", "email": f"parent.{wid.lower()}@judge.invalid",
                                                         "status": "accepted", "created": int(time.time())})
            guardian = self.users.create(role="guardian", name="Mst Nishi", email=f"parent.{wid.lower()}@judge.invalid",
                                         password=pw(), relationship="Mother", students=[sid], world=wid, judge=True,
                                         phone="01800000000", phone_masked=mask_phone("01800000000"))
            self.world(wid)
            self.audit.append("judge_sandbox_created", actor="system", sim_time=self.bank.now.isoformat(), world=wid,
                              student_id=sid, user_id=student["id"])
        return {"student": student, "guardian": guardian, "world": wid}

    def next_student_id(self, cc: str) -> str:
        n = 100 + sum(1 for u in self.users.users.values() if u["role"] == "student")
        while any(sid.endswith(f"-{n}") for sid in self.bank.students):
            n += 1
        return f"STU-{cc}-{n}"


class Handler(BaseHTTPRequestHandler):
    app: App = None
    hits: dict = defaultdict(deque)
    server_version = "SudoRoute/2.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    # ------------------------------------------------------------ plumbing
    @property
    def ip(self) -> str:
        return self.client_address[0]

    def _secure(self) -> bool:
        return SECURE_COOKIES or self.headers.get("X-Forwarded-Proto", "") == "https"

    def _headers(self, status: int, ctype: str, extra: dict | None = None, cache: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' "
                         "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: blob: https://images.unsplash.com; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; "
                         "object-src 'none'")
        if self._secure():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, status: int, ctype: str, body: bytes, extra: dict | None = None, cache: str = "no-store"):
        extra = dict(extra or {})
        if len(body) > 1024 and ctype.startswith(COMPRESSIBLE) and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = gzip.compress(body, 6)
            extra["Content-Encoding"] = "gzip"
            extra["Vary"] = "Accept-Encoding"
        extra["Content-Length"] = str(len(body))
        self._headers(status, ctype, extra, cache)
        self.wfile.write(body)

    def _json(self, obj, status: int = 200, extra: dict | None = None):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self._send(status, "application/json; charset=utf-8", body, extra)

    def _err(self, status: int, message: str, code: str = "error"):
        return self._json({"ok": False, "error": message, "code": code}, status)

    def _redirect(self, location: str):
        self._headers(302, "text/plain", {"Location": location})

    def _body(self, limit: int = MAX_BODY) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("Request too large.")
        ctype = self.headers.get("Content-Type", "")
        if n and "application/json" not in ctype:
            raise ValueError("Send JSON.")
        data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if not isinstance(data, dict):
            raise ValueError("Send a JSON object.")
        return data

    def _rate_limited(self) -> bool:
        q = self.hits[self.ip]
        now = time.monotonic()
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        q.append(now)
        return len(q) > RATE_MAX

    def _token(self) -> str | None:
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c[COOKIE].value if COOKIE in c else None

    def _session(self):
        self.app = type(self).app  # never carry a previous request's world over a kept-alive connection
        sess = self.app.sessions.get(self._token())
        if not sess:
            return None, None
        user = self.app.users.get(sess["user_id"])
        if user and user.get("world"):
            self.app = WorldView(type(self).app, self.app.world(user["world"]))
        return (sess, user) if user else (None, None)

    def _cookie(self, token: str, max_age: int) -> dict:
        v = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"
        return {"Set-Cookie": v + ("; Secure" if self._secure() else "")}

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc == self.headers.get("Host", "")

    def _audit(self, event: str, **data):
        self.app.audit.append(event, actor="auth", sim_time=self.app.bank.now.isoformat(), ip=self.ip, **data)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        if self._rate_limited():
            return self._err(429, "Too many requests. Wait a few seconds.", "rate_limited")
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        path = url.path.rstrip("/") or "/"
        try:
            pages = {"/": "index.html", "/login": "auth.html", "/register": "auth.html", "/verify": "verify.html",
                     "/security-lab": "lab.html", "/accuracy": "accuracy.html", "/offline": "offline.html",
                     "/help": "help.html", "/contact": "contact.html", "/pricing": "pricing.html", "/legal": "legal.html"}
            if path in pages:
                return self._file(pages[path], "text/html; charset=utf-8")
            if path in ("/app", "/guardian"):
                sess, user = self._session()
                want = "student" if path == "/app" else "guardian"
                if not user or user["role"] != want:
                    return self._redirect(f"/login?role={want}")
                return self._file("student.html" if want == "student" else "guardian.html",
                                  "text/html; charset=utf-8")
            if path == "/sw.js":  # served from the root so it can cover the whole site; always revalidated
                with open(os.path.join(WEB_DIR, "static", "sw.js"), "rb") as f:
                    return self._send(200, "text/javascript; charset=utf-8", f.read(), cache="no-cache")
            if path == "/manifest.webmanifest":
                with open(os.path.join(WEB_DIR, "static", "manifest.json"), "rb") as f:
                    return self._send(200, "application/manifest+json; charset=utf-8", f.read(), cache="no-cache")
            if path.startswith("/static/"):
                name = path[len("/static/"):]
                if not re.fullmatch(r"(img/|video/)?[a-z0-9_-]+\.(css|js|svg|json|webp|png|jpg|webm|mp4|vtt)", name):
                    return self._err(404, "Not found.")
                ctype = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "json": "application/json",
                         "webp": "image/webp", "png": "image/png", "jpg": "image/jpeg", "webm": "video/webm", "mp4": "video/mp4",
                         "vtt": "text/vtt"}[name.rsplit(".", 1)[1]]
                return self._file(os.path.join("static", name), ctype if ctype.startswith(("image/", "video/")) and "svg" not in ctype
                                  else ctype + "; charset=utf-8")
            if path.startswith("/api/"):
                return self._api_get(path, q)
            return self._err(404, "Not found.")
        except (KeyError, ValueError) as e:
            return self._err(400, str(e).strip("'\""))

    def _file(self, rel: str, ctype: str):
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            return self._err(404, "Not found.")
        with open(full, "rb") as f:
            body = f.read()
        if rel.endswith(".html"):
            # Point every page at versioned static URLs; HTML itself is always revalidated.
            body = re.sub(rb'(/static/(?:img/|video/)?[a-z0-9_-]+\.(?:css|js|svg|webp|png|webm|mp4|vtt))(?=["\'])', rb"\1?v=" + ASSET_V.encode(), body)
            return self._send(200, ctype + ("" if "charset" in ctype else ""), body, cache="no-cache")
        if ctype.startswith("video/"):
            return self._video(body, ctype)
        etag = '"' + ASSET_V + "-" + hashlib.sha1(body).hexdigest()[:12] + '"'
        if self.headers.get("If-None-Match") == etag:
            return self._headers(304, ctype, {"ETag": etag}, "public, max-age=31536000, immutable")
        self._send(200, ctype, body, {"ETag": etag}, cache="public, max-age=31536000, immutable")

    def _video(self, body: bytes, ctype: str):
        """Serve a video with byte-range support so the player can seek."""
        size = len(body)
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        base = {"Accept-Ranges": "bytes"}
        if not m or (not m.group(1) and not m.group(2)):
            self._headers(200, ctype, {**base, "Content-Length": str(size)}, "public, max-age=86400")
            self.wfile.write(body)
            return None
        start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
        end = min(size - 1, int(m.group(2))) if m.group(1) and m.group(2) else size - 1
        if start >= size or start > end:
            return self._headers(416, ctype, {**base, "Content-Range": f"bytes */{size}"})
        chunk = body[start:end + 1]
        self._headers(206, ctype, {**base, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(len(chunk))},
                      "public, max-age=86400")
        self.wfile.write(chunk)
        return None

    def _api_get(self, path: str, q: dict):
        app = self.app
        if path == "/api/health":
            return self._json({"ok": True, "sim_date": app.bank.now.date().isoformat(), "ai": llm.status()})
        if path == "/api/public/meta":
            return self._json({
                "universities": [registry.public(u) for u in UNIVERSITIES.values() if u.get("verified", True)],
                "study_countries": [{"code": k, "name": v["name"], "currency": v["currency"]}
                                    for k, v in sorted(STUDY_COUNTRIES.items(), key=lambda kv: kv[1]["name"])],
                "countries": [{"code": c, "name": COUNTRY_RULES[c]["name"], "currency": HOME_CURRENCY[c]}
                              for c in HOME_CURRENCY],
                "relationships": RELATIONSHIPS, "ai": llm.status(), "demo_mode": DEMO_MODE, "fx": fx_live.public()})
        if path == "/api/public/fx":
            return self._json(fx_live.public())
        if path == "/api/public/benchmark":
            from .benchmark.scam_shield import run as run_benchmark
            return self._json(run_benchmark())
        if path == "/api/public/chain":
            return self._json(self.app.anchors.summary())
        if path in ("/api/public/anchor", "/api/public/anchor/record", "/api/public/anchor/ots"):
            h = str(q.get("h", "")).lower() or (cert_hash(q["code"]) if q.get("code") else "")
            if not re.fullmatch(r"[0-9a-f]{64}", h):
                return self._err(400, "Give a certificate hash (h) or code.")
            if path.endswith("/record"):
                body = self.app.anchors.record_bytes(h)
                if body is None:
                    return self._err(404, "No anchor for this certificate.")
                return self._send(200, "application/json; charset=utf-8", body,
                                  {"Content-Disposition": f'attachment; filename="sudoroute-anchor-{h[:12]}.json"'}, cache="no-store")
            if path.endswith("/ots"):
                body = self.app.anchors.ots(h)
                if body is None:
                    return self._err(404, "No on-chain proof yet for this certificate.")
                return self._send(200, "application/octet-stream", body,
                                  {"Content-Disposition": f'attachment; filename="sudoroute-anchor-{h[:12]}.json.ots"'}, cache="no-store")
            return self._json(self.app.anchors.public(h))
        if path == "/api/public/pilot":
            return self._json(self.app.feedback.summary())
        if path == "/api/public/baselines":
            return self._json(_baselines())
        if path == "/api/public/issuer":
            return self._json(app.issuer.info())
        sess, user = self._session()
        if not user:
            return self._err(401, "Your session has ended. Sign in again.", "unauthenticated")
        app = self.app  # a judge's private sandbox, if any
        if path == "/api/auth/me":
            return self._json({"ok": True, "user": public_user(user), "csrf": sess["csrf"],
                               "idle_timeout": 1800, "session_started": int(sess["created"])})
        with app.lock:
            if user["role"] == "student":
                sid = user["student_id"]
                if path == "/api/state":
                    st = app.agent.state(sid)
                    st["user"] = public_user(user)
                    st["guardian_invite"] = user.get("guardian_invite")
                    st["totp_enabled"] = sid in app.agent.totp
                    return self._json(st)
                if path == "/api/dashboard":
                    return self._json(app.agent.dashboard(sid))
                if path == "/api/insights":
                    return self._json(app.agent.insights(sid))
                if path == "/api/certificates":
                    return self._json({"records": app.agent.payment_records(sid),
                                       "issued": app.agent.certificates.get(sid, []), "issuer": app.issuer.info()})
                if path == "/api/audit":
                    return self._json({"verify": app.audit.verify(),
                                       "entries": app.agent.audit_for(sid, user["id"], int(q.get("n", 40)))})
            if user["role"] == "guardian":
                if path == "/api/guardian/overview":
                    students = [app.agent.guardian_view(sid) for sid in user.get("students", [])
                                if sid in app.bank.students]
                    return self._json({"user": public_user(user), "students": students,
                                       "pending": app.agent.pending_for_guardian(user["id"]),
                                       "inbox": app.agent.guardian_inbox.get(user["id"], [])[-6:],
                                       "funding": app.agent.guardian_funding.get(user["id"], [])[-10:],
                                       "sim_date": app.bank.now.date().isoformat(), "ai": llm.status()})
                if path == "/api/audit":
                    rows = []
                    for sid in user.get("students", []):
                        rows += app.agent.audit_for(sid, None, 40)
                    rows += app.agent.audit_for(None, user["id"], 20)
                    rows = sorted({e["seq"]: e for e in rows}.values(), key=lambda e: e["seq"])[-50:]
                    return self._json({"verify": app.audit.verify(), "entries": rows})
        return self._err(403 if path.startswith("/api/") else 404, "Not allowed for this account.", "forbidden")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        if self._rate_limited():
            return self._err(429, "Too many requests. Wait a few seconds.", "rate_limited")
        path = urlparse(self.path).path.rstrip("/")
        if not self._same_origin():
            return self._err(403, "Cross-site request blocked.", "bad_origin")
        try:
            data = self._body(MAX_PHOTO_BODY if path == "/api/profile/photo" else MAX_BODY)
        except (ValueError, json.JSONDecodeError) as e:
            return self._err(400, str(e))
        try:
            if path == "/api/auth/login":
                return self._login(data)
            if path == "/api/auth/register":
                return self._register(data)
            if path == "/api/public/security-lab/run":
                last = LAB_RUNS.get(self.ip, 0)
                if time.time() - last < LAB_MIN_INTERVAL:
                    return self._err(429, f"The lab was just run from your network. Try again in "
                                          f"{int(LAB_MIN_INTERVAL - (time.time() - last)) + 1} s.", "rate_limited")
                LAB_RUNS[self.ip] = time.time()
                from .security.redteam import run_lab
                return self._json({"ok": True, **run_lab()})
            if path == "/api/public/ask":
                q = str(data.get("question", ""))[:600].strip()
                if not q:
                    return self._err(400, "Type a question first.")
                hist = PUBLIC_ASKS[self.ip]
                now = time.time()
                while hist and now - hist[0] > 3600:
                    hist.popleft()
                if len(hist) >= PUBLIC_ASK_PER_HOUR or (hist and now - hist[-1] < 1.5):
                    return self._err(429, "Please wait a moment before asking again.", "rate_limited")
                hist.append(now)
                from .agent import assist
                return self._json({"ok": True, **assist.public_answer(q, _lang(data), use_llm=self.app.agent.use_llm)})
            if path == "/api/public/judge":
                hist = JUDGE_STARTS[self.ip]
                now = time.time()
                while hist and now - hist[0] > 3600:
                    hist.popleft()
                if len(hist) >= JUDGE_PER_IP_HOUR:
                    return self._err(429, "Too many demo sandboxes from this network. Try again later.", "rate_limited")
                hist.append(now)
                made = self.app.create_judge()
                self.app.sessions.destroy(self._token())
                token, sess = self.app.sessions.create(made["student"], self.ip)
                self.app.audit.append("judge_login", actor="auth", sim_time=self.app.bank.now.isoformat(), ip=self.ip,
                                      user_id=made["student"]["id"], world=made["world"])
                return self._json({"ok": True, "csrf": sess["csrf"], "redirect": "/app#overview?judge"},
                                  extra=self._cookie(token, 12 * 3600))
            if path in ("/api/public/contact", "/api/public/newsletter"):
                from . import inbox
                hist = FORM_POSTS[self.ip]
                now = time.time()
                while hist and now - hist[0] > 3600:
                    hist.popleft()
                if len(hist) >= FORM_PER_IP_HOUR:
                    return self._err(429, "Too many messages from this network. Please try again later.", "rate_limited")
                if path == "/api/public/contact":
                    item, errors = inbox.contact(data)
                    if errors.get("_bot"):
                        return self._json({"ok": True})  # quietly drop bots
                    if errors:
                        return self._json({"ok": False, "code": "invalid", "error": "Please check the highlighted fields.",
                                           "fields": errors}, 400)
                    hist.append(now)
                    saved = self.app.messages.add(item)
                    return self._json({"ok": True, "id": saved["id"]})
                item, err = inbox.newsletter(data)
                if err == "rejected":
                    return self._json({"ok": True})
                if err:
                    return self._err(400, err, "invalid")
                hist.append(now)
                if any(x.get("email") == item["email"] for x in self.app.subscribers.items):
                    return self._json({"ok": True, "already": True})
                self.app.subscribers.add(item)
                return self._json({"ok": True})
            if path == "/api/public/verify":
                res = self.app.issuer.verify(str(data.get("code", ""))[:8000])
                return self._json({"ok": True, **res, "issuer": self.app.issuer.info()})
            sess, user = self._session()
            if not user:
                return self._err(401, "Your session has ended. Sign in again.", "unauthenticated")
            if self.headers.get("X-CSRF-Token", "") != sess["csrf"]:
                return self._err(403, "Security token missing or wrong. Reload the page.", "csrf")
            if path == "/api/judge/switch":
                if not user.get("judge"):
                    return self._err(403, "Only judge demo accounts can switch roles.", "forbidden")
                other = next((u for u in self.app.users.users.values()
                              if u.get("world") == user["world"] and u["role"] != user["role"]), None)
                if not other:
                    return self._err(404, "No partner account in this sandbox.")
                self.app.sessions.destroy(self._token())
                token, sess2 = self.app.sessions.create(other, self.ip)
                self._audit("judge_switch_role", user_id=other["id"], role=other["role"], world=user["world"])
                return self._json({"ok": True, "csrf": sess2["csrf"],
                                   "redirect": ("/app#payments?judge" if other["role"] == "student" else "/guardian#approvals?judge")},
                                  extra=self._cookie(token, 12 * 3600))
            if path == "/api/auth/logout":
                self.app.sessions.destroy(self._token())
                self._audit("logout", user_id=user["id"], student_id=user.get("student_id"))
                return self._json({"ok": True}, extra=self._cookie("", 0))
            if path == "/api/auth/password":
                return self._change_password(user, data)
            if path == "/api/feedback":
                try:
                    return self._json(self.app.feedback.submit(user, data))
                except ValueError as e:
                    return self._err(400, str(e))
            if path == "/api/profile/photo":
                return self._photo(user, data)
            # Read-only AI helpers call the model without holding the sandbox lock, so a slow model never
            # freezes the rest of the page (balances, approvals, the phone) while it writes.
            if user["role"] == "student" and path in ("/api/brief", "/api/email-draft"):
                return self._student_post(path, user, data)
            if user["role"] == "guardian" and path == "/api/guardian/ask":
                return self._guardian_post(path, user, data)
            with self.app.lock:
                if path == "/api/sandbox/advance" and DEMO_MODE:
                    return self._json(self.app.agent.advance(max(1, min(60, int(data.get("days", 1))))))
                if path == "/api/sandbox/reset" and DEMO_MODE:
                    if not self._check_password(user, data.get("password")):
                        return self._err(403, "Enter your password to reset the sandbox.", "reauth_required")
                    self._audit("sandbox_reset_requested", user_id=user["id"], role=user["role"])
                    self.app.reset()
                    return self._json({"ok": True})
                if user["role"] == "student":
                    return self._student_post(path, user, data)
                if user["role"] == "guardian":
                    return self._guardian_post(path, user, data)
            return self._err(404, "Not found.")
        except (KeyError, ValueError, TypeError) as e:
            return self._err(400, str(e).strip("'\""))

    # ------------------------------------------------------------ auth
    def _login(self, data: dict):
        email = normalise_email(str(data.get("email", "")))[:200]
        password = str(data.get("password", ""))[:200]
        role = str(data.get("role", ""))
        wait = self.app.guard.locked("ip:" + self.ip, IP_LOCK_AFTER) or self.app.guard.locked("email:" + email)
        if wait:
            self._audit("login_blocked_locked", email=email)
            return self._err(429, f"Too many failed attempts. Try again in {max(1, wait // 60)} minute(s).", "locked")
        user = self.app.users.by_email(email)
        ok = verify_password(password, user["password"]) if user else (burn_time(password) or False)
        if not ok or user["role"] != role:
            self.app.guard.fail("email:" + email)
            self.app.guard.fail("ip:" + self.ip, IP_LOCK_AFTER)
            self._audit("login_failed", email=email, user_id=user["id"] if user else None,
                        student_id=user.get("student_id") if user else None)
            return self._err(401, "That e-mail, password or account type doesn't match. Check and try again.",
                             "bad_credentials")
        self.app.guard.success("email:" + email)
        self.app.sessions.destroy(self._token())  # rotate: never reuse a pre-login session
        token, sess = self.app.sessions.create(user, self.ip)
        self._audit("login_succeeded", user_id=user["id"], student_id=user.get("student_id"), role=user["role"])
        return self._json({"ok": True, "user": public_user(user), "csrf": sess["csrf"],
                           "redirect": "/app" if user["role"] == "student" else "/guardian"},
                          extra=self._cookie(token, 12 * 3600))

    def _register(self, data: dict):
        app = self.app
        if app.guard.locked("reg:" + self.ip, 10):
            return self._err(429, "Too many sign-ups from this network. Try again later.", "locked")
        role = str(data.get("role", ""))
        name = re.sub(r"\s+", " ", str(data.get("name", ""))).strip()
        email = normalise_email(str(data.get("email", "")))
        password = str(data.get("password", ""))
        errors = {}
        phone_raw = str(data.get("phone", "")).strip()
        if not clean_phone(phone_raw):
            errors["phone"] = "Enter your phone number (7 to 15 digits, optional +)."
        if role not in ("student", "guardian"):
            errors["role"] = "Choose student or guardian."
        if not (2 <= len(name) <= 80) or not re.fullmatch(r"[^\d<>{}\[\]@#$%^*=+|\\/]{2,80}", name):
            errors["name"] = "Enter your full name (letters only)."
        if not EMAIL_RE.fullmatch(email):
            errors["email"] = "Enter a valid e-mail address."
        elif app.users.by_email(email):
            errors["email"] = "An account with this e-mail already exists. Sign in instead."
        probs = password_problems(password, email, name)
        if probs:
            errors["password"] = " ".join(probs)
        profile = None
        new_uni = None
        if role == "student":
            cc, uni, program = str(data.get("home_country", "")), str(data.get("university_id", "")), \
                re.sub(r"[<>]", "", str(data.get("program", "")))[:80].strip()
            if cc not in HOME_CURRENCY:
                errors["home_country"] = "Choose your home country."
            if uni not in UNIVERSITIES:
                # Typed university: use the registry entry if the name matches exactly, else request verification.
                typed = registry.clean_name(data.get("university_name", ""))
                match = registry.find_exact(typed)
                if match:
                    uni = match["id"]
                elif len(typed) < 3:
                    errors["university_name"] = "Type the full name of your university."
                elif str(data.get("study_country", "")) not in STUDY_COUNTRIES:
                    errors["study_country"] = "Choose the country where you study."
                else:
                    new_uni = (typed, str(data["study_country"]), str(data.get("university_website", "")),
                               str(data.get("university_city", "")))
            profile = {"home_country": cc, "university_id": uni, "program": program or "Undergraduate programme",
                       "phone": clean_phone(phone_raw), "phone_masked": mask_phone(phone_raw)}
        g_name = re.sub(r"\s+", " ", str(data.get("guardian_name", ""))).strip()
        g_email = normalise_email(str(data.get("guardian_email", "")))
        if role == "student":
            if not (2 <= len(g_name) <= 80) or not re.fullmatch(r"[^\d<>{}\[\]@#$%^*=+|\\/]{2,80}", g_name):
                errors["guardian_name"] = "Enter your parent's or guardian's full name."
            if not EMAIL_RE.fullmatch(g_email):
                errors["guardian_email"] = "Enter your guardian's e-mail address."
            elif g_email == email:
                errors["guardian_email"] = "Use your guardian's own e-mail, not yours."
        rel = str(data.get("relationship", "Parent"))
        if role == "guardian" and rel not in RELATIONSHIPS:
            errors["relationship"] = "Choose your relationship to the student."
        if errors:
            return self._json({"ok": False, "code": "invalid", "error": "Check the highlighted fields.",
                               "fields": errors}, 400)
        app.guard.fail("reg:" + self.ip, 10)
        with app.lock:
            if role == "student" and new_uni:
                u = registry.request(*new_uni, requested_by=email)
                profile["university_id"] = u["id"]
                self._audit("university_requested", university_id=u["id"], verified=u.get("verified", True))
            if role == "student":
                sid = app.next_student_id(profile["home_country"])
                app.bank.create_student(student_id=sid, name=name, **profile)
                user = app.users.create(role="student", name=name, email=email, password=password,
                                        student_id=sid, profile=profile,
                                        guardian_invite={"name": g_name, "email": g_email, "status": "pending",
                                                         "created": int(time.time())})
                existing = app.users.by_email(g_email)
                if existing and existing["role"] == "guardian":
                    self._link_invited(existing, user)
            else:
                user = app.users.create(role="guardian", name=name, email=email, password=password,
                                        relationship=rel, students=[], phone=clean_phone(phone_raw), phone_masked=mask_phone(phone_raw))
                # Students who named this e-mail as their guardian are linked automatically.
                for st_user in list(app.users.users.values()):
                    inv = st_user.get("guardian_invite") or {}
                    if st_user["role"] == "student" and inv.get("email") == email and inv.get("status") == "pending":
                        self._link_invited(app.users.get(user["id"]), st_user)
                code = str(data.get("link_code", "")).strip()
                if code:
                    sid = app.users.redeem_link_code(code)
                    if sid:
                        app.users.update(user["id"], students=[sid])
                        app.sync_links()
                        self._audit("guardian_linked", user_id=user["id"], student_id=sid)
            self._audit("account_registered", user_id=user["id"], student_id=user.get("student_id"), role=role)
        token, sess = app.sessions.create(user, self.ip)
        return self._json({"ok": True, "user": public_user(user), "csrf": sess["csrf"],
                           "redirect": "/app" if role == "student" else "/guardian"},
                          extra=self._cookie(token, 12 * 3600))

    def _link_invited(self, guardian: dict, student_user: dict) -> None:
        app = self.app
        sid = student_user["student_id"]
        if sid not in guardian.get("students", []):
            app.users.update(guardian["id"], students=guardian.get("students", []) + [sid])
        inv = dict(student_user.get("guardian_invite") or {})
        inv.update(status="accepted", guardian_id=guardian["id"])
        app.users.update(student_user["id"], guardian_invite=inv)
        app.sync_links()
        self._audit("guardian_linked_by_invite", user_id=guardian["id"], student_id=sid)

    def _photo(self, user: dict, data: dict):
        """Profile photo: a small JPEG/PNG/WebP sent as a data URL, checked by its real file signature."""
        if data.get("remove"):
            self.app.users.update(user["id"], photo=None)
            return self._json({"ok": True, "photo": None})
        url = str(data.get("data_url", ""))
        m = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", url)
        if not m:
            return self._err(400, "Upload a JPG, PNG or WebP image.", "bad_image")
        import base64
        try:
            raw = base64.b64decode(m.group(2), validate=True)
        except ValueError:
            return self._err(400, "That image could not be read.", "bad_image")
        if len(raw) > 200_000:
            return self._err(400, "The photo is too large (max 200 KB after resizing).", "too_large")
        sig_ok = {"png": raw.startswith(b"\x89PNG\r\n\x1a\n"), "jpeg": raw.startswith(b"\xff\xd8\xff"),
                  "webp": raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"}[m.group(1)]
        if not sig_ok:
            return self._err(400, "The file is not the image type it claims to be.", "bad_image")
        self.app.users.update(user["id"], photo=url)
        self._audit("profile_photo_changed", user_id=user["id"], student_id=user.get("student_id"))
        return self._json({"ok": True, "photo": url})

    def _check_password(self, user: dict, password: str) -> bool:
        key = "reauth:" + user["id"]
        if self.app.guard.locked(key):
            return False
        if verify_password(str(password or ""), user["password"]):
            self.app.guard.success(key)
            return True
        self.app.guard.fail(key)
        self._audit("reauth_failed", user_id=user["id"], student_id=user.get("student_id"))
        return False

    def _change_password(self, user: dict, data: dict):
        if not self._check_password(user, data.get("current")):
            return self._err(403, "Your current password is wrong.", "bad_password")
        new = str(data.get("new", ""))
        probs = password_problems(new, user["email"], user["name"])
        if probs:
            return self._err(400, " ".join(probs), "weak_password")
        self.app.users.set_password(user["id"], new)
        revoked = self.app.sessions.destroy_user(user["id"], keep_token=self._token())
        self._audit("password_changed", user_id=user["id"], student_id=user.get("student_id"), revoked=revoked)
        return self._json({"ok": True, "revoked_sessions": revoked})

    # ------------------------------------------------------------ student actions
    def _student_post(self, path: str, user: dict, data: dict):
        app, sid = self.app, user["student_id"]
        if path == "/api/chat":
            msg = str(data.get("message", ""))[:4000]
            if not msg.strip():
                return self._err(400, "Type a message first.")
            return self._json(app.agent.chat(sid, msg, _lang(data)))
        if path == "/api/brief":
            from .agent import assist
            return self._json(assist.brief(app.agent, sid, _lang(data)))
        if path == "/api/email-draft":
            from .agent import assist
            res = assist.draft_email(app.agent, sid, invoice_id=data.get("invoice_id") and str(data["invoice_id"]),
                                     transfer_id=data.get("transfer_id") and str(data["transfer_id"]), lang=_lang(data))
            return self._json(res, 200 if res.get("ok") else 404)
        if path == "/api/confirm":
            res = app.agent.confirm(sid, str(data.get("proposal_id", "")), str(data.get("token", "")),
                                    str(data.get("otp", "")), bool(data.get("acknowledge_review", False)),
                                    bool(data.get("acknowledge_hold", False)))
            return self._json(res, 200 if res.get("ok") else 403)
        if path == "/api/totp/setup":
            # Step 1: password, then a fresh secret to scan. Nothing changes until a code from the app is entered.
            if not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to link an authenticator app.", "reauth_required")
            secret = totp.new_secret()
            app.users.update(user["id"], totp_pending={"secret": secret, "created": int(time.time())})
            self._audit("totp_setup_started", user_id=user["id"], student_id=sid)
            return self._json({"ok": True, "secret": secret, "uri": totp.provisioning_uri(secret, user["email"])})
        if path == "/api/totp/enable":
            pend = (app.users.get(user["id"]) or {}).get("totp_pending")
            if not pend or time.time() - pend["created"] > 900:
                return self._err(400, "Start again: the setup expired.", "expired")
            if self.app.guard.locked("totp:" + user["id"]):
                return self._err(429, "Too many wrong codes. Try again in 15 minutes.", "locked")
            step = totp.verify(pend["secret"], str(data.get("code", "")))
            if step is None:
                self.app.guard.fail("totp:" + user["id"])
                return self._err(400, "That code doesn't match. Check the time on your phone and try the newest code.", "bad_otp")
            app.users.update(user["id"], totp={"secret": pend["secret"], "enabled": int(time.time())}, totp_pending=None)
            app.agent.totp[sid] = {"secret": pend["secret"], "last_step": step}
            self._audit("totp_enabled", user_id=user["id"], student_id=sid)
            return self._json({"ok": True})
        if path == "/api/totp/disable":
            if not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to remove the authenticator app.", "reauth_required")
            cur = app.agent.totp.get(sid)
            if cur:
                step = totp.verify(cur["secret"], str(data.get("code", "")), cur.get("last_step"))
                if step is None:
                    return self._err(400, "Enter the current code from your authenticator app.", "bad_otp")
            app.users.update(user["id"], totp=None, totp_pending=None)
            app.agent.totp.pop(sid, None)
            self._audit("totp_disabled", user_id=user["id"], student_id=sid)
            return self._json({"ok": True})
        if path == "/api/mandate/cancel":
            return self._json(app.agent.cancel_mandate(sid, str(data.get("mandate_id", ""))))
        if path == "/api/settings":
            level, ga = data.get("level"), data.get("guardian_approval")
            sess_level = app.agent.session(sid)["level"]
            raising = level in permissions.LEVELS and \
                permissions.LEVELS[level]["max_tier"] > permissions.LEVELS[sess_level]["max_tier"]
            weakening = ga is False and app.bank.student(sid).get("guardian_approval", True)
            if (raising or weakening) and not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to give the agent more power or remove guardian approval.",
                                 "reauth_required")
            if level is not None:
                app.agent.set_level(sid, str(level), actor=f"student {user['id']}")
            if ga is not None:
                app.bank.student(sid)["guardian_approval"] = bool(ga)
                app.audit.append("guardian_approval_setting", actor="student", sim_time=app.bank.now.isoformat(),
                                 student_id=sid, user_id=user["id"], enabled=bool(ga))
            return self._json({"ok": True, "level": app.agent.session(sid)["level"],
                               "guardian_approval": app.bank.student(sid).get("guardian_approval", True)})
        if path == "/api/university/simulate-verification" and DEMO_MODE:
            s = app.bank.student(sid)
            u = registry.verify_sandbox(s["university_id"])
            for other in app.bank.students.values():
                if other["university_id"] == u["id"] and not app.bank.student_invoices(other["id"]):
                    app.bank.issue_starter_invoices(other["id"])
            app.audit.append("university_verified_sandbox", actor="sandbox", sim_time=app.bank.now.isoformat(),
                             student_id=sid, user_id=user["id"], university_id=u["id"])
            return self._json({"ok": True, "university": registry.public(u)})
        if path == "/api/sandbox/transfer-issue" and DEMO_MODE:
            res = app.agent.inject_issue(sid, str(data.get("transfer_id", "")), str(data.get("kind", "")))
            return self._json(res, 200 if res.get("ok") else 400)
        if path == "/api/transfer/recover":
            res = app.agent.recover(sid, str(data.get("transfer_id", "")))
            return self._json(res, 200 if res.get("ok") else 404)
        if path == "/api/chain/retry":
            h = str(data.get("h", "")).lower()
            mine = {c.get("anchor") for c in app.agent.certificates.get(sid, [])}
            if h not in mine:
                return self._err(404, "No such certificate in your account.")
            return self._json(app.anchors.submit(h))
        if path == "/api/certificates/issue":
            res = app.agent.issue_certificate(sid, str(data.get("kind", "payment")), data.get("transfer_id"),
                                              at_least=data.get("at_least"), currency=data.get("currency") and str(data["currency"])[:3],
                                              purpose=data.get("purpose") and str(data["purpose"])[:80])
            return self._json(res, 200 if res.get("ok") else 400)
        if path == "/api/killswitch":
            if data.get("engage", True):
                return self._json(app.agent.freeze(sid, "student", user))
            if not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to release the kill switch.", "reauth_required")
            res = app.agent.unfreeze(sid, "student", user)
            return self._json(res, 200 if res.get("ok") else 403)
        if path == "/api/guardian/invite-email":
            g_name = re.sub(r"\s+", " ", str(data.get("name", ""))).strip()[:80]
            g_email = normalise_email(str(data.get("email", "")))
            if len(g_name) < 2 or not EMAIL_RE.fullmatch(g_email) or g_email == user["email"]:
                return self._err(400, "Enter your guardian's name and their own e-mail address.", "invalid")
            app.users.update(user["id"], guardian_invite={"name": g_name, "email": g_email, "status": "pending",
                                                         "created": int(time.time())})
            existing = app.users.by_email(g_email)
            if existing and existing["role"] == "guardian":
                self._link_invited(existing, app.users.get(user["id"]))
            self._audit("guardian_invited_by_email", user_id=user["id"], student_id=sid)
            return self._json({"ok": True, "invite": app.users.get(user["id"]).get("guardian_invite")})
        if path == "/api/guardian/invite":
            code = app.users.new_link_code(sid)
            self._audit("guardian_invite_created", user_id=user["id"], student_id=sid)
            return self._json({"ok": True, **code})
        if path == "/api/guardian/unlink":
            if not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to remove a guardian.", "reauth_required")
            g = app.users.get(str(data.get("guardian_id", "")))
            if not g or sid not in g.get("students", []):
                return self._err(404, "That guardian isn't linked to you.")
            app.users.update(g["id"], students=[x for x in g["students"] if x != sid])
            app.sync_links()
            self._audit("guardian_unlinked", user_id=user["id"], student_id=sid, guardian_id=g["id"])
            return self._json({"ok": True})
        return self._err(404, "Not found.")

    # ------------------------------------------------------------ guardian actions
    def _guardian_post(self, path: str, user: dict, data: dict):
        app = self.app
        if path == "/api/guardian/ask":
            q = str(data.get("question", ""))[:800].strip()
            if not q:
                return self._err(400, "Type a question first.")
            from .agent import assist
            return self._json({"ok": True, **assist.guardian_answer(app.agent, user, q, _lang(data)), "ai": llm.status()})
        if path == "/api/guardian/decide":
            res = app.agent.guardian_decide(user, str(data.get("proposal_id", "")), str(data.get("otp", "")),
                                            bool(data.get("approve", False)))
            return self._json(res, 200 if res.get("ok") else 403)
        if path == "/api/guardian/killswitch":
            sid = str(data.get("student_id", ""))
            if sid not in user.get("students", []) or sid not in app.bank.students:
                return self._err(403, "You are not linked to this student.", "forbidden")
            if data.get("engage", True):
                return self._json(app.agent.freeze(sid, "guardian", user))
            if not self._check_password(user, data.get("password")):
                return self._err(403, "Enter your password to release the kill switch.", "reauth_required")
            return self._json(app.agent.unfreeze(sid, "guardian", user))
        if path == "/api/guardian/link":
            key = "link:" + user["id"]
            if app.guard.locked(key):
                return self._err(429, "Too many wrong codes. Try again in 15 minutes.", "locked")
            sid = app.users.redeem_link_code(str(data.get("code", "")))
            if not sid:
                app.guard.fail(key)
                return self._err(400, "That code is wrong or has expired. Ask the student for a new one.", "bad_code")
            if sid not in user.get("students", []):
                app.users.update(user["id"], students=user.get("students", []) + [sid])
            app.sync_links()
            self._audit("guardian_linked", user_id=user["id"], student_id=sid)
            return self._json({"ok": True, "student_id": sid})
        if path == "/api/guardian/fund":
            try:
                amount = float(data.get("amount", 0))
            except (TypeError, ValueError):
                return self._err(400, "Enter a number.")
            res = app.agent.guardian_fund(user, str(data.get("student_id", "")), amount)
            return self._json(res, 200 if res.get("ok") else 400)
        return self._err(404, "Not found.")


def serve(host: str = "127.0.0.1", port: int = 8000, data_dir: str | None = None):
    if os.environ.get("TS_LIVE_FX", "1") != "0":
        fx = fx_live.fetch()
        print(f"Exchange rates: {fx['source']} ({fx['provider']}, {fx['as_of']})")
    Handler.app = App(data_dir or config.DATA_DIR)
    httpd = ThreadingHTTPServer((host, port), Handler)
    ai = llm.status()
    print(f"SudoRoute running on http://{host}:{port}  (sandbox — no real money)")
    print(f"Language model: {ai['provider']} {ai['model'] or ''}".rstrip() if ai["enabled"]
          else "Language model: off (rule engine). Add GEMINI_API_KEY to .env to enable Gemini.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd


def main():
    ap = argparse.ArgumentParser(description="SudoRoute sandbox server")
    ap.add_argument("--host", default=os.environ.get("TS_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
