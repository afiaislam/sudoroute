(async () => {
  const { $, $$, esc, fmt, date, api, md, toast } = TS;
  const { pill, st } = Cards;
  const me = await TS.session();
  let S = null;            // latest /api/state
  let current = "overview";
  const view = $("#view");

  // The assistant's conversation survives switching pages.
  const chat = Cards.el(`<div class="chatwrap">
    <section class="chat" aria-label="Conversation with SudoRoute">
      <div class="thread" id="thread" aria-live="polite"></div>
      <div class="chips" id="chips"></div>
      <form class="composer" id="composer"><label class="sr" for="msg">Message</label>
        <textarea id="msg" rows="1" placeholder="Ask in English or বাংলা, or paste a suspicious e-mail"></textarea>
        <button class="btn primary" type="submit">Send</button></form>
    </section>
    <aside class="panel" style="margin:0"><h3>What the assistant did <small id="intent"></small></h3><ul class="trace" id="trace"><li class="empty" style="background:none">Each step appears here, with its permission level.</li></ul></aside>
  </div>`);
  const CHIPS = ["Is my invoice real? If yes, pay it the cheapest legal way", "Pay at the best rate before my deadline", "Pay my tuition", "Pay my tuition in installments", "Compare transfer options", "When should I pay?", "Show my budget", "How do I build credit?", "Where is my payment?"];
  chat.querySelector("#chips").innerHTML = CHIPS.map(c => `<button class="chip" type="button">${esc(c)}</button>`).join("");
  chat.querySelectorAll("#chips .chip").forEach(b => b.addEventListener("click", () => send(b.textContent)));
  chat.querySelector("#composer").addEventListener("submit", e => { e.preventDefault(); const t = chat.querySelector("#msg"); const v = t.value; t.value = ""; send(v); });
  chat.querySelector("#msg").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); chat.querySelector("#composer").requestSubmit(); } });

  document.addEventListener("sr:send", e => send(e.detail));
  function addMsg(who, html) {
    const d = document.createElement("div"); d.className = `msg ${who}`; d.innerHTML = html;
    const th = chat.querySelector("#thread"); th.appendChild(d); th.scrollTop = th.scrollHeight; return d;
  }
  async function send(text) {
    text = (text || "").trim(); if (!text) return;
    if (current !== "assistant") location.hash = "assistant";
    addMsg("user", `<div class="bubble">${esc(text)}</div>`);
    const wait = addMsg("bot", `<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>`);
    const r = await api("/api/chat", { message: text, lang: I18N.lang });
    wait.remove();
    if (r.ok === false) { addMsg("bot", `<div class="bubble">${esc(r.error)}</div>`); return; }
    const fromAI = r.reply_source && r.reply_source !== "template";
    const d = addMsg("bot", `<div class="bubble">${md(r.reply)}</div><div class="src">${fromAI ? `<span class="ai">Written by Gemini</span>${r.reply_draft ? `<span>numbers checked</span><button type="button" class="showdraft">Show checked facts</button>` : `<span>general guidance</span>`}` : `<span>SudoRoute</span>`}</div>`);
    const sd = d.querySelector(".showdraft");
    if (sd) sd.addEventListener("click", () => { const ex = d.querySelector(".draft"); if (ex) { ex.remove(); sd.textContent = "Show checked facts"; } else { d.querySelector(".src").insertAdjacentHTML("afterend", `<div class="draft">${esc(r.reply_draft)}</div>`); sd.textContent = "Hide checked facts"; } });
    if (r.plan && r.plan.length) d.querySelector(".src").insertAdjacentHTML("afterend", `<details class="planbox"><summary><span class="aitag">✦ AI plan</span> ${r.plan.reduce((n, p) => n + p.steps.length, 0)} tool step${r.plan.reduce((n, p) => n + p.steps.length, 0) === 1 ? "" : "s"} in ${r.plan.length} round${r.plan.length > 1 ? "s" : ""}</summary><ol>${r.plan.map(p => `<li><b>${p.steps.length ? p.steps.map(x => esc(x.replace(/_/g, " "))).join(" → ") : "finished"}</b>${p.thought ? `<br><span>${esc(p.thought)}</span>` : ""}</li>`).join("")}</ol><p>Gemini chose these tools from a fixed list. Each one still passed the permission gate and the policy checks; it can prepare a payment, never send one.</p></details>`);
    (r.cards || []).forEach(c => d.appendChild(Cards.render(c, { send, onChange: refresh })));
    chat.querySelector("#intent").textContent = r.intent.replace(/_/g, " ");
    chat.querySelector("#trace").innerHTML = r.trace.length ? r.trace.map(t => `<li class="${t.tier.startsWith("AI") ? "ai" : ""}"><span><span class="t">${esc(t.tool.replace(/_/g, " "))}</span><br><span class="d">${esc(t.tier)}${t.detail ? ` · ${esc(t.detail)}` : ""}</span></span>${pill(t.status, t.status)}</li>`).join("") : `<li class="empty" style="background:none">No tools were needed.</li>`;
    if (r.ai) Portal.ai(r.ai);
    const th = chat.querySelector("#thread"); th.scrollTop = th.scrollHeight;
    refresh(false);
  }

  // ------------------------------------------------------------ helpers
  const due = () => S.invoices.filter(i => i.verdict !== "BLOCK" && i.status !== "paid");
  const outstanding = () => due().reduce((a, i) => a + (i.amount - i.paid), 0);
  const inTransit = () => S.transfers.filter(t => t.status === "in_transit");
  function head(title, sub, actions = "") { return `<div class="pagehead"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div>${actions}</div>`; }
  function greeting() { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; }

  function invoiceRows(list, withActions = true) {
    if (!list.length) return `<p class="empty">No invoices.</p>`;
    return `<ul class="list">${list.map(i => `<li data-inv="${esc(i.id)}"><div class="grow"><b>${esc(i.currency)} ${fmt(i.amount, 2)} · ${esc(i.id)}</b><span>${esc(i.sender_email)} · due ${date(i.due)}${i.paid ? ` · paid ${fmt(i.paid, 2)}` : ""}</span></div>
      ${i.status === "open" ? pill(i.verdict, Cards.VERDICT[i.verdict]) : st(i.status)}
      ${withActions ? `<button class="btn sm" data-verify="${esc(i.id)}">Check</button>${i.status !== "paid" && i.verdict !== "BLOCK" ? `<button class="btn sm primary" data-pay="${esc(i.id)}">Pay</button>` : ""}` : ""}</li>`).join("")}</ul>`;
  }
  function bindInvoiceActions(root) {
    $$("[data-pay]", root).forEach(b => b.addEventListener("click", () => send(`Pay ${b.dataset.pay}`)));
    $$("[data-verify]", root).forEach(b => b.addEventListener("click", async () => {
      b.disabled = true;
      const r = await api("/api/chat", { message: `Is ${b.dataset.verify} real?` });
      b.disabled = false;
      const li = b.closest("li"); const old = li.nextElementSibling;
      if (old && old.classList.contains("inline-result")) old.remove();
      const holder = document.createElement("li"); holder.className = "inline-result"; holder.style.display = "block";
      (r.cards || []).forEach(c => holder.appendChild(Cards.render(c)));
      const risky = (r.cards || []).some(c => c.type === "risk" && c.verdict !== "SAFE");
      if (risky) {
        holder.insertAdjacentHTML("beforeend", `<button class="btn sm" data-email-inv="${esc(b.dataset.verify)}">✦ Draft an e-mail to the university</button><div class="emailout"></div>`);
        bindEmail(holder);
      }
      li.after(holder);
    }));
  }
  // AI-drafted message to the university's finance office. SudoRoute never sends it.
  function bindEmail(root) {
    $$("[data-email-inv], [data-email-tx]", root).forEach(b => b.addEventListener("click", () => Motion.busy(b, async () => {
      const r = await api("/api/email-draft", b.dataset.emailInv ? { invoice_id: b.dataset.emailInv, lang: I18N.lang } : { transfer_id: b.dataset.emailTx, lang: I18N.lang });
      const out = b.nextElementSibling;
      if (r.ok === false) { out.innerHTML = `<div class="alert info">${esc(r.error)}</div>`; return; }
      out.innerHTML = `<div class="card emailcard"><div class="emhead"><span>To: ${esc(r.to)}</span><span class="aisrcl">${r.source !== "template" ? "✦ Written by Gemini · facts checked" : "SudoRoute template"}</span></div>
        <label>Subject<input class="input" value="${esc(r.subject)}" readonly></label><label>Message<textarea class="input" rows="9" readonly>${esc(r.body)}</textarea></label>
        <div class="emact"><button type="button" class="btn sm primary" data-copy>Copy message</button><small>${esc(r.note)}</small></div></div>`;
      out.querySelector("[data-copy]").addEventListener("click", async e => {
        try { await navigator.clipboard.writeText(`Subject: ${r.subject}\n\n${r.body}`); e.target.textContent = "Copied"; } catch (err) { out.querySelector("textarea").select(); }
      });
    })));
  }
  function transferTable(list, actions = false) {
    if (!list.length) return `<p class="empty">No payments yet. Ask the assistant to pay your tuition.</p>`;
    const recv = t => t.status === "returned" ? `<span style="color:var(--seal)">Returned</span>` : `${esc(t.dst_currency)} ${fmt(t.received_amount ?? t.dst_amount, 2)}${t.status === "credited_short" ? `<br><span style="color:var(--seal);font-size:12.5px">short by ${fmt(t.dst_amount - t.received_amount, 2)}</span>` : ""}`;
    const act = t => !actions ? "" : t.status === "returned" || t.status === "credited_short"
      ? `<button class="btn sm primary" data-recover="${esc(t.id)}">Fix this</button>`
      : t.status === "in_transit" ? `<details class="whatfail"><summary>Sandbox: make it fail</summary><div><button class="btn sm" data-inject="returned" data-t="${esc(t.id)}">Bank returns it</button><button class="btn sm" data-inject="short" data-t="${esc(t.id)}">Bank deducts a fee</button></div></details>` : "";
    return `<div class="tablewrap"><table><thead><tr><th>Payment</th><th>Channel</th><th class="n">Sent</th><th class="n">Received</th><th>Arrives</th><th></th>${actions ? "<th></th>" : ""}</tr></thead><tbody>
      ${list.slice().reverse().map(t => `<tr data-tid="${esc(t.id)}"><td>${esc(t.id)}${t.leg > 1 ? `<br><span style="color:var(--ink-3);font-size:12.5px">installment ${t.leg}</span>` : ""}</td><td>${esc(t.provider_name)}</td><td class="n">${esc(t.src_currency)} ${fmt(t.src_amount)}</td><td class="n">${recv(t)}</td><td>${date(t.eta)}</td><td>${st(t.status)}</td>${actions ? `<td>${act(t)}</td>` : ""}</tr>`).join("")}</tbody></table></div><div id="recovery"></div>`;
  }
  function bindRecovery(root) {
    $$("[data-inject]", root).forEach(b => b.addEventListener("click", () => Motion.busy(b, async () => {
      const r = await api("/api/sandbox/transfer-issue", { transfer_id: b.dataset.t, kind: b.dataset.inject });
      if (r.ok === false) { toast(r.error); return; }
      toast(b.dataset.inject === "returned" ? "The receiving bank returned the transfer. The money is back in the wallet." : "An intermediary bank will deduct a fee. Move the sandbox clock forward to see it arrive short.");
      await refresh();
    })));
    $$("[data-recover]", root).forEach(b => b.addEventListener("click", () => Motion.busy(b, async () => {
      const r = await api("/api/transfer/recover", { transfer_id: b.dataset.recover });
      const box = $("#recovery", root); if (!box) return;
      if (r.ok === false) { box.innerHTML = `<div class="alert info">${esc(r.error)}</div>`; return; }
      box.innerHTML = `<div class="card recovercard"><h4>What happened to ${esc(r.transfer_id)} ${pill(r.kind === "returned" ? "bad" : "warn", r.kind === "returned" ? "Returned" : "Arrived short")}</h4>
        <p>${esc(r.diagnosis)}</p><ol class="rsteps">${r.steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
        <div class="emact">${r.action ? `<button class="btn primary" data-recover-pay="${esc(r.action.message)}">${esc(r.action.label)}</button>` : ""}${r.kind === "returned" || r.kind === "short" ? `<button class="btn" data-email-tx="${esc(r.transfer_id)}">✦ Draft an e-mail to the university</button><div class="emailout" style="flex-basis:100%"></div>` : ""}</div>
        <p class="note">No money moves from this screen. A new payment needs a new signed proposal and fresh one-time codes.</p></div>`;
      const pay = $("[data-recover-pay]", box); if (pay) pay.addEventListener("click", () => send(pay.dataset.recoverPay));
      bindEmail(box);
      box.scrollIntoView({ block: "nearest", behavior: "smooth" });
    })));
  }

  // ------------------------------------------------------------ live payment journey (driven only by real state)
  const jprev = new Map();
  function journeyHTML() {
    const p = S.pending.length ? S.pending[S.pending.length - 1] : null;
    const t = S.transfers.length ? S.transfers.slice().sort((a, b) => a.created.localeCompare(b.created)).pop() : null;
    if (!p && !t) return "";
    const withG = p ? !!p.proposal.guardian_required : S.guardians.length > 0 && S.guardian_approval;
    const names = ["Invoice checked", "Route chosen", "Currency risk priced"].concat(withG ? ["Guardian approved"] : [], ["You confirmed", "Arrived at university"]);
    let done, key, title, status;
    if (p) {
      done = 3 + (withG && p.guardian_approval ? 1 : 0); key = p.proposal.proposal_id; status = p.status;
      title = `${esc(p.proposal.dst_currency)} ${fmt(p.proposal.total_dst, 2)} to ${esc(p.proposal.university_name)}`;
    } else {
      done = names.length - (["credited", "credited_short"].includes(t.status) ? 0 : 1); key = t.id; status = t.status;
      title = `${esc(t.dst_currency)} ${fmt(t.dst_amount, 2)} via ${esc(t.provider_name)}`;
    }
    const prog = Math.max(0, Math.min(1, (done - 1) / (names.length - 1)));
    const prev = jprev.has(key) ? jprev.get(key) : prog;
    jprev.set(key, prog);
    return `<div class="journey has-head" role="group" style="--n:${names.length};--p:${prev}" data-p="${prog}" aria-label="Payment progress: ${done} of ${names.length} steps done">
      <div class="jhead"><b>Latest payment · ${title}</b>${st(status)}</div><div class="jrow">
      ${names.map((n, i) => `<div class="jst ${i < done ? "done" : i === done ? "now" : ""}"><i></i><b>${esc(n)}</b>${i === done ? `<span>${i === names.length - 1 ? (status === "returned" ? "Returned by the bank" : "In transit") : "Waiting"}</span>` : ""}</div>`).join("")}</div></div>`;
  }
  function animateJourney() {
    const j = $(".journey", view); if (!j) return;
    requestAnimationFrame(() => requestAnimationFrame(() => j.style.setProperty("--p", j.dataset.p)));
  }
  const kprev = {};
  function tweenKPIs() {
    $$("[data-k]", view).forEach(el => {
      const k = el.dataset.k, to = +el.dataset.v, d = +(el.dataset.d || 0), pre = el.dataset.pre || "";
      Motion.tween(el, kprev[k], to, v => pre + fmt(v, d));
      kprev[k] = to;
    });
  }
  let seenT = null;
  function markFresh() {
    const ids = $$("[data-tid]", view).map(e => e.dataset.tid);
    if (seenT) $$("[data-tid]", view).forEach(e => { if (!seenT.has(e.dataset.tid)) e.classList.add("fresh"); });
    seenT = new Set([...(seenT || []), ...ids]);
  }

  // ------------------------------------------------------------ views
  const V = {};
  const PHOTO = id => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=1600&q=70`;
  const photoImg = id => `<img src="${PHOTO(id)}" alt="" loading="lazy" decoding="async">`;
  V.overview = () => {
    const d = due().sort((a, b) => a.due.localeCompare(b.due));
    const g = S.guardians;
    const attention = [];
    S.pending.forEach(p => attention.push(`<li><div class="grow"><b>${esc(p.proposal.dst_currency)} ${fmt(p.proposal.total_dst, 2)} to ${esc(p.proposal.university_name)}</b><span>${p.status === "awaiting_guardian" ? "Waiting for your guardian's approval" : "Approved — confirm it with your one-time code"}</span></div>${st(p.status)}<a class="btn sm" href="#payments">Open</a></li>`));
    S.invoices.filter(i => i.verdict === "BLOCK" && i.status === "open").forEach(i => attention.push(`<li><div class="grow"><b>Suspicious invoice ${esc(i.id)}</b><span>From ${esc(i.sender_email)}. Don't pay it — see why.</span></div>${pill("BLOCK", "Scam")}<button class="btn sm" data-verify="${esc(i.id)}">See why</button></li>`));
    S.notifications.slice(-2).reverse().forEach(n => attention.push(`<li><div class="grow"><b>Update</b><span>${esc(n)}</span></div></li>`));
    const next = d[0];
    view.innerHTML = `
      <section class="pbanner">${photoImg("1562774053-701939374585")}<div class="pbanner-shade" aria-hidden="true"></div>
        <div class="pb-copy">
          <span class="badge">${S.university.verified ? "✓ Verified university" : "University waiting for verification"} · ${g.length ? `Guardian: ${esc(TS.first(g[0].name))}` : S.guardian_invite ? `Guardian invited` : "No guardian yet"}</span>
          <h2>${greeting()}, ${esc(TS.first(S.name))}</h2>
          <p>${esc(S.program)} · ${esc(S.university.name)}, ${esc(S.university.city)}</p>
          <div class="pb-actions"><button class="btn accent" id="paybtn" ${d.length && !S.frozen ? "" : "disabled"}>Pay tuition</button><button class="btn ghost" id="tourbtn">${esc(I18N.t("p.tour", "Guided tour"))}</button></div>
        </div>
        <div class="pb-next">
          <small>${next ? "Next tuition payment" : inTransit().length ? "Payment on its way" : "Tuition"}</small>
          <b class="num" data-k="due" data-d="2" data-pre="${esc(S.study_currency)} " data-v="${outstanding()}">${esc(S.study_currency)} ${fmt(outstanding(), 2)}</b>
          <span>${!S.university.verified ? "Invoice arrives after verification" : next ? `Due ${date(next.due)}` : inTransit().length ? "Arriving soon" : "Nothing due"}</span>
          <div class="wallets"><div><small>${esc(S.home_currency)} wallet</small><b class="num" data-k="home" data-v="${S.balances[S.home_currency] || 0}">${fmt(S.balances[S.home_currency] || 0)}</b></div>
            <div><small>${esc(S.study_currency)} wallet</small><b class="num" data-k="study" data-d="2" data-v="${S.balances[S.study_currency] || 0}">${fmt(S.balances[S.study_currency] || 0, 2)}</b></div></div>
        </div>
      </section>
      <div class="kpi4" id="kpis">${[1, 2, 3, 4].map(() => `<div><small>&nbsp;</small><b>…</b><div class="meterbar"></div><span>&nbsp;</span></div>`).join("")}</div>
      <section class="aibrief" id="aibrief"><span class="aibicon" aria-hidden="true">✦</span><div><b>Your money brief</b><p class="aibtext"><span class="typing"><i></i><i></i><i></i></span></p><small class="aibsrc"></small></div><button type="button" class="btn sm" id="aibask">Ask SudoRoute AI</button></section>
      ${journeyHTML()}
      ${S.university.verified ? "" : `<section class="panel" id="unipending" style="border-color:var(--amber)"><h3>${esc(S.university.name)} is waiting for verification ${pill("warn", "Pending")}</h3>
        <p style="color:var(--ink-2);margin:0 0 12px;max-width:72ch">You typed a university that isn't in SudoRoute's verified registry yet. Before the first payment we confirm its official bank account directly with the university — so no one can slip in a fake account. Until then the assistant can check invoice e-mails for scams, but it won't prepare a payment.</p>
        <ol class="steplist" style="margin-bottom:14px"><li>We find the finance office's phone number on the university's own website${S.university.website ? ` (${esc(S.university.website)})` : ""} — never from an e-mail.</li><li>We call back and receive a signed letter with the official bank account.</li><li>The account is added to the registry. Your tuition invoice appears and you can pay.</li></ol>
        <button class="btn" id="simverify">Simulate verification (sandbox only)</button></section>`}
      <div class="cols even">
        <section class="panel"><h3>Needs your attention</h3>${attention.length ? `<ul class="list">${attention.join("")}</ul>` : `<p class="empty">Nothing right now.</p>`}</section>
        <section class="panel"><h3>This semester's bills <small id="billsum"></small></h3><div id="bills"><p class="empty">Loading…</p></div></section>
      </div>
      <div class="cols even">
        <section class="panel"><h3>Invoices <a class="btn sm quiet" href="#invoices">Check an e-mail</a></h3>${invoiceRows(S.invoices)}</section>
        <div>
          <section class="panel"><h3>Recent payments <a class="btn sm quiet" href="#payments">All payments</a></h3>${S.transfers.length ? `<ul class="list">${S.transfers.slice(-4).reverse().map(t => `<li data-tid="${esc(t.id)}"><div class="grow"><b>${esc(t.dst_currency)} ${fmt(t.dst_amount, 2)} for ${esc(t.src_currency)} ${fmt(t.src_amount)}</b><span>${esc(t.provider_name)} · arrives ${date(t.eta)}</span></div>${st(t.status)}</li>`).join("")}</ul>` : `<p class="empty">No payments yet. Ask the assistant to pay your tuition.</p>`}</section>
          <section class="panel"><h3>Ask the assistant</h3><div class="chips" style="padding:0">${["Pay my tuition", "When should I pay?", "Compare transfer options", "Show my budget"].map(c => `<button class="chip" data-ask="${esc(c)}">${esc(c)}</button>`).join("")}</div></section>
        </div>
      </div>`;
    tweenKPIs(); animateJourney(); markFresh(); Portal.photos(view);
    $("#paybtn").addEventListener("click", () => send("Pay my tuition"));
    $("#tourbtn").addEventListener("click", () => { tourAuto = false; tourShow(0); });
    const sv = $("#simverify");
    if (sv) sv.addEventListener("click", async () => { const r = await Motion.busy(sv, () => api("/api/university/simulate-verification", {})); toast(r.ok ? `${r.university.name} verified in the sandbox. Your tuition invoice is ready.` : r.error); refresh(); });
    $$("[data-ask]", view).forEach(b => b.addEventListener("click", () => send(b.dataset.ask)));
    bindInvoiceActions(view);
    loadDashboard();
    loadBrief();
  };
  async function loadBrief() {
    const box = $("#aibrief"); if (!box) return;
    $("#aibask").addEventListener("click", () => window.SRAI && SRAI.open(true));
    const r = await api("/api/brief", { lang: I18N.lang });
    if (current !== "overview" || !$("#aibrief")) return;
    $("#aibrief .aibtext").innerHTML = TS.md(r.text || "");
    $("#aibrief .aibsrc").textContent = r.source && r.source !== "template" ? "✦ Written by Gemini from your live numbers · every figure checked" : "Computed by SudoRoute from your live numbers" ;
  }

  function billsTable(plan) {
    if (!plan.bills.length) return `<p class="empty">No bills this semester.</p>`;
    const lbl = { covered: "Covered", partly: "Part funded", short: "Not funded" };
    return `<div class="tablewrap"><table class="bills"><thead><tr><th>Bill</th><th class="n">${esc(plan.currency)}</th><th>Due</th><th>Funding</th></tr></thead><tbody>
      ${plan.bills.map(b => `<tr><td>${esc(b.label)}<br><span class="kind">${b.kind === "tuition" ? "Paid through SudoRoute" : "Planning only"}</span></td><td class="n">${fmt(b.amount, 2)}</td><td>${date(b.due)}<br><span class="kind">${b.days_left} days</span></td>
      <td><span class="pill ${b.status}">${b.status === "partly" ? `${b.funded_pct}% funded` : lbl[b.status]}</span></td></tr>`).join("")}</tbody></table></div>
      <p style="color:var(--ink-3);font-size:12.5px;margin:10px 0 0">${esc(plan.note)}</p>`;
  }
  async function loadDashboard() {
    const r = await api("/api/dashboard");
    if (current !== "overview" || !$("#kpis")) return;
    const k = r.kpis, cur = k.currency || S.study_currency;
    const bar = (pct, cls = "") => `<div class="meterbar"><i class="${cls}" style="width:${Math.max(2, Math.min(100, pct))}%"></i></div>`;
    const cards = [];
    cards.push(k.days_to_due != null
      ? `<div><small>Tuition due in</small><b class="num">${k.days_to_due} days</b>${bar(Math.min(100, k.days_to_due / 30 * 100))}<span>${esc(cur)} ${fmt(k.due_amount, 2)} · ${date(k.due_date)}${k.pay_by ? `<br><span class="payby ${k.pay_by_days <= 3 ? "tight" : ""}">Pay by ${date(k.pay_by)}</span>` : ""}</span></div>`
      : `<div><small>Tuition due</small><b class="num">—</b>${bar(0)}<span>${S.university.verified ? "Nothing to pay right now" : "After your university is verified"}</span></div>`);
    cards.push(k.on_time_pct != null
      ? `<div><small>Arrives on time if paid today</small><b class="num">${k.on_time_pct}%</b>${bar(k.on_time_pct)}<span>via ${esc(k.best_route)}</span></div>`
      : `<div><small>Arrives on time if paid today</small><b class="num">—</b>${bar(0)}<span>Shown once a tuition invoice is open</span></div>`);
    cards.push(k.shortfall_if_wait_pct != null
      ? `<div><small>Budget risk if you wait</small><b class="num">${k.shortfall_if_wait_pct}%</b>${bar(k.shortfall_if_wait_pct, k.shortfall_if_wait_pct > 20 ? "bad" : k.shortfall_if_wait_pct > 5 ? "warn" : "")}<span>Chance tuition outgrows your budget by the due date</span></div>`
      : `<div><small>Budget risk if you wait</small><b class="num">—</b>${bar(0)}<span>Shown once a tuition invoice is open</span></div>`);
    cards.push(`<div><small>Semester funded</small><b class="num">${k.semester_funded_pct}%</b>${bar(k.semester_funded_pct, k.semester_funded_pct < 100 ? "warn" : "")}<span>${r.plan.bills.length} bills · ${esc(r.plan.currency)} ${fmt(r.plan.total_needed)}</span></div>`);
    $("#kpis").innerHTML = cards.join("");
    $("#bills").innerHTML = billsTable(r.plan);
  }

  V.assistant = () => {
    view.innerHTML = "";
    view.appendChild(chat);
    const th = chat.querySelector("#thread");
    if (!th.children.length) {
      addMsg("bot", `<div class="bubble"><p>Hi ${esc(TS.first(S.name))}. I can pay your tuition, check an invoice for scams, compare ways to send money, show exchange-rate risk, and review your budget or credit.</p><p>I'll prepare payments, but nothing moves until you confirm with your one-time code${S.guardians.length ? ` and ${esc(TS.first(S.guardians[0].name))} approves` : ""}.</p></div>`);
    }
    setTimeout(() => chat.querySelector("#msg").focus(), 50);
  };

  V.payments = () => {
    view.innerHTML = head("Payments", "Payments waiting for approval, money on its way, and installment plans.") +
      journeyHTML() + `<section id="pending"></section>
       <section class="panel" id="history"><h3>Payment history</h3>${transferTable(S.transfers, true)}</section>
       <section class="panel"><h3>Plans the agent runs for you</h3>${S.mandates.length ? `<ul class="list">${S.mandates.map(m => m.kind === "smart_timing"
         ? `<li><div class="grow"><b>${esc(m.invoice_id)} · smart timing ${m.executed_legs.length ? "— paid" : "— watching the rate"}</b><span>Pays when ${esc(m.src_currency)}/${esc(m.dst_currency)} reaches ${m.target_rate.toFixed(6)}, at the latest on ${date(m.deadline)} · never below ${m.floor_rate.toFixed(6)} · to ${esc(m.payee_account)}${m.last_check ? ` · last check ${date(m.last_check.date)}: ${m.last_check.rate.toFixed(6)} (${esc(m.last_check.decision.replace(/_/g, " "))})` : ""}</span></div>${st(m.status)}${m.status === "active" ? `<button class="btn sm danger" data-cancel="${esc(m.mandate_id)}">Cancel plan</button>` : ""}</li>`
         : `<li><div class="grow"><b>${esc(m.invoice_id)} · ${m.executed_legs.length} of ${m.total_legs} installments sent</b><span>To ${esc(m.payee_account)} · pauses if the rate moves more than ${(m.max_slippage * 100).toFixed(0)}% · ends ${date(m.expires)}</span></div>${st(m.status)}${m.status === "active" ? `<button class="btn sm danger" data-cancel="${esc(m.mandate_id)}">Cancel plan</button>` : ""}</li>`).join("")}</ul>` : `<p class="empty">No installment or smart-timing plans. Ask the assistant to "pay at the best rate before my deadline".</p>`}</section>`;
    animateJourney(); markFresh(); bindRecovery($("#history"));
    const pend = $("#pending");
    if (S.pending.length) {
      pend.innerHTML = `<h3 style="font:600 16px var(--sans);margin:0 0 4px">Waiting for approval</h3>`;
      S.pending.forEach(p => pend.appendChild(Cards.render({ ...p, type: "proposal" }, { onChange: refresh, compact: true })));
      pend.lastElementChild.style.marginBottom = "18px";
    }
    $$("[data-cancel]", view).forEach(b => b.addEventListener("click", async () => { await api("/api/mandate/cancel", { mandate_id: b.dataset.cancel }); toast("Installment plan cancelled."); refresh(); }));
  };

  V.invoices = () => {
    view.innerHTML = head("Invoices", "Every invoice is compared with the university's verified record before you pay.") +
      `<div class="cols"><section class="panel"><h3>Your invoices</h3>${invoiceRows(S.invoices)}</section>
       <section class="panel"><h3>Check a suspicious e-mail</h3><p style="color:var(--ink-2);margin:0 0 12px;font-size:14px">Paste the whole message. It's treated as evidence only — any instructions inside it are ignored.</p>
        <form id="paste"><textarea class="input" id="pastetext" rows="7" placeholder="From: …&#10;Subject: …&#10;&#10;Paste the e-mail here"></textarea><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px"><button class="btn primary" type="submit">Check e-mail</button><label class="btn quiet filepick">Or open a saved e-mail (.eml / .txt)<input type="file" id="emlfile" accept=".eml,.txt,message/rfc822,text/plain" hidden></label></div></form><div id="pasteout"></div></section></div>`;
    bindInvoiceActions(view);
    $("#emlfile").addEventListener("change", async e => {
      const f = e.target.files[0]; if (!f) return;
      if (f.size > 200000) { toast("That file is too large. Paste the e-mail text instead."); return; }
      const raw = await f.text();
      // Keep headers that matter and the readable body; drop attachments and encoded parts.
      const text = raw.split(/\r?\n--[^\n]*\r?\nContent-Type:\s*(?!text\/plain)/i)[0].slice(0, 6000);
      $("#pastetext").value = text; $("#paste").requestSubmit();
    });
    $("#paste").addEventListener("submit", async e => {
      e.preventDefault(); const t = $("#pastetext").value.trim();
      if (t.length < 40) { $("#pasteout").innerHTML = `<div class="alert info" style="margin-top:12px">Paste the full e-mail, including the sender address and the payment request.</div>`; return; }
      const r = await api("/api/chat", { message: t });
      $("#pasteout").innerHTML = ""; (r.cards || []).forEach(c => $("#pasteout").appendChild(Cards.render(c)));
    });
  };

  V.insights = async () => {
    view.innerHTML = head("Insights", "Your budget, exchange-rate risk for the next payment, transfer costs and credit readiness.") + `<p class="empty">Loading…</p>`;
    const r = await api("/api/insights");
    if (current !== "insights") return;
    view.innerHTML = head("Insights", "Your budget, exchange-rate risk for the next payment, transfer costs and credit readiness.");
    if (r.denied) { view.insertAdjacentHTML("beforeend", `<div class="alert info">The assistant is in read-only mode, so it can't analyse your finances. Change this under Security.</div>`); return; }
    const dash = await api("/api/dashboard");
    if (current !== "insights") return;
    const wi = dash.whatif;
    if (wi) {
      const box = Cards.el(`<section class="panel whatif"><h3>What if the exchange rate moves? <small>${esc(wi.home)} → ${esc(wi.study)}</small></h3>
        <p style="color:var(--ink-2);margin:0 0 14px;font-size:14px">Drag to see what your tuition of ${esc(wi.study)} ${fmt(wi.outstanding, 2)} would cost if ${esc(wi.home)} weakens or strengthens before you pay. Uses the same rate, channel markup and fee as your best route.</p>
        <label for="wislider" style="font-weight:700;font-size:14px">${esc(wi.home)} change: <span id="wipct">0%</span></label>
        <input type="range" id="wislider" min="-30" max="10" step="1" value="0" aria-describedby="wiverdict">
        <div class="wres"><div><small>Tuition would cost</small><b class="num" id="wicost"></b></div><div><small>Against your budget</small><b class="num" id="wibud"></b></div><div><small>Against your ${esc(wi.home)} wallet</small><b class="num" id="wibal"></b></div></div>
        <p class="verdictline" id="wiverdict" aria-live="polite"></p></section>`);
      view.appendChild(box);
      const calc = () => {
        const shock = +$("#wislider").value, rate = wi.mid * (1 + shock / 100);
        const cost = wi.outstanding / (rate * (1 - wi.markup)) + wi.fee_home;
        const base = wi.outstanding / (wi.mid * (1 - wi.markup)) + wi.fee_home;
        const sign = v => (v >= 0 ? "+" : "−") + fmt(Math.abs(v));
        $("#wipct").textContent = `${shock > 0 ? "+" : ""}${shock}%${shock < 0 ? " (weaker)" : shock > 0 ? " (stronger)" : ""}`;
        $("#wicost").textContent = `${wi.home} ${fmt(cost)}`;
        $("#wibud").textContent = sign(wi.budget_home - cost);
        $("#wibal").textContent = sign(wi.balance_home - cost);
        $("#wibud").style.color = wi.budget_home - cost < 0 ? "var(--seal)" : "var(--ok)";
        $("#wibal").style.color = wi.balance_home - cost < 0 ? "var(--seal)" : "var(--ok)";
        $("#wiverdict").textContent = cost <= wi.budget_home ? `Still within budget — ${wi.home} ${fmt(cost - base)} ${cost >= base ? "more" : "less"} than paying at today's rate.`
          : cost <= wi.balance_home ? "Over budget, but your wallet still covers it. Paying now or in instalments limits this risk."
          : "Your wallet would no longer cover the full amount. Pay now, or ask your guardian to top up before the rate moves.";
      };
      $("#wislider").addEventListener("input", calc); calc();
    }
    const grid = Cards.el(`<div class="cols even"><div id="c1"></div><div id="c2"></div></div>`);
    view.appendChild(grid);
    if (r.fx) $("#c1").appendChild(Cards.render({ type: "fx", ...r.fx }));
    if (r.budget) $("#c1").appendChild(Cards.render({ type: "budget", ...r.budget }));
    if (r.routes) $("#c2").appendChild(Cards.render({ type: "routes", ...r.routes }));
    if (r.credit) $("#c2").appendChild(Cards.render({ type: "credit", ...r.credit }));
    $$(".card", view).forEach(c => { c.style.marginTop = "0"; c.style.marginBottom = "18px"; });
  };

  V.security = async () => {
    view.innerHTML = head("Security", "Control what the assistant may do, who approves your payments, and see everything that happened.") +
      `<div class="cols even"><div>
        <section class="panel"><h3>What the assistant may do</h3><div class="levels">${Object.entries(S.levels).map(([k, v]) => `<button class="level" type="button" data-level="${k}" aria-pressed="${k === S.level}"><b>${esc(v.label)}</b><span>${esc(v.description)}</span></button>`).join("")}</div>
          <p style="color:var(--ink-3);font-size:13px;margin:12px 0 0">Giving the assistant more power asks for your password. Some actions — like paying an unverified account or skipping your code — are blocked in every mode.</p></section>
        <section class="panel"><h3>Guardian approval</h3>
          <label class="switch"><span><b style="display:block">Require my guardian to approve payments</b><span style="color:var(--ink-3);font-size:13.5px">${S.guardians.length ? "Recommended when family money pays your fees." : "Link a guardian below to use this."}</span></span><input type="checkbox" id="gappr" ${S.guardian_approval ? "checked" : ""} ${S.guardians.length ? "" : "disabled"}></label>
          <hr style="border:0;border-top:1px solid var(--line);margin:16px 0">
          ${!S.guardians.length && S.guardian_invite ? `<div class="alert info" style="margin-bottom:12px">Invited <b>${esc(S.guardian_invite.name)}</b> (${esc(S.guardian_invite.email)}). They're linked to you as soon as they create a guardian account with this e-mail.</div>` : ""}
          <form id="ginvite" class="ginvite" novalidate><div class="field"><label for="gi-name">Guardian's name</label><input class="input" id="gi-name" value="${esc(S.guardian_invite ? S.guardian_invite.name : "")}"></div>
            <div class="field"><label for="gi-email">Guardian's e-mail</label><input class="input" id="gi-email" type="email" value="${esc(S.guardian_invite ? S.guardian_invite.email : "")}"></div>
            <button class="btn" type="submit">${S.guardian_invite ? "Update invitation" : "Invite guardian"}</button></form>
          ${S.guardians.length ? `<ul class="list">${S.guardians.map(g => `<li><div class="avatar">${esc(Portal.initials(g.name))}</div><div class="grow"><b>${esc(g.name)}</b><span>${esc(g.relationship)}</span></div><button class="btn sm danger" data-unlink="${esc(g.id)}">Remove</button></li>`).join("")}</ul>` : `<p class="empty">No guardian linked yet.</p>`}
          <div style="margin-top:12px"><button class="btn" id="invite">Create a guardian link code</button><div id="codeout" style="margin-top:12px"></div></div></section>
        <section class="panel" id="totpbox"><h3>Authenticator app <small>${S.totp_enabled ? "linked" : "recommended"}</small></h3>
          ${S.totp_enabled ? `<div class="alert ok" style="margin:0 0 12px">Payments are approved with the code from your authenticator app. No payment codes are sent by text message.</div><button class="btn sm danger" id="totpoff">Remove authenticator app</button>`
            : `<p style="color:var(--ink-2);margin:0 0 12px;font-size:14px">Use Google Authenticator, Microsoft Authenticator, 1Password or any TOTP app instead of text messages. Codes then exist only on your phone — not in SMS, and never visible to the AI.</p><button class="btn" id="totpon">Link an authenticator app</button>`}
          <div id="totpout"></div></section>
        <section class="panel"><h3>Password</h3><div id="pwc"></div></section>
      </div><div>
        <section class="panel"><h3>Your sandbox phone <small>${esc(S.phone || S.phone_masked)}</small></h3>${S.sms_inbox.length ? S.sms_inbox.slice().reverse().map(m => `<div class="sms">${esc(m.text).replace(/code (\d{6})/, "code <b>$1</b>")}<small>${esc(m.proposal_id)}</small></div>`).join("") : `<p class="empty">One-time codes for your payments arrive here.</p>`}</section>
        <section class="panel"><h3>Activity log</h3><div id="auditbox"><p class="empty">Loading…</p></div></section>
      </div></div>`;
    $("#pwc").appendChild(Portal.changePasswordForm());
    if ($("#totpon")) $("#totpon").addEventListener("click", async () => {
      const pw = await Portal.askPassword("Link an authenticator app?", "Enter your password to continue.");
      if (pw === null) return;
      const r = await api("/api/totp/setup", { password: pw });
      if (!r.ok) { toast(r.error); return; }
      let qr = "";
      try { const q = qrcode(0, "M"); q.addData(r.uri); q.make(); qr = q.createSvgTag(4, 8); } catch (e) { qr = ""; }
      $("#totpout").innerHTML = `<div class="totpsetup"><div class="qr">${qr}</div><div><ol class="steplist" style="margin:0 0 10px"><li>Scan this code with your authenticator app.</li><li>Or enter this key by hand: <code class="key">${esc(r.secret.replace(/(.{4})/g, "$1 ").trim())}</code></li><li>Type the 6-digit code the app shows.</li></ol>
        <form id="totpform" class="otp"><input inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" aria-label="Code from the app"><button class="btn primary" type="submit">Link app</button></form></div></div>`;
      $("#totpform").addEventListener("submit", async e => {
        e.preventDefault();
        const x = await Motion.busy($("#totpform button"), () => api("/api/totp/enable", { code: $("#totpform input").value }));
        toast(x.ok ? "Authenticator app linked. Payments now need its code." : x.error);
        if (x.ok) refresh();
      });
    });
    if ($("#totpoff")) $("#totpoff").addEventListener("click", async () => {
      const pw = await Portal.askPassword("Remove the authenticator app?", "Payment codes will be sent by text message again.");
      if (pw === null) return;
      const code = prompt("Enter the current code from your authenticator app");
      if (code === null) return;
      const r = await api("/api/totp/disable", { password: pw, code });
      toast(r.ok ? "Authenticator app removed." : r.error); if (r.ok) refresh();
    });
    $$("[data-level]", view).forEach(b => b.addEventListener("click", async () => {
      let r = await api("/api/settings", { level: b.dataset.level });
      if (r.code === "reauth_required") {
        const pw = await Portal.askPassword("Give the assistant more power?", `Enter your password to switch to "${S.levels[b.dataset.level].label}".`);
        if (pw === null) return;
        r = await api("/api/settings", { level: b.dataset.level, password: pw });
      }
      toast(r.ok ? `Assistant set to ${S.levels[r.level].label}.` : r.error); refresh();
    }));
    $("#gappr").addEventListener("change", async e => {
      const on = e.target.checked;
      let r = await api("/api/settings", { guardian_approval: on });
      if (r.code === "reauth_required") {
        const pw = await Portal.askPassword("Stop asking your guardian?", "Payments would no longer need your guardian's approval. Enter your password to confirm.");
        r = pw === null ? { ok: false, error: "Nothing changed." } : await api("/api/settings", { guardian_approval: on, password: pw });
      }
      toast(r.ok ? (r.guardian_approval ? "Guardian approval is on." : "Guardian approval is off.") : r.error); refresh();
    });
    $("#ginvite").addEventListener("submit", async e => {
      e.preventDefault();
      const r = await Motion.busy($("#ginvite button"), () => api("/api/guardian/invite-email", { name: $("#gi-name").value, email: $("#gi-email").value }));
      toast(r.ok ? (r.invite.status === "accepted" ? "Guardian linked." : "Invitation saved. They're linked when they sign up with that e-mail.") : r.error);
      if (r.ok) refresh();
    });
    $("#invite").addEventListener("click", async () => {
      const r = await Motion.busy($("#invite"), () => api("/api/guardian/invite", {}));
      $("#codeout").innerHTML = r.ok ? `<div class="code">${esc(r.code)}</div><p style="color:var(--ink-2);font-size:13.5px;margin:6px 0 0">Share this with your guardian. It works once and expires in 24 hours.</p>` : `<div class="alert bad">${esc(r.error)}</div>`;
    });
    $$("[data-unlink]", view).forEach(b => b.addEventListener("click", async () => {
      const pw = await Portal.askPassword("Remove this guardian?", "They will no longer see your payments or approve them.");
      if (pw === null) return;
      const r = await api("/api/guardian/unlink", { guardian_id: b.dataset.unlink, password: pw });
      toast(r.ok ? "Guardian removed." : r.error); refresh();
    }));
    const a = await api("/api/audit?n=30");
    if (current !== "security") return;
    $("#auditbox").innerHTML = `<div class="chain"><i class="${a.verify.valid ? "" : "bad"}"></i>${a.verify.valid ? `Every record is intact (${a.verify.entries} linked entries).` : `Tampering detected at record ${a.verify.broken_at}.`}</div>` + Portal.auditList(a.entries);
  };

  V.profile = async () => {
    const u = S.user;
    const lvl = S.levels[S.level] ? S.levels[S.level].label : S.level;
    view.innerHTML = `<div class="profcover">${photoImg("1627556704290-2b1f5853ff78")}</div>
      <section class="profhead"><div id="pe"></div>
        <div class="who"><h2>${esc(S.name)}</h2><span style="color:var(--ink-3)">${esc(u.email)}</span>
          <div class="tags">${pill("ok", "Student")}${pill(S.university.verified ? "ok" : "warn", S.university.verified ? "Verified university" : "University pending")}${S.guardians.length ? pill("ok", "Guardian linked") : pill("neutral", S.guardian_invite ? "Guardian invited" : "No guardian")}${S.frozen ? pill("bad", "Frozen") : ""}</div></div>
        <div class="acts">${u.photo ? `<button class="btn sm" id="rmphoto">Remove photo</button>` : ""}<a class="btn sm" href="#security">Security settings</a></div></section>
      <div class="profgrid">
        <section class="panel"><h3>Personal details</h3><dl class="kv"><dt>Full name</dt><dd>${esc(S.name)}</dd><dt>E-mail</dt><dd>${esc(u.email)}</dd>
          <dt>Phone</dt><dd>${esc(S.phone || S.phone_masked || "—")}</dd><dt>Home country</dt><dd>${esc(S.home_country)} · ${esc(S.home_currency)}</dd>
          <dt>Member since</dt><dd>${new Date(u.created * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}</dd><dt>Account no.</dt><dd>${esc(S.id)}</dd></dl></section>
        <section class="panel"><h3>Study</h3><dl class="kv"><dt>University</dt><dd>${esc(S.university.name)}</dd><dt>City</dt><dd>${esc(S.university.city)}</dd>
          <dt>Programme</dt><dd>${esc(S.program)}</dd><dt>Student ID</dt><dd>${esc(S.student_ref)}</dd><dt>Study currency</dt><dd>${esc(S.study_currency)}</dd>
          <dt>Payee account</dt><dd>${S.university.verified ? "Verified in the registry" : "Waiting for verification"}</dd></dl></section>
        <section class="panel"><h3>Family</h3>${S.guardians.length ? `<ul class="list">${S.guardians.map(gg => `<li><span class="avatar">${esc(Portal.initials(gg.name))}</span><div class="grow"><b>${esc(gg.name)}</b><span>${esc(gg.relationship)} · approves payments</span></div></li>`).join("")}</ul>`
          : S.guardian_invite ? `<p style="margin:0;color:var(--ink-2)">Invited <b>${esc(S.guardian_invite.name)}</b> (${esc(S.guardian_invite.email)}). They're linked when they sign up with that e-mail.</p>` : `<p class="empty">No guardian yet.</p>`}
          <a class="btn sm" href="#security" style="margin-top:12px">Manage guardian</a></section>
        <section class="panel"><h3>Payment record</h3><div class="statmini" id="precord"><div><b>…</b><small>payments</small></div><div><b>…</b><small>on time</small></div><div><b>…</b><small>paid in total</small></div><div><b>…</b><small>certificates</small></div></div>
          <a class="btn sm" href="#certs" style="margin-top:12px">Payment certificates</a></section>
        <section class="panel"><h3>Security</h3><dl class="kv"><dt>Assistant mode</dt><dd>${esc(lvl)}</dd><dt>Guardian approval</dt><dd>${S.guardian_approval ? "On" : "Off"}</dd>
          <dt>Kill switch</dt><dd>${S.frozen ? "On — payments frozen" : "Off"}</dd><dt>Password changed</dt><dd>${u.password_changed ? date(new Date(u.password_changed * 1000).toISOString()) : "—"}</dd>
          <dt>Activity log</dt><dd>${S.audit.valid ? "Intact" : "Tampering detected"} · ${S.audit.entries} entries</dd></dl></section>
        <section class="panel"><h3>Wallets</h3><dl class="kv">${Object.entries(S.balances).map(([c, v]) => `<dt>${esc(c)}</dt><dd class="num">${fmt(v, 2)}</dd>`).join("")}</dl>
          <p style="color:var(--ink-3);font-size:12.5px;margin:12px 0 0">Sandbox balances. Family support arrives on its schedule.</p></section>
      </div>`;
    view.appendChild(Portal.feedbackPanel());
    Portal.photos(view);
    const done = photo => { S.user.photo = photo; Portal.avatar($("#me-av"), S.user); V.profile(); };
    $("#pe").replaceWith(Portal.photoEditor(u, done));
    const rm = $("#rmphoto"); if (rm) rm.addEventListener("click", () => Portal.removePhoto(done));
    const r = await api("/api/certificates");
    if (current !== "profile" || !$("#precord")) return;
    const recs = r.records || [], tot = {};
    recs.forEach(x => { tot[x.currency] = (tot[x.currency] || 0) + x.amount; });
    const b = $$("#precord b");
    b[0].textContent = recs.length; b[1].textContent = `${recs.filter(x => x.on_time).length}/${recs.length}`;
    b[2].textContent = Object.keys(tot).length ? Object.entries(tot).map(([c, v]) => `${c} ${fmt(v)}`).join(", ") : "—";
    b[3].textContent = (r.issued || []).length;
  };


  V.certs = async () => {
    const H = head(I18N.t("p.certs", "Payment certificates"), "Turn on-time tuition payments into signed proof that a landlord, bank or scholarship office can check — a first step to a credit history abroad.");
    view.innerHTML = H + `<p class="empty">Loading…</p>`;
    const r = await api("/api/certificates");
    if (current !== "certs") return;
    const recs = r.records || [];
    view.innerHTML = H + `<div class="cols"><div>
      <section class="panel"><h3>Settled payments <small>${recs.filter(x => x.on_time).length} of ${recs.length} on time</small></h3>
      ${recs.length ? `<ul class="list">${recs.map(x => `<li><div class="grow"><b>${esc(x.currency)} ${fmt(x.amount, 2)} to ${esc(x.institution)}</b><span>Arrived ${date(x.paid_on)} · due ${date(x.due)}${x.on_time ? ` · ${x.days_early} day(s) early` : ""} · ${esc(x.channel)}</span></div>${pill(x.on_time ? "ok" : "warn", x.on_time ? "On time" : "Late")}<button class="btn sm ${x.certificate ? "" : "primary"}" data-issue="${esc(x.transfer_id)}">${x.certificate ? "Issue again" : "Create certificate"}</button></li>`).join("")}</ul>
        <button class="btn" id="histbtn" style="margin-top:14px">Certificate for my whole payment history</button>`
      : `<p class="empty">Payment certificates appear once a tuition payment has arrived. Pay an invoice, then move the sandbox clock forward a few days. A proof of funds can be created any time.</p>`}</section>
      <section class="panel"><h3>Issued certificates</h3><div id="issued">${(r.issued || []).length ? "" : `<p class="empty">None yet.</p>`}</div></section>
    </div><div>
      <section class="panel"><h3>Proof of funds <small>for a visa, landlord or scholarship</small></h3>
        <p style="color:var(--ink-2);font-size:14px;margin:0 0 12px">Prove you hold <b>at least</b> an amount — without sharing a bank statement. The certificate never shows your real balance, and it's valid for 30 days.</p>
        <form id="fundsform" class="fundsform"><label>Amount to prove<input class="input" id="f-amt" inputmode="decimal" required placeholder="e.g. 5000"></label>
          <label>Currency<select class="input" id="f-ccy">${[...new Set([S.study_currency, S.home_currency, "USD"])].map(c => `<option>${esc(c)}</option>`).join("")}</select></label>
          <label class="wide">What it's for<input class="input" id="f-purpose" maxlength="60" placeholder="Student pass renewal"></label>
          <button class="btn primary" type="submit">Create proof of funds</button></form></section>
      <section class="panel"><h3>How others check it</h3><p style="color:var(--ink-2);font-size:14px;margin:0 0 12px">Each certificate is signed with SudoRoute's Ed25519 key. Anyone can check it on the public verify page, with no account. Changing a single character makes the check fail.</p>
        <dl class="claims" style="grid-template-columns:110px 1fr;font-size:13.5px"><dt>Algorithm</dt><dd>${esc(r.issuer.alg)}</dd><dt>Key ID</dt><dd>${esc(r.issuer.kid)}</dd><dt>Public key</dt><dd style="font:500 12px var(--mono)">${esc(r.issuer.public_key_hex)}</dd></dl>
        <a class="btn" href="/verify" target="_blank" rel="noopener" style="margin-top:14px">Open the verify page</a></section>
    </div></div>`;
    const showIssued = list => {
      const box = $("#issued"); if (!list.length) return;
      box.innerHTML = list.slice().reverse().map(c => `<div class="card" style="margin:0 0 12px"><h4>${esc(c.type === "payment_history" ? "Payment history" : c.type === "proof_of_funds" ? "Proof of funds" : "Tuition payment")} · ${esc(c.cert_id)} ${pill("ok", "Signed")}</h4>
        <div class="certcode">${esc(c.code)}</div><div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center"><button class="btn sm" data-copy="${esc(c.code)}">Copy</button><a class="btn sm" href="/verify#${encodeURIComponent(c.code)}" target="_blank" rel="noopener">Check it</a><a class="btn sm" href="/verify?pdf=1#${encodeURIComponent(c.code)}" target="_blank" rel="noopener">Download PDF</a>${c.anchor ? `<span class="chainstat" data-anchor="${esc(c.anchor)}">⛓ checking on-chain anchor…</span>` : ""}</div></div>`).join("");
      $$("[data-anchor]", box).forEach(async el => {
        const a = await api("/api/public/anchor?h=" + el.dataset.anchor);
        el.innerHTML = a.status === "submitted" ? `⛓ Anchored on Bitcoin via OpenTimestamps (${esc(a.calendars.length)} calendar${a.calendars.length > 1 ? "s" : ""})`
          : `⛓ On-chain anchor not submitted yet <button class="btn sm quiet" data-retry="${esc(el.dataset.anchor)}">Try again</button>`;
        const rb = el.querySelector("[data-retry]");
        if (rb) rb.addEventListener("click", () => Motion.busy(rb, async () => { const x = await api("/api/chain/retry", { h: rb.dataset.retry }); el.textContent = x.status === "submitted" ? "⛓ Anchored on Bitcoin via OpenTimestamps" : "⛓ Still offline — try again later"; }));
      });
      $$("[data-copy]", box).forEach(b => b.addEventListener("click", async () => { try { await navigator.clipboard.writeText(b.dataset.copy); toast("Certificate copied."); } catch (e) { toast("Select the text and copy it."); } }));
    };
    showIssued(r.issued || []);
    const issue = async (body, btn) => { const x = await Motion.busy(btn, () => api("/api/certificates/issue", body)); if (!x.ok) { toast(x.error); return; } toast(`Certificate ${x.cert_id} signed.`); V.certs(); };
    $$("[data-issue]", view).forEach(b => b.addEventListener("click", () => issue({ kind: "payment", transfer_id: b.dataset.issue }, b)));
    const hb = $("#histbtn"); if (hb) hb.addEventListener("click", () => issue({ kind: "history" }, hb));
    $("#fundsform").addEventListener("submit", e => { e.preventDefault(); issue({ kind: "funds", at_least: parseFloat($("#f-amt").value.replace(/,/g, "")), currency: $("#f-ccy").value, purpose: $("#f-purpose").value }, $("#fundsform button")); });
  };

  // ------------------------------------------------------------ kill switch
  async function toggleKill() {
    if (!S.frozen) {
      const r = await Motion.busy($("#killbtn"), () => api("/api/killswitch", { engage: true }));
      toast(r.ok ? `Kill switch on. ${r.cancelled ? r.cancelled.length : 0} pending payment(s) cancelled.` : r.error);
    } else {
      const pw = await Portal.askPassword("Release the kill switch?", "The assistant will be able to prepare payments again. Stopped instalment plans stay stopped.");
      if (pw === null) return;
      const r = await api("/api/killswitch", { engage: false, password: pw });
      toast(r.ok ? "Kill switch released." : r.error);
    }
    refresh();
  }
  function paintKill() {
    const b = $("#killbtn"), bar = $("#frozenbar"); if (!b) return;
    b.classList.toggle("on", !!S.frozen);
    b.querySelector("span").textContent = S.frozen ? I18N.t("p.killon", "Frozen") : I18N.t("p.kill", "Kill switch");
    b.setAttribute("aria-pressed", String(!!S.frozen));
    bar.hidden = !S.frozen;
    $("#releasebtn").hidden = !!(S.frozen && S.frozen.by === "guardian");
    if (S.frozen) bar.querySelector("span").textContent = I18N.t("p.frozen", "Kill switch is on: no money can be prepared or sent.") +
      ` (${S.frozen.by === "guardian" ? `by ${S.frozen.name}, your guardian — only they can release it` : "by you"})`;
  }

  // ------------------------------------------------------------ guided tour (for demos and screen recordings)
  const TOUR = [
    { view: "overview", spot: ".kpis", title: "A student's tuition at a glance", text: "Wallets in two currencies, what is still due, and the linked guardian who co-approves payments. Every number comes from the sandbox bank." },
    { view: "invoices", spot: "[data-verify^='INV-PHISH']", act: () => { const b = $("[data-verify^='INV-PHISH']"); b && b.click(); }, title: "A scam invoice arrives", text: "A look-alike e-mail asks for crypto and hides instructions for AI assistants. The scam shield scores it 100/100 and explains every point." },
    { view: "assistant", act: () => send("Pay my tuition"), wait: 2200, spot: ".prop", title: "Ask the agent to pay", text: "It verifies the invoice, compares every channel on true cost, prices currency risk and runs ten compliance checks — then prepares a signed proposal. Nothing has moved yet." },
    { view: "assistant", spot: "#trace", title: "Every step, with its permission tier", text: "Read, Analyse, Prepare. Executing money is a separate tier the chat can never reach — it needs one-time codes from the student and, here, the guardian." },
    { view: "payments", spot: "#pending", title: "Two approvals", text: "The guardian approves from their own portal with their own code, then the student confirms. Tamper with the amount or replay the request and it is rejected." },
    { view: "insights", spot: ".card", title: "Currency risk and true cost", text: "4,000 simulated futures show the chance that waiting breaks the family budget, and the route table shows hidden exchange-rate markups and why illegal channels are excluded." },
    { view: "security", spot: "#killbtn", title: "Kill switch and permission levels", text: "One press cancels everything pending and stops instalment plans. Giving the agent more power, or removing the guardian, needs the password again." },
    { view: "certs", spot: ".panel", title: "Proof for a credit history", text: "After a payment arrives, the student can create a signed certificate that any landlord or bank can verify on a public page." },
    { view: "overview", title: "Now try to break it", text: "Open the Security Lab from the home page: it fires 57 real attacks at a live copy of SudoRoute and shows each one being stopped." },
  ];
  let tourIdx = -1, tourAuto = false, tourTimer = null;
  function tourStop() { tourIdx = -1; clearTimeout(tourTimer); $$(".tour-spot").forEach(e => e.classList.remove("tour-spot")); const t = $("#tourbox"); if (t) t.remove(); }
  async function tourShow(i) {
    clearTimeout(tourTimer);
    if (i < 0 || i >= TOUR.length) return tourStop();
    tourIdx = i; const step = TOUR[i];
    if (location.hash.slice(1).split("?")[0] !== step.view) { location.hash = step.view; await new Promise(r => setTimeout(r, 900)); }
    if (step.act) { await step.act(); await new Promise(r => setTimeout(r, step.wait || 1200)); }
    $$(".tour-spot").forEach(e => e.classList.remove("tour-spot"));
    const el = step.spot && $(step.spot);
    if (el) { el.classList.add("tour-spot"); el.scrollIntoView({ behavior: "smooth", block: "center" }); }
    let box = $("#tourbox");
    if (!box) { box = document.createElement("div"); box.id = "tourbox"; box.className = "tour"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Guided tour"); document.body.appendChild(box); }
    box.innerHTML = `<b>${esc(step.title)}</b><p>${esc(step.text)}</p><div class="bar2"><span>Step ${i + 1} of ${TOUR.length}</span>
      <button type="button" data-t="exit">Exit</button><button type="button" data-t="back" ${i ? "" : "disabled"}>Back</button><button type="button" class="primary" data-t="next">${i === TOUR.length - 1 ? "Finish" : "Next"}</button></div>`;
    box.querySelector('[data-t="exit"]').onclick = tourStop;
    box.querySelector('[data-t="back"]').onclick = () => tourShow(i - 1);
    box.querySelector('[data-t="next"]').onclick = () => { tourAuto = false; tourShow(i + 1); };
    if (tourAuto) tourTimer = setTimeout(() => tourShow(i + 1), 7500);
  }
  document.addEventListener("keydown", e => {
    if (tourIdx < 0) return;
    if (e.key === "Escape") tourStop(); else if (e.key === "ArrowRight") { tourAuto = false; tourShow(tourIdx + 1); } else if (e.key === "ArrowLeft") { tourAuto = false; tourShow(tourIdx - 1); }
  });

  // ------------------------------------------------------------ boot
  async function refresh(rerender = true) {
    S = await api("/api/state");
    $("#me-name").textContent = S.name; Portal.avatar($("#me-av"), S.user);
    $("#simdate").textContent = TS.date(S.sim_date);
    Portal.ai(S.ai);
    Portal.setCount("payments", S.pending.length);
    Portal.setCount("invoices", S.invoices.filter(i => i.verdict === "BLOCK" && i.status === "open").length);
    paintKill();
    Phone.mount("student", S.id, S.phone_masked || S.phone); Phone.sync(S.sms_inbox, S.pending.filter(p => p.status === "awaiting_guardian").map(p => p.proposal.proposal_id));
    if (rerender && current !== "assistant") V[current]();
  }
  const go = Portal.init({
    items: [{ id: "overview", label: "Overview", group: "Money" }, { id: "assistant", label: "Assistant", group: "Money" },
      { id: "payments", label: "Payments", group: "Money" }, { id: "invoices", label: "Invoices", group: "Money" },
      { id: "insights", label: "Insights", group: "Planning" }, { id: "certs", label: "Certificates", group: "Planning" },
      { id: "security", label: "Security", group: "Account" }, { id: "profile", label: "Profile", group: "Account" }],
    render: id => { current = id; if (id === "assistant") { V.assistant(); refresh(false); } else refresh(); },
    onClock: r => { const mine = r.events.filter(e => e.student_id === S.id || S.invoices.some(i => i.id === e.invoice_id)); const arrived = mine.filter(e => e.type === "settlement").length, sent = mine.filter(e => e.type === "mandate_leg_executed").length;
      toast(`Sandbox date is now ${TS.date(r.sim_date)}.${arrived ? ` ${arrived} payment(s) arrived at the university.` : ""}${sent ? ` ${sent} installment(s) sent.` : ""}`); refresh(); },
  });
  $(".topbar .right [data-lang-picker]").insertAdjacentHTML("beforebegin", `<button class="kill" id="killbtn" type="button" title="Freeze all payments instantly"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v8"/><path d="M6.3 7.5a8 8 0 1 0 11.4 0"/></svg><span>Kill switch</span></button>`);
  $(".topbar").insertAdjacentHTML("afterend", `<div class="frozenbar" id="frozenbar" role="alert" hidden><span></span><button type="button" id="releasebtn">Release</button></div>`);
  $("#killbtn").addEventListener("click", toggleKill);
  $("#releasebtn").addEventListener("click", toggleKill);
  document.addEventListener("sr:changed", () => refresh(false));
  await refresh(false);
  go();
  if (location.hash.includes("tour")) { tourAuto = true; setTimeout(() => tourShow(0), 800); }
  // Pick up approvals and arrivals made elsewhere (e.g. by a guardian) without a reload.
  setInterval(async () => {
    if (document.hidden || current === "assistant" || document.activeElement?.closest("form")) return;
    const before = JSON.stringify([S.pending.map(p => p.status), S.transfers.map(t => t.status), S.notifications.length, S.sms_inbox.length]);
    const next = await api("/api/state");
    if (JSON.stringify([next.pending.map(p => p.status), next.transfers.map(t => t.status), next.notifications.length, next.sms_inbox.length]) !== before) refresh();
  }, 15000);
})();
