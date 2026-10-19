// Public site v9: announcement bar, newsletter, help-center search, contact form, pricing calculator.
(() => {
  const { $, $$, api, esc } = TS;
  const store = { get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };

  // ---- announcement bar (dismissible, remembered)
  const an = $("#announce");
  if (an) {
    if (store.get("sr-announce-off") === "1") an.remove();
    else {
      document.body.classList.add("has-announce");
      const past = () => document.body.classList.toggle("past-an", window.scrollY > 40);
      past(); window.addEventListener("scroll", past, { passive: true });
      $("[data-announce-close]", an).addEventListener("click", () => {
        an.classList.add("bye"); store.set("sr-announce-off", "1");
        setTimeout(() => { an.remove(); document.body.classList.remove("has-announce"); }, 280);
      });
    }
  }

  // ---- mark the current page in the navigation
  const here = location.pathname.replace(/\/+$/, "") || "/";
  $$("#mainnav [data-nav]").forEach(a => {
    if (a.dataset.nav.split(" ").includes(here)) a.setAttribute("aria-current", "page");
  });

  // ---- rolling-digit counters (each digit spins into place when it scrolls into view)
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const rolls = $$("[data-roll]");
  const build = el => {
    const text = el.textContent.trim();
    el.setAttribute("aria-label", text);
    el.innerHTML = [...text].map((ch, i) => /\d/.test(ch)
      ? `<span class="rd" aria-hidden="true" style="--d:${ch};--i:${i}"><span class="rs">${"0123456789".split("").map(n => `<span>${n}</span>`).join("")}</span></span>`
      : `<span class="rc" aria-hidden="true">${ch === " " ? "&nbsp;" : esc(ch)}</span>`).join("");
    el.classList.add("rolled-ready");
  };
  if (!reduce && "IntersectionObserver" in window) {
    rolls.forEach(build);
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("roll-in"); io.unobserve(e.target); } }), { threshold: 0.4 });
    rolls.forEach(el => io.observe(el));
  }

  // ---- "check / smarter" panels rise one after another
  const s3 = $$("[data-s3]");
  if (s3.length && "IntersectionObserver" in window && !reduce) {
    s3.forEach((el, i) => el.style.setProperty("--k", i));
    const io2 = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("s3-in"); io2.unobserve(e.target); } }), { threshold: 0.25 });
    s3.forEach(el => io2.observe(el));
  } else s3.forEach(el => el.classList.add("s3-in"));

  // ---- scroll motion (public pages): progress line, drifting photos, screenshots that settle, rising blocks
  (() => {
    if (typeof Motion === "undefined" || Motion.reduced() || !document.querySelector(".topnav")) return;
    const bar = document.createElement("div"); bar.className = "scrollbar-p"; bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
    // photos drift slower than the page (subtle depth); never more than ~40px
    $$(".hero-photo, .photoband > img, .ctaband > img").forEach(img => img.setAttribute("data-parallax", img.classList.contains("hero-photo") ? ".12" : ".08"));
    const par = $$("[data-parallax]"), browser = $(".shots .browser");
    // blocks with no animation of their own rise into view
    const rise = $$(".page9 .card9, .page9 details.hq, .ctaband-copy h2").filter(e => !e.closest("[data-reveal],[data-stagger]") && !e.hasAttribute("data-reveal"));
    rise.forEach(e => e.classList.add("sr-rise"));
    if ("IntersectionObserver" in window && rise.length) {
      const io = new IntersectionObserver(es => es.forEach(x => { if (x.isIntersecting) { x.target.classList.add("in"); io.unobserve(x.target); } }), { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
      rise.forEach(e => io.observe(e));
    } else rise.forEach(e => e.classList.add("in"));
    let ticking = false;
    const frame = () => {
      ticking = false;
      const y = window.scrollY, vh = window.innerHeight, max = document.documentElement.scrollHeight - vh;
      bar.style.transform = `scaleX(${max > 0 ? Math.min(1, y / max) : 0})`;
      par.forEach(img => {
        const r = img.parentElement.getBoundingClientRect();
        if (r.bottom < -100 || r.top > vh + 100) return;
        const k = +img.dataset.parallax, off = (r.top + r.height / 2 - vh / 2) * -k;
        img.style.transform = `translate3d(0, ${Math.max(-40, Math.min(40, off)).toFixed(1)}px, 0) scale(1.08)`;
      });
      if (browser) {
        const r = browser.getBoundingClientRect(), p = Math.max(0, Math.min(1, (vh - r.top) / (vh * 0.75)));
        browser.style.setProperty("--tilt", ((1 - p) * 10).toFixed(2) + "deg");
        browser.style.setProperty("--sc", (0.94 + p * 0.06).toFixed(3));
      }
    };
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(frame); } };
    window.addEventListener("scroll", onScroll, { passive: true }); window.addEventListener("resize", onScroll); frame();
  })();

  // ---- "Get started" popup: choose sign in or create account (only the home-page judge button signs in by itself)
  (() => {
    const t = (k, f) => (window.I18N ? I18N.t(k, f) : f);
    let dlg = null, last = null;
    const build = () => {
      dlg = document.createElement("div");
      dlg.className = "authpop"; dlg.hidden = true;
      dlg.innerHTML = `<div class="ap-back" data-ap-close></div>
        <div class="ap-card" role="dialog" aria-modal="true" aria-labelledby="ap-title">
          <button type="button" class="ap-x" data-ap-close aria-label="Close">×</button>
          <h2 id="ap-title">${t("ap.title", "Welcome to SudoRoute")}</h2>
          <p class="ap-sub">${t("ap.sub", "Sign in, or create a free sandbox account. No real money moves.")}</p>
          <div class="ap-grid">
            <div class="ap-role"><span class="ap-ic">🎓</span><b>${t("ap.student", "I'm a student")}</b><small>${t("ap.studentd", "Pay your own tuition, with checks at every step.")}</small>
              <a class="btn accent" href="/register?role=student">${t("ap.create", "Create account")}</a><a class="btn quiet" href="/login?role=student">${t("cta.signin", "Sign in")}</a></div>
            <div class="ap-role"><span class="ap-ic">👪</span><b>${t("ap.guardian", "I'm a parent or guardian")}</b><small>${t("ap.guardiand", "Approve payments and support a student.")}</small>
              <a class="btn accent" href="/register?role=guardian">${t("ap.create", "Create account")}</a><a class="btn quiet" href="/login?role=guardian">${t("cta.signin", "Sign in")}</a></div>
          </div>
        </div>`;
      document.body.appendChild(dlg);
      dlg.addEventListener("click", e => { if (e.target.closest("[data-ap-close]")) close(); });
      document.addEventListener("keydown", e => { if (!dlg.hidden && e.key === "Escape") close(); });
    };
    const open = () => {
      if (!dlg) build();
      last = document.activeElement; dlg.hidden = false;
      requestAnimationFrame(() => dlg.classList.add("in"));
      document.documentElement.classList.add("ap-lock");
      dlg.querySelector(".ap-role .btn").focus({ preventScroll: true });
    };
    const close = () => {
      dlg.classList.remove("in"); document.documentElement.classList.remove("ap-lock");
      setTimeout(() => { dlg.hidden = true; }, 200);
      if (last) last.focus({ preventScroll: true });
    };
    document.addEventListener("click", e => { const a = e.target.closest("[data-auth]"); if (a) { e.preventDefault(); open(); } });
  })();

  // ---- newsletter (footer)
  $$("[data-newsletter]").forEach(f => f.addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $(".nlmsg", f), btn = $("button", f), email = $("input[type=email]", f).value.trim();
    msg.className = "nlmsg";
    if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(email)) { msg.textContent = "Please enter a valid e-mail address."; msg.classList.add("bad"); return; }
    btn.disabled = true;
    const r = await api("/api/public/newsletter", { email, website: $(".hp", f).value, lang: I18N.lang }).catch(() => ({ ok: false }));
    btn.disabled = false;
    if (r.ok) { msg.textContent = r.already ? "You're already subscribed — thank you!" : "Subscribed ✓ — see you next month."; msg.classList.add("ok"); f.classList.add("done"); $("input[type=email]", f).value = ""; }
    else { msg.textContent = r.error || "Something went wrong. Try again."; msg.classList.add("bad"); }
  }));

  // ---- smooth open/close for <details> accordions
  $$("details.hq").forEach(d => {
    const s = $("summary", d), body = $(".ha", d);
    s.addEventListener("click", e => {
      e.preventDefault();
      if (d.open) {
        const h = body.scrollHeight; body.style.height = h + "px"; requestAnimationFrame(() => { body.style.height = "0px"; });
        body.addEventListener("transitionend", () => { d.open = false; body.style.height = ""; }, { once: true });
      } else {
        d.open = true; const h = body.scrollHeight; body.style.height = "0px";
        requestAnimationFrame(() => { body.style.height = h + "px"; });
        body.addEventListener("transitionend", () => { body.style.height = ""; }, { once: true });
      }
    });
  });

  // ---- help-center search
  const q = $("#hq");
  if (q) {
    const items = $$("details.hq"), groups = $$(".hgroup"), none = $("#hnone"), count = $("#hcount");
    const run = () => {
      const terms = q.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      let shown = 0;
      items.forEach(d => {
        const text = d.textContent.toLowerCase();
        const hit = terms.every(t => text.includes(t));
        d.hidden = !hit; if (hit) shown++;
        if (terms.length && hit && !d.open) d.open = true;
        if (!terms.length) d.open = false;
      });
      groups.forEach(g => {
        let n = g.nextElementSibling, any = false;
        while (n && !n.classList.contains("hgroup")) { if (n.matches("details") && !n.hidden) any = true; n = n.nextElementSibling; }
        g.hidden = !any;
      });
      none.hidden = shown > 0;
      count.textContent = terms.length ? `${shown} result${shown === 1 ? "" : "s"}` : "";
    };
    q.addEventListener("input", run);
    if (location.hash === "#faq") setTimeout(() => $("#faq").scrollIntoView({ behavior: "smooth" }), 200);
  }

  // ---- contact form
  const cf = $("#ctform");
  if (cf) {
    let topic = "general", rating = null;
    const topics = $$("[data-topic]", cf), box = $("#ratingbox");
    const pick = t => {
      topic = t; topics.forEach(b => b.setAttribute("aria-checked", String(b.dataset.topic === t)));
      box.hidden = t !== "feedback";
    };
    topics.forEach(b => b.addEventListener("click", () => pick(b.dataset.topic)));
    $$("[data-r]", cf).forEach(b => b.addEventListener("click", () => {
      rating = +b.dataset.r; $$("[data-r]", cf).forEach(x => x.classList.toggle("on", +x.dataset.r <= rating));
    }));
    const want = new URLSearchParams(location.search).get("topic");
    if (want && topics.some(b => b.dataset.topic === want)) pick(want);
    cf.addEventListener("submit", async e => {
      e.preventDefault();
      $$(".field", cf).forEach(f => f.classList.remove("bad"));
      const btn = $("button[type=submit]", cf);
      const body = { name: $("#ct-name").value, email: $("#ct-email").value, message: $("#ct-msg").value, topic, website: $(".hp", cf).value };
      if (rating) body.rating = rating;
      const r = await Motion.busy(btn, () => api("/api/public/contact", body)).catch(() => ({ ok: false }));
      if (r.ok) {
        cf.classList.add("sent"); $(".ctdone", cf).hidden = false;
      } else if (r.fields) {
        Object.entries(r.fields).forEach(([k, v]) => { const f = $(`[data-f="${k}"]`, cf); if (f) { f.classList.add("bad"); $(".err", f).textContent = v; } });
      } else TS.toast(r.error || "Could not send. Try again.");
    });
    $("[data-ct-again]", cf).addEventListener("click", () => {
      cf.reset(); rating = null; $$("[data-r]", cf).forEach(x => x.classList.remove("on"));
      cf.classList.remove("sent"); $(".ctdone", cf).hidden = true; pick("general");
    });
  }

  // ---- pricing calculator (illustrative sandbox figures)
  const amt = $("#amt");
  if (amt) {
    const fmt = n => "USD " + Math.round(n).toLocaleString("en-US");
    const calc = () => {
      const a = +amt.value;
      const bank = a * 0.025 + 30, fee = Math.min(25, Math.max(3, a * 0.005)), sr = a * 0.008 + 5 + fee;
      const max = Math.max(bank, sr);
      $("#amtout").textContent = fmt(a);
      $("#c-bank").textContent = fmt(bank); $("#c-sr").textContent = fmt(sr);
      $("#bar-bank").style.width = (bank / max * 100) + "%"; $("#bar-sr").style.width = (sr / max * 100) + "%";
      $("#save").innerHTML = `You keep about <b>${fmt(bank - sr)}</b> — of which SudoRoute's own fee is ${fmt(fee)} (waived in the pilot).`;
      amt.style.setProperty("--p", ((a - amt.min) / (amt.max - amt.min) * 100) + "%");
    };
    amt.addEventListener("input", calc); calc();
  }
})();
