(async () => {
  const { $, $$, esc, api } = TS;
  $$("[data-logo]").forEach(el => { el.innerHTML = TS.LOGO; });
  TS.bindTheme();
  $$(".aside img").forEach(img => img.addEventListener("error", () => { img.style.display = "none"; }, { once: true }));

  const params = new URLSearchParams(location.search);
  const mode = location.pathname.startsWith("/register") ? "register" : "login";
  let role = params.get("role") === "guardian" ? "guardian" : "student";

  const COPY = {
    login: { student: ["Welcome back", "Sign in to pay tuition, check invoices and track payments."],
             guardian: ["Welcome back", "Sign in to approve payments and support your student."] },
    register: { student: ["Create your student account", "Pay tuition across borders with checks at every step."],
                guardian: ["Create a guardian account", "Approve your student's payments and send family support."] },
  };

  function setRole(r) {
    role = r;
    $$(".role").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.role === r)));
    $$("[data-for]").forEach(el => { el.hidden = el.dataset.for !== r; });
    const [t, s] = COPY[mode][r];
    $("#title").textContent = I18N.t(`auth.t.${mode}.${r}`, t); $("#subtitle").textContent = I18N.t(`auth.s.${mode}.${r}`, s);
    document.title = `${mode === "login" ? "Sign in" : "Create account"} — SudoRoute`;
    const q = new URLSearchParams(location.search); q.set("role", r);
    history.replaceState(null, "", `${location.pathname}?${q}`);
  }
  $$(".role").forEach(b => b.addEventListener("click", () => setRole(b.dataset.role)));
  $("#tab-login").href = `/login?role=${role}`; $("#tab-register").href = `/register?role=${role}`;
  $$(".role").forEach(b => b.addEventListener("click", () => { $("#tab-login").href = `/login?role=${role}`; $("#tab-register").href = `/register?role=${role}`; }));
  $(mode === "login" ? "#tab-login" : "#tab-register").setAttribute("aria-current", "page");
  $("#login").hidden = mode !== "login";
  $("#register").hidden = mode !== "register";
  setRole(role);
  I18N.onChange(() => setRole(role));

  const alertBox = $("#alert");
  const show = (kind, text) => { alertBox.innerHTML = text ? `<div class="alert ${kind}" role="alert">${esc(text)}</div>` : ""; };
  if (params.get("expired")) show("info", "Your session ended. Sign in again to continue.");

  $$("[data-showpw]").forEach(b => b.addEventListener("click", () => {
    const i = b.parentElement.querySelector("input");
    const vis = i.type === "text"; i.type = vis ? "password" : "text"; b.textContent = vis ? "Show" : "Hide";
  }));

  // Public metadata: countries, universities, relationships.
  const meta = await api("/api/public/meta");
  $("#r-country").innerHTML = `<option value="">Choose…</option>` + meta.countries.map(c => `<option value="${esc(c.code)}">${esc(c.name)} (${esc(c.currency)})</option>`).join("");
  $("#uni-list").innerHTML = meta.universities.map(u => `<option value="${esc(u.name)}">${esc(u.city)}</option>`).join("");
  $("#r-scountry").innerHTML = `<option value="">Choose…</option>` + meta.study_countries.map(c => `<option value="${esc(c.code)}">${esc(c.name)} (${esc(c.currency)})</option>`).join("");
  const norm = t => String(t || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
  const uniHint = () => {
    const known = meta.universities.find(u => norm(u.name) === norm($("#r-uni").value));
    const h = $("#unihint");
    if (known) {
      $("#r-scountry").value = known.country; $("#r-scountry").disabled = true; $("#webfield").hidden = true;
      h.textContent = `✓ Verified university — ${known.city}. Payments go only to its registered account.`; h.style.color = "var(--ok)";
    } else {
      $("#r-scountry").disabled = false; $("#webfield").hidden = false; h.style.color = "";
      h.textContent = $("#r-uni").value.trim().length > 2
        ? "Not in our verified list yet. You can register now; we confirm its official bank account with the university before the first payment."
        : I18N.t("auth.unihint", "Type any university. If it isn't verified yet, we confirm its bank account with the university before the first payment.");
    }
  };
  $("#r-uni").addEventListener("input", uniHint);
  $("#r-rel").innerHTML = meta.relationships.map(r => `<option>${esc(r)}</option>`).join("");

  // Live password checklist (guidance only; the server enforces the same rule).
  const RULES = { len: p => p.length >= 8, upper: p => /[A-Z]/.test(p), lower: p => /[a-z]/.test(p), digit: p => /\d/.test(p) };
  $("#r-pw").addEventListener("input", e => {
    const p = e.target.value;
    $$("#pwrules li").forEach(li => li.classList.toggle("ok", RULES[li.dataset.rule](p)));
  });

  function busy(form, on) { const b = form.querySelector("button[type=submit]"); b.disabled = on; if (on) b.setAttribute("aria-busy", "true"); else b.removeAttribute("aria-busy"); }

  $("#login").addEventListener("submit", async e => {
    e.preventDefault(); show(); busy(e.target, true);
    const r = await api("/api/auth/login", { email: $("#l-email").value, password: $("#l-pw").value, role });
    busy(e.target, false);
    if (r.ok) { location.href = r.redirect; return; }
    show("bad", r.error || "Sign-in failed.");
  });

  $("#register").addEventListener("submit", async e => {
    e.preventDefault(); show(); busy(e.target, true);
    $$("#register .field").forEach(f => { f.classList.remove("bad"); const er = f.querySelector(".err"); if (er) er.textContent = ""; });
    $("#r-scountry").disabled = false;
    const fd = Object.fromEntries(new FormData(e.target).entries());
    uniHint();
    const r = await api("/api/auth/register", { ...fd, role });
    busy(e.target, false);
    if (r.ok) { location.href = r.redirect; return; }
    show("bad", r.error || "Registration failed.");
    Object.entries(r.fields || {}).forEach(([k, msg]) => {
      const f = $(`#register [data-f="${k}"]`); if (!f) return;
      f.classList.add("bad"); const er = f.querySelector(".err"); if (er) er.textContent = msg;
    });
  });
})();
