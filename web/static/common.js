// Shared helpers: escaping, formatting, safe markdown, API calls with CSRF, theme toggle, guilloche art.
const TS = (() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 0) => (n == null || isNaN(n)) ? "—" : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const money = (n, ccy, d = 0) => `${esc(ccy)} ${fmt(n, d)}`;
  const date = iso => { if (!iso) return "—"; const d = new Date(String(iso).slice(0, 10) + "T00:00:00Z"); return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); };
  let csrf = null;

  async function api(path, body) {
    const opts = { credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      if (csrf) opts.headers["X-CSRF-Token"] = csrf;
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    let data = {};
    try { data = await r.json(); } catch (e) { data = { ok: false, error: "Unexpected response from the server." }; }
    if (r.status === 401 && !path.startsWith("/api/auth/login")) {
      location.href = "/login?expired=1";
      throw new Error("unauthenticated");
    }
    data._status = r.status;
    return data;
  }
  async function session() {
    const me = await api("/api/auth/me");
    csrf = me.csrf;
    return me;
  }
  const setCsrf = t => { csrf = t; };

  // Escape first, then apply a tiny safe subset of markdown.
  function md(text) {
    const inline = t => esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>").replace(/`([^`]+)`/g, "<code>$1</code>");
    const out = []; let list = null;
    for (const raw of String(text || "").split("\n")) {
      const line = raw.trimEnd();
      const ul = line.match(/^\s*[-•*]\s+(.*)$/), ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ul || ol) {
        const kind = ul ? "ul" : "ol";
        if (!list || list !== kind) { if (list) out.push(`</${list}>`); out.push(`<${kind}>`); list = kind; }
        out.push(`<li>${inline((ul || ol)[1])}</li>`); continue;
      }
      if (list) { out.push(`</${list}>`); list = null; }
      if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    if (list) out.push(`</${list}>`);
    return out.join("");
  }

  let toastEl = null, toastTimer = null;
  function toast(text, ms = 3800) {
    if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.appendChild(toastEl); }
    toastEl.textContent = text; toastEl.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
  }

  // ------------------------------------------------------------ theme
  const ICON_SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const ICON_MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/></svg>';
  function bindTheme() {
    $$("[data-theme-toggle]").forEach(b => {
      const paint = () => {
        const dark = document.documentElement.getAttribute("data-theme") === "dark";
        b.innerHTML = dark ? ICON_SUN : ICON_MOON;
        b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
        b.title = b.getAttribute("aria-label");
      };
      paint();
      b.addEventListener("click", () => {
        const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        try { localStorage.setItem("ts-theme", next); } catch (e) {}
        $$("[data-theme-toggle]").forEach(x => x.dispatchEvent(new Event("repaint")));
        paint();
      });
      b.addEventListener("repaint", paint);
    });
  }

  // ------------------------------------------------------------ guilloche (banknote rosette)
  function guilloche(el, opts = {}) {
    const size = 900, c = size / 2, rings = opts.rings || 3;
    let paths = "";
    for (let k = 0; k < rings; k++) {
      const R = 300 - k * 70, r = 23 + k * 6, d = 120 - k * 22, turns = r;
      let p = "";
      const steps = 2400;
      for (let i = 0; i <= steps; i++) {
        const t = (i / steps) * Math.PI * 2 * turns / Math.max(1, gcd(R, r));
        const x = c + (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t);
        const y = c + (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t);
        p += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }
      paths += `<path d="${p}" fill="none" stroke="currentColor" stroke-width="${0.6 - k * 0.1}" opacity="${0.9 - k * 0.2}"/>`;
    }
    paths += `<circle cx="${c}" cy="${c}" r="420" fill="none" stroke="currentColor" stroke-width=".8" stroke-dasharray="2 5"/>`;
    paths += `<circle cx="${c}" cy="${c}" r="438" fill="none" stroke="currentColor" stroke-width=".5"/>`;
    el.innerHTML = `<svg viewBox="0 0 ${size} ${size}" width="100%" height="100%" aria-hidden="true">${paths}</svg>`;
  }
  function gcd(a, b) { return b ? gcd(b, a % b) : a; }

  const LOGO = '<svg viewBox="0 0 34 34" aria-hidden="true"><rect width="34" height="34" rx="9" fill="var(--note)"/><path d="M9 25c0-8 16-7 16-16" stroke="var(--gold)" stroke-width="3.4" fill="none" stroke-linecap="round"/><circle cx="9" cy="25" r="3.6" fill="var(--surface)" stroke="var(--gold)" stroke-width="2"/><circle cx="25" cy="9" r="3.6" fill="var(--surface)" stroke="var(--gold)" stroke-width="2"/></svg>';

  return { $, $$, esc, fmt, money, date, api, session, setCsrf, md, toast, bindTheme, guilloche, LOGO };
})();

// Installable web app (see /sw.js). Registration failures are harmless.
if ("serviceWorker" in navigator && location.protocol !== "file:") { window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => {}); }); }
