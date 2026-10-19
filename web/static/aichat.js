// Floating AI assistant. One button in the corner of every page; the panel talks to:
//   student  → /api/chat          (the full agent: same tools, tiers and approvals as the Assistant page)
//   guardian → /api/guardian/ask  (read-only answers grounded in the linked students' data)
//   public   → /api/public/ask    (questions about SudoRoute, grounded in a fixed fact sheet)
// Gemini writes the words when it is connected; every reply is checked against the facts first.
(() => {
  const mode = (document.currentScript && document.currentScript.dataset.mode) || "public";
  const { esc, md, api } = TS;
  const lang = () => (window.I18N && I18N.lang) || "en";
  const T = {
    en: { title: "SudoRoute AI", sub: { student: "Ask about your tuition, invoices and payments", guardian: "Ask about your student's tuition and approvals", public: "Ask how SudoRoute works" },
      hello: { student: "Hi! I'm your SudoRoute AI. I can check invoices, compare transfer options, explain your currency risk — and prepare a payment for you to approve.", guardian: "Hello! Ask me anything about your student's tuition, payments and approvals. I can only read — approving always needs your own code.", public: "Hi! Ask me anything about SudoRoute — how payments are approved, how scams are stopped, or what the 6-digit code is." },
      chips: { student: ["When should I pay?", "Is my latest invoice real?", "Compare transfer options", "Pay my tuition"], guardian: ["What is waiting for my approval?", "How much tuition is left?", "Where is the last payment?", "Is any invoice a scam?"], public: ["What is the 6-digit code?", "How do you stop scams?", "Is this real money?", "How do guardians approve?"] },
      ph: "Ask in English, বাংলা or 中文…", send: "Send", ai: "Written by Gemini · facts checked", rules: "SudoRoute", open: "Open the payment to approve →", busy: "Thinking…", err: "Sorry, that didn't work. Try again." },
    zh: { title: "SudoRoute AI", sub: { student: "询问学费、账单和付款", guardian: "询问学生的学费和审批", public: "了解 SudoRoute 如何运作" },
      hello: { student: "你好！我是 SudoRoute AI。我可以核查账单、比较汇款方式、解释汇率风险，并为你准备一笔需要你批准的付款。", guardian: "您好！可以问我学生的学费、付款和审批情况。我只能查看——批准始终需要您自己的验证码。", public: "你好！可以问我 SudoRoute 的任何问题——付款如何批准、如何拦截诈骗、6 位验证码是什么。" },
      chips: { student: ["我什么时候付款？", "我最新的账单是真的吗？", "比较汇款方式", "支付我的学费"], guardian: ["有什么等待我批准？", "还剩多少学费？", "最近一笔付款在哪？", "有诈骗账单吗？"], public: ["6 位验证码是什么？", "如何拦截诈骗？", "这是真钱吗？", "家长如何批准？"] },
      ph: "用中文、English 或 বাংলা 提问…", send: "发送", ai: "由 Gemini 撰写 · 已核对事实", rules: "SudoRoute", open: "打开付款进行批准 →", busy: "思考中…", err: "抱歉，出错了，请重试。" },
    bn: { title: "SudoRoute AI", sub: { student: "আপনার টিউশন, ইনভয়েস ও পেমেন্ট নিয়ে জিজ্ঞেস করুন", guardian: "শিক্ষার্থীর টিউশন ও অনুমোদন নিয়ে জিজ্ঞেস করুন", public: "SudoRoute কীভাবে কাজ করে জানুন" },
      hello: { student: "হ্যালো! আমি আপনার SudoRoute AI। আমি ইনভয়েস যাচাই, টাকা পাঠানোর উপায় তুলনা, মুদ্রার ঝুঁকি ব্যাখ্যা করতে পারি — আর আপনার অনুমোদনের জন্য পেমেন্ট প্রস্তুত করতে পারি।", guardian: "আসসালামু আলাইকুম! শিক্ষার্থীর টিউশন, পেমেন্ট ও অনুমোদন নিয়ে যেকোনো প্রশ্ন করুন। আমি শুধু দেখতে পারি — অনুমোদনে সবসময় আপনার নিজের কোড লাগে।", public: "হ্যালো! SudoRoute নিয়ে যেকোনো প্রশ্ন করুন — পেমেন্ট কীভাবে অনুমোদন হয়, প্রতারণা কীভাবে আটকানো হয়, ৬ ডিজিটের কোড কী।" },
      chips: { student: ["কখন পেমেন্ট করব?", "আমার শেষ ইনভয়েসটা কি আসল?", "টাকা পাঠানোর উপায় তুলনা করো", "আমার টিউশন ফি দাও"], guardian: ["কী অনুমোদনের অপেক্ষায় আছে?", "কত টিউশন বাকি?", "শেষ পেমেন্ট কোথায়?", "কোনো ইনভয়েস কি ভুয়া?"], public: ["৬ ডিজিটের কোড কী?", "প্রতারণা কীভাবে আটকান?", "এটা কি আসল টাকা?", "অভিভাবক কীভাবে অনুমোদন দেন?"] },
      ph: "বাংলা, English বা 中文-তে প্রশ্ন করুন…", send: "পাঠান", ai: "Gemini লিখেছে · তথ্য যাচাই করা", rules: "SudoRoute", open: "অনুমোদনের জন্য পেমেন্ট খুলুন →", busy: "ভাবছি…", err: "দুঃখিত, হয়নি। আবার চেষ্টা করুন।" },
  };
  const L = () => T[lang()] || T.en;
  // An expressive little AI face: it blinks, looks at you, smiles on hover, thinks while answering, beams when done.
  const FACE = '<svg class="aiface" viewBox="0 0 48 48" aria-hidden="true">' +
    '<defs><linearGradient id="aifg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5eead4"/><stop offset="1" stop-color="#0f766e"/></linearGradient></defs>' +
    '<line x1="24" y1="7" x2="24" y2="2.5" stroke="#0b5e57" stroke-width="2.2" stroke-linecap="round"/><circle class="af-bulb" cx="24" cy="2.6" r="2.4" fill="#fbbf24"/>' +
    '<rect x="5" y="7" width="38" height="36" rx="14" fill="url(#aifg)"/>' +
    '<rect x="9.5" y="13" width="29" height="22" rx="10" fill="#04211e"/>' +
    '<g class="af-eyes"><ellipse class="af-eye" cx="18" cy="23" rx="3" ry="3.6" fill="#99f6e4"/><ellipse class="af-eye" cx="30" cy="23" rx="3" ry="3.6" fill="#99f6e4"/>' +
    '<path class="af-happy" d="M15 23.5q3-4 6 0M27 23.5q3-4 6 0" fill="none" stroke="#99f6e4" stroke-width="2.4" stroke-linecap="round"/></g>' +
    '<path class="af-mouth" d="M19.5 29.5q4.5 3.6 9 0" fill="none" stroke="#fbbf24" stroke-width="2.2" stroke-linecap="round"/>' +
    '<g class="af-dots" fill="#fbbf24"><circle cx="19" cy="30" r="1.4"/><circle cx="24" cy="30" r="1.4"/><circle cx="29" cy="30" r="1.4"/></g>' +
    '<circle class="af-cheek" cx="12.5" cy="29" r="2" fill="#fb7185" opacity=".55"/><circle class="af-cheek" cx="35.5" cy="29" r="2" fill="#fb7185" opacity=".55"/></svg>';
  const SPARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>';

  const root = document.createElement("div");
  root.className = "aichat"; root.dataset.mode = mode;
  root.innerHTML = `<button type="button" class="aifab" aria-expanded="false" aria-controls="aipanel" aria-label="Open SudoRoute AI">${FACE}<span class="aifab-l">AI</span></button>
    <section class="aipanel" id="aipanel" role="dialog" aria-label="SudoRoute AI" hidden>
      <header><span class="aiicon">${FACE}</span><div><b class="ai-title"></b><small class="ai-sub"></small></div><button type="button" class="aiclose" aria-label="Close">×</button></header>
      <div class="aibody" aria-live="polite"></div>
      <div class="aichips"></div>
      <form class="aiform"><textarea rows="1" maxlength="800" class="aiinput"></textarea><button type="submit" class="btn primary sm aisend"></button></form>
    </section>`;
  document.body.appendChild(root);
  const fab = root.querySelector(".aifab"), panel = root.querySelector(".aipanel"), body = root.querySelector(".aibody");
  const input = root.querySelector(".aiinput"), form = root.querySelector(".aiform");
  let started = false;

  function paint() {
    const l = L();
    root.querySelector(".ai-title").textContent = l.title;
    root.querySelector(".ai-sub").textContent = l.sub[mode];
    input.placeholder = l.ph; root.querySelector(".aisend").textContent = l.send;
    root.querySelector(".aichips").innerHTML = l.chips[mode].map(c => `<button type="button" class="chip">${esc(c)}</button>`).join("");
  }
  paint();
  if (window.I18N) I18N.onChange(paint);
  root.querySelector(".aichips").addEventListener("click", e => { const b = e.target.closest(".chip"); if (b) ask(b.textContent); });

  function add(cls, html) {
    const d = document.createElement("div"); d.className = "aimsg " + cls; d.innerHTML = html;
    body.appendChild(d); body.scrollTop = body.scrollHeight; return d;
  }
  function open(on) {
    panel.hidden = !on; root.classList.toggle("open", on); fab.setAttribute("aria-expanded", String(on));
    if (on && !started) { started = true; add("bot", `<div class="bubble">${esc(L().hello[mode])}</div>`); }
    if (on) setTimeout(() => input.focus(), 50);
  }
  fab.addEventListener("click", () => open(panel.hidden));
  root.querySelector(".aiclose").addEventListener("click", () => { open(false); fab.focus(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) open(false); });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener("submit", e => { e.preventDefault(); const v = input.value; input.value = ""; ask(v); });

  const badge = src => `<div class="aisrc ${src && src !== "template" ? "gem" : ""}">${src && src !== "template" ? "✦ " + esc(L().ai) : esc(L().rules)}</div>`;

  async function ask(text) {
    text = (text || "").trim(); if (!text) return;
    if (panel.hidden) open(true);
    add("me", `<div class="bubble">${esc(text)}</div>`);
    const wait = add("bot", `<div class="bubble"><span class="typing"><i></i><i></i><i></i></span><span class="sr-only">${esc(L().busy)}</span></div>`);
    root.classList.remove("ai-happy", "ai-sad"); root.classList.add("ai-thinking");
    let r;
    try {
      if (mode === "student") r = await api("/api/chat", { message: text, lang: lang() });
      else if (mode === "guardian") r = await api("/api/guardian/ask", { question: text, lang: lang() });
      else r = await api("/api/public/ask", { question: text, lang: lang() });
    } catch (e) { r = { ok: false, error: L().err }; }
    wait.remove();
    root.classList.remove("ai-thinking");
    const mood = m => { root.classList.add(m); clearTimeout(root._mood); root._mood = setTimeout(() => root.classList.remove(m), 2600); };
    if (!r || r.ok === false) { mood("ai-sad"); add("bot", `<div class="bubble">${esc((r && r.error) || L().err)}</div>`); return; }
    mood("ai-happy");
    const reply = mode === "student" ? r.reply : r.text;
    const src = mode === "student" ? r.reply_source : r.source;
    const d = add("bot", `<div class="bubble">${md(reply)}</div>${badge(src)}`);
    if (mode === "student" && r.plan && r.plan.length) {
      const steps = r.plan.flatMap(p => p.steps).map(x => esc(String(x).replace(/_/g, " ")));
      if (steps.length) d.insertAdjacentHTML("beforeend", `<div class="aiplanline"><span class="aitag">✦ AI plan</span> ${steps.join(" → ")}</div>`);
    }
    if (mode === "student") {
      (r.cards || []).forEach(c => {
        if (c.type === "proposal") { d.insertAdjacentHTML("beforeend", `<a class="btn sm primary aiopen" href="#payments">${esc(L().open)}</a>`); return; }
        if (c.type === "suggestions") return;
        if (window.Cards) { try { const n = Cards.render(c, { send: ask, compact: true }); n.classList.add("aicard"); d.appendChild(n); } catch (e) { /* skip */ } }
      });
      const op = d.querySelector(".aiopen"); if (op) op.addEventListener("click", () => open(false));
      document.dispatchEvent(new CustomEvent("sr:changed"));
    }
    body.scrollTop = body.scrollHeight;
  }

  // The student's Assistant page already is a full chat — hide the bubble there.
  const sync = () => root.classList.toggle("hide", mode === "student" && location.hash.replace("#", "").startsWith("assistant"));
  window.addEventListener("hashchange", sync); sync();
  window.SRAI = { open, ask };
})();
