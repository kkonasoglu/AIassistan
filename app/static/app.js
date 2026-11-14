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
