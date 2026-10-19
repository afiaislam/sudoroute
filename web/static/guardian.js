(async () => {
  const { $, $$, esc, fmt, date, api, toast } = TS;
  const { pill, st } = Cards;
  await TS.session();
  let G = null;
  let current = "overview";
  const view = $("#view");
  const head = (t, s, a = "") => `<div class="pagehead"><div><h2>${esc(t)}</h2>${s ? `<p>${esc(s)}</p>` : ""}</div>${a}</div>`;
  const first = n => TS.first(n);

  function linkForm() {
    const n = Cards.el(`<form class="linkform" novalidate><div class="field"><label for="lk">Student's link code</label><input class="input" id="lk" placeholder="ABCD-2345" autocomplete="off" style="max-width:220px;text-transform:uppercase"><span class="hint">The student creates it in SudoRoute under Security → Create a guardian link code.</span></div><button class="btn primary" type="submit">Link student</button><div class="out" style="margin-top:12px"></div></form>`);
    n.addEventListener("submit", async e => {
      e.preventDefault();
      const r = await api("/api/guardian/link", { code: n.querySelector("#lk").value });
      n.querySelector(".out").innerHTML = `<div class="alert ${r.ok ? "ok" : "bad"}">${esc(r.ok ? "Linked. You can now see their payments and approve them." : r.error)}</div>`;
      if (r.ok) setTimeout(refresh, 600);
    });
    return n;
  }

  async function freeze(sid) {
    const s = G.students.find(x => x.id === sid);
    if (!s.frozen) {
      const r = await Motion.busy(document.querySelector(`[data-freeze="${sid}"]`), () => api("/api/guardian/killswitch", { student_id: sid, engage: true }));
      toast(r.ok ? `Frozen. ${r.cancelled ? r.cancelled.length : 0} pending payment(s) cancelled.` : r.error);
    } else {
      const pw = await Portal.askPassword("Release the kill switch?", `${first(s.name)} will be able to prepare payments again.`);
      if (pw === null) return;
      const r = await api("/api/guardian/killswitch", { student_id: sid, engage: false, password: pw });
      toast(r.ok ? "Kill switch released." : r.error);
    }
    refresh();
  }
  const V = {};
  V.overview = () => {
    const h = new Date().getHours(), gr = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    view.innerHTML = `<section class="pbanner"><img src="https://images.unsplash.com/photo-1752652013112-6734bf1a682a?auto=format&fit=crop&w=1600&q=70" alt="" loading="lazy" decoding="async"><div class="pbanner-shade" aria-hidden="true"></div>
      <div class="pb-copy"><span class="badge">Guardian${G.user.relationship ? " · " + esc(G.user.relationship) : ""}</span><h2>${gr}, ${esc(first(G.user.name))}</h2>
        <p>${G.students.length ? "Here's where your student's tuition stands. Nothing is paid without your code." : "Link a student to see their tuition and approve payments."}</p>
        <div class="pb-actions">${G.pending.length ? `<a class="btn accent" href="#approvals">Review ${G.pending.length} approval${G.pending.length > 1 ? "s" : ""}</a>` : `<a class="btn accent" href="#funds">Send family support</a>`}<a class="btn ghost" href="#activity">Activity log</a></div></div>
      <div class="pb-next"><small>Waiting for your approval</small><b>${G.pending.length}</b><span>${G.students.length} linked student${G.students.length === 1 ? "" : "s"}</span></div></section>`;
    Portal.photos(view);
    if (!G.students.length) { const p = Cards.el(`<section class="panel"><h3>Link a student</h3></section>`); p.appendChild(linkForm()); view.appendChild(p); return; }
    G.students.forEach(s => {
      const dueInv = s.invoices.filter(i => i.verdict !== "BLOCK" && i.status !== "paid").sort((a, b) => a.due.localeCompare(b.due));
      const pend = G.pending.filter(p => p.proposal.student_id === s.id);
      const scams = s.invoices.filter(i => i.verdict === "BLOCK" && i.status === "open");
      view.insertAdjacentHTML("beforeend", `
        <section class="panel">
          <div style="display:flex;gap:14px;align-items:center;margin-bottom:16px"><div class="avatar">${esc(Portal.initials(s.name))}</div><div class="grow" style="flex:1"><h3 style="font:800 22px var(--sans);margin:0">${esc(s.name)}</h3><span style="color:var(--ink-3);font-size:13.5px">${esc(s.program)} · ${esc(s.university.name)}, ${esc(s.university.city)}</span></div>${pill(s.guardian_approval ? "ok" : "warn", s.guardian_approval ? "Your approval required" : "Approval switched off")}
            <button class="kill ${s.frozen ? "on" : ""}" type="button" data-freeze="${esc(s.id)}" aria-pressed="${!!s.frozen}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v8"/><path d="M6.3 7.5a8 8 0 1 0 11.4 0"/></svg><span>${s.frozen ? esc(I18N.t("p.killon", "Frozen")) : esc(I18N.t("p.kill", "Kill switch"))}</span></button></div>
          ${s.frozen ? `<div class="alert bad">${esc(I18N.t("p.frozen", "Kill switch is on: no money can be prepared or sent."))} ${s.frozen.by === "guardian" ? "You switched it on; only a guardian can release it." : `${esc(first(s.name))} switched it on.`}</div>` : ""}
          <div class="kpis" style="margin-bottom:16px">
            <div><small>${esc(s.home_currency)} wallet</small><b class="num">${fmt(s.balances[s.home_currency] || 0)}</b><span>Family savings</span></div>
            <div><small>${esc(s.study_currency)} wallet</small><b class="num">${fmt(s.balances[s.study_currency] || 0, 2)}</b><span>Living costs</span></div>
            <div><small>Tuition still due</small><b class="num">${esc(s.study_currency)} ${fmt(s.outstanding, 2)}</b><span>${dueInv.length ? `Next due ${date(dueInv[0].due)}` : "Nothing due"}</span></div>
            <div><small>Waiting for you</small><b>${pend.length}</b><span>${pend.length ? `<a href="#approvals">Review now</a>` : "No requests"}</span></div>
          </div>
          ${scams.length ? `<div class="alert bad">${scams.length} suspicious invoice${scams.length > 1 ? "s were" : " was"} sent to ${esc(first(s.name))} and blocked: ${scams.map(i => esc(i.sender_email)).join(", ")}.</div>` : ""}
          <div class="cols even"><div><h4 style="margin:0 0 8px;font-weight:600">Recent payments</h4>${s.transfers.length ? `<ul class="list">${s.transfers.slice(-4).reverse().map(t => `<li><div class="grow"><b>${esc(t.dst_currency)} ${fmt(t.dst_amount, 2)}</b><span>${esc(t.provider_name)} · ${date(t.created)}</span></div>${st(t.status)}</li>`).join("")}</ul>` : `<p class="empty">No payments yet.</p>`}</div>
          <div><h4 style="margin:0 0 8px;font-weight:600">Invoices</h4><ul class="list">${s.invoices.map(i => `<li><div class="grow"><b>${esc(i.currency)} ${fmt(i.amount, 2)}</b><span>${esc(i.sender_email)} · due ${date(i.due)}</span></div>${i.status === "open" ? pill(i.verdict, Cards.VERDICT[i.verdict]) : st(i.status)}</li>`).join("")}</ul></div></div>
        </section>`);
    });
  };

  view.addEventListener("click", e => { const b = e.target.closest("[data-freeze]"); if (b) freeze(b.dataset.freeze); });
  V.approvals = () => {
    view.innerHTML = head("Approvals", "Check each payment, then approve with the code sent to your phone. Your student confirms after you.");
    if (!G.pending.length) { view.insertAdjacentHTML("beforeend", `<section class="panel"><p class="empty">No payments are waiting for you. When your student prepares one, it appears here.</p></section>`); }
    const cols = Cards.el(`<div class="cols"><div id="reqs"></div><aside><section class="panel"><h3>Your sandbox phone <small>${esc(G.user.phone || G.user.phone_masked || "")}</small></h3>${G.inbox.length ? G.inbox.slice().reverse().map(m => `<div class="sms">${esc(m.text).replace(/code (\d{6})/, "code <b>$1</b>")}<small>${esc(m.proposal_id)}</small></div>`).join("") : `<p class="empty">Approval codes arrive here.</p>`}</section></aside></div>`);
    if (G.pending.length) view.appendChild(cols);
    G.pending.forEach(p => {
      const s = G.students.find(x => x.id === p.proposal.student_id) || { name: "Your student" };
      const card = Cards.render({ ...p, type: "proposal" }, { readonly: true, compact: true });
      card.querySelector("h4 span").textContent = `${first(s.name)} asks you to approve`;
      card.insertAdjacentHTML("beforeend", `<form class="otp" novalidate><label class="otplabel" for="g-${esc(p.proposal.proposal_id)}">Enter the 6-digit approval code we texted to your phone</label><input id="g-${esc(p.proposal.proposal_id)}" inputmode="numeric" maxlength="6" placeholder="••••••" autocomplete="one-time-code">
        <button class="btn primary" type="submit" data-act="approve">Approve</button><button class="btn danger" type="button" data-act="decline">Decline</button></form>${Cards.otpHelp(p.proposal.proposal_id, "guardian")}<div class="gout"></div>`);
      const form = card.querySelector("form.otp");
      const decide = async approve => {
        const btn = form.querySelector(approve ? '[data-act="approve"]' : '[data-act="decline"]');
        const r = await Motion.busy(btn, () => api("/api/guardian/decide", { proposal_id: p.proposal.proposal_id, otp: form.querySelector("input").value, approve }));
        card.querySelector(".gout").innerHTML = `<div class="alert ${r.ok ? "ok" : "bad"}" style="margin-top:12px">${esc(r.ok ? r.message : r.error)}</div>`;
        if (r.ok) { form.remove(); setTimeout(refresh, 1400); }
      };
      form.addEventListener("submit", e => { e.preventDefault(); decide(true); });
      form.querySelector("[data-act=decline]").addEventListener("click", () => decide(false));
      cols.querySelector("#reqs").appendChild(card);
    });
  };

  V.activity = async () => {
    view.innerHTML = head("Activity", "Every payment and check for your students, recorded in a log that shows if anything was altered.") +
      G.students.map(s => `<section class="panel"><h3>${esc(s.name)} — payments</h3>${s.transfers.length ? `<div class="tablewrap"><table><thead><tr><th>Payment</th><th>Channel</th><th class="n">Sent</th><th class="n">Received</th><th>Arrives</th><th></th></tr></thead><tbody>${s.transfers.slice().reverse().map(t => `<tr><td>${esc(t.id)}</td><td>${esc(t.provider_name)}</td><td class="n">${esc(t.src_currency)} ${fmt(t.src_amount)}</td><td class="n">${esc(t.dst_currency)} ${fmt(t.dst_amount, 2)}</td><td>${date(t.eta)}</td><td>${st(t.status)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="empty">No payments yet.</p>`}
        ${s.mandates.length ? `<h4 style="margin:16px 0 6px">Installment plans</h4><ul class="list">${s.mandates.map(m => `<li><div class="grow"><b>${m.executed_legs.length} of ${m.total_legs} installments sent</b><span>${esc(m.invoice_id)} · to ${esc(m.payee_account)}</span></div>${st(m.status)}</li>`).join("")}</ul>` : ""}</section>`).join("") +
      `<section class="panel"><h3>Activity log</h3><div id="auditbox"><p class="empty">Loading…</p></div></section>`;
    const a = await api("/api/audit");
    if (current !== "activity") return;
    $("#auditbox").innerHTML = `<div class="chain"><i class="${a.verify.valid ? "" : "bad"}"></i>${a.verify.valid ? `Every record is intact (${a.verify.entries} linked entries).` : `Tampering detected at record ${a.verify.broken_at}.`}</div>` + Portal.auditList(a.entries);
  };

  V.funds = () => {
    view.innerHTML = head("Send funds", "Move family support into your student's wallet. Sandbox transfers are limited to about USD 10,000 a day.");
    if (!G.students.length) { view.insertAdjacentHTML("beforeend", `<section class="panel"><p class="empty">Link a student first.</p></section>`); return; }
    view.insertAdjacentHTML("beforeend", `<div class="cols"><section class="panel"><h3>New transfer</h3><form id="fund" novalidate>
      <div class="field"><label for="f-st">Student</label><select class="input" id="f-st">${G.students.map(s => `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.home_currency)})</option>`).join("")}</select></div>
      <div class="field"><label for="f-amt">Amount</label><input class="input" id="f-amt" inputmode="decimal" placeholder="e.g. 50000"><span class="hint" id="f-ccy"></span></div>
      <button class="btn primary" type="submit">Send funds</button><div class="out" style="margin-top:12px"></div></form></section>
      <section class="panel"><h3>Sent today and earlier</h3>${G.funding.length ? `<ul class="list">${G.funding.slice().reverse().map(f => `<li><div class="grow"><b>${esc(f.currency)} ${fmt(f.amount)}</b><span>${date(f.date)}</span></div>${pill("ok", "Received")}</li>`).join("")}</ul>` : `<p class="empty">Nothing sent yet.</p>`}</section></div>`);
    const ccy = () => { const s = G.students.find(x => x.id === $("#f-st").value); $("#f-ccy").textContent = `In ${s.home_currency}. Current balance ${s.home_currency} ${fmt(s.balances[s.home_currency] || 0)}.`; };
    $("#f-st").addEventListener("change", ccy); ccy();
    $("#fund").addEventListener("submit", async e => {
      e.preventDefault();
      const r = await api("/api/guardian/fund", { student_id: $("#f-st").value, amount: parseFloat($("#f-amt").value.replace(/,/g, "")) });
      $("#fund .out").innerHTML = `<div class="alert ${r.ok ? "ok" : "bad"}">${esc(r.ok ? `Sent. New balance ${r.currency} ${fmt(r.balance)}.` : r.error)}</div>`;
      if (r.ok) setTimeout(refresh, 1200);
    });
  };

  V.settings = () => {
    const u = G.user;
    view.innerHTML = `<div class="profcover"><img src="https://images.unsplash.com/photo-1752652012592-8f618322a63c?auto=format&fit=crop&w=1600&q=70" alt="" loading="lazy" decoding="async"></div>
      <section class="profhead"><div id="pe"></div><div class="who"><h2>${esc(u.name)}</h2><span style="color:var(--ink-3)">${esc(u.email)}</span>
        <div class="tags">${pill("ok", "Guardian")}${u.relationship ? pill("neutral", u.relationship) : ""}${pill(G.students.length ? "ok" : "warn", G.students.length ? `${G.students.length} student${G.students.length > 1 ? "s" : ""} linked` : "No student linked")}</div></div>
        <div class="acts">${u.photo ? `<button class="btn sm" id="rmphoto">Remove photo</button>` : ""}</div></section>
      <div class="cols even"><div><section class="panel"><h3>Account</h3><dl class="kv"><dt>Account type</dt><dd>Guardian (${esc(u.relationship || "")})</dd><dt>Linked students</dt><dd>${G.students.length ? G.students.map(s => esc(s.name)).join(", ") : "None"}</dd>
        <dt>Registered phone</dt><dd>${esc(u.phone || u.phone_masked || "—")}</dd><dt>Member since</dt><dd>${new Date(u.created * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}</dd></dl></section>
        <section class="panel"><h3>Link another student</h3><div id="lf"></div></section></div>
        <div><section class="panel"><h3>Password</h3><div id="pwc"></div></section>
        <section class="panel"><h3>What you can and can't do</h3><ul class="ticks" style="margin:0"><li>See balances, invoices, payments and the activity log of linked students.</li><li>Approve or decline payments with your own code.</li><li>Send family support into their wallet.</li><li>You can't sign in as the student, change their settings or move their money elsewhere.</li></ul></section></div></div>`;
    $("#lf").appendChild(linkForm());
    $("#pwc").appendChild(Portal.changePasswordForm());
    view.appendChild(Portal.feedbackPanel());
    Portal.photos(view);
    const done = photo => { G.user.photo = photo; Portal.avatar($("#me-av"), G.user); V.settings(); };
    $("#pe").replaceWith(Portal.photoEditor(u, done));
    const rm = $("#rmphoto"); if (rm) rm.addEventListener("click", () => Portal.removePhoto(done));
  };

  async function refresh(rerender = true) {
    G = await api("/api/guardian/overview");
    $("#me-name").textContent = G.user.name; Portal.avatar($("#me-av"), G.user);
    $("#me-role").textContent = `Guardian · ${G.user.relationship || ""}`;
    $("#simdate").textContent = date(G.sim_date);
    Portal.ai(G.ai);
    Portal.setCount("approvals", G.pending.length);
    Phone.mount("guardian", G.user.id, G.user.phone_masked || G.user.phone); Phone.sync(G.inbox);
    if (rerender) V[current]();
  }
  const go = Portal.init({
    items: [{ id: "overview", label: "Overview", group: "Family" }, { id: "approvals", label: "Approvals", group: "Family" },
      { id: "funds", label: "Send funds", group: "Family" }, { id: "activity", label: "Activity", group: "Account" },
      { id: "settings", label: "Profile and security", icon: "profile", group: "Account" }],
    render: id => { current = id; refresh(); },
    onClock: () => refresh(),
  });
  await refresh(false);
  go();
  setInterval(async () => {
    if (document.hidden || document.activeElement?.closest("form")) return;
    const next = await api("/api/guardian/overview");
    if (next.pending.length !== G.pending.length || (next.inbox || []).length !== (G.inbox || []).length) refresh();
  }, 15000);
})();
