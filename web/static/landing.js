// Public pages: navigation (transparent → solid, pointer highlight, dropdowns, mobile menu),
// screenshot tabs, scroll reveals. Everything degrades to plain links without JavaScript.
(() => {
  const { $, $$ } = TS;
  $$("[data-logo]").forEach(el => { el.innerHTML = TS.LOGO; });
  TS.bindTheme();

  // A photo that cannot load (offline, blocked) simply disappears; the designed background stays.
  $$("img").forEach(img => {
    const fail = () => { img.style.display = "none"; img.parentElement.classList.add("nophoto"); };
    if (img.complete && img.naturalWidth === 0 && img.src) fail(); else img.addEventListener("error", fail, { once: true });
  });

  const top = $("#topnav"), nav = $("#mainnav"), menu = $("#menubtn");
  const overPhoto = document.body.classList.contains("home");
  const solid = () => top && top.classList.toggle("solid", !overPhoto || window.scrollY > 24 || nav.classList.contains("open"));
  solid();
  window.addEventListener("scroll", solid, { passive: true });

  // Sliding highlight that follows the pointer across the menu items.
  const hl = nav && $(".hl", nav);
  if (hl && window.matchMedia("(hover: hover)").matches) {
    let shown = false;
    $$(".navlink", nav).forEach(a => a.addEventListener("pointerenter", () => {
      const r = a.getBoundingClientRect(), n = nav.getBoundingClientRect();
      if (!shown) { hl.style.transition = "opacity var(--t-control) var(--ease-out)"; void hl.offsetWidth; }
      hl.style.transform = `translateX(${r.left - n.left}px)`; hl.style.width = `${r.width}px`; hl.style.opacity = "1";
      if (!shown) { requestAnimationFrame(() => { hl.style.transition = ""; }); shown = true; }
    }));
    nav.addEventListener("pointerleave", () => { hl.style.opacity = "0"; shown = false; });
  }

  // Dropdowns: click or keyboard on every device, hover on devices with a pointer.
  const dds = $$(".dd");
  const close = except => dds.forEach(d => { if (d !== except) { d.classList.remove("open"); $(".navlink", d).setAttribute("aria-expanded", "false"); } });
  dds.forEach(d => {
    const btn = $(".navlink", d);
    const set = open => { close(d); d.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); };
    btn.addEventListener("click", () => set(!d.classList.contains("open")));
    if (window.matchMedia("(hover: hover) and (min-width: 921px)").matches) {
      let t; d.addEventListener("pointerenter", () => { clearTimeout(t); set(true); });
      d.addEventListener("pointerleave", () => { t = setTimeout(() => set(false), 140); });
    }
  });
  document.addEventListener("click", e => { if (!e.target.closest(".dd")) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { close(); if (nav) nav.classList.remove("open"); } });

  if (menu) menu.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    menu.setAttribute("aria-expanded", String(open)); solid();
  });
  $$("#mainnav a, .footer4 a").forEach(a => a.addEventListener("click", () => {
    close(); if (nav) nav.classList.remove("open"); if (menu) menu.setAttribute("aria-expanded", "false"); solid();
  }));

  // Screenshot tabs with a sliding selection and arrow-key support.
  const tabs = $$(".shot-tabs [role=tab]"), ind = $(".shot-tabs .tab-ind");
  const moveInd = t => { if (ind && t) { ind.style.transform = `translate(${t.offsetLeft - 5}px, ${t.offsetTop - 5}px)`; ind.style.width = `${t.offsetWidth}px`; ind.style.height = `${t.offsetHeight}px`; ind.style.left = "5px"; ind.style.top = "5px"; ind.style.bottom = "auto"; } };
  const select = t => {
    tabs.forEach(x => { const on = x === t; x.setAttribute("aria-selected", String(on)); x.tabIndex = on ? 0 : -1; $("#shot-" + x.dataset.shot).hidden = !on; });
    moveInd(t);
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => select(t));
    t.addEventListener("keydown", e => {
      const k = { ArrowRight: 1, ArrowLeft: -1 }[e.key]; if (!k) return;
      e.preventDefault(); const n = tabs[(i + k + tabs.length) % tabs.length]; n.focus(); select(n);
    });
  });
  if (tabs.length) { select(tabs[0]); window.addEventListener("resize", () => moveInd($(".shot-tabs [aria-selected=true]"))); I18N.onChange(() => moveInd($(".shot-tabs [aria-selected=true]"))); }

  // Demo video chapters: jump, and highlight the chapter that is playing.
  const vid = $("#demovideo"), chs = $$(".chapters [data-t]");
  if (vid && chs.length) {
    chs.forEach(b => b.addEventListener("click", () => { vid.currentTime = +b.dataset.t; vid.play().catch(() => {}); }));
    vid.addEventListener("timeupdate", () => {
      let on = chs[0]; chs.forEach(b => { if (vid.currentTime >= +b.dataset.t) on = b; });
      if (!on.classList.contains("on")) {
        chs.forEach(b => b.classList.toggle("on", b === on));
        const box = on.parentNode;  // keep the playing chapter visible inside the list, without moving the page
        if (box.scrollHeight > box.clientHeight) {
          const top = on.offsetTop, bottom = top + on.offsetHeight;
          if (top < box.scrollTop || bottom > box.scrollTop + box.clientHeight) box.scrollTop = top - box.clientHeight / 2 + on.offsetHeight / 2;
        }
      }
    });
  }

  Motion.reveal();
  Motion.pointer();
})();
