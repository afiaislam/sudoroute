# Changelog

## v10 — final submission build (October 2026)

- **Judge tour, one click per step:** the student's code stays quiet until the parent approves, then pops up on the
  sandbox phone; *Fill Nishi's code* / *Fill Soron's code* put the code in the right box and scroll to it. The tour
  ticks steps as soon as they happen; the panel no longer covers the payment card on laptop screens.
- **PDF certificate:** *Download PDF certificate* on the verify page (and *Download PDF* next to each issued
  certificate) prints a one-page A4 certificate with the verified claims, the on-chain hashes and the signed code.
  The anchor record (.json) and the OpenTimestamps proof (.ots) stay as they are: those are the files OpenTimestamps
  needs to check the Bitcoin timestamp.
- **Home page:** counters and the *check smarter · pay cheaper · approve safer* section in the brand colour;
  light proof section and footer links; scroll motion (progress line, headings, photo parallax, screenshots).
- **Corrected copy:** "Bounded AI" now describes the v7 design accurately (fixed tool list without a pay tool;
  e-mails read only by a tool-less AI that can raise but never clear a warning), and the FAQ explains that smart
  timing pays by itself only inside the signed payee, amount, price floor and deadline.
- **New demo video (4:10):** student and guardian sign-up and **login**, scam check, guardian and student approval with
  one-tap codes, arrival, certificate + PDF, on-chain proof (incl. the record confirmed in Bitcoin block 972087),
  smart timing, judge mode, Security Lab. Chapters on the home page updated.
- **README** rewritten: shorter, one table per topic, judge steps, results with the command that reproduces each one.
- **Contact:** WhatsApp (+880 1906-032900) and e-mail on the contact page (the footer stays clean); the separate
  *Home* link is gone (the logo goes home).
- **Only the home-page *Try it now — 1 click* button signs in by itself** (for judges). Every other *Get started*
  (navigation, announcement bar, pricing) opens a sign-in / create-account window for students and guardians.
- Greetings skip honorific prefixes ("Good morning, Soron", not "Md").
- 229 tests · Security Lab 63/63 · demo 41/41.


## v9 — a real website (October 2026)

- New language menu (dark glass, animated, keyboard accessible) replaces the native select that showed blank options.
- Announcement bar, new navigation (Product, Proof, Pricing, Help, Contact), wise-style footer with newsletter,
  five link columns and regulatory small print.
- New pages: Pricing (business model + calculator), Help center (search, animated accordions), Contact (topics,
  rating, success animation), Legal (terms, privacy, disclosure). Endpoints `/api/public/contact`, `/api/public/newsletter`.
- Every quote shows the SudoRoute service fee (0.5%, USD 3–25), waived during the pilot.
- Judge demo renamed: student **Md Soron**, mother **Mst Nishi**.
- Portal: sidebar never spills past short screens; help links in the sidebar; activity panel stays in view; menus above the judge panel.
- 229 tests.


## v8 — judge mode, AI auditor (October 2026)

- **Try it now — 1 click** (home and sign-in pages): a private sandbox per judge (own bank, FX market, clock, agent)
  with a student and a linked parent, a *Judge mode* panel (ask the agent → approve as parent → confirm → +7 days →
  certificate) and one-click role switching. Concurrent judges never affect each other; sandboxes expire after 24 h.
- **Independent AI auditor (hold-only).** Reviews every prepared payment and every autonomous smart-timing payment;
  may only HOLD with a reason. Holds are signed into the proposal and need an explicit human acknowledgment; any
  `approve`/`override` output is ignored. *AI proposes, code disposes, humans execute.*
- **Follow-ups:** the planner sees the student's last three requests.
- **Optional real SMS** (Twilio) to the account's own registered number, rate-limited, never logged.
- **Eval:** AI on vs off ablation (by language), follow-ups, verbatim real-Gemini transcript.
- **Security Lab 63/63** (57 attacks + 6 controls): AI-18 compromised auditor, PAY-14 skip a hold, CTL-06 human
  override. **220 tests.**
- **Design:** calmer section intros, compact cards and full-width buttons on phones, fixed phone layout of the portal.


## v7 — "AI as a Financial Participant" (October 2026)

**AI that participates, inside fences**
- **Agentic planner (Gemini).** Plan → act → observe → re-plan (≤3 rounds, ≤5 tools) over a fixed tool list with no
  execute tool. Multi-step requests in English, Bangla, Chinese and Malay ("Is my invoice real? If yes, pay it the
  cheapest legal way" → verify invoice → compare routes → prepare payment). The plan and every tool call are shown in
  the chat with their permission tier; every call still passes the permission gate, policy engine and audit log.
  Falls back to the rule engine without a key. (`sudoroute/agent/core.py::_plan_and_act`, `llm.plan`)
- **Quarantined AI reader (dual-LLM pattern).** A model with no tools reads untrusted e-mails/invoices inside random
  fences and returns typed, validated JSON only. Its findings can add risk points the rules missed but can never
  lower a verdict (monotonic merge, tested on all 16 flag combinations). Its output never reaches the planner.
  (`llm.read_document`, `engines/invoice_check.py::apply_ai_reading`)
- **Smart-timing autopay.** "Pay at the best rate before my deadline": target rate priced with EWMA volatility and
  3,000 Monte Carlo paths (chance reached, expected saving, worst case); one approval; the agent checks the rate
  every sandbox day and executes by itself on the target or on the latest safe day; never below a signed price floor
  (pauses instead); policy re-checked on execution; cancel and kill switch stop it. (`engines/fx_timing.py`,
  `core.py::_run_smart`)

**Security**
- **Authenticator app (RFC 6238 TOTP)** for students, with QR enrolment; SMS codes stop working once linked; each
  time-step accepted once; enabling/disabling needs password (+ code). (`security/totp.py`, `/api/totp/*`)
- **Security Lab: 60/60** (55 attacks + 5 controls). New: a deliberately hostile model replaces Gemini — plans
  `execute_payment`, two payments and a scam invoice (AI-14), ignores Advisor mode (AI-15), vouches for a phishing
  e-mail (AI-16), fakes an amount and asks for the code (AI-17); smart-timing replay (PAY-12) and price-floor
  tampering (PAY-13); SMS code after TOTP (AU-07); TOTP replay (AU-08); control: a smart-timing payment executes by
  itself inside its limits (CTL-05).

**Evidence**
- `scripts/eval_live_llm.py` — measures the real Gemini model (planner accuracy on 24 requests in 4 languages,
  reader on all 84 hold-out invoices, jailbreak leaks) → `evidence/live_llm_eval.md`.
- `scripts/run_demo.py` — 9 scenarios, 41 checked steps (adds smart timing and authenticator approval).
- 205 unit tests (was 179). Screenshots 36–39.
- Bitcoin anchor of the test record confirmed in block 972087.
