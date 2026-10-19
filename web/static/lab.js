(() => {
  const { $, esc, api } = TS;
  const run = $("#run");
  function render(rep) {
    const att = rep.results.filter(r => r.cat !== "control" && r.passed).length, ctl = rep.results.filter(r => r.cat === "control" && r.passed).length;
    Motion.tween($("#s-pass"), 0, rep.passed, v => `${Math.round(v)}/${rep.total}`);
    Motion.tween($("#s-att"), 0, att, v => `${Math.round(v)}/${rep.attacks}`);
    Motion.tween($("#s-ctl"), 0, ctl, v => `${Math.round(v)}/${rep.controls}`);
    $("#s-time").textContent = `${rep.duration_s} s`;
    $("#meta").textContent = `Run at ${rep.ran_at} UTC on a fresh in-memory copy. Its tamper-evident audit log recorded ${rep.audit_chain.entries} entries and is ${rep.audit_chain.valid ? "intact" : "BROKEN"}.`;
    const groups = {}; let idx = 0;
    rep.results.forEach(r => (groups[r.category] = groups[r.category] || []).push(r));
    $("#results").innerHTML = Object.entries(groups).map(([cat, rows]) => `<section class="labgroup"><h2>${esc(cat)} <small>${rows.filter(r => r.passed).length}/${rows.length}</small></h2>
      ${rows.map(r => `<div class="labrow reveal" style="--si:${idx++}"><span class="id">${esc(r.id)}</span><div><b>${esc(r.name)}</b><span class="att">${esc(r.attack)}</span></div>
        <div class="obs"><em>${esc(r.defence)}</em>${esc(r.observed)}</div>
        <div class="res">${r.passed ? `<span class="pill ok">${r.cat === "control" ? "Succeeded" : "Stopped"}</span>` : `<span class="pill bad">Failed</span>`}${r.owasp && r.owasp !== "—" ? `<br><span style="font-size:12px;color:var(--ink-3)">OWASP ${esc(r.owasp)}</span>` : ""}</div></div>`).join("")}</section>`).join("");
  }
  run.addEventListener("click", async () => {
    // No fake progress: the bar is indeterminate until the server returns the real results.
    const prog = $("#prog"), status = $("#labstatus");
    prog.hidden = false; status.textContent = "Starting a private copy of SudoRoute and attacking it over HTTP…";
    $("#results").innerHTML = "";
    const rep = await Motion.busy(run, () => api("/api/public/security-lab/run", {}));
    prog.hidden = true;
    if (!rep.ok) { status.textContent = rep.error; return; }
    status.textContent = `Finished: ${rep.passed} of ${rep.total} checks passed.`;
    render(rep);
  });
  if (location.hash === "#run") run.click();
})();
