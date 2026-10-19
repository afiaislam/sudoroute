// Runs in <head> before first paint so there is no flash of the wrong theme.
(function () {
  var t = null;
  try { t = localStorage.getItem("ts-theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", t);
  // Motion is opt-out: content is fully visible without JS or with reduced motion.
  if (!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) document.documentElement.classList.add("motion");
})();
