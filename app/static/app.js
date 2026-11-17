// Ortak yardımcılar. Kullanıcıdan gelen metinler HİÇBİR ZAMAN innerHTML ile basılmaz.

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "X-Requested-With": "fetch", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    let msg = data && data.detail;
    if (typeof msg !== "string") msg = "Geçersiz bilgi girdiniz.";
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

// el("button", {class: "primary", onclick: fn}, "Metin", altEleman)
function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);   // string -> metin düğümü (güvenli)
  return node;
}

function say(box, text, kind = "error") {
  box.textContent = text;
  box.className = "msg " + (text ? kind : "");
}

async function logout() {
  try { await api("/api/auth/logout", "POST"); } catch (_) {}
  location.href = "/";
}

// Şifre değiştirme penceresi (her sayfada kullanılabilir)
function openPasswordDialog() {
  const cur = el("input", { type: "password", autocomplete: "current-password" });
  const nw = el("input", { type: "password", autocomplete: "new-password" });
  const msg = el("div", { class: "msg" });
  const dlg = el("dialog", {});
  const save = el("button", { class: "primary" }, "Kaydet");
  const cancel = el("button", { onclick: () => dlg.close() }, "Vazgeç");
  save.addEventListener("click", async () => {
    try {
      await api("/api/auth/password", "POST", { current: cur.value, new: nw.value });
      say(msg, "Şifre değiştirildi.", "ok");
      setTimeout(() => dlg.close(), 900);
    } catch (e) { say(msg, e.message); }
  });
  dlg.append(el("h2", {}, "Şifre değiştir"),
    el("label", {}, "Mevcut şifre"), cur, el("label", {}, "Yeni şifre (en az 6 karakter)"), nw,
    msg, el("div", { class: "form-actions" }, save, " ", cancel));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
}


// Tema rengi: gözlere dokununca sıradaki neon renge geçilir; tercih bu tarayıcıda hatırlanır, tüm sayfalarda geçerlidir.
const Theme = (() => {
  const COLORS = [   // [ad, ana renk, parlama]
    ["Mavi", "#19c8ff", "#0aa4ff"], ["Yeşil", "#2ee89a", "#10b36d"], ["Mor", "#b18cff", "#7c4dff"],
    ["Pembe", "#ff66b3", "#e0388a"], ["Turuncu", "#ffa72b", "#e07b00"], ["Sarı", "#ffe14d", "#d9b400"],
  ];
  let i = 0;
  function apply(n) {
    i = ((n % COLORS.length) + COLORS.length) % COLORS.length;
    const [, main, glow] = COLORS[i], root = document.documentElement.style;
    root.setProperty("--accent", main);
    root.setProperty("--accent-hover", `color-mix(in srgb, ${main} 75%, #fff)`);
    root.setProperty("--accent-soft", `color-mix(in srgb, ${main} 16%, #0b0b0e)`);
    root.setProperty("--neon", main);
    root.setProperty("--neon-glow", glow);
    try { localStorage.setItem("dinyo-color", String(i)); } catch (_) {}
    return COLORS[i][0];
  }
  try { apply(parseInt(localStorage.getItem("dinyo-color") || "0", 10) || 0); } catch (_) { apply(0); }
  return { next: () => apply(i + 1), name: () => COLORS[i][0] };
})();

// Ad penceresi: Dinyo kullanıcıya bu adla seslenir. Kaydedilince done(kullanıcı) çağrılır.
function openNameDialog(current, done) {
  const input = el("input", { maxlength: "40", autocomplete: "name", value: current || "", placeholder: "Örn. Kerem" });
  const msg = el("div", { class: "msg" });
  const dlg = el("dialog", {});
  const save = el("button", { class: "primary", type: "button" }, "Kaydet");
  const skip = el("button", { type: "button", onclick: () => dlg.close() }, "Şimdilik geç");
  const submit = async () => {
    try {
      const u = await api("/api/auth/display-name", "POST", { name: input.value });
      dlg.close();
      done(u);
    } catch (e) { say(msg, e.message); }
  };
  save.addEventListener("click", submit);
  input.addEventListener("keydown", ev => { if (ev.key === "Enter") { ev.preventDefault(); submit(); } });
  dlg.append(el("h2", {}, "Size nasıl hitap edeyim?"),
    el("p", { class: "muted" }, "Dinyo size bu adla seslenecek. İstediğiniz zaman sağ üstteki adınıza tıklayarak değiştirebilirsiniz."),
    el("label", {}, "Adınız"), input, msg, el("div", { class: "form-actions" }, save, skip));
  dlg.addEventListener("close", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  input.focus();
}
