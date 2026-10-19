// Renderers for the agent's structured results. Everything from the server is escaped.
const Cards = (() => {
  const { esc, fmt, md, api, date } = TS;
  const el = html => { const t = document.createElement("div"); t.innerHTML = html.trim(); return t.firstElementChild; };
  const pill = (cls, text) => `<span class="pill ${esc(cls)}">${esc(text)}</span>`;
  const VERDICT = { SAFE: "Looks genuine", REVIEW: "Check with university", BLOCK: "Scam — blocked" };
  const STATUS = { in_transit: "In transit", credited: "Arrived", credited_short: "Arrived short", returned: "Returned", awaiting_guardian: "Waiting for guardian", awaiting_confirmation: "Ready to confirm",
    open: "Open", paid: "Paid", partially_paid: "Part paid", active: "Running", completed: "Completed", paused: "Paused", revoked: "Cancelled" };
  const st = s => pill(s, STATUS[s] || String(s).replace(/_/g, " "));

  function render(c, ctx = {}) {
    const f = { suggestions, balances, invoices, risk, routes, fx, budget, credit, audit, status, refusal, proposal }[c.type];
    return f ? f(c, ctx) : el(`<div class="card"><pre>${esc(JSON.stringify(c, null, 2))}</pre></div>`);
  }

  function suggestions(c, ctx) {
    const n = el(`<div class="chips" style="padding:10px 0 0">${c.items.map(i => `<button class="chip" type="button">${esc(i)}</button>`).join("")}</div>`);
    n.querySelectorAll("button").forEach(b => b.addEventListener("click", () => ctx.send && ctx.send(b.textContent)));
    return n;
  }
  function balances(c) {
    return el(`<div class="card"><h4>Wallets</h4><table><thead><tr><th>Currency</th><th class="n">Balance</th><th class="n">In ${esc(c.study_currency)}</th></tr></thead><tbody>
      ${c.rows.map(r => `<tr><td>${esc(r.currency)}</td><td class="n">${fmt(r.amount, 2)}</td><td class="n">${fmt(r.in_study, 2)}</td></tr>`).join("")}</tbody></table></div>`);
  }
  function invoices(c) {
    return el(`<div class="card"><h4>Invoices</h4><div class="tablewrap"><table><thead><tr><th>Invoice</th><th>From</th><th class="n">Amount</th><th>Due</th><th>Check</th></tr></thead><tbody>
      ${c.rows.map(r => `<tr><td>${esc(r.id)}</td><td>${esc(r.from)}</td><td class="n">${esc(r.currency)} ${fmt(r.amount, 2)}</td><td>${date(r.due)}</td><td>${pill(r.verdict, VERDICT[r.verdict])}</td></tr>`).join("")}</tbody></table></div></div>`);
  }
  function risk(c) {
    const color = { SAFE: "var(--ok)", REVIEW: "var(--amber)", BLOCK: "var(--seal)" }[c.verdict];
    const inj = (c.injection_scan.findings || []).filter(x => x.excerpt);
    return el(`<div class="card verdict-${esc(c.verdict)}" role="${c.verdict === "BLOCK" ? "alert" : "group"}"><div class="riskhead">
        <div class="gauge" style="--v:${Math.max(c.score, 3)};--c:${color}"><div>${c.score}</div></div>
        <div>${pill(c.verdict, VERDICT[c.verdict])}<div style="font-weight:600;margin-top:6px">${esc(c.invoice.id)}</div>
        <div style="color:var(--ink-3);font-size:13px;overflow-wrap:anywhere">${esc(c.invoice.from || "")} · ${esc(c.invoice.currency || "")} ${fmt(c.invoice.amount, 2)}</div></div></div>
      ${c.reasons.length ? `<ul class="reasons">${c.reasons.map(r => `<li><span class="pts">+${r.points}</span><span>${esc(r.message)}</span></li>`).join("")}</ul>`
        : `<p style="color:var(--ink-2);margin:0">No warning signs. Sender, bank account, amount and currency all match the university's verified record.</p>`}
      ${inj.length ? `<div class="quarantine"><b>Hidden instructions found and ignored</b>${inj.map(x => esc(x.excerpt)).join("<br>")}</div>` : ""}
      <div class="advice ${c.verdict}">${esc(c.advice)}</div></div>`);
  }
  function routes(c) {
    const max = Math.max(...c.routes.map(r => r.total_src));
    return el(`<div class="card"><h4>Ways to send ${esc(c.dst)} ${fmt(c.amount_dst, 2)} ${pill("neutral", `paying from ${c.src}`)}</h4>
      <div class="tablewrap"><table><thead><tr><th>Channel</th><th class="n">Total cost</th><th class="n">Hidden FX</th><th class="n">Fee</th><th class="n">Days</th><th class="n">Late risk</th><th></th></tr></thead><tbody>
      ${c.routes.map(r => { const best = r.eligible && c.best && r.provider_id === c.best.provider_id; return `<tr class="${best ? "best" : ""} ${r.eligible ? "" : "blocked"}">
        <td>${esc(r.provider)}<div style="height:4px;background:var(--sunk);border-radius:9px;margin-top:6px;position:relative"><div class="routefill" style="position:absolute;inset:0 auto 0 0;width:${(r.total_src / max * 100).toFixed(1)}%;background:${r.eligible ? "var(--note)" : "var(--line-2)"};border-radius:9px"></div></div>
        ${r.eligible ? "" : `<div style="font-size:12.5px;margin-top:4px">${esc(r.blocked_reasons[0])}</div>`}</td>
        <td class="n">${fmt(r.total_src)}</td><td class="n">${fmt(r.hidden_fx_cost_src)}</td><td class="n">${fmt(r.fee_src)}</td><td class="n">${r.arrival_days.join("–")}</td><td class="n">${(r.p_late * 100).toFixed(1)}%</td>
        <td>${r.eligible ? (best ? pill("ok", "Best") : "") : pill("bad", "Not allowed")}</td></tr>`; }).join("")}
      </tbody></table></div>
      ${c.savings_vs_bank_src ? `<p style="color:var(--ink-2);margin:12px 0 0;font-size:14px">Saves <b style="color:var(--ok)">${esc(c.src)} ${fmt(c.savings_vs_bank_src)}</b> compared with a bank wire. At the mid-market rate it would cost ${esc(c.src)} ${fmt(c.mid_cost_src)}.</p>` : ""}</div>`);
  }
  function fanChart(c) {
    const W = 640, H = 220, P = { l: 74, r: 12, t: 12, b: 26 };
    const fan = c.fan, last = fan[fan.length - 1].day;
    const vals = fan.flatMap(f => [f.p05, f.p95]).concat(c.budget_src ? [c.budget_src] : []);
    const lo = Math.min(...vals) * .995, hi = Math.max(...vals) * 1.005;
    const X = d => P.l + d / Math.max(1, last) * (W - P.l - P.r), Y = v => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
    const band = fan.map(f => `${X(f.day)},${Y(f.p95)}`).join(" ") + " " + fan.slice().reverse().map(f => `${X(f.day)},${Y(f.p05)}`).join(" ");
    const med = fan.map(f => `${X(f.day)},${Y(f.p50)}`).join(" "), now = c.strategies.pay_now.expected;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Range of possible tuition cost in ${esc(c.currency_src)} if you wait">
      ${[lo, (lo + hi) / 2, hi].map(t => `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line)"/><text x="${P.l - 8}" y="${Y(t) + 4}" text-anchor="end" fill="var(--ink-3)" font-size="11">${fmt(t)}</text>`).join("")}
      <polygon points="${band}" fill="var(--note)" opacity=".16"/>
      <polyline points="${med}" fill="none" stroke="var(--note)" stroke-width="2"/>
      <line x1="${P.l}" x2="${W - P.r}" y1="${Y(now)}" y2="${Y(now)}" stroke="var(--gold)" stroke-width="2" stroke-dasharray="6 4"/>
      ${c.budget_src ? `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(c.budget_src)}" y2="${Y(c.budget_src)}" stroke="var(--seal)" stroke-width="1.5"/>` : ""}
      <text x="${P.l}" y="${H - 6}" fill="var(--ink-3)" font-size="11">Today</text><text x="${W - P.r}" y="${H - 6}" text-anchor="end" fill="var(--ink-3)" font-size="11">Day ${last}</text></svg>
      <div class="legend"><span><i style="background:var(--note);opacity:.4;height:8px"></i>90% of outcomes if you wait</span><span><i style="background:var(--note)"></i>Middle outcome</span><span><i style="background:var(--gold)"></i>Pay now</span>${c.budget_src ? `<span><i style="background:var(--seal)"></i>Your budget ${fmt(c.budget_src)}</span>` : ""}</div>`;
  }
  function fx(c) {
    return el(`<div class="card"><h4>Exchange-rate risk ${pill("neutral", `${c.pair} · ${(c.annual_vol * 100).toFixed(1)}% yearly swings`)}</h4>
      ${fanChart(c)}
      <div class="tablewrap" style="margin-top:12px"><table><thead><tr><th>Option</th><th class="n">Expected</th><th class="n">Worst 5%</th><th class="n">Over budget</th><th></th></tr></thead><tbody>
      ${Object.entries(c.strategies).map(([k, s]) => `<tr class="${k === c.recommended ? "best" : ""}"><td>${esc(s.label)}${s.affordable_now ? "" : ` ${pill("warn", "needs more funds today")}`}</td><td class="n">${fmt(s.expected)}</td><td class="n">${fmt(s.p95)}</td><td class="n">${s.prob_over_budget == null ? "—" : (s.prob_over_budget * 100).toFixed(1) + "%"}</td><td>${k === c.recommended ? pill("ok", "Recommended") : ""}</td></tr>`).join("")}
      </tbody></table></div><p style="color:var(--ink-3);font-size:13px;margin:10px 0 0">Costs in ${esc(c.currency_src)}, from ${fmt(c.paths)} simulated paths of the exchange rate.</p></div>`);
  }
  function budget(c) {
    const mx = Math.max(...c.categories.map(x => Math.max(x.latest, x.average)));
    return el(`<div class="card"><h4>Budget and runway ${pill("neutral", c.study_currency)}</h4>
      <div class="stats"><div class="stat"><small>Monthly spending</small><span>${fmt(c.monthly_burn)}</span></div><div class="stat"><small>Monthly support</small><span>${fmt(c.monthly_inflow)}</span></div>
      <div class="stat"><small>Tuition still due</small><span>${fmt(c.tuition_outstanding)}</span></div><div class="stat"><small>Savings last</small><span>${c.runway_months == null ? "Covered by support" : c.runway_months + " months"}</span></div></div>
      <div class="bars">${c.categories.map(x => `<div class="bar"><span>${esc(x.category)}</span><div class="track"><div class="fill ${x.change_pct >= 20 ? "hot" : ""}" style="width:${(x.latest / mx * 100).toFixed(1)}%"></div></div><span class="v">${fmt(x.latest)} (${x.change_pct >= 0 ? "+" : ""}${x.change_pct}%)</span></div>`).join("")}</div>
      <ul class="reasons" style="margin-top:14px">${c.insights.map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`);
  }
  function credit(c) {
    const col = c.readiness_score >= 70 ? "var(--ok)" : c.readiness_score >= 40 ? "var(--amber)" : "var(--seal)";
    return el(`<div class="card verdict-${esc(c.verdict)}" role="${c.verdict === "BLOCK" ? "alert" : "group"}"><div class="riskhead"><div class="gauge" style="--v:${c.readiness_score};--c:${col}"><div>${c.readiness_score}</div></div>
      <div><div style="font-weight:600">Credit readiness in ${esc(c.study_country)}</div><div style="color:var(--ink-3);font-size:13px">${c.on_time_streak_months}-month on-time streak${c.months_to_reach_70 ? ` · about ${c.months_to_reach_70} month${c.months_to_reach_70 > 1 ? "s" : ""} to reach 70` : ""}</div></div></div>
      <ol class="steplist">${c.next_steps.map(s => `<li><b>${esc(s.step)}</b> ${pill("ok", "+" + s.points)}<br><span style="color:var(--ink-2)">${esc(s.action)}</span></li>`).join("")}</ol>
      <p style="color:var(--ink-3);font-size:13px;margin:10px 0 0">${esc(c.disclaimer)}</p></div>`);
  }
  function audit(c) {
    return el(`<div class="card"><h4>Activity log ${pill(c.verify.valid ? "ok" : "bad", c.verify.valid ? "Chain intact" : "Chain broken")}</h4>
      <ul class="list auditlist">${c.entries.slice().reverse().map(e => `<li><div class="grow"><b>${esc(e.event.replace(/_/g, " "))}</b><span class="h">#${e.seq} · ${esc(e.actor)} · ${esc(e.hash.slice(0, 16))}…</span></div></li>`).join("")}</ul></div>`);
  }
  function status(c) {
    return el(`<div class="card"><h4>Payments</h4><div class="tablewrap"><table><thead><tr><th>Transfer</th><th>Channel</th><th class="n">Sent</th><th class="n">Received</th><th>Arrives</th><th></th></tr></thead><tbody>
      ${c.transfers.map(t => `<tr><td>${esc(t.id)}</td><td>${esc(t.provider_name)}</td><td class="n">${esc(t.src_currency)} ${fmt(t.src_amount)}</td><td class="n">${esc(t.dst_currency)} ${fmt(t.dst_amount, 2)}</td><td>${date(t.eta)}</td><td>${st(t.status)}</td></tr>`).join("")}</tbody></table></div></div>`);
  }
  function refusal(c) {
    return el(`<div class="card" style="border-color:var(--seal)"><h4>Blocked in every mode ${pill("bad", "Not allowed")}</h4><p style="margin:0;color:var(--ink-2)">${esc(c.rule)}</p></div>`);
  }

  // Explains the one-time code and, in the sandbox, shows the "text message" that a real phone would receive.
  function otpHelp(pid, who) {
    return `<div class="otphelp" data-otp-for="${esc(pid)}" data-who="${who}"><b>What is this code?</b> ${who === "guardian"
      ? "Your student can't approve family money alone. SudoRoute texts a separate 6-digit code to your phone; entering it proves that you approve this exact payment."
      : "When a payment is ready, SudoRoute texts a 6-digit one-time code to your registered phone. Typing it proves it's really you approving this exact payment — not the AI, and not someone who got into your account. Each code works once, for this payment only."}
      <div class="smsline"><span>Demo mode: no real SMS is sent — the message arrives on the <b>phone icon</b> at the top of this page.</span><button type="button" class="btn sm" data-showsms>Show the text message</button></div></div>`;
  }
  async function revealSms(box) {
    const pid = box.dataset.otpFor, who = box.dataset.who;
    const data = await api(who === "guardian" ? "/api/guardian/overview" : "/api/state");
    const inbox = who === "guardian" ? (data.inbox || []) : (data.sms_inbox || []);
    const m = inbox.slice().reverse().find(x => x.proposal_id === pid);
    const line = box.querySelector(".smsline");
    if (!m) { line.innerHTML = `<span>No message for this payment yet.</span>`; return; }
    const code = (m.text.match(/\b(\d{6})\b/) || [])[1];
    line.innerHTML = `<span class="smsbox">📱 ${esc(m.to)}: ${esc(m.text)}</span>${code ? `<button type="button" class="btn sm primary" data-usecode="${code}">Use this code</button>` : ""}`;
    const use = line.querySelector("[data-usecode]");
    if (use) use.addEventListener("click", () => {
      const input = box.closest(".card").querySelector("form.otp input");
      if (input && !input.disabled) { input.value = use.dataset.usecode; input.focus(); }
    });
  }
  document.addEventListener("click", e => { const b = e.target.closest("[data-showsms]"); if (b) Motion.busy(b, () => revealSms(b.closest(".otphelp"))); });

  function proposal(c, ctx = {}) {
    const p = c.proposal;
    const status = c.status || "awaiting_confirmation";
    const waitingG = status === "awaiting_guardian";
    const passed = c.checks.checks.filter(x => x.status === "PASS").length;
    const card = el(`<div class="card prop"><h4><span>Payment ready for approval</span>${st(status)}</h4>
      <div class="bigamt num">${esc(p.dst_currency)} ${fmt(p.total_dst, 2)}</div>
      <div style="color:var(--ink-2);margin-top:4px">to <b>${esc(p.university_name)}</b>, ${esc(p.payee_bank)} · reference ${esc(p.reference)}</div>
      <div class="stats"><div class="stat"><small>Channel</small><span style="font-weight:500">${esc(p.provider_name)}</span></div>
        <div class="stat"><small>You pay about</small><span>${esc(p.src_currency)} ${fmt(p.total_src_quote)}</span></div>
        <div class="stat"><small>Payee account</small><span>${esc(p.payee_account.slice(0, 3))}•••${esc(p.payee_account.slice(-4))}</span></div>
        <div class="stat"><small>Quote valid until</small><span>${new Date(p.expires_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span></div></div>
      ${p.legs.length > 1 ? `<div class="legrow">${p.legs.map(l => `<div class="leg"><small>Installment ${l.leg} · ${date(l.execute_on)}</small><b>${esc(p.dst_currency)} ${fmt(l.dst_amount, 2)}</b><small>≈ ${esc(p.src_currency)} ${fmt(l.src_amount_quote)}</small></div>`).join("")}</div>
        <p style="color:var(--ink-2);font-size:13.5px;margin:0">After you confirm, installments 2–${p.legs.length} run on their dates — same payee and invoice only, and they pause if ${esc(p.src_currency)} weakens more than ${(p.max_slippage * 100).toFixed(0)}%. You can cancel any time.</p>` : ""}
      ${p.guardian_required && !ctx.readonly ? `<div class="alert ${c.guardian_approval ? "ok" : "info"}" style="margin:14px 0 0">${c.guardian_approval ? `Approved by ${esc(c.guardian_approval.name)}.` : `Waiting for ${esc((c.guardians || []).join(" and ") || "your guardian")} to approve. You can confirm after that.`}</div>` : ""}
      <details class="more" ${ctx.compact ? "" : "open"}><summary>${passed} of ${c.checks.checks.length} checks passed</summary>
        <div class="checks" style="margin-top:8px">${c.checks.checks.map(x => `<div class="check"><span class="ic ${x.status}">${{ PASS: "✓", WARN: "!", FAIL: "✕" }[x.status]}</span><span class="nm">${esc(x.check)}</span><span class="dt">${esc(x.detail)}</span></div>`).join("")}</div></details>
      ${c.route_explanation ? `<details class="more"><summary>Why this route</summary><ul class="reasons" style="margin-top:8px">${c.route_explanation.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
      ${ctx.readonly ? "" : `<form class="otp"><label class="otplabel" for="otp-${esc(p.proposal_id)}">Enter the 6-digit code texted to your phone</label><input id="otp-${esc(p.proposal_id)}" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" ${waitingG ? "disabled" : ""}>
        <button class="btn primary" type="submit" ${c.can_confirm === false || waitingG ? "disabled" : ""}>Confirm and pay</button></form>
        ${otpHelp(p.proposal_id, "student")}`}
      <div class="out"></div></div>`);
    const form = card.querySelector("form.otp");
    if (form) form.addEventListener("submit", async e => {
      e.preventDefault();
      const btn = form.querySelector("button");
      const r = await Motion.busy(btn, () => api("/api/confirm", { proposal_id: p.proposal_id, token: c.token, otp: form.querySelector("input").value }));
      btn.disabled = true;
      const out = card.querySelector(".out");
      if (r.ok) { out.innerHTML = `<div class="alert ok" style="margin:12px 0 0">${esc(r.message)}</div>`; form.remove(); }
      else { out.innerHTML = `<div class="alert bad" style="margin:12px 0 0">${esc(r.error)}</div>`; if (!["replay", "locked", "expired", "policy", "bank", "declined"].includes(r.code)) btn.disabled = false; }
      ctx.onChange && ctx.onChange();
    });
    return card;
  }

  return { render, pill, st, VERDICT, STATUS, el, otpHelp };
})();
