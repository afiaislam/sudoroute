"""Record SudoRoute's captioned demo video (real app, real clicks, no editing tricks).

Optional tool: needs `pip install playwright` and a freshly started server (python run.py) with an empty data folder.
usage: python scripts/record_demo.py <out_dir>      → <out_dir>/sudoroute-demo.webm + chapters.txt
"""
import asyncio, os, re, sys, shutil
from playwright.async_api import async_playwright

BASE = os.environ.get("SR_BASE", "http://127.0.0.1:8000")
OUT = sys.argv[1]
W, H = 1280, 720
CHAPTERS = []
CAPLOG = []   # (chapter or "", caption) in order, used to place chapter marks on the final video
T0 = None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAP_JS = """(t) => {
  let c = document.getElementById('demo-cap');
  if (!c) { c = document.createElement('div'); c.id = 'demo-cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:9999;max-width:860px;width:calc(100% - 80px);' +
      'background:rgba(4,27,25,.94);color:#fff;font:600 19px/1.45 "Plus Jakarta Sans",system-ui,sans-serif;padding:14px 22px;border-radius:14px;' +
      'box-shadow:0 20px 50px -20px rgba(0,0,0,.6);border-left:5px solid #fbbf24;transition:opacity .25s;pointer-events:none';
    document.body.appendChild(c); }
  c.style.opacity = t ? '1' : '0'; c.textContent = t || '';
}"""
# lets the caption and a centred certificate show while the page is in print (PDF) view
PRINT_CSS = """@media print { #demo-cap { display:block !important; } html, body { background:#e9eef0 !important; }
  #certprint { max-width: 760px; margin: 24px auto !important; background:#fff; padding: 34px 40px; box-shadow: 0 30px 60px -30px rgba(0,0,0,.35); border-radius: 6px; } }"""


async def cap(pg, text, ms=2600, chapter=None):
    if chapter:
        CHAPTERS.append((chapter, round(asyncio.get_event_loop().time() - T0, 1)))
    if text:
        CAPLOG.append((chapter or "", text))
    if os.environ.get("SR_REC_DEBUG"):
        print(round(asyncio.get_event_loop().time() - T0, 1), text[:60], flush=True)
    await pg.evaluate(CAP_JS, text)
    await pg.wait_for_timeout(ms)
    if text:
        await pg.evaluate(CAP_JS, "")
        await pg.wait_for_timeout(220)


async def type_slow(pg, sel, text, delay=24):
    await pg.click(sel)
    await pg.type(sel, text, delay=delay)


async def scroll_to(pg, sel, ms=800):
    await pg.evaluate(f"(() => {{ const e = document.querySelector({sel!r}); if (e) e.scrollIntoView({{block:'center',behavior:'smooth'}}); }})()")
    await pg.wait_for_timeout(ms)


async def login(pg, email, pw, role, caption, chapter):
    """Visible sign-in through the real login page."""
    await pg.goto(BASE + f"/login?role={role}"); await pg.wait_for_timeout(600)
    await cap(pg, caption, 1900, chapter)
    await type_slow(pg, "#l-email", email, 18)
    await type_slow(pg, "#l-pw", pw, 18)
    await pg.wait_for_timeout(250)
    await pg.click("#login button[type=submit]")
    await pg.wait_for_url(re.compile(".*/(app|guardian).*"))
    await pg.wait_for_timeout(1100)


async def logout(pg):
    await pg.evaluate("document.querySelectorAll('#phonetoast').forEach(e => e.remove())")
    await pg.click("#mebtn"); await pg.wait_for_timeout(350)
    await pg.click("#logout"); await pg.wait_for_timeout(800)


async def main():
    global T0
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_raw"); shutil.rmtree(tmp, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp, record_video_size={"width": W, "height": H})
        await ctx.add_init_script("try{localStorage.setItem('ts-theme','light');localStorage.setItem('sr-lang','en');localStorage.setItem('sr-announce-off','1');localStorage.setItem('sr-judge-collapsed','0')}catch(e){}")
        pg = await ctx.new_page()
        T0 = asyncio.get_event_loop().time()

        # ---------------------------------------------------------------- 1. welcome
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1600)
        await cap(pg, "SudoRoute is an AI agent that pays international students' tuition — safely, cheaply and on time.", 3600, "Welcome")
        await pg.evaluate("window.scrollTo({top:760,behavior:'smooth'})"); await pg.wait_for_timeout(1500)
        await cap(pg, "It checks every invoice, picks the cheapest licensed route, and nothing moves until the student — and the family — approve.", 3800)
        await pg.evaluate("window.scrollTo({top:1500,behavior:'smooth'})"); await pg.wait_for_timeout(1200)
        await cap(pg, "Every payment passes five checkpoints. The AI can prepare a payment — it can never send money on its own.", 3200)

        # ---------------------------------------------------------------- 2. student signs up
        await pg.goto(BASE + "/register?role=student"); await pg.wait_for_timeout(600)
        await cap(pg, "A student creates an account: university, phone, and the guardian's name and e-mail.", 1900, "Student sign-up")
        await type_slow(pg, "#r-name", "Md Soron")
        await pg.fill("#r-email", "soron@example.com")
        await pg.fill("#r-pw", "Tuition8Safe")
        await pg.fill("#r-phone", "01712345678")
        await pg.select_option("#r-country", "BD")
        await type_slow(pg, "#r-uni", "Meridian University of Technology", 14)
        await pg.wait_for_timeout(400)
        await pg.fill("#r-prog", "BSc Data Science, Year 2")
        await scroll_to(pg, ".gfield", 400)
        await pg.fill("#r-gname", "Mst Nishi")
        await pg.fill("#r-gemail", "nishi@example.com")
        await pg.wait_for_timeout(500)
        await pg.click("#register button[type=submit]")
        await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1500)
        await cap(pg, "His dashboard: what's due, the latest safe day to pay, the chance it arrives on time, and the risk of waiting.", 3600, "Dashboard")
        await pg.click(".aifab"); await pg.wait_for_timeout(700)
        await cap(pg, "SudoRoute AI is on every page — in English, Bangla or Chinese. It uses the same limits as the agent.", 3000)
        await pg.click(".aiclose"); await pg.wait_for_timeout(300)

        # ---------------------------------------------------------------- 3. guardian account (linked by e-mail)
        await logout(pg)
        await pg.goto(BASE + "/register?role=guardian"); await pg.wait_for_timeout(500)
        await cap(pg, "His mother, Mst Nishi, creates a guardian account with that e-mail — and is linked to him automatically.", 2000, "Guardian sign-up")
        await type_slow(pg, "#r-name", "Mst Nishi")
        await pg.fill("#r-email", "nishi@example.com")
        await pg.fill("#r-pw", "Family8Pass")
        await pg.fill("#r-phone", "01811223344")
        try:
            await pg.select_option("#r-rel", label="Mother")
        except Exception:
            pass
        await pg.click("#register button[type=submit]")
        await pg.wait_for_url(re.compile(".*/guardian.*")); await pg.wait_for_timeout(1400)
        await cap(pg, "The guardian sees his tuition, invoices and balances, and must approve any payment made with family money.", 3200)
        await logout(pg)

        # ---------------------------------------------------------------- 4. student login → scam → pay
        await login(pg, "soron@example.com", "Tuition8Safe", "student", "Student login: Soron signs in.", "Student login")
        await pg.click("#sidenav a[data-view=invoices]"); await pg.wait_for_selector("[data-verify^='INV-PHISH']"); await pg.wait_for_timeout(600)
        await cap(pg, "A fake invoice arrived: look-alike domain, new bank account, crypto, and hidden instructions for AI assistants.", 2000, "Scam check")
        await pg.click("[data-verify^='INV-PHISH']"); await pg.wait_for_timeout(1300)
        await scroll_to(pg, ".inline-result")
        await cap(pg, "Scored 100/100 and blocked. The hidden instructions are quarantined — never followed.", 3000)

        await pg.click("#sidenav a[data-view=assistant]"); await pg.wait_for_timeout(600)
        await cap(pg, "Now he asks the agent in plain words.", 1300, "Pay tuition")
        await type_slow(pg, "#msg", "Is my invoice real? If yes, pay it the cheapest legal way", 18); await pg.press("#msg", "Enter")
        await pg.wait_for_selector(".prop", timeout=30000); await pg.wait_for_timeout(1000)
        await cap(pg, "The real invoice is verified, the cheapest licensed route chosen, currency risk priced and ten compliance checks run.", 3800)
        await scroll_to(pg, ".prop .otphelp")
        await cap(pg, "The payment is signed — nothing has moved. Family money is used, so his mother must approve first.", 3400)
        await logout(pg)

        # ---------------------------------------------------------------- 5. guardian login → approve
        await login(pg, "nishi@example.com", "Family8Pass", "guardian", "Guardian login: his mother signs in.", "Guardian login")
        await pg.click("#sidenav a[data-view=approvals]"); await pg.wait_for_timeout(900)
        await pg.wait_for_selector("#phonetoast.in", timeout=10000); await pg.wait_for_timeout(500)
        await cap(pg, "Her own one-time code arrives on her phone, with the amount and the university. (Sandbox: no real SMS.)", 3200)
        await pg.click("#phonetoast [data-use]"); await pg.wait_for_timeout(1300)
        await cap(pg, "One tap fills in the code. She checks the payment and approves.", 2200)
        await pg.click("form.otp [data-act=approve]"); await pg.wait_for_timeout(1500)
        await logout(pg)

        # ---------------------------------------------------------------- 6. student confirms
        await login(pg, "soron@example.com", "Tuition8Safe", "student", "Back to the student.", "Student confirms")
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(900)
        await pg.wait_for_selector("#phonetoast.in", timeout=10000); await pg.wait_for_timeout(400)
        await cap(pg, "Approved by his mother — only now is his own code sent to him.", 2600)
        await pg.click("#phonetoast [data-use]"); await pg.wait_for_timeout(1000)
        await pg.click(".prop form.otp button[type=submit]"); await pg.wait_for_timeout(1800)
        await scroll_to(pg, "#history")
        await cap(pg, "Confirmed. The money goes only to the university's verified account.", 2600)
        await pg.click("[data-adv='7']"); await pg.wait_for_timeout(1800)
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(1000)
        await scroll_to(pg, "#history")
        await cap(pg, "A week later in the sandbox: the university has received it, on time.", 2600)

        # ---------------------------------------------------------------- 7. certificate + PDF + on-chain
        await pg.click("#sidenav a[data-view=certs]"); await pg.wait_for_timeout(900)
        await pg.click("[data-issue]"); await pg.wait_for_timeout(1500)
        await cap(pg, "The on-time payment becomes a signed certificate — proof for a landlord or bank, to start a credit history abroad.", 3400, "Certificate")
        cert = (await pg.inner_text(".certcode")).strip()
        await pg.goto(BASE + "/verify#" + cert); await pg.wait_for_timeout(1800)
        await scroll_to(pg, "#vout")
        await cap(pg, "Anyone can verify it with SudoRoute's public key. Change one character and it fails.", 3000)
        await pg.add_style_tag(content=PRINT_CSS)
        await scroll_to(pg, "#pdfbtn", 600)
        await pg.hover("#pdfbtn"); await pg.wait_for_timeout(700)
        await pg.emulate_media(media="print"); await pg.wait_for_timeout(500)
        await pg.evaluate("window.scrollTo(0,0)")
        await cap(pg, "Download PDF: a one-page certificate with the verified details, the Bitcoin hash and the signed code.", 3800)
        await pg.emulate_media(media="screen"); await pg.wait_for_timeout(400)
        await pg.wait_for_selector(".anchorbox", timeout=15000)
        await scroll_to(pg, ".anchorbox", 900)
        await cap(pg, "On-chain proof: a fingerprint of the certificate and the audit log is timestamped on Bitcoin via OpenTimestamps — no money, no personal data.", 4400, "On-chain proof")
        import base64
        with open(os.path.join(ROOT, "evidence", "onchain", "onchain_confirmed.png"), "rb") as f:
            img = base64.b64encode(f.read()).decode()
        await pg.set_content(f"""<html><body style="margin:0;background:#f4f7f6;font-family:system-ui,sans-serif;display:grid;place-items:center;height:100vh">
          <div style="text-align:center"><div style="font:700 15px system-ui;color:#0b5e57;letter-spacing:.08em;text-transform:uppercase;margin-bottom:12px">opentimestamps.org · our anchored test record</div>
          <img src="data:image/png;base64,{img}" style="width:1000px;border-radius:14px;box-shadow:0 30px 60px -30px rgba(0,0,0,.35)"></div></body></html>""")
        await pg.wait_for_timeout(500)
        await cap(pg, "This recording runs offline, so the badge above says 'not submitted'. Our test record, checked at opentimestamps.org, is confirmed in Bitcoin block 972087.", 4600)

        # ---------------------------------------------------------------- 8. smart timing (a second student)
        await pg.goto(BASE + "/app"); await pg.wait_for_timeout(900)
        await logout(pg)
        await pg.goto(BASE + "/register?role=student"); await pg.wait_for_timeout(400)
        await pg.fill("#r-name", "Rahim Uddin"); await pg.fill("#r-email", "rahim@example.com"); await pg.fill("#r-pw", "Tuition8Safe")
        await pg.fill("#r-phone", "01911223344"); await pg.select_option("#r-country", "BD")
        await pg.fill("#r-uni", "Meridian University of Technology"); await pg.wait_for_timeout(300)
        await pg.fill("#r-prog", "BBA, Year 1")
        await pg.fill("#r-gname", "Karim Uddin"); await pg.fill("#r-gemail", "karim@example.com")
        await pg.click("#register button[type=submit]")
        await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1000)
        await pg.click("#sidenav a[data-view=assistant]"); await pg.wait_for_timeout(500)
        await cap(pg, "AI as a financial participant: another student, Rahim, asks it to pay at the best rate — but never late.", 2600, "Smart timing")
        await type_slow(pg, "#msg", "Pay at the best rate before my deadline", 18); await pg.press("#msg", "Enter")
        await pg.wait_for_selector(".smartbox", timeout=30000); await pg.wait_for_timeout(800)
        await scroll_to(pg, ".smartbox")
        await cap(pg, "It prices a target rate with 3,000 simulated futures: the chance it is reached, the expected saving, and a signed price floor.", 4000)
        await pg.wait_for_selector("#phonetoast.in", timeout=10000); await pg.wait_for_timeout(300)
        await pg.click("#phonetoast [data-use]"); await pg.wait_for_timeout(800)
        await pg.click(".prop form.otp button[type=submit] >> nth=-1"); await pg.wait_for_timeout(1400)
        await cap(pg, "He approves once. From then on the agent watches the rate every day by itself.", 2800)
        for _ in range(8):
            await pg.click("[data-adv='7']"); await pg.wait_for_timeout(800)
            done = await pg.evaluate("async () => (await TS.api('/api/state')).mandates.some(m => m.kind === 'smart_timing' && m.status !== 'active')")
            if done:
                break
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(1200)
        await cap(pg, "It paid on its own — at the target rate or on the last safe day — to the verified account, on time, never below the floor.", 4000)
        await logout(pg)

        # ---------------------------------------------------------------- 9. judge mode
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(900)
        await cap(pg, "Judges can try all of this in one click — a private sandbox with a student and his mother.", 2600, "Judge mode")
        await pg.click(".hero4 [data-judge]"); await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1500)
        await cap(pg, "The 60-second tour on the right: one button per step.", 2000)
        await pg.click("[data-j=ask]"); await pg.wait_for_selector(".prop", timeout=30000); await pg.wait_for_timeout(1300)
        await pg.click("[data-j=switch]"); await pg.wait_for_url(re.compile(".*/guardian.*")); await pg.wait_for_timeout(1300)
        await pg.evaluate("document.querySelectorAll('#phonetoast').forEach(e => e.remove())")
        await pg.click("[data-j=gcode]"); await pg.wait_for_timeout(1100)
        await cap(pg, "Switch to the mother, fill her code in one click, approve…", 1800)
        await pg.click("form.otp [data-act=approve]"); await pg.wait_for_timeout(1200)
        await pg.click("[data-j=switch]"); await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1300)
        await pg.evaluate("document.querySelectorAll('#phonetoast').forEach(e => e.remove())")
        await pg.click("[data-j=payments]"); await pg.wait_for_timeout(1100)
        await cap(pg, "…switch back, fill the student's code, confirm. No copying, no setup.", 1800)
        await pg.click(".prop form.otp button[type=submit]"); await pg.wait_for_timeout(1800)

        # ---------------------------------------------------------------- 10. security lab
        await pg.goto(BASE + "/security-lab"); await pg.wait_for_timeout(800)
        await cap(pg, "Finally, try to break it: 57 real attacks against a live copy — including a deliberately hostile AI model.", 2000, "Security Lab")
        await pg.click("#run")
        await pg.wait_for_selector(".labrow", timeout=60000); await pg.wait_for_timeout(1300)
        await cap(pg, "Prompt injection in four languages, tampering, replay, forged approvals — every attack stopped, every control works: 63 of 63.", 3800)
        await pg.evaluate("window.scrollTo({top:900,behavior:'smooth'})"); await pg.wait_for_timeout(1000)
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1200)
        await cap(pg, "SudoRoute — AI proposes, code disposes, humans execute.", 3000, "Wrap-up")
        await cap(pg, "", 300)
        video = pg.video
        await ctx.close()
        src = await video.path()
        await b.close()
    shutil.move(src, os.path.join(OUT, "sudoroute-demo.webm"))
    shutil.rmtree(tmp, ignore_errors=True)
    with open(os.path.join(OUT, "chapters.txt"), "w") as f:
        for name, t in CHAPTERS:
            f.write(f"{t}\t{name}\n")
    with open(os.path.join(OUT, "captions.txt"), "w") as f:
        for ch, text in CAPLOG:
            f.write(f"{ch}\t{text}\n")
    print("chapters", CHAPTERS)


asyncio.run(main())
