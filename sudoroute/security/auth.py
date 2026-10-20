"""Accounts, sessions and login protection (standard library only).

* Passwords: PBKDF2-HMAC-SHA256, 310,000 iterations, 16-byte random salt, constant-time compare.
  Unknown e-mails still run a full hash so response time does not reveal which accounts exist.
* Password policy: 8+ characters with an uppercase letter, a lowercase letter and a digit; not a common password, not built on the e-mail or first name.
* Sessions: 256-bit random token in an HttpOnly, SameSite=Strict cookie. Only its SHA-256 hash is
  stored server-side. 30-minute idle and 12-hour absolute timeout. New token on every login
  (prevents session fixation). All sessions are revoked when the password changes.
* CSRF: a per-session token that must be echoed in the X-CSRF-Token header on every state change.
* Brute force: 5 failed logins lock that e-mail for 15 minutes; 20 failures lock the IP address.
* Guardian links: single-use 8-character codes that expire after 24 hours.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

ITERATIONS = int(os.environ.get("TS_PBKDF2_ITER", 310000))
SESSION_IDLE = int(os.environ.get("TS_SESSION_IDLE", 30 * 60))
SESSION_ABSOLUTE = 12 * 3600
LOCK_AFTER, LOCK_SECONDS, IP_LOCK_AFTER = 5, 15 * 60, 20
LINK_CODE_TTL = 24 * 3600
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COMMON_PASSWORDS = {"password123", "password1234", "1234567890", "qwerty12345", "iloveyou123", "admin12345",
                    "welcome123", "letmein123", "passw0rd123", "abc1234567", "student123", "bangladesh1"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,180}\.[A-Za-z]{2,24}$")


# ------------------------------------------------------------------ passwords
def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, AttributeError):
        return False


_DUMMY_HASH = None


def burn_time(password: str) -> None:
    """Hash anyway when the account does not exist, so timing doesn't reveal valid e-mails."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("dummy-password-1")
    verify_password(password, _DUMMY_HASH)


def password_problems(password: str, email: str = "", name: str = "") -> list[str]:
    p = password or ""
    problems = []
    if len(p) < 8:
        problems.append("Use at least 8 characters.")
    if len(p) > 128:
        problems.append("Use at most 128 characters.")
    if not re.search(r"[A-Z]", p):
        problems.append("Add an uppercase letter.")
    if not re.search(r"[a-z]", p):
        problems.append("Add a lowercase letter.")
    if not re.search(r"\d", p):
        problems.append("Add a number.")
    if p.lower() in COMMON_PASSWORDS:
        problems.append("This password is too common.")
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in p.lower():
        problems.append("Don't include your e-mail name in the password.")
    first = (name or "").split(" ")[0].lower()
    if len(first) >= 4 and first in p.lower() and len(p) < 14:
        problems.append("Don't build the password around your name.")
    return problems


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


# ------------------------------------------------------------------ users
class UserStore:
    def __init__(self, path: str | None):
        self.path = path
        self.lock = threading.RLock()
        self.users: dict[str, dict] = {}
        self.link_codes: dict[str, dict] = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.users = data.get("users", {})
            self.link_codes = data.get("link_codes", {})

    def save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users, "link_codes": self.link_codes}, f, indent=1)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def by_email(self, email: str) -> dict | None:
        email = normalise_email(email)
        return next((u for u in self.users.values() if u["email"] == email), None)

    def get(self, uid: str) -> dict | None:
        return self.users.get(uid)

    def create(self, *, role: str, name: str, email: str, password: str, **extra) -> dict:
        with self.lock:
            uid = f"USR-{secrets.token_hex(5)}"
            user = {"id": uid, "role": role, "name": name.strip(), "email": normalise_email(email),
                    "password": hash_password(password), "created": int(time.time()),
                    "password_changed": int(time.time()), **extra}
            self.users[uid] = user
            self.save()
            return user

    def set_password(self, uid: str, password: str) -> None:
        with self.lock:
            self.users[uid]["password"] = hash_password(password)
            self.users[uid]["password_changed"] = int(time.time())
            self.save()

    def update(self, uid: str, **fields) -> dict:
        with self.lock:
            self.users[uid].update(fields)
            self.save()
            return self.users[uid]

    def guardians_of(self, student_id: str) -> list[dict]:
        return [u for u in self.users.values() if u["role"] == "guardian" and student_id in u.get("students", [])]

    def student_user(self, student_id: str) -> dict | None:
        return next((u for u in self.users.values() if u.get("student_id") == student_id), None)

    # --------------------------------------------------- guardian link codes
    def new_link_code(self, student_id: str) -> dict:
        with self.lock:
            now = time.time()
            self.link_codes = {c: v for c, v in self.link_codes.items()
                               if v["expires"] > now and v["student_id"] != student_id}
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
            self.link_codes[code] = {"student_id": student_id, "expires": now + LINK_CODE_TTL}
            self.save()
            return {"code": f"{code[:4]}-{code[4:]}", "expires": int(now + LINK_CODE_TTL)}

    def redeem_link_code(self, code: str) -> str | None:
        code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
        with self.lock:
            rec = self.link_codes.pop(code, None)
            self.save()
            if rec and rec["expires"] > time.time():
                return rec["student_id"]
            return None


# ------------------------------------------------------------------ sessions
def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()

    def create(self, user: dict, ip: str) -> tuple[str, dict]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        sess = {"user_id": user["id"], "role": user["role"], "csrf": secrets.token_urlsafe(24),
                "created": now, "last": now, "ip": ip}
        with self.lock:
            self.sessions[_h(token)] = sess
        return token, sess

    def get(self, token: str | None) -> dict | None:
        if not token:
            return None
        key = _h(token)
        now = time.time()
        with self.lock:
            sess = self.sessions.get(key)
            if not sess:
                return None
            if now - sess["last"] > SESSION_IDLE or now - sess["created"] > SESSION_ABSOLUTE:
                del self.sessions[key]
                return None
            sess["last"] = now
            return sess

    def destroy(self, token: str | None) -> None:
        if token:
            with self.lock:
                self.sessions.pop(_h(token), None)

    def destroy_user(self, user_id: str, keep_token: str | None = None) -> int:
        keep = _h(keep_token) if keep_token else None
        with self.lock:
            victims = [k for k, v in self.sessions.items() if v["user_id"] == user_id and k != keep]
            for k in victims:
                del self.sessions[k]
        return len(victims)


# ------------------------------------------------------------------ brute-force guard
class LoginGuard:
    def __init__(self):
        self.fails: dict[str, list] = {}
        self.lock = threading.Lock()

    def locked(self, key: str, limit: int = LOCK_AFTER) -> int:
        """Seconds remaining on a lock for `key`, or 0."""
        with self.lock:
            rec = self.fails.get(key)
            if not rec:
                return 0
            count, until = rec
            if until and time.time() < until:
                return int(until - time.time()) + 1
            if until and time.time() >= until:
                del self.fails[key]
            return 0

    def fail(self, key: str, limit: int = LOCK_AFTER) -> None:
        with self.lock:
            count, until = self.fails.get(key, [0, 0])
            count += 1
            until = time.time() + LOCK_SECONDS if count >= limit else 0
            self.fails[key] = [count, until]

    def success(self, key: str) -> None:
        with self.lock:
            self.fails.pop(key, None)
