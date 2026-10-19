"""Record SudoRoute's captioned demo video (real app, real clicks). Optional: needs `pip install playwright` and a running server (python run.py).


usage: python record_demo.py <out_dir>
"""
import asyncio, os, re, sys, shutil, glob
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT = sys.argv[1]
W, H = 1280, 720
CHAPTERS = []
T0 = None

CAP_JS = """(t) => {
  let c = document.getElementById('demo-cap');
  if (!c) { c = document.createElement('div'); c.id = 'demo-cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:9999;max-width:860px;width:calc(100% - 80px);' +
      'background:rgba(4,27,25,.94);color:#fff;font:600 19px/1.45 "Plus Jakarta Sans",system-ui,sans-serif;padding:14px 22px;border-radius:14px;' +
      'box-shadow:0 20px 50px -20px rgba(0,0,0,.6);border-left:5px solid #fbbf24;transition:opacity .25s';
    document.body.appendChild(c); }
  c.style.opacity = t ? '1' : '0'; c.textContent = t || '';
}"""


async def cap(pg, text, ms=2600, chapter=None):
    if chapter:
        CHAPTERS.append((chapter, round(asyncio.get_event_loop().time() - T0, 1)))
    await pg.evaluate(CAP_JS, text)
    await pg.wait_for_timeout(ms)
    if text:
        await pg.evaluate(CAP_JS, "")  # captions never linger into the next scene
        await pg.wait_for_timeout(250)


async def type_slow(pg, sel, text):
    await pg.click(sel)
    await pg.type(sel, text, delay=28)


async def api_login(pg, email, pw, role):
    await pg.goto(BASE + f"/login?role={role}")
    await pg.wait_for_timeout(500)
    await pg.fill("#l-email", email); await pg.fill("#l-pw", pw); await pg.wait_for_timeout(300)
    await pg.click("#login button[type=submit]")
    await pg.wait_for_url(re.compile(".*/(app|guardian).*"))
    await pg.wait_for_timeout(900)


async def logout(pg):
    await pg.click("#mebtn"); await pg.wait_for_timeout(400)
    await pg.click("#logout"); await pg.wait_for_timeout(900)


async def main():
    global T0
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_raw"); shutil.rmtree(tmp, ignore_errors=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp, record_video_size={"width": W, "height": H})
        await ctx.add_init_script("try{localStorage.setItem('ts-theme','light');localStorage.setItem('sr-lang','en')}catch(e){}")
        pg = await ctx.new_page()
        T0 = asyncio.get_event_loop().time()

        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1800)
        await cap(pg, "SudoRoute is an AI agent that pays international students' tuition — safely, cheaply and on time.", 3600, "Welcome")
        await pg.mouse.move(300, 36); await pg.hover("#mainnav .dd:nth-of-type(2) .navlink"); await pg.wait_for_timeout(1300)
        await pg.mouse.move(640, 400)
        for y in (700, 1500, 2300):
            await pg.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})"); await pg.wait_for_timeout(1100)
        await cap(pg, "Every payment passes five checkpoints. Nothing moves before the last one.", 2600)

        # ---- student sign-up
        await pg.goto(BASE + "/register?role=student"); await pg.wait_for_timeout(700)
        await cap(pg, "A student signs up: their university, and their guardian's name and e-mail.", 1800, "Sign up")
        await type_slow(pg, "#r-name", "Afia Islam")
        await type_slow(pg, "#r-email", "afia@example.com")
        await type_slow(pg, "#r-pw", "Tuition8Safe")
        await pg.fill("#r-phone", "01712345678")
        await pg.select_option("#r-country", "BD")
        await type_slow(pg, "#r-uni", "Meridian University of Technology")
        await pg.wait_for_timeout(500)
        await pg.fill("#r-prog", "BSc Data Science, Year 2")
        await pg.evaluate("document.querySelector('.gfield').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(500)
        await type_slow(pg, "#r-gname", "Ashraful Islam")
        await type_slow(pg, "#r-gemail", "ashraful@example.com")
        await pg.wait_for_timeout(500)
        await pg.click("#register button[type=submit]")
        await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1600)
        await cap(pg, "The dashboard: what's due, the latest safe day to pay, the chance it arrives on time, and the risk of waiting.", 3600, "Dashboard")
        await pg.evaluate("document.querySelector('#aibrief').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(800)
        await cap(pg, "SudoRoute AI writes a money brief from her live numbers — in English, Bangla or Chinese — and every figure is checked.", 3400, "SudoRoute AI")
        await pg.click(".aifab"); await pg.wait_for_timeout(600)
        await pg.click(".aichips .chip >> nth=0"); await pg.wait_for_timeout(2200)
        await cap(pg, "The AI button is on every page. It uses the same tools and limits as the agent: it can advise and prepare, never pay alone.", 3800)
        await pg.click(".aiclose"); await pg.wait_for_timeout(400)

        # ---- guardian signs up (linked by e-mail)
        await logout(pg)
        await pg.goto(BASE + "/register?role=guardian"); await pg.wait_for_timeout(600)
        await cap(pg, "Her father, Ashraful Islam, signs up with the e-mail she gave — and is linked automatically.", 2000, "Guardian joins")
        await type_slow(pg, "#r-name", "Ashraful Islam")
        await type_slow(pg, "#r-email", "ashraful@example.com")
        await type_slow(pg, "#r-pw", "Family8Pass")
        await pg.fill("#r-phone", "01811223344")
        await pg.select_option("#r-rel", "Father")
        await pg.click("#register button[type=submit]")
        await pg.wait_for_url(re.compile(".*/guardian.*")); await pg.wait_for_timeout(1500)
        await cap(pg, "The guardian sees the student's tuition, invoices and balances — and approves every payment made with family money.", 3200)
        await logout(pg)
        await api_login(pg, "afia@example.com", "Tuition8Safe", "student")

        # ---- scam check
        await pg.click("#sidenav a[data-view=invoices]"); await pg.wait_for_selector("[data-verify^='INV-PHISH']"); await pg.wait_for_timeout(700)
        await cap(pg, "A fake invoice arrived: look-alike domain, new bank account, crypto, and hidden instructions for AI assistants.", 1600, "Scam check")
        await pg.click("[data-verify^='INV-PHISH']"); await pg.wait_for_timeout(1300)
        await pg.evaluate("document.querySelector('.inline-result').scrollIntoView({block:'center',behavior:'smooth'})")
        await cap(pg, "Scored 100/100 and blocked. The hidden instructions are quarantined — never followed.", 3200)
        await pg.click("[data-email-inv]"); await pg.wait_for_timeout(1200)
        await pg.evaluate("document.querySelector('.emailcard').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(700)
        await cap(pg, "The AI drafts a message to the university's real finance office. SudoRoute never sends it for her.", 3000)

        # ---- pay
        await pg.click("#sidenav a[data-view=assistant]"); await pg.wait_for_timeout(700)
        await cap(pg, "Now the student asks the agent to pay.", 1300, "Pay tuition")
        await type_slow(pg, "#msg", "Pay my tuition"); await pg.press("#msg", "Enter")
        await pg.wait_for_selector(".prop"); await pg.wait_for_timeout(900)
        await cap(pg, "It picked the cheapest licensed route, priced currency risk and ran ten compliance checks. The proposal is signed — nothing has moved yet.", 4200)
        await pg.wait_for_selector("#phonetoast.in", timeout=8000); await pg.wait_for_timeout(700)
        await cap(pg, "A 6-digit one-time code is texted to her phone. In this sandbox no real SMS is sent — the phone is the icon at the top right.", 4200)
        await pg.click("#phonetoast .px"); await pg.wait_for_timeout(500)
        await pg.evaluate("document.querySelector('.prop .otphelp').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(900)
        await cap(pg, "Because family money is used, her father must approve first, with his own code.", 2800)
        await logout(pg)

        # ---- guardian approves
        await api_login(pg, "ashraful@example.com", "Family8Pass", "guardian")
        await pg.click("#sidenav a[data-view=approvals]"); await pg.wait_for_timeout(1200)
        await pg.wait_for_selector("#phonetoast.in", timeout=8000); await pg.wait_for_timeout(600)
        await cap(pg, "Ashraful's phone receives his own approval code, with the amount and the university.", 2600, "Guardian approves")
        await pg.click("#phonetoast [data-use]"); await pg.wait_for_timeout(1400)
        await cap(pg, "He checks the payment, the code is filled in, and he approves.", 1800)
        await pg.click("form.otp [data-act=approve]"); await pg.wait_for_timeout(1600)
        await logout(pg)

        # ---- student confirms
        await api_login(pg, "afia@example.com", "Tuition8Safe", "student")
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(1000)
        await cap(pg, "Back to the student: approved. Now the student confirms with their own code.", 1800, "Student confirms")
        await pg.click("#phonebtn"); await pg.wait_for_timeout(1000)
        await cap(pg, "Her code is waiting on her phone.", 1400)
        await pg.click("[data-phone-use]"); await pg.wait_for_timeout(900)
        await pg.click("form.otp button[type=submit]"); await pg.wait_for_timeout(1800)
        await pg.evaluate("document.querySelector('#history').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(700)
        await cap(pg, "Sent. Now a stress test: in the sandbox, an intermediary bank takes a fee on the way.", 2400, "When a transfer goes wrong")
        await pg.click(".whatfail summary"); await pg.wait_for_timeout(500)
        await pg.click("[data-inject=short]"); await pg.wait_for_timeout(1400)
        await pg.click("[data-adv='7']"); await pg.wait_for_timeout(1800)
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(1200)
        await pg.evaluate("document.querySelector('#history').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(700)
        await cap(pg, "A week later the money arrived — but short. SudoRoute reconciles every receipt against the invoice.", 2800)
        await pg.click("[data-recover]"); await pg.wait_for_timeout(1200)
        await cap(pg, "It explains what happened and offers to pay only the shortfall. Sending the full amount again is blocked, so the university is never paid twice.", 4400)

        # ---- certificate
        await pg.click("#sidenav a[data-view=certs]"); await pg.wait_for_timeout(1000)
        await pg.click("[data-issue]"); await pg.wait_for_timeout(1600)
        await cap(pg, "The on-time payment becomes a signed certificate — proof for a landlord or bank, to start a credit history abroad.", 3400, "Certificate")
        cert = (await pg.inner_text(".certcode")).strip()
        await pg.goto(BASE + "/verify#" + cert); await pg.wait_for_timeout(1800)
        await pg.evaluate("document.querySelector('#vout').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(700)
        await cap(pg, "Anyone can verify it with SudoRoute's public key. Change one digit and it fails.", 3000)
        await pg.wait_for_selector(".anchorbox", timeout=15000)
        await pg.evaluate("document.querySelector('.anchorbox').scrollIntoView({block:'center',behavior:'smooth'})"); await pg.wait_for_timeout(900)
        await cap(pg, "On-chain proof: a fingerprint of the certificate and the audit log is timestamped on the Bitcoin blockchain via OpenTimestamps — no money, no personal data, only a hash.", 4600, "On-chain proof")
        await cap(pg, "This recording was made offline, so it honestly says 'not submitted'. With internet it is sent within seconds and anyone can check it at opentimestamps.org.", 4400)

        # ---- security lab
        await pg.goto(BASE + "/security-lab"); await pg.wait_for_timeout(900)
        await cap(pg, "Finally, try to break it: 47 real attacks against a live copy of SudoRoute.", 1500, "Security Lab")
        await pg.click("#run")
        await pg.wait_for_selector(".labrow", timeout=60000); await pg.wait_for_timeout(1500)
        await cap(pg, "Prompt injection in four languages, tampering, replay, forged approvals, broken access control — every one stopped. 51 of 51.", 3800)
        for y in (900, 1800):
            await pg.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})"); await pg.wait_for_timeout(1000)
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1400)
        await cap(pg, "SudoRoute — tuition, routed safely from home to campus.", 3000, "Wrap-up")
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
    print("chapters", CHAPTERS)


asyncio.run(main())
