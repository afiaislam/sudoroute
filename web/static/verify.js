(async () => {
  const { $, esc, api, fmt, date } = TS;
  const issuer = await api("/api/public/issuer");
  $("#issuer").innerHTML = `<dt>Algorithm</dt><dd>${esc(issuer.alg)}</dd><dt>Key ID</dt><dd>${esc(issuer.kid)}</dd><dt>Public key</dt><dd style="font:500 12px var(--mono)">${esc(issuer.public_key_hex)}</dd>`;
  const row = (k, v) => `<dt>${esc(k)}</dt><dd>${v}</dd>`;
  async function check(code) {
    $("#vout").innerHTML = "";
    const r = await Motion.busy($("#vform button"), () => api("/api/public/verify", { code }));
    const c = r.claims || {};
    // Three honest states, decided by the server's cryptographic check — never by the animation.
    const kind = r.valid ? "valid" : (r.claims && /signature/i.test(r.reason || "")) ? "invalid" : "unverifiable";
    const ICON = { valid: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', invalid: '<path d="M6 6l12 12M18 6 6 18"/>', unverifiable: '<path d="M12 7v6M12 17h.01"/><circle cx="12" cy="12" r="9"/>' };
    const TITLE = { valid: "Valid signature", invalid: "Not valid — this certificate was changed or forged", unverifiable: "Can't be verified" };
    let html = `<div class="vstate ${kind}" role="status"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${ICON[kind]}</svg><div><b>${TITLE[kind]}</b>${r.valid ? `Signed by SudoRoute (key ${esc(issuer.kid)}). Nothing has been changed.` : esc(r.reason)}</div></div>`;
    if (r.valid) {
      html += `<dl class="claims">` + row("Certificate", esc(c.cert_id)) + row("Holder", esc(c.holder) + ` <span style="color:var(--ink-3)">(student ref ${esc(c.holder_ref)})</span>`);
      if (c.type === "tuition_payment") {
        const p = c.payment;
        html += row("Payment", `${esc(p.currency)} ${fmt(p.amount, 2)} to ${esc(p.institution)}`) + row("Arrived", `${date(p.paid_on)} — due ${date(p.due)}`) +
          row("On time", p.on_time ? `<span class="pill ok">Yes, ${p.days_early} day(s) early</span>` : `<span class="pill bad">No</span>`) + row("Channel", esc(p.channel));
      } else if (c.type === "payment_history") {
        const h = c.history;
        html += row("Payments", `${h.payments} (${h.on_time} on time)`) + row("Period", `${date(h.first)} – ${date(h.last)}`) +
          row("Totals", Object.entries(h.totals).map(([k, v]) => `${esc(k)} ${fmt(v, 2)}`).join(", ")) + row("Institutions", esc(h.institutions.join(", ")));
      } else if (c.type === "proof_of_funds") {
        const f = c.funds;
        html += row("Proves", `Funds of <b>at least ${esc(f.currency)} ${fmt(f.at_least, 2)}</b> held on ${date(f.as_of)}`) + row("Purpose", esc(f.purpose)) +
          row("Valid until", esc(date(f.valid_until))) + row("Privacy", esc(f.method));
      }
      html += row("Issued", esc(c.issued_at)) + row("Audit anchor", `entry #${esc(c.audit_anchor && c.audit_anchor.seq)} · <span style="font:500 12px var(--mono)">${esc((c.audit_anchor && c.audit_anchor.hash || "").slice(0, 24))}…</span>`) +
        row("Environment", c.sandbox ? "Sandbox (competition demo)" : "Production") + `</dl>`;
    }
    $("#vout").innerHTML = html;
    if (r.valid) anchorBox(code);
  }
  // On-chain anchor: a hash of the certificate and the audit-log state, timestamped on Bitcoin via OpenTimestamps.
  async function anchorBox(code) {
    const a = await api("/api/public/anchor?code=" + encodeURIComponent(code.replace(/\s+/g, "")));
    const box = document.createElement("div"); box.className = "anchorbox";
    const label = { submitted: ["ok", "Anchored — waiting for Bitcoin confirmation"], queued: ["warn", "Being submitted"], not_submitted: ["warn", "Not submitted yet (server offline)"], disabled: ["warn", "Anchoring turned off on this server"], unknown: ["warn", "No on-chain anchor for this certificate"] }[a.status] || ["warn", a.status];
    box.innerHTML = `<h4><span class="chainic" aria-hidden="true">⛓</span> On-chain proof <span class="pill ${label[0]}">${esc(label[1])}</span></h4>
      <p>A SHA-256 fingerprint of this certificate and of SudoRoute's audit log is timestamped on the <b>Bitcoin blockchain</b> through OpenTimestamps. Only the hash goes on-chain — no money and no personal data. Anyone can check it without trusting SudoRoute.</p>
      ${a.status === "unknown" ? "" : `<dl class="claims"><dt>Certificate hash</dt><dd style="font:500 12px var(--mono)">${esc(a.cert_sha256)}</dd><dt>Anchored record</dt><dd style="font:500 12px var(--mono)">sha256 ${esc(a.digest)}</dd><dt>Audit log at issue</dt><dd>entry #${esc(a.record.audit_entries)} · <span style="font:500 12px var(--mono)">${esc((a.record.audit_head || "").slice(0, 24))}…</span></dd>${a.calendars.length ? `<dt>Calendars</dt><dd>${a.calendars.map(esc).join("<br>")}</dd>` : ""}</dl>
      <div class="anchoract"><a class="btn sm" href="/api/public/anchor/record?h=${esc(a.cert_sha256)}">Download anchor record</a>${a.has_proof ? `<a class="btn sm primary" href="/api/public/anchor/ots?h=${esc(a.cert_sha256)}">Download .ots proof</a><a class="btn sm quiet" href="https://opentimestamps.org" target="_blank" rel="noopener">Check on opentimestamps.org ↗</a>` : ""}</div>
      <small>${esc(a.how_to_check)}</small>`}`;
    $("#vout").appendChild(box);
  }
  $("#vform").addEventListener("submit", e => { e.preventDefault(); check($("#code").value); });
  if (location.hash.length > 5) { $("#code").value = decodeURIComponent(location.hash.slice(1)); check($("#code").value); }
})();
