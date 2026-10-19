// Shared portal chrome: navigation, routing, sandbox clock, sign-out, password re-entry dialog.
const Portal = (() => {
  const { $, $$, esc, api, toast } = TS;
  const ICONS = {
    overview: '<path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z"/>',
    assistant: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 10h8M8 13h5"/>',
    payments: '<path d="M3 7h18v10H3z"/><path d="M3 11h18M7 15h3"/>',
    invoices: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7M9 16h5"/>',
    insights: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    security: '<path d="M12 3 20 6v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    approvals: '<path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/>',
    activity: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
    certs: '<path d="M5 3h14v12l-7 6-7-6z"/><path d="m9 10 2 2 4-4"/>',
    tour: '<path d="M5 3v18l14-9z"/>',
    funds: '<path d="M12 3v18M17 7.5c0-1.9-2.2-3-5-3s-5 1.1-5 3 2.2 2.6 5 3 5 1.2 5 3.2-2.2 3.3-5 3.3-5-1.3-5-3.3"/>',
  };
  const icon = k => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[k] || ""}</svg>`;

  function init({ items, render, onClock }) {
    $$("[data-logo]").forEach(el => { el.innerHTML = TS.LOGO; });
    TS.bindTheme();
    const label = i => I18N.t(`p.${i.id}`, i.label);
    const paintNav = () => {
      const counts = {}; $$("[data-count]").forEach(c => { counts[c.dataset.count] = c.textContent; });
      let lastGroup = null;
      $("#sidenav").innerHTML = `<span class="ind" aria-hidden="true"></span>` + items.map(i => {
        const g = i.group && i.group !== lastGroup ? `<p class="grp">${esc(I18N.t("g." + i.group.toLowerCase(), i.group))}</p>` : "";
        lastGroup = i.group || lastGroup;
        return g + `<a href="#${i.id}" data-view="${i.id}">${icon(i.icon || i.id)}<span>${esc(label(i))}</span><span class="count" data-count="${i.id}" ${counts[i.id] ? "" : "hidden"}>${esc(counts[i.id] || "")}</span></a>`;
      }).join("");
    };
    paintNav();
    const moveInd = (animate = true) => {
      const nav = $("#sidenav"), ind = $("#sidenav .ind"), a = $('#sidenav a[aria-current="page"]');
      if (!ind || !a) return;
      if (!animate) ind.style.transition = "none";
      ind.style.transform = `translateY(${a.offsetTop}px)`; ind.style.height = `${a.offsetHeight}px`;
      nav.classList.add("has-ind");
      if (!animate) { void ind.offsetWidth; ind.style.transition = ""; }
    };
    const right = $(".topbar .right");
    right.insertAdjacentHTML("afterbegin", `<span class="fxbadge hide-sm" id="fxbadge" title="Exchange rates"><i></i><span>Rates</span></span>`);
    $("[data-theme-toggle]", right).insertAdjacentHTML("beforebegin", `<span data-lang-picker></span>`);
    I18N.pickers(); I18N.apply(document);
    api("/api/public/fx").then(fx => {
      const b = $("#fxbadge"); if (!b || !fx.source) return;
      b.classList.toggle("live", fx.source === "LIVE");
      b.querySelector("span").textContent = `${fx.source === "LIVE" ? "Live rates" : "Reference rates"} · ${new Date(fx.as_of).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`;
      b.title = `${fx.source === "LIVE" ? "Live" : "Reference snapshot of real"} exchange rates from ${fx.provider}, ${fx.as_of}`;
    });
    const side = $("#side"), mb = $("#menubtn");
    mb.addEventListener("click", () => { const o = side.classList.toggle("open"); mb.setAttribute("aria-expanded", String(o)); });
    const go = () => {
      const id = (location.hash.slice(1) || items[0].id).split("?")[0];
      const item = items.find(i => i.id === id) || items[0];
      $$("#sidenav a").forEach(a => { if (a.dataset.view === item.id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      moveInd(!!$("#sidenav.has-ind"));
      Motion.enter($("#view"));
      $("#viewtitle").textContent = label(item);
      document.title = `${label(item)} — SudoRoute`;
      side.classList.remove("open"); mb.setAttribute("aria-expanded", "false");
      render(item.id);
    };
    window.addEventListener("hashchange", go);
    I18N.onChange(() => { paintNav(); go(); });
    window.addEventListener("resize", () => moveInd(false));
    $("#logout").setAttribute("data-i18n", "p.signout"); I18N.apply($(".topbar"));
    const meb = $("#mebtn"), mem = $(".me-dd");
    if (meb) {
      meb.addEventListener("click", e => { e.stopPropagation(); const o = mem.classList.toggle("open"); meb.setAttribute("aria-expanded", String(o)); });
      document.addEventListener("click", e => { if (!e.target.closest(".me-dd")) { mem.classList.remove("open"); meb.setAttribute("aria-expanded", "false"); } });
      document.addEventListener("keydown", e => { if (e.key === "Escape") { mem.classList.remove("open"); meb.setAttribute("aria-expanded", "false"); } });
      $$(".memenu a").forEach(a => a.addEventListener("click", () => mem.classList.remove("open")));
    }
    $("#logout").addEventListener("click", async () => { await api("/api/auth/logout", {}); location.href = "/"; });
    $$("[data-adv]").forEach(b => b.addEventListener("click", async () => {
      const r = await api("/api/sandbox/advance", { days: +b.dataset.adv });
      if (r.sim_date) { toast(`Sandbox date is now ${TS.date(r.sim_date)}.`); onClock && onClock(r); }
    }));
    return go;
  }

  function setCount(id, n) {
    const el = $(`[data-count="${id}"]`);
    if (!el) return;
    el.hidden = !n; el.textContent = n || "";
  }

  function ai(st) {
    const el = $("#aistat"); if (!el || !st) return;
    el.classList.toggle("on", !!st.enabled);
    el.querySelector("span").textContent = st.enabled ? `Gemini · ${st.model}` : "Rule engine";
    el.title = st.enabled ? (st.last_error ? `Last issue: ${st.last_error}` : "Gemini writes replies; numbers are checked by SudoRoute.") : "Add GEMINI_API_KEY to .env to enable Gemini.";
  }

  function askPassword(title, text) {
    return new Promise(resolve => {
      const d = $("#pwdialog");
      $("#pwtitle").textContent = title; $("#pwtext").textContent = text; $("#pwinput").value = "";
      const done = v => { Motion.closeDialog(d); cleanup(); resolve(v); };
      const onSubmit = e => { e.preventDefault(); done($("#pwinput").value); };
      const onCancel = e => { if (e && e.type === "cancel") e.preventDefault(); done(null); };
      const cleanup = () => { $("#pwform").removeEventListener("submit", onSubmit); $("#pwcancel").removeEventListener("click", onCancel); d.removeEventListener("cancel", onCancel); };
      $("#pwform").addEventListener("submit", onSubmit);
      $("#pwcancel").addEventListener("click", onCancel);
      d.addEventListener("cancel", onCancel);
      d.showModal(); $("#pwinput").focus();
    });
  }

  // Decorative photos vanish quietly if they can't load; the designed gradient behind them stays.
  function photos(root) {
    root.querySelectorAll("img").forEach(img => {
      if (img.complete && img.naturalWidth === 0 && img.src && !img.src.startsWith("data:")) img.remove();
      else img.addEventListener("error", () => img.remove(), { once: true });
    });
  }
  // Big avatar with a camera button: resize in the browser (256 px, JPEG), upload, server re-checks the file type.
  function photoEditor(user, onChange) {
    const n = Cards.el(`<div class="bigavatar"><span class="avatar"></span>
      <label title="Change photo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>
      <span class="sr">Change profile photo</span><input type="file" accept="image/png,image/jpeg,image/webp"></label></div>`);
    avatar(n.querySelector(".avatar"), user);
    n.querySelector("input").addEventListener("change", e => {
      const f = e.target.files[0]; if (!f) return;
      if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { toast("Choose a JPG, PNG or WebP photo."); return; }
      const img = new Image(), url = URL.createObjectURL(f);
      img.onload = async () => {
        const side = Math.min(img.width, img.height), c = document.createElement("canvas"); c.width = c.height = 256;
        c.getContext("2d").drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 256, 256);
        URL.revokeObjectURL(url);
        const r = await api("/api/profile/photo", { data_url: c.toDataURL("image/jpeg", 0.86) });
        toast(r.ok ? "Profile photo updated." : r.error);
        if (r.ok) onChange(r.photo);
      };
      img.onerror = () => toast("That file couldn't be read as an image.");
      img.src = url;
    });
    return n;
  }
  async function removePhoto(onChange) { const r = await api("/api/profile/photo", { remove: true }); toast(r.ok ? "Photo removed." : r.error); if (r.ok) onChange(null); }
  // Profile photo if the user uploaded one, initials otherwise.
  function avatar(el, user) {
    if (!el || !user) return;
    el.classList.toggle("has-photo", !!user.photo);
    el.innerHTML = user.photo ? `<img src="${esc(user.photo)}" alt="">` : esc(initials(user.name));
  }
  function initials(name) { return String(name || "?").split(" ").filter(Boolean).slice(0, 2).map(x => x[0]).join("").toUpperCase(); }

  function auditList(entries) {
    if (!entries.length) return `<p class="empty">Nothing recorded yet.</p>`;
    return `<ul class="list auditlist">${entries.slice().reverse().map(e => `<li><div class="grow"><b>${esc(e.event.replace(/_/g, " "))}</b><span class="h">#${e.seq} · ${esc(e.actor)} · ${esc((e.sim_time || e.ts || "").slice(0, 10))} · hash ${esc(e.hash.slice(0, 12))}…</span></div></li>`).join("")}</ul>`;
  }

  function changePasswordForm() {
    const n = Cards.el(`<form class="pwchange" novalidate>
      <div class="field"><label for="cp-cur">Current password</label><input class="input" id="cp-cur" type="password" autocomplete="current-password"></div>
      <div class="field"><label for="cp-new">New password</label><input class="input" id="cp-new" type="password" autocomplete="new-password"><span class="hint">At least 10 characters with a letter and a number. Other signed-in devices will be signed out.</span></div>
      <button class="btn" type="submit">Change password</button><div class="out" style="margin-top:12px"></div></form>`);
    n.addEventListener("submit", async e => {
      e.preventDefault();
      const r = await api("/api/auth/password", { current: n.querySelector("#cp-cur").value, new: n.querySelector("#cp-new").value });
      n.querySelector(".out").innerHTML = `<div class="alert ${r.ok ? "ok" : "bad"}">${esc(r.ok ? `Password changed. ${r.revoked_sessions} other session(s) signed out.` : r.error)}</div>`;
      if (r.ok) n.reset();
    });
    return n;
  }

  // Pilot feedback: real testers rate SudoRoute; only totals are ever published (/accuracy#pilot).
  function feedbackPanel() {
    const n = document.createElement("section");
    n.className = "panel fbpanel";
    const stars = name => `<div class="fbstars" role="radiogroup" aria-label="${name}">${[1, 2, 3, 4, 5].map(i => `<label><input type="radio" name="${name}" value="${i}" required><span>${i}</span></label>`).join("")}</div>`;
    n.innerHTML = `<h3>Help us improve SudoRoute <small>pilot feedback</small></h3>
      <form class="fbform"><p>How useful would SudoRoute be for paying tuition?</p>${stars("useful")}
        <p>How much would you trust it with a real payment?</p>${stars("trust")}
        <p>Would you use it for a real tuition payment?</p><div class="fbwould">${["yes", "maybe", "no"].map(v => `<label><input type="radio" name="would_use" value="${v}" required><span>${v[0].toUpperCase() + v.slice(1)}</span></label>`).join("")}</div>
        <textarea class="input" name="comment" rows="2" maxlength="500" placeholder="Anything we should change? (optional, private)"></textarea>
        <button class="btn primary" type="submit">Send feedback</button><small>Only totals are published — never your name or comment.</small></form>`;
    const f = n.querySelector("form");
    f.addEventListener("submit", async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f).entries());
      const r = await Motion.busy(f.querySelector("button"), () => api("/api/feedback", d));
      if (r.ok === false) { toast(r.error); return; }
      f.innerHTML = `<p class="fbthanks">✓ Thank you! Your answer is counted in the pilot results on the <a href="/accuracy#pilot">proof page</a>.</p>`;
    });
    return n;
  }

  return { init, setCount, feedbackPanel, ai, askPassword, initials, avatar, photos, photoEditor, removePhoto, auditList, changePasswordForm, icon };
})();
