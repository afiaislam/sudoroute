# SudoRoute 🛡️

**A permission-tiered AI agent that pays international students' tuition safely, cheaply and on time.**

2026 Shenzhen International FinTech Competition (FinTechathon) · International Track · Theme *"AI as a Financial Participant"* · **Topic C — Cross-border & Student Finance Assistant**

---

## The problem

Every semester, millions of international students move their family's savings across borders to pay tuition. Three things go wrong:

1. **Scams.** Fake "tuition invoices" from look-alike domains with "our bank details have changed" are a common fraud against students — and new scam emails now hide instructions aimed at AI assistants.
2. **Hidden cost.** A standard bank wire hides 2–3% in the exchange rate plus fees. Cheaper channels exist, but some are illegal (hundi/hawala) or not allowed by home-country rules.
3. **Currency risk.** For a Nigerian or Bangladeshi family, the tuition bill in GBP or MYR can grow while they wait. Nobody tells them how likely it is to blow their budget.

## What SudoRoute does

SudoRoute is an AI agent that **completes the whole task**, not just advises:

| Task | What the agent does |
|---|---|
| **Pay tuition end-to-end** | Reads the invoice → verifies it → picks the cheapest *licensed* route that arrives before the due date → prices FX risk → runs 10 compliance checks → prepares an HMAC-signed proposal → executes after the student confirms with a one-time code → tracks settlement until the university ledger shows "paid". |
| **Autonomous installments** | When a student can't pay everything today, the agent proposes a 3-installment plan. After one confirmation, it executes the later installments **by itself** under a bounded mandate (same payee, same invoice, auto-pause if the currency moves > 5%, revocable any time). |
| **Scam shield** | Scores every invoice 0–100 (look-alike domains, typosquats, bank-detail changes, urgency/threats, crypto requests, amount anomalies, hidden prompt-injection) and explains every point. |
| **True-cost route comparison** | Landed cost = hidden FX spread + fees + priced deadline risk, across bank wire, education platform, licensed MTO, card and informal channels — with rule-based exclusions. |
| **FX budget-at-risk** | EWMA volatility + 4,000-path Monte Carlo: probability that waiting pushes tuition over the family's budget, and the worst-case (95th percentile) cost of each strategy. |
| **Budget & runway** | Multi-currency spending insights, spending spikes, months of runway after tuition. |
| **Credit-building plan** | A transparent readiness score and next steps to build a credit history in the study country. |
| **Verifiable payment certificates** | After a payment settles, the student can create an **Ed25519-signed certificate** of the on-time payment (or of their whole payment history). Landlords, banks or scholarship offices check it on the public `/verify` page — no account, no shared secret; one changed character fails. |
| **Kill switch** | Student or guardian freezes everything with one press: pending proposals are cancelled, instalment mandates stopped. Releasing needs the password, and a guardian's freeze can only be lifted by a guardian. |
| **Any university, safely** | Students type their university instead of picking from a short list. Exact matches use the verified registry; anything else is added as *pending verification* and can't receive money until its bank account is confirmed with the university itself — never from the student, an invoice or an e-mail. |
| **On-chain proof (Bitcoin)** | Every certificate also gets an **on-chain anchor**: the SHA-256 of a small record (certificate hash + the audit-log head at that moment) is timestamped on the **Bitcoin blockchain via OpenTimestamps**. Anyone can download the record and the `.ots` proof from `/verify` and check them at opentimestamps.org — without trusting SudoRoute. No wallet, coins or personal data go on-chain, only a 32-byte hash. Offline servers show "not submitted" honestly and can retry. Check it from your computer with `python scripts/anchor_check.py`. |
| **Proof of funds** | For a visa, landlord or scholarship: an Ed25519-signed certificate that the student held **at least** an amount on a date — the real balance is never written into it. SudoRoute refuses to sign a claim the wallets can't back. Valid 30 days; checked on `/verify`. |
| **Pay-by date** | The dashboard shows the latest safe day to pay (due date − delivery time − buffer) and warns when it is already tight. Route choice prices the real harm of a late payment, not just the late fee. |
| **Failed-transfer recovery** | If the receiving bank **returns** a transfer, the money goes back to the wallet and the agent explains why and refuses a blind resend. If an intermediary bank **deducts a fee**, the agent reconciles the receipt against the invoice and offers to pay **only the shortfall**; a repeat of the full amount is blocked by the overpayment check. The sandbox can inject both faults (*Payments → Sandbox: make it fail*). |
| **Live exchange rates** | At start-up the server fetches today's rates from a free public feed; every screen labels rates **LIVE** or a dated **REFERENCE** snapshot. Implausible rates (outside 0.5×–2× of reference) are rejected so a broken or spoofed feed can't distort a quote. |

**SudoRoute AI, powered by Google Gemini, everywhere it helps — and nowhere it could hurt.**

| Where | What the AI does | What keeps it safe |
|---|---|---|
| **AI button on every page** (student, guardian, public site) | Students talk to the full agent; guardians ask about their student's tuition and approvals; visitors ask how SudoRoute works. English, বাংলা, 中文. | Students' AI uses the same tier-gated tools as the agent. The guardian AI is read-only and answers only from that student's facts. The public AI answers only from a fixed fact sheet and is rate-limited. |
| **Understanding requests** | Maps free-form messages in any language ("আমার টিউশন ফি পরিশোধ করো") to an action. | It may only pick from a fixed list of actions, and can only make a refusal stricter, never lift one. |
| **Money brief** on the dashboard | Writes a 2–4 sentence brief from the live numbers: what's due, the latest safe day to pay, on-time chance, risk of waiting. | Every number and date must survive unchanged and none may be added — otherwise the template is shown. |
| **E-mail drafts** | Drafts a message to the university's real finance office about a suspicious invoice, or a returned / short-paid transfer. | Full account numbers never reach the model; SudoRoute never sends e-mails. |
| **Replies** | Rewrites the agent's verified replies in the user's language. | Number-preservation check; forbidden phrases (codes, passwords) rejected. |

The model never sees pasted invoices or e-mails (hidden instructions can't reach it), never moves money and never sees a one-time code. Any error or failed check falls back silently to the rule engine, so the app works fully without a key. Two Security Lab attacks (AI-12, AI-13) try to jailbreak the new assistants.

## Check our claims yourself (no account needed)

| Page | What it proves |
|---|---|
| **`/security-lab`** | Starts a private live copy of SudoRoute and fires **47 real attacks** at it over HTTP — prompt injection in English, Bangla and Chinese, hidden-instruction invoices, homoglyph domains, signature tampering, replay, forged guardian approval, IDOR, mass assignment, CSRF, cross-origin, brute force, account enumeration, link-code guessing, path traversal, oversized and non-JSON bodies, audit-log editing, permission escalation, kill switch, jailbreaking the guardian and public AI assistants, AI e-mail drafts and recovery for another student (IDOR), unbacked and inflated proof-of-funds certificates, fake pilot ratings — plus **4 controls** that must still succeed (a real two-party payment settles, a certificate verifies, a genuine invoice is not flagged). Current result: **51/51**. Also `python scripts/security_lab.py`. |
| **`/accuracy`** | The scam shield on **two hold-out sets in English, Malay, Bangla and Chinese**. Set v1 (60 invoices, rules frozen first): 100% of scams flagged, 0 genuine blocked, but **13.3% false alarms** — genuine warnings like "we never accept crypto". We added a negation-aware rule, so v1 is no longer unseen (now 0%). Set v2 (24 invoices) was written next, evaluated once, and includes **scams built to beat the new rule** ("don't use the old account — USDT only"): **100% of scams flagged, 0 genuine blocked, 16.7% false alarms (2/12)**. Every sample and every miss is published. Also `python scripts/benchmark_scam_shield.py`. |
| **`/accuracy#baselines`** | **SudoRoute vs today's options**, computed live: a bank wire to the invoice's account (how most families pay) and a cheapest-fee AI assistant, on **84 invoices**, **160 priced payments** (4 countries × 4 universities × 5 deadlines × 2 amounts) and **3 retry situations replayed on the real agent**. SudoRoute: 0 scams paid to a fraudster (others 42/42), 0 rule-breaking channels (assistant 120/160), 1.8% cheaper than a bank wire, 11.0% vs 27.5% expected-late — and **0% avoidable lateness** (24 of the 160 deadlines are too close for any allowed channel) — 0 overpayments on retry (others 2/3), and a **fairness table** showing the same protection for every home country. The assistant is cheaper and faster only because it uses channels the rules don't allow — stated on the page. Also `python scripts/benchmark_baselines.py`. |
| **`/accuracy#pilot`** | **Pilot feedback from real testers**: signed-in students and guardians rate SudoRoute under Profile → *Help us improve*; the page shows live totals only (no names or comments). It says "0" until people answer — nothing is pre-filled. |
| **`/verify`** | Paste any SudoRoute payment certificate and check its signature with the public key. Offline: `python scripts/verify_certificate.py`. |

## The website

| Page | What it is |
|---|---|
| `/` | Public landing page with a photo hero, how a payment passes five checkpoints, the scam check, the guardian role, the proof pages, security measures and questions. |
| `/login`, `/register` | Sign in or create an account as a **Student** or a **Guardian**. New students get a sandbox wallet and a real tuition invoice from their chosen university. |
| `/app` | **Student portal**: Overview, Assistant (chat), Payments, Invoices (incl. paste-an-e-mail scam check), Insights (budget, FX risk, routes, credit), Certificates, Security (permission level, guardian approval, link codes, sandbox phone, activity log, password), Profile. Kill switch and LIVE/REFERENCE rate badge in the top bar. **Guided tour** button (or open `/app#overview?tour` to auto-play — ideal for screen-recording the demo video). |
| `/guardian` | **Guardian portal**: Overview of linked students with a per-student kill switch, Approvals (approve/decline with their own one-time code), Activity log, Send funds, Profile and security. |
| `/security-lab`, `/accuracy`, `/verify` | Public proof pages (see above). |

**Motion design.** One motion system across the site (tokens in `site.css`, timing logic in `static/motion.js`, no animation library): a single orchestrated entrance on the landing page (headline → copy → buttons → the route board unmasks → the example payment travels its five checkpoints), calm scroll reveals in which each section heading is a station that lights up, a sliding navigation indicator, page transitions, animated dialogs, busy states on every real request. Inside the portal, motion follows real state only: the **live payment journey** moves a station forward only when the server reports a guardian approval, a confirmation or a settlement; balances tween only when they actually change; the Security Lab shows an indeterminate indicator until the real results arrive (no fake progress); the certificate checker shows *valid / not valid / can't be verified* only after the server's Ed25519 check. `prefers-reduced-motion` removes all of it, and every page is fully readable without JavaScript animation.

**Demo video (submission item 03).** `web/static/video/sudoroute-demo.mp4` (about 3 min 48 s, 1280×720, captioned; WebM copy alongside) is a real screen recording of the app, made by an automated browser clicking through the running site (`scripts/record_demo.py`, optional, needs Playwright): sign-up, SudoRoute AI (money brief and chat), her father (Ashraful Islam) joins by e-mail, scam blocked with an AI-drafted e-mail to the university, one-time codes arriving on the sandbox phone, payment approved by guardian and student, a transfer that arrives short and is reconciled, certificate, public verification, the on-chain (Bitcoin) proof, Security Lab. It is embedded on the home page with clickable chapters.

**Student dashboard.** Four headline numbers computed by the same engines — days until tuition is due, chance it arrives on time if paid today, chance the bill outgrows the budget if the student waits, and how much of the semester is funded — plus **This semester's bills** (tuition and typical living bills, checked in due-date order against wallets and scheduled family support) and a **what-if** slider that shows what tuition would cost if the home currency weakens.

**Profiles with photos.** Students and guardians can upload a profile photo (resized to 256 px in the browser; the server accepts only PNG/JPEG/WebP up to 200 KB and checks the file's real signature, not just its name).

**One-time codes and the sandbox phone.** Every payment card says what the 6-digit code is (a text message to the registered phone that proves the person — not the AI — approves this exact payment). The sandbox sends no real SMS, so the portal plays the phone: a **phone icon** in the top bar with an unread badge, and a phone-style notification that slides in the moment a code is "texted". *Use this code* fills the right code box, wherever it is. In production the same message goes through a licensed SMS gateway (or TOTP/passkeys).

**Guardians by e-mail.** At sign-up a student enters their parent's or guardian's name and e-mail. When the guardian registers with that e-mail they are linked automatically (the student can also change the invitation, or share a one-time link code instead).

**Real-world website.** Photo-led home page and portals (Unsplash licence, loaded from the Unsplash CDN, with designed fallbacks when offline), transparent navigation that turns solid on scroll with a pointer-following highlight and dropdown menus, real screenshots of the working portals, and a full footer. No city or country is hard-coded on the public pages — everything inside the portal follows the signed-in user's own data.

**Performance.** Static files are served with year-long immutable caching behind content-hashed URLs, text responses are gzip-compressed, photos are lazy-loaded and size-capped through CDN parameters, the four product screenshots are ~40–55 KB WebP each, and there is no JavaScript framework or build step.

Interface in **English, 简体中文 and বাংলা** (globe menu on every page). **Installable** as an app on phones and laptops (web app manifest + a service worker that never caches money screens; an offline page explains why). Light and dark mode everywhere. Responsive down to phone width.

### Getting started (there are no built-in accounts)

Nothing is pre-created. Register your own accounts:

1. Open `/register`, choose **Student**, fill in your name, e-mail, password (at least 8 characters with an uppercase letter, a lowercase letter and a number), your phone number and your home country, and **type your university** (suggestions show the verified ones). A university that isn't in the verified registry yet is accepted as **pending verification**: the agent can check invoice e-mails for scams but prepares no payment until the university's official bank account is confirmed out-of-band (production: call-back to the number on the university's own website + signed bank letter; sandbox: a clearly labelled *Simulate verification* button). 16 study countries are supported. You get a sandbox wallet, one tuition invoice and one suspicious look-alike e-mail addressed to you, so you can try the scam shield straight away.
2. Open **Security → Link codes** in the student portal and create a link code for your guardian.
3. In a private window open `/register`, choose **Guardian** and paste the link code.
4. As the student press **Pay tuition**. The guardian approves under **Approvals** with the code in their sandbox phone panel, then the student confirms with their own code.

Your own name and phone number appear only for you (profile, greetings, assistant, SMS panel). Guardians and the audit log only ever see the masked form (for example `019••••••00`). The live website creates no pre-made people; the two scripted sample students exist only in the tests and in `scripts/run_demo.py`.

## Security design (summary)

| Layer | Mechanism |
|---|---|
| **Permission tiers** | T0 Read · T1 Analyze · T2 Prepare · T3 Execute · T4 Prohibited. The student picks *Read only / Advisor / Assisted payments*; the agent can never raise its own level. |
| **Execution only via signed proposals** | Money moves only through `/api/confirm` with an HMAC-SHA256-signed proposal + step-up OTP. It can never be triggered from chat text. Tampering with payee or amount → `bad_signature`. |
| **Control-plane / data-plane separation** | Payee bank details come **only** from the verified university registry — never from an invoice, email or chat message. |
| **Prompt-injection defence** | Invoices and pasted emails are untrusted data, scanned for instruction-like and hidden content, quarantined in the UI and logged; they can never create a proposal. |
| **Policy engine** | 10 checks before **and again at** execution: verified beneficiary, invoice authenticity, no overpayment, licensed & country-permitted channel, sanctions screening, per-transaction / 24h / annual limits, funds, AML structuring pattern, documents. |
| **Anti-replay, expiry, lockout** | Idempotent execution, 10-minute quote expiry, OTP lockout after 3 wrong codes, proposal bound to its owner. |
| **Bounded autonomy** | Installment mandates are limited to one payee, one invoice, the approved legs, a max-slippage guard and the invoice due date; revocable. |
| **Tamper-evident audit** | Every step is appended to a SHA-256 hash-chained log with PII redaction; any edit or deletion is detected. |
| **Bounded language model** | Gemini only classifies intent, rewrites verified drafts and answers general questions. It never sees pasted documents, cannot call tools, cannot lift a refusal, and any reply that alters, adds or drops a number/ID — or asks for codes or card numbers — is discarded for the template. Errors fall back silently. |
| **Accounts** | PBKDF2-SHA256 (310,000 iterations, random salt) passwords; policy of 8+ characters with uppercase, lowercase and a digit, no common or e-mail-based passwords; identical error and timing for wrong password, unknown e-mail or wrong account type (no account enumeration). |
| **Sessions** | 256-bit random token in an `HttpOnly; SameSite=Strict` cookie (`Secure` behind HTTPS); only its hash is stored; 30-min idle / 12-h absolute expiry; rotated on login; all other sessions revoked on password change. |
| **CSRF & origin** | Per-session CSRF token required on every state-changing request; cross-origin POSTs rejected. |
| **Brute force** | 5 wrong passwords lock the account for 15 min; 20 lock the IP; sign-up, re-authentication and link codes are rate-limited too. |
| **Roles & isolation** | Student and guardian APIs are separated; the student ID always comes from the session, never the request (no IDOR); guardians see only linked students; activity logs are filtered per user. |
| **Guardian co-approval** | When a guardian is linked, a signed proposal needs the guardian's own one-time code before the student can confirm. Declines are final. A new quote supersedes older pending ones. |
| **Step-up for risky settings** | Giving the agent more power, turning off guardian approval or removing a guardian requires the password again. |
| **Kill switch** | One press (student or guardian) cancels pending proposals and stops mandates; nothing can be prepared, approved or executed while frozen; release needs the password; a guardian's freeze can only be released by a guardian. Stopped mandates stay stopped until re-approved. |
| **Multilingual attack detection** | Prompt-injection, urgency, threat and crypto/personal-account cues in English, Malay, Bangla and Chinese; IDN homograph detection (Cyrillic/Greek look-alike letters, punycode); zero-width and bidi-override characters flagged as hidden content. |
| **Signed certificates** | Ed25519 (RFC 8032, implemented on the standard library and checked against the RFC's official test vectors); issuer key stored with 0600 permissions; each certificate is anchored to the audit-log head at issue time. |
| **Live data safety** | Live FX rates outside 0.5×–2× of the reference are rejected per currency; on any network error the dated reference snapshot is used and labelled. |
| **Hardened API** | Input validation, JSON-only bodies, body-size cap, rate limiting, strict CSP (`script-src 'self'`, no inline scripts), X-Frame-Options, nosniff, Permissions-Policy, COOP, HSTS behind HTTPS, path-traversal-safe static files, binds to localhost by default. |

## Quick start (no dependencies)

Requires **Python 3.10+**. Nothing to install — standard library only.

```bash
git clone https://github.com/<your-account>/sudoroute.git
cd sudoroute
python run.py
# open http://127.0.0.1:8000
```

### Turn on Gemini (recommended)

```bash
cp .env.example .env          # Windows: copy .env.example .env
# edit .env and paste your key:  GEMINI_API_KEY=...
python scripts/check_gemini.py   # confirms the key and picks a working model
python run.py
```
The header shows **✦ Gemini · model** when connected. Default model `gemini-3.1-flash-lite` (Gemini 2.5 models were retired on 16 Oct 2026), with automatic fallback; override with `TS_LLM_MODEL`.

Then open http://127.0.0.1:8000 and register a student and a guardian (see *Getting started* above).

### Run the tests

```bash
python -m unittest discover -s tests -t . -v      # 179 tests
python scripts/security_lab.py                    # 47 live attacks + 4 controls → evidence/security_lab_report.md
python scripts/benchmark_scam_shield.py           # multilingual hold-out → evidence/scam_shield_benchmark.md
python scripts/benchmark_baselines.py             # vs bank wire and a basic AI assistant → evidence/baseline_comparison.md
```
The same run on every push in GitHub Actions (`.github/workflows/tests.yml`).

179 tests, including on-chain anchoring (OpenTimestamps proof format, offline honesty, scoping), the AI assistants with a simulated Gemini (number and grounding checks, jailbreaks, language), proof of funds, pilot feedback, the installable app, the second scam hold-out set, failed-transfer recovery (returned and short-paid transfers, no double payment), the baseline comparison, RFC 8032 Ed25519 vectors, kill switch, certificates, live-FX sanity checks, multilingual detection, the benchmark floor (0 genuine blocked, 0 scams missed) and the full Security Lab; the original 107 (Gemini is simulated, so no key or network is needed): accounts (no built-in accounts, masked phone), append-only audit log across restarts and resets, sessions, CSRF, lockout, role separation, IDOR, guardian co-approval, registration, link codes, security headers, engines, permission tiers, signature tampering, replay, expiry, OTP lockout, policy limits, mandate slippage guard, audit-chain tampering, PII redaction, prompt injection, full task completion, the HTTP API, and the Gemini layer (model fallback, hallucinated-number rejection, no access to pasted documents, cannot lift refusals, silent fallback on errors).

### Generate execution evidence

```bash
python scripts/run_demo.py
```
Runs 7 scripted sandbox scenarios (34 checked steps, including guardian co-approval, attacks in Bangla and Chinese, the kill switch and a signed certificate) and writes `evidence/sandbox_operation_log.jsonl`, `evidence/demo_transcript.md` and `evidence/execution_summary.json`.

### Publish it (free public link for the judges)

**Render (one click):** push this repo to GitHub → on render.com choose **New → Blueprint** → select the repo. `render.yaml` builds the Dockerfile, generates `TS_SECRET`, turns on secure cookies, and serves the site at `https://sudoroute-<id>.onrender.com`. Optionally paste `GEMINI_API_KEY` in the Render dashboard (never in the repo). Free instances sleep when idle, so open the link once a minute before you present.

Any host that runs Docker works the same way (`PORT` is respected).

### Docker (optional)

```bash
docker build -t sudoroute .
docker run -p 8000:8000 sudoroute
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `TS_SECRET` | random per start | Proposal-signing key (use a KMS/HSM in production) |
| `TS_LIMIT_PER_TXN_USD` / `TS_LIMIT_DAILY_USD` | 30000 / 40000 | Transaction limits |
| `TS_MANDATE_MAX_SLIPPAGE` | 0.05 | Installment auto-pause threshold |
| `TS_PROPOSAL_TTL` | 600 | Quote validity (seconds) |
| `GEMINI_API_KEY` | — | Enables Gemini (auto-selected when present; can be put in `.env`) |
| `TS_LLM_MODEL` | `gemini-3.1-flash-lite` | Preferred model; falls back to `gemini-3-flash-preview`, `gemini-flash-latest` |
| `TS_LLM_PROVIDER` | auto | `gemini`, `anthropic` or `openai` (the latter two need `TS_LLM_MODEL` + their key) |

## Architecture

```
web/index.html  ──HTTP──▶  sudoroute/server.py  (stdlib ThreadingHTTPServer, validation, rate limit, headers)
                                   │
                                   ▼
                     agent/core.py  SudoRouteAgent
   intents.py rules ─┐
   llm.py Gemini ────┴→ intent → planner → tier-gated tool calls (_call) → verified draft → Gemini rewrite (number-checked)
                                   │
        ┌──────────────┬───────────┴───────────┬────────────────┬──────────────┐
        ▼              ▼                       ▼                ▼              ▼
  engines/        engines/routes.py     engines/fx_risk.py   engines/        engines/
  invoice_check   (landed cost,         (EWMA + Monte Carlo  budget.py       credit.py
  (scam shield)    rule eligibility)     budget-at-risk)
                                   │
        security/: permissions.py · proposals.py (HMAC, OTP, replay) · policy.py · guardrails.py · audit.py
                                   │
        sandbox/: bank.py (wallets, transfers, settlement, inflows) · fx_market.py · reference_data.py
```

## Project layout

```
sudoroute/
├── run.py                     start the server
├── sudoroute/
│   ├── agent/                 intents, optional LLM adapter, core agent + mandate scheduler
│   ├── engines/               invoice_check, routes, fx_risk, budget, credit
│   ├── security/              auth, permissions, proposals, policy, guardrails, audit,
│   │                          ed25519 + certificates, redteam (Security Lab)
│   ├── sandbox/               simulated bank, FX market, live FX feed, university registry, reference data
│   ├── benchmark/             multilingual scam-shield hold-out set + scorer
│   └── server.py              HTTP API
├── web/                       index, auth, student, guardian, lab, accuracy, verify pages
│   └── static/                site.css design system, i18n.js (EN/中文/বাংলা), theme, per-page JS (no build step)
├── tests/                     138 unittest cases
├── scripts/run_demo.py        produces execution evidence
├── scripts/security_lab.py    live attack suite → evidence
├── scripts/benchmark_scam_shield.py
├── scripts/verify_certificate.py   offline certificate check
├── render.yaml, Dockerfile    deployment
├── scripts/check_gemini.py    verifies your Gemini key
├── .env.example               put GEMINI_API_KEY here (copy to .env)
└── evidence/                  generated logs, transcript, test report (screenshots: see evidence/screenshots/README.md)
```

## API

All `/api` routes except sign-in, registration and public metadata need a session cookie; every POST also needs the `X-CSRF-Token` header.

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | public |
| POST | `/api/auth/logout`, `/api/auth/password` · GET `/api/auth/me` | signed in |
| GET | `/api/state`, `/api/insights`, `/api/audit` | student |
| POST | `/api/chat`, `/api/confirm`, `/api/settings`, `/api/mandate/cancel`, `/api/guardian/invite`, `/api/guardian/unlink` | student |
| GET | `/api/guardian/overview`, `/api/audit` | guardian |
| POST | `/api/guardian/decide`, `/api/guardian/link`, `/api/guardian/fund` | guardian |
| GET | `/api/certificates` · POST `/api/certificates/issue`, `/api/killswitch` | student |
| POST | `/api/guardian/killswitch` | guardian |
| POST | `/api/transfer/recover`, `/api/brief`, `/api/email-draft` | student |
| POST | `/api/guardian/ask` | guardian |
| POST | `/api/feedback` | signed in |
| GET | `/api/public/pilot`, `/api/public/chain`, `/api/public/anchor?h=` (+ `/record`, `/ots`) · POST `/api/public/ask` | public (rate-limited) |
| POST | `/api/chain/retry` | student (own certificates only) |
| POST | `/api/university/simulate-verification`, `/api/sandbox/transfer-issue` | student, sandbox only |
| GET | `/api/public/fx`, `/api/public/issuer`, `/api/public/benchmark`, `/api/public/baselines` · POST `/api/public/verify`, `/api/public/security-lab/run` | public (rate-limited) |
| POST | `/api/sandbox/advance`, `/api/sandbox/reset` | signed in, sandbox tools only (`TS_DEMO_MODE=0` disables) |

## Honest limitations

- Everything runs in a **sandbox**: fictional universities, banks, accounts and channels. FX levels are real (live feed or a dated snapshot); their future movement is simulated.
- The sandbox clock (`+1 day`, `+7`, `+20`) is shared by every user of one server, so on a public demo one visitor can move time for others.
- Both scam-shield sets are synthetic and written by the team. On the unseen set v2, 2 of 12 genuine invoices (an FAQ answer "No." and a bookshop gift-card note) are still sent to review — a held invoice costs the student a check with the university, never a lost payment.
- The AI assistants are tested with a simulated Gemini; with a real key, wording varies, but every reply passes the same number / grounding checks or falls back to templates.
- Pilot feedback starts empty on a new server; it only shows what real testers submit.
- On-chain anchoring needs internet; the `.ots` format was checked with the official OpenTimestamps parser, but live submission to the calendars was not possible from the build environment — run `python scripts/anchor_check.py` once with internet. Bitcoin confirmation takes a few hours after submission.
- Payment certificates prove what SudoRoute's sandbox recorded; they are not yet recognised by any credit bureau.
- Country rule packs (BD, NG, IN, PK) are **simplified illustrations** and must be validated with regulators/authorised banks before production.
- No real SMS is sent: one-time codes arrive on the in-app sandbox phone. Production would use an SMS gateway, TOTP or passkeys on a channel the agent cannot read.
- The baseline comparison uses illustrative sandbox fees, markups and delivery times; the baselines are defined in code (`sudoroute/benchmark/baselines.py`) and deliberately reasonable, but they are models, not observed behaviour.
- Credit-readiness score is an educational heuristic, not an official credit score.

## Photo credits

Photos are from [Unsplash](https://unsplash.com) under the Unsplash License (free to use, no permission needed), hot-linked from the Unsplash CDN as Unsplash recommends: `photo-1541339907198-e08756dedf3f` (graduates throwing caps), `photo-1752652013112-6734bf1a682a` (mother and daughter looking at a phone), `photo-1507812984078-917a274065be` (aeroplane window at golden hour), `photo-1543269664-02e941c052f7` (laptop on a student's lap), `photo-1607013407627-6ee814329547` (graduates holding caps). Product screenshots are our own.

## License

MIT — see `LICENSE`. No third-party code or data is included.
