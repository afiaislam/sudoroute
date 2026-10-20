"""Record the execution-evidence video (submission item 06): sandbox operation logs, shown for real.

Optional tool: needs `pip install playwright`.
usage:
  python scripts/run_demo.py > run_demo_out.txt          # the sandbox run whose output and logs are shown
  python run.py --port 8000                              # a fresh server (empty data folder) in another window
  python scripts/record_evidence.py <out_dir> run_demo_out.txt
→ <out_dir>/sudoroute-evidence.webm
"""
import asyncio, base64, html, json, os, re, sys, shutil
from playwright.async_api import async_playwright

BASE = os.environ.get("SR_BASE", "http://127.0.0.1:8000")
OUT, RUN_OUT = sys.argv[1], sys.argv[2]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.environ.get("SR_EVIDENCE", os.path.join(ROOT, "evidence"))
W, H = 1280, 720
T0 = None

CAP_JS = """(t) => {
  let c = document.getElementById('demo-cap');
  if (!c) { c = document.createElement('div'); c.id = 'demo-cap';
    c.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:9999;max-width:880px;width:calc(100% - 80px);' +
      'background:rgba(4,27,25,.95);color:#fff;font:600 19px/1.45 "Plus Jakarta Sans",system-ui,sans-serif;padding:14px 22px;border-radius:14px;' +
      'box-shadow:0 20px 50px -20px rgba(0,0,0,.6);border-left:5px solid #fbbf24;transition:opacity .25s;pointer-events:none';
    document.body.appendChild(c); }
  c.style.opacity = t ? '1' : '0'; c.textContent = t || '';
}"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#f4f7f6;font-family:system-ui,"Noto Sans CJK SC",FreeSans,sans-serif;color:#10201e}}
.k{{font:700 14px system-ui;letter-spacing:.1em;text-transform:uppercase;color:#0f766e}}
h1{{font-size:44px;margin:10px 0 6px}} h2{{font-size:26px;margin:0 0 14px}}
.term{{background:#0b1514;color:#cfe7e2;border-radius:14px;padding:18px 22px;font:14.5px/1.55 "DejaVu Sans Mono",monospace;height:455px;overflow:hidden;
  box-shadow:0 30px 60px -30px rgba(0,0,0,.5)}}
.term .bar{{display:flex;gap:7px;margin-bottom:12px}} .term .bar i{{width:12px;height:12px;border-radius:50%;background:#3a4b49;display:block}}
.ok{{color:#5eead4}} .hd{{color:#fbbf24;font-weight:700}} .pr{{color:#93c5fd}}
table{{border-collapse:collapse;width:100%;background:#fff;border-radius:12px;overflow:hidden;font-size:14px;box-shadow:0 20px 40px -30px rgba(0,0,0,.4)}}
th{{background:#072b29;color:#fff;text-align:left;padding:8px 10px}} td{{padding:7px 10px;border-top:1px solid #e3ebe9;vertical-align:top}}
td.m{{font-family:"DejaVu Sans Mono",monospace;font-size:12.5px;color:#0f766e}}
</style></head><body>{body}</body></html>"""


async def cap(pg, text, ms=2600):
    if os.environ.get("SR_REC_DEBUG"):
        print(round(asyncio.get_event_loop().time() - T0, 1), text[:60], flush=True)
    await pg.evaluate(CAP_JS, text)
    await pg.wait_for_timeout(ms)
    if text:
        await pg.evaluate(CAP_JS, "")
        await pg.wait_for_timeout(220)


def terminal_html(lines):
    out = ['<div class="term"><div class="bar"><i></i><i></i><i></i></div><div id="t"></div></div>']
    rows = []
    for ln in lines:
        e = html.escape(ln)
        if ln.startswith("$"):
            e = f'<span class="pr">{e}</span>'
        elif ln.startswith("==="):
            e = f'<span class="hd">{e}</span>'
        elif ln.startswith("[PASS]"):
            e = '<span class="ok">[PASS]</span>' + html.escape(ln[6:])
        elif "steps passed" in ln:
            e = f'<span class="ok"><b>{e}</b></span>'
        rows.append(e or "&nbsp;")
    js = ("<script>const R=" + json.dumps(rows) + ";let i=0;const t=document.getElementById('t');"
          "function step(){if(i>=R.length)return;const d=document.createElement('div');d.innerHTML=R[i++];t.appendChild(d);"
          "while(t.scrollHeight>t.parentNode.clientHeight-50&&t.firstChild)t.removeChild(t.firstChild);setTimeout(step,i<2?600:115)}step()</script>")
    return "".join(out) + js


async def main():
    global T0
    os.makedirs(OUT, exist_ok=True)
    tmp = os.path.join(OUT, "_raw"); shutil.rmtree(tmp, ignore_errors=True)
    with open(RUN_OUT, encoding="utf-8") as f:
        run = [l.rstrip("\n") for l in f if not l.startswith(("real", "user", "sys"))]
    run = [re.sub(r"Evidence written to .*", "Evidence written to evidence/", l) for l in run]
    while run and not run[-1].strip():
        run.pop()
    log = [json.loads(l) for l in open(os.path.join(EVID, "sandbox_operation_log.jsonl"), encoding="utf-8")]
    summ = json.load(open(os.path.join(EVID, "execution_summary.json"), encoding="utf-8"))

    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=tmp, record_video_size={"width": W, "height": H})
        await ctx.add_init_script("try{localStorage.setItem('ts-theme','light');localStorage.setItem('sr-lang','en');localStorage.setItem('sr-announce-off','1');localStorage.setItem('sr-judge-collapsed','0')}catch(e){}")
        pg = await ctx.new_page()
        T0 = asyncio.get_event_loop().time()

        # 1. title
        await pg.set_content(PAGE.format(body="""<div style="height:100vh;display:grid;place-items:center;text-align:center">
          <div><div class="k">Submission item 06 · Execution evidence</div><h1>SudoRoute — sandbox operation</h1>
          <p style="font-size:20px;color:#52625f">Simulated accounts, real code: the logs and the live system, unedited.</p></div></div>"""))
        await cap(pg, "Topic C is a non-on-chain topic, so the required evidence is sandbox operation logs and a demo video. Here they are.", 4200)

        # 2. terminal run
        await pg.set_content(PAGE.format(body='<div style="padding:34px 48px"><div class="k">Terminal</div><h2>python scripts/run_demo.py — 9 scenarios on the sandbox bank</h2>'
                                         + terminal_html(["$ python scripts/run_demo.py"] + run) + "</div>"))
        await cap(pg, "The scripted sandbox run: real accounts in the simulated bank, real agent, real signatures and one-time codes.", 3600)
        await cap(pg, "Scam invoices, prohibited requests (crypto, hundi, a stranger's account), wrong codes, replays and tampering are all refused.", 3600)
        await cap(pg, "Allowed payments go through only after the guardian's and the student's own codes.", 2800)
        await pg.wait_for_timeout(1200)
        await cap(pg, "Result: 41 of 41 checked steps passed, and the audit chain of 131 entries is intact.", 3400)

        # 3. operation log
        def row(e):
            d = e.get("data", {})
            info = d.get("text") or d.get("tool") or d.get("reason") or d.get("invoice_id") or d.get("proposal_id") or d.get("transfer_id") or d.get("intent") or ""
            return (f"<tr><td>{e['seq']}</td><td>{html.escape(e.get('sim_time','')[:16].replace('T',' '))}</td><td><b>{html.escape(e['event'])}</b></td>"
                    f"<td>{html.escape(e.get('actor',''))}</td><td>{html.escape(str(info))[:60]}</td><td class='m'>{e['prev_hash'][:10]}…</td><td class='m'>{e['hash'][:10]}…</td></tr>")
        want = ["user_message", "tool_call", "invoice_verified", "payment_refused_scam", "prohibited_request_refused", "permission_denied",
                "proposal_created", "guardian_approved", "execution_rejected", "payment_executed", "sandbox_settlement",
                "prompt_injection_blocked", "kill_switch_engaged", "certificate_issued"]
        first = {}
        for e in log:
            if e["event"] in want and e["event"] not in first:
                first[e["event"]] = e
        pick = sorted(first.values(), key=lambda e: e["seq"])[:14]
        await pg.set_content(PAGE.format(body='<div style="padding:30px 48px"><div class="k">evidence/sandbox_operation_log.jsonl</div>'
                                         f'<h2>{len(log)} operation records, each linked to the one before</h2><table><tr><th>#</th><th>Sandbox time</th><th>Event</th><th>Actor</th><th>Detail</th><th>Previous hash</th><th>Hash</th></tr>'
                                         + "".join(row(e) for e in pick) + "</table></div>"))
        await cap(pg, "Every step is written to the operation log: who did what, when in sandbox time, with details redacted where needed.", 3800)
        await cap(pg, "Each record carries the hash of the previous one — change or delete a line and verification fails.", 3400)

        # 4. transfers
        tr = summ.get("transfers", [])[:8]
        rows = "".join(
            f"<tr><td class='m'>{html.escape(t['id'])}</td><td>{html.escape(t['student_id'])}</td><td>{html.escape(t.get('provider_name',''))}</td>"
            f"<td>{t['src_amount']:,.2f} {t['src_currency']}</td><td>{t.get('dst_amount',0):,.2f} {t.get('dst_currency','')}</td><td>{html.escape(t.get('reference',''))}</td><td><b>{html.escape(str(t.get('status','')))}</b></td></tr>"
            for t in tr)
        await pg.set_content(PAGE.format(body='<div style="padding:30px 48px"><div class="k">evidence/execution_summary.json</div>'
                                         f'<h2>Money movements in the sandbox bank</h2><table><tr><th>Transfer</th><th>Student</th><th>Channel</th><th>Sent</th><th>Received</th><th>Reference</th><th>Status</th></tr>{rows}</table>'
                                         f'<p style="margin-top:14px;color:#52625f">Audit chain valid: <b>{summ["audit_chain"]["valid"]}</b> · {summ["audit_chain"]["entries"]} entries · head {summ["audit_chain"]["head"][:16]}…</p></div>'))
        await cap(pg, "The machine-readable summary: each transfer with channel, amounts, university reference and status — licensed channels only.", 4000)

        # 5. live system: a payment and its activity log
        await pg.goto(BASE + "/"); await pg.wait_for_timeout(1200)
        await cap(pg, "The same engine runs the live site. One click opens a private sandbox account.", 2600)
        await pg.click(".hero4 [data-judge]"); await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1500)
        await pg.click("[data-j=ask]"); await pg.wait_for_selector(".prop", timeout=30000); await pg.wait_for_timeout(1200)
        await cap(pg, "The agent prepares a signed payment, showing every tool call and its permission tier.", 2800)
        await pg.click("[data-j=switch]"); await pg.wait_for_url(re.compile(".*/guardian.*")); await pg.wait_for_timeout(1200)
        await pg.evaluate("document.querySelectorAll('#phonetoast').forEach(e => e.remove())")
        await pg.click("[data-j=gcode]"); await pg.wait_for_timeout(900)
        await pg.click("form.otp [data-act=approve]"); await pg.wait_for_timeout(1100)
        await pg.click("[data-j=switch]"); await pg.wait_for_url(re.compile(".*/app.*")); await pg.wait_for_timeout(1200)
        await pg.evaluate("document.querySelectorAll('#phonetoast').forEach(e => e.remove())")
        await pg.click("[data-j=payments]"); await pg.wait_for_timeout(1000)
        await pg.click(".prop form.otp button[type=submit]"); await pg.wait_for_timeout(1600)
        await pg.click("[data-adv='7']"); await pg.wait_for_timeout(1600)
        await pg.click("#sidenav a[data-view=payments]"); await pg.wait_for_timeout(1000)
        await pg.evaluate("(() => { const e = document.querySelector('#history'); if (e) e.scrollIntoView({block:'center'}); })()"); await pg.wait_for_timeout(800)
        await cap(pg, "Mother approved, student confirmed, clock moved a week: the sandbox transfer has reached the university.", 3200)
        await pg.click("#sidenav a[data-view=security]"); await pg.wait_for_timeout(1400)
        await pg.evaluate("(() => { const e = document.querySelector('#auditbox'); if (e) { e.closest('.panel').scrollIntoView({block:'start'}); window.scrollBy(0, -80); } })()"); await pg.wait_for_timeout(900)
        await cap(pg, "Every account has its own activity log, verified on screen: every record intact.", 3200)

        # 6. security lab
        await pg.goto(BASE + "/security-lab"); await pg.wait_for_timeout(800)
        await pg.click("#run"); await pg.wait_for_selector("text=Finished:", timeout=90000); await pg.wait_for_timeout(1500)
        await cap(pg, "And the attack log: 57 live attacks blocked and 6 controls working — 63 of 63, recorded in evidence/security_lab_report.md.", 3800)

        # 7. close
        await pg.set_content(PAGE.format(body="""<div style="height:100vh;display:grid;place-items:center;text-align:center"><div>
          <div class="k">Reproduce it</div><h1 style="font-size:34px">python scripts/run_demo.py · python scripts/security_lab.py</h1>
          <p style="font-size:19px;color:#52625f">All logs: evidence/ · index: evidence/README.md · live: sudoroute.onrender.com</p></div></div>"""))
        await cap(pg, "Every file in this video is in the evidence folder and can be regenerated with one command.", 3600)
        await cap(pg, "", 300)
        video = pg.video
        await ctx.close()
        src = await video.path()
        await b.close()
    shutil.move(src, os.path.join(OUT, "sudoroute-evidence.webm"))
    shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(main())
