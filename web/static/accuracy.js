(async () => {
  const { $, esc, api } = TS;
  const r = await api("/api/public/benchmark");
  const o = r.overall;
  $("#score").innerHTML = `<div class="good"><b class="num">${o.detection_rate_pct}%</b><small>of scams flagged (${o.scam - o.scam_missed}/${o.scam})</small></div>
    <div class="good"><b class="num">${o.false_block_rate_pct}%</b><small>of genuine invoices blocked (${o.genuine_blocked}/${o.genuine})</small></div>
    <div><b class="num">${o.block_rate_pct}%</b><small>of scams hard-blocked; the rest sent to review</small></div>
    <div><b class="num">${o.false_alarm_rate_pct}%</b><small>of genuine invoices sent to review (${o.genuine_review}/${o.genuine})</small></div>`;
  if (r.v2) {
    const v = r.v2.overall, h = r.v1_history;
    $("#v2note").textContent = `Set v1 (above) first showed ${h.frozen_rules_false_alarm_pct}% false alarms with the frozen rules: genuine warnings such as "we never accept crypto" were sent to review. We added a negation-aware rule — so v1 is no longer unseen. Set v2 was written next, evaluated once, and includes scams built to beat the new rule. ${r.v2.protocol}`;
    $("#v2score").innerHTML = `<div class="good"><b class="num">${v.detection_rate_pct}%</b><small>of scams flagged (${v.scam - v.scam_missed}/${v.scam})</small></div>
      <div class="good"><b class="num">${v.false_block_rate_pct}%</b><small>of genuine invoices blocked</small></div>
      <div><b class="num">${v.false_alarm_rate_pct}%</b><small>genuine sent to review (${v.genuine_review}/${v.genuine})</small></div>
      <div><b class="num">${v.block_rate_pct}%</b><small>scams hard-blocked; the rest held for review</small></div>`;
    const bad = r.v2.samples.filter(x => (x.label === "genuine" && x.verdict !== "SAFE") || (x.label === "scam" && x.verdict === "SAFE"));
    $("#v2misses").innerHTML = bad.length ? `<thead><tr><th>ID</th><th>Truth</th><th>Verdict</th><th>What it is</th></tr></thead><tbody>${bad.map(x => `<tr><td>${esc(x.id)}</td><td>${x.label === "scam" ? "Scam" : "Genuine"}</td><td><span class="pill ${esc(x.verdict)}">${esc(x.verdict)}</span></td><td>${esc(x.note)}</td></tr>`).join("")}</tbody>` : "";
  }
  $("#bylang").innerHTML = `<thead><tr><th>Language</th><th class="n">Scams flagged</th><th class="n">Hard-blocked</th><th class="n">Genuine blocked</th><th class="n">Genuine sent to review</th></tr></thead><tbody>` +
    Object.entries(r.by_language).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="n">${v.detection_rate_pct}%</td><td class="n">${v.block_rate_pct}%</td><td class="n">${v.false_block_rate_pct}%</td><td class="n">${v.false_alarm_rate_pct}%</td></tr>`).join("") + `</tbody>`;
  $("#defs").innerHTML = ["detection_rate_pct", "block_rate_pct", "false_block_rate_pct", "false_alarm_rate_pct", "note"].map(k => `<li>${esc(r.definitions[k])}</li>`).join("");
  const rank = s => (s.label === "scam" && s.verdict === "SAFE") ? 0 : (s.label === "genuine" && s.verdict !== "SAFE") ? 1 : (s.label === "scam" && s.verdict === "REVIEW") ? 2 : 3;
  const rows = r.samples.slice().sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
  $("#samples").innerHTML = `<thead><tr><th>ID</th><th>Language</th><th>Truth</th><th>Verdict</th><th class="n">Score</th><th>Signals</th><th>What it is</th></tr></thead><tbody>` +
    rows.map(s => `<tr><td>${esc(s.id)}</td><td>${esc(s.lang)}</td><td>${s.label === "scam" ? "Scam" : "Genuine"}</td><td><span class="pill ${esc(s.verdict)}">${esc(s.verdict)}</span></td><td class="n">${s.score}</td><td style="font-size:12.5px;color:var(--ink-2)">${esc(s.reasons.join(", ") || "—")}</td><td>${esc(s.note)}</td></tr>`).join("") + `</tbody>`;
  const b = await api("/api/public/baselines");
  const cols = b.systems, S = b.summary;
  const good = (k, c) => { const v = cols.map(x => S[x][k]); const best = ["avg_saving_vs_bank_pct", "genuine_paid_without_delay"].includes(k) ? Math.max(...v) : Math.min(...v); return S[c][k] === best; };
  const rowsB = [["Scam invoices that send money to a fraudster", "scams_that_reach_a_fraudster", `of ${b.fraud.scams}`, ""],
    ["Genuine invoices paid without delay", "genuine_paid_without_delay", `of ${b.fraud.genuine}`, ""],
    ["Genuine invoices sent to the student for a check", "genuine_sent_for_a_check", "", ""],
    ["Average saving vs bank wire", "avg_saving_vs_bank_pct", "", "%"],
    ["Payments breaking a country, university or channel rule", "rule_violations", `of ${b.routes.scenarios}`, ""],
    ["Expected late payments (deadlines 2–21 days)", "late_rate_pct", "", "%"],
    ["Avoidable lateness (an allowed on-time channel existed)", "avoidable_late_pct", "", "%"],
    ["Retry situations that overpay the university", "overpayments_on_retry", "of 3", ""]];
  $("#base").innerHTML = `<thead><tr><th>Measure</th>${cols.map(c => `<th class="n">${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
    rowsB.map(([label, k, of, unit]) => `<tr><td>${esc(label)} ${of ? `<small style="color:var(--ink-3)">${esc(of)}</small>` : ""}</td>${cols.map(c => `<td class="n" style="${c === "SudoRoute" ? "font-weight:700;" : ""}${good(k, c) && k !== "genuine_sent_for_a_check" ? "color:var(--ok)" : ""}">${esc(String(S[c][k]))}${unit}</td>`).join("")}</tr>`).join("") + `</tbody>`;
  const fc = b.routes.by_country, names = { BD: "Bangladesh", NG: "Nigeria", IN: "India", PK: "Pakistan" };
  $("#fair").innerHTML = `<thead><tr><th>Home country</th><th class="n">Payments</th><th class="n">Saving vs bank wire</th><th class="n">Rule violations</th><th class="n">Expected late</th><th class="n">Bank wire late</th></tr></thead><tbody>` +
    Object.entries(fc).map(([c, v]) => `<tr><td>${esc(names[c] || c)}</td><td class="n">${v.payments}</td><td class="n">${v.saving_vs_bank_pct}%</td><td class="n">${v.rule_violations}</td><td class="n">${v.late_rate_pct}%</td><td class="n">${v.bank_wire_late_rate_pct}%</td></tr>`).join("") + `</tbody>`;
  $("#impossible").textContent = `${b.routes.impossible_on_time_legally} of ${b.routes.scenarios} payments have a deadline too close for any allowed channel — they count as late for every legal option. SudoRoute shows a "pay by" date on the dashboard so students see this coming.`;
  $("#basedefs").innerHTML = ["Bank wire", "Cheapest-fee assistant", "why_assistant_cheaper", "avoidable_late_pct", "note"].map(k => `<li>${k.includes(" ") ? `<b>${esc(k)}:</b> ` : ""}${esc(b.definitions[k])}</li>`).join("");
  const pl = await api("/api/public/pilot");
  $("#pilotscore").innerHTML = pl.responses
    ? `<div class="good"><b class="num">${pl.responses}</b><small>testers (${pl.students} students, ${pl.guardians} guardians)</small></div>
       <div class="good"><b class="num">${pl.useful_avg}/5</b><small>how useful for paying tuition</small></div>
       <div><b class="num">${pl.trust_avg}/5</b><small>trust with a real payment</small></div>
       <div><b class="num">${pl.would_use_pct}%</b><small>would use it for real (${pl.maybe_pct}% maybe)</small></div>`
    : `<div><b class="num">0</b><small>No pilot responses yet on this server. Sign up, try a payment, and rate it under Profile.</small></div>`;
})();
