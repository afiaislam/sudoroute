// Sandbox phone. In production SudoRoute sends one-time codes by SMS through a licensed SMS
// gateway. The sandbox never sends real texts, so this module plays the role of the user's phone:
// a phone button in the top bar, and a phone-style notification that slides in the moment a code
// is "texted". "Use this code" fills the matching code box, wherever it is on the page.
const Phone = (() => {
  const { $, esc } = TS;
  let who = "student", key = "", items = [], seen = new Set(), number = "", quiet = new Set();
  const idOf = m => `${m.proposal_id}`;
  const codeOf = m => (String(m.text).match(/\b(\d{6})\b/) || [])[1] || "";
  const reduce = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function save() { try { sessionStorage.setItem(key, JSON.stringify([...seen])); } catch (e) { /* storage unavailable */ } }
  function load() { try { return new Set(JSON.parse(sessionStorage.getItem(key) || "[]")); } catch (e) { return new Set(); } }

  const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2.5" width="12" height="19" rx="3"/><path d="M10.5 18.5h3"/></svg>';

  function mount(role, userId, phone) {
    who = role; key = `sr-phone-${userId}`; seen = load(); number = phone || "";
    if ($("#phonebtn")) return;
    const right = $(".topbar .right"), anchor = $("[data-theme-toggle]", right);
    const wrap = document.createElement("div");
    wrap.className = "phone-dd";
    wrap.innerHTML = `<button class="iconbtn phonebtn" id="phonebtn" type="button" aria-expanded="false" aria-controls="phonepanel" title="Your phone (sandbox): one-time codes arrive here">${ICON}<span class="pbadge" hidden>0</span></button>
      <div class="phonepanel" id="phonepanel" role="dialog" aria-label="Sandbox phone">
        <div class="phead"><b>Your phone</b><small>${esc(number)}</small></div>
        <p class="pnote">Demo mode: no real SMS is sent. In a live deployment this exact message goes to your registered phone by SMS.</p>
        <div class="plist"></div></div>`;
    right.insertBefore(wrap, anchor);
    const btn = $("#phonebtn", wrap);
    btn.addEventListener("click", e => { e.stopPropagation(); const open = !wrap.classList.contains("open"); wrap.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); if (open) { items.forEach(m => seen.add(idOf(m))); save(); badge(); } });
    document.addEventListener("click", e => { if (!e.target.closest(".phone-dd")) { wrap.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); } });
    wrap.addEventListener("click", e => { const u = e.target.closest("[data-phone-use]"); if (u) { use(u.dataset.pid, u.dataset.phoneUse); wrap.classList.remove("open"); } });
    document.addEventListener("keydown", e => { if (e.key === "Escape") wrap.classList.remove("open"); });
  }

  function badge() {
    const b = $("#phonebtn .pbadge"); if (!b) return;
    const n = items.filter(m => !seen.has(idOf(m)) && !quiet.has(idOf(m))).length;
    b.hidden = !n; b.textContent = n;
  }

  function list() {
    const box = $("#phonepanel .plist"); if (!box) return;
    box.innerHTML = items.length ? items.slice().reverse().map(m => {
      const c = codeOf(m);
      return `<div class="pmsg"><div class="pfrom">SudoRoute <small>to ${esc(m.to)}</small></div><div>${esc(m.text).replace(/(\d{6})/, "<b>$1</b>")}</div>${!c ? "" : quiet.has(idOf(m)) ? `<small class="pwait">Usable after your guardian approves.</small>` : `<button type="button" class="btn sm primary" data-phone-use="${c}" data-pid="${esc(m.proposal_id)}">Use this code</button>`}</div>`;
    }).join("") : `<p class="empty">No messages yet. When a payment needs your approval, its one-time code arrives here.</p>`;
  }

  // Called after every state refresh with the latest inbox. `held` = proposal ids whose code can't be
  // used yet (still waiting for the guardian): their message stays quiet until it becomes usable.
  function sync(inbox, held) {
    items = (inbox || []).slice();
    quiet = new Set([...(held || [])].map(String));
    list();
    const fresh = items.filter(m => !seen.has(idOf(m)) && !quiet.has(idOf(m)));
    badge();
    if (fresh.length) notify(fresh[fresh.length - 1]);
  }

  function notify(m) {
    const old = $("#phonetoast"); if (old) old.remove();
    const c = codeOf(m);
    const t = document.createElement("div");
    t.id = "phonetoast"; t.className = "phonetoast"; t.setAttribute("role", "status"); t.setAttribute("aria-live", "polite");
    t.innerHTML = `<div class="ptop"><span class="papp">${ICON}</span><b>Messages</b><span>now</span><button type="button" class="px" aria-label="Dismiss">×</button></div>
      <div class="pbody"><b>SudoRoute</b><p>${esc(m.text).replace(/(\d{6})/, "<strong>$1</strong>")}</p></div>
      <div class="pact">${c ? `<button type="button" class="btn sm primary" data-use>Use this code</button>` : ""}<span>Sandbox phone · ${esc(m.to)}</span></div>`;
    document.body.appendChild(t);
    if (!reduce()) requestAnimationFrame(() => t.classList.add("in")); else t.classList.add("in");
    const close = () => { seen.add(idOf(m)); save(); badge(); t.classList.remove("in"); setTimeout(() => t.remove(), reduce() ? 0 : 260); };
    t.querySelector(".px").addEventListener("click", close);
    const u = t.querySelector("[data-use]");
    if (u) u.addEventListener("click", () => { use(m.proposal_id, c); close(); });
  }

  // Put the code into the matching code box; open the right page first if needed.
  function use(pid, code) {
    seen.add(String(pid)); save(); badge();
    const find = () => {
      const help = document.querySelector(`.otphelp[data-otp-for="${CSS.escape(pid)}"]`);
      const input = help && help.closest(".card")?.querySelector("form.otp input");
      return input && !input.disabled ? input : null;
    };
    let input = find();
    if (!input) location.hash = who === "guardian" ? "approvals" : "payments";
    let tries = 0;
    const tick = () => {
      input = find();
      if (input) { input.value = code; input.scrollIntoView({ block: "center", behavior: reduce() ? "auto" : "smooth" }); input.focus({ preventScroll: true }); input.classList.add("filled"); setTimeout(() => input.classList.remove("filled"), 1200); return; }
      if (++tries < 30) setTimeout(tick, 100);
      else TS.toast(who === "student" ? "This code can be used once your guardian has approved." : "That request is no longer waiting for you.");
    };
    tick();
  }

  // Use the newest usable code (judge tour: one click instead of copy and paste).
  function useLatest() {
    const m = items.slice().reverse().find(x => codeOf(x) && !quiet.has(idOf(x)));
    if (!m) { TS.toast("No code is waiting — ask the agent to prepare a payment first."); return false; }
    const t = document.getElementById("phonetoast"); if (t) t.remove();
    use(m.proposal_id, codeOf(m)); return true;
  }

  return { mount, sync, use, useLatest };
})();
