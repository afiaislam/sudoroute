// SudoRoute motion helpers. Small on purpose: CSS does the animating, this file only decides WHEN.
// Rules: content is visible without JS; nothing animates unless something real happened;
// prefers-reduced-motion turns all of it off.
const Motion = (() => {
  const reduced = () => !document.documentElement.classList.contains("motion") ||
    (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // ------------------------------------------------------------ scroll reveals
  let io = null;
  function reveal(root = document) {
    const els = [...root.querySelectorAll("[data-reveal], [data-stagger], h2[data-station]")];
    els.forEach(el => { if (el.hasAttribute("data-stagger")) [...el.children].forEach((c, i) => c.style.setProperty("--si", i)); });
    if (reduced() || !("IntersectionObserver" in window)) { els.forEach(e => e.classList.add("in")); return; }
    // A clip-path-masked element has no visible area yet, so watch its parent instead.
    const targets = new Map();
    els.forEach(el => {
      const t = el.getAttribute("data-reveal") === "mask" ? el.parentElement : el;
      targets.set(t, (targets.get(t) || []).concat(el));
    });
    io = new IntersectionObserver(entries => entries.forEach(e => {
      if (e.isIntersecting) { (targets.get(e.target) || [e.target]).forEach(x => x.classList.add("in")); io.unobserve(e.target); }
    }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    targets.forEach((_, t) => io.observe(t));
  }

  // ------------------------------------------------------------ numbers that genuinely changed
  // Tweens from the previous real value to the new real value, then writes the exact formatted value.
  function tween(el, from, to, format, ms = 650) {
    if (from === to || from == null || reduced()) { el.textContent = format(to); return; }
    const t0 = performance.now();
    el.setAttribute("aria-label", format(to));
    const step = now => {
      const k = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      el.textContent = format(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step); else { el.textContent = format(to); el.removeAttribute("aria-label"); }
    };
    requestAnimationFrame(step);
  }

  // ------------------------------------------------------------ busy buttons during real requests
  async function busy(btn, fn) {
    if (!btn) return fn();
    btn.setAttribute("aria-busy", "true"); btn.disabled = true;
    try { return await fn(); } finally { btn.removeAttribute("aria-busy"); btn.disabled = false; }
  }

  // ------------------------------------------------------------ dialogs: animate out before closing
  function closeDialog(d) {
    if (reduced() || !d.open) { d.close(); return; }
    d.classList.add("closing");
    setTimeout(() => { d.classList.remove("closing"); d.close(); }, 140);
  }

  // ------------------------------------------------------------ pointer highlight on proof cards
  function pointer(root = document) {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    root.querySelectorAll(".proofcard").forEach(c => c.addEventListener("pointermove", e => {
      const r = c.getBoundingClientRect();
      c.style.setProperty("--mx", `${e.clientX - r.left}px`); c.style.setProperty("--my", `${e.clientY - r.top}px`);
    }));
  }

  // ------------------------------------------------------------ portal page change
  function enter(el) {
    if (reduced() || !el) return;
    el.classList.remove("enter"); void el.offsetWidth; el.classList.add("enter");
  }

  return { reveal, tween, busy, closeDialog, pointer, enter, reduced };
})();
