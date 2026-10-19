import os

os.environ.setdefault("TS_SECRET", "test-secret")
os.environ.setdefault("TS_PBKDF2_ITER", "2000")  # fast hashing in tests only
os.environ.setdefault("TS_ANCHOR", "0")  # no network in tests; anchoring is tested with a fake calendar

from sudoroute.agent.core import SudoRouteAgent  # noqa: E402
from sudoroute.sandbox.bank import SandboxBank  # noqa: E402
from sudoroute.security.audit import AuditLog  # noqa: E402
from sudoroute.security.proposals import ProposalStore, sandbox_otp  # noqa: E402

STU_BD, STU_NG = "STU-BD-001", "STU-NG-002"


def make_agent():
    bank = SandboxBank()
    store = ProposalStore(key=b"test-key")
    return SudoRouteAgent(bank, AuditLog(), store)


def propose(agent, sid=STU_BD, msg="Pay my tuition"):
    out = agent.chat(sid, msg)
    card = next(c for c in out["cards"] if c["type"] == "proposal")
    return out, card


def otp_for(agent, pid):
    return sandbox_otp(pid, agent.proposals.key)


# Accounts used by the HTTP tests only. The application itself ships with no accounts at all.
from sudoroute.util import SAMPLE_NAME, SAMPLE_PHONE, mask_phone  # noqa: E402

TEST_ACCOUNTS = [
    {"role": "student", "name": SAMPLE_NAME, "email": "student.bd@example.test", "password": "Student#2026", "student_id": STU_BD},
    {"role": "student", "name": SAMPLE_NAME, "email": "student.ng@example.test", "password": "Student#2026", "student_id": STU_NG},
    {"role": "guardian", "name": SAMPLE_NAME, "email": "guardian.bd@example.test", "password": "Guardian#2026", "relationship": "Father",
     "students": [STU_BD], "phone_masked": mask_phone(SAMPLE_PHONE)},
    {"role": "guardian", "name": SAMPLE_NAME, "email": "guardian.ng@example.test", "password": "Guardian#2026", "relationship": "Mother",
     "students": [STU_NG], "phone_masked": mask_phone(SAMPLE_PHONE)},
]


def seed_accounts(app):
    for d in TEST_ACCOUNTS:
        if not app.users.by_email(d["email"]):
            extra = {k: v for k, v in d.items() if k not in ("role", "name", "email", "password")}
            app.users.create(role=d["role"], name=d["name"], email=d["email"], password=d["password"], **extra)
    app.sync_links()
