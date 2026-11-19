// Sohbet ekranı. Mesaj metinleri her zaman textContent ile basılır (güvenli).
const Chat = (() => {
  const $ = id => document.getElementById(id);
  let convId = null;      // açık sohbet (yoksa ilk mesajda oluşturulur)
  let controller = null;  // devam eden akışı durdurmak için
  let started = false;

  function scrollDown() { const m = $("messages"); m.scrollTop = m.scrollHeight; }

  // Bilgi bankası kaydı: başlık + çözüm, birebir. kind: "draft" (onay bekliyor) | "saved" | (yok)
  const LABELS = { draft: "Kaydedilecek kayıt (onayınız bekleniyor)", saved: "Bilgi bankasına eklendi",
                   web: "İnternet sonucu (şirket kaydı değil)" };
  function card(c, withActions) {
    const node = el("div", { class: "kb-card" + (c.kind ? " " + c.kind : "") },
      el("div", { class: "kb-label" }, LABELS[c.kind] || "Bilgi bankası kaydı"),
      el("div", { class: "kb-title" }, c.title),
      el("div", { class: "kb-solution" }, c.solution));
    if (c.kind === "web" && /^https?:\/\//.test(c.url || ""))
      node.append(el("a", { class: "kb-link", href: c.url, target: "_blank", rel: "noopener noreferrer" }, c.url));
    if (c.kind === "draft" && withActions) {
      const bar = el("div", { class: "kb-actions" });
      const done = () => bar.remove();
      bar.append(
        el("button", { class: "primary", onclick: () => { done(); send("kaydet"); } }, "Kaydet"),
        el("button", { onclick: () => { done(); send("iptal"); } }, "İptal"));
      node.append(bar);
    }
    return node;
  }

  // Asistan balonu: üstte kısa not (.text), altında kartlar (.cards)
  function bubble(role, text, cards) {
    const b = el("div", { class: "bubble " + role });
    const body = el("div", { class: "text" }, text || "");
    const box = el("div", { class: "cards" });
    b.append(body, box);
    if (role === "assistant" && typeof Speaker !== "undefined") {   // 🔊: bu cevabı sesli oku / durdur
      const sp = el("button", { type: "button", class: "speak-btn", title: "Sesli oku" }, "🔊");
      sp.addEventListener("click", () => Speaker.toggle(b, sp));
      b.append(sp);
    }
    for (const c of cards || []) box.append(card(c));
    $("messages").append(b);
    scrollDown();
    return { node: b, body, box };
  }

  function showWelcome() {
    const tips = [["KNK-204 hatası alıyorum", "Hata koduyla sorun çözümü"],
                  ["e-Fatura gönderemiyorum", "Fatura gönderim sorunları"],
                  ["e-İmza cihazı görünmüyor", "İmza cihazı ve sertifika"]];
    const grid = el("div", { class: "tips" });
    for (const [q, d] of tips)
      grid.append(el("button", { type: "button", class: "tip", onclick: () => send(q) },
        el("b", {}, q), el("span", {}, d)));
    $("messages").replaceChildren(el("div", { class: "welcome" },
      el("h3", {}, `Merhaba${typeof Dinyo !== "undefined" && Dinyo.name() ? " " + Dinyo.name() : ""}, ben Dinyo. Size nasıl yardımcı olabilirim?`),
      el("p", { class: "muted" }, "Sorunu ya da hata kodunu yazın; kayıtlı çözümü hemen getiririm. Konuşmak için F8'e basılı tutun."),
      grid));
  }

  async function refreshList() {
    let list = [];
    try { list = await api("/api/chat/conversations"); } catch (e) { if (e.status === 401) location.reload(); return; }
    const box = $("conv-list"); box.replaceChildren();
    for (const c of list) {
      const del = el("button", { class: "icon", title: "Sohbeti sil", onclick: async ev => {
        ev.stopPropagation();
        if (!confirm("Bu sohbet silinsin mi?")) return;
        await api(`/api/chat/conversations/${c.id}`, "DELETE");
        if (c.id === convId) newChat();
        refreshList();
      } }, "×");
      box.append(el("div", { class: "conv" + (c.id === convId ? " active" : ""), onclick: () => open(c.id) },
        el("span", { class: "title" }, c.title), del));
    }
  }

  async function open(id) {
    if (controller) return;  // cevap gelirken sohbet değiştirme
    const msgs = await api(`/api/chat/conversations/${id}`);
    convId = id;
    $("messages").replaceChildren();
    msgs.forEach((m, i) => {
      const b = bubble(m.role, m.content, m.cards);
      // yalnızca son mesajdaki taslak hâlâ onay bekliyor olabilir
      if (i === msgs.length - 1 && m.role === "assistant") {
        const d = (m.cards || []).findIndex(c => c.kind === "draft");
        if (d >= 0) b.box.replaceChild(card(m.cards[d], true), b.box.children[d]);
      }
    });
    if (!msgs.length) showWelcome();
    say($("chat-status"), "");
    refreshList();
  }

  function newChat() {
    if (controller) return;
    convId = null;
    showWelcome();
    say($("chat-status"), "");
    refreshList();
    $("chat-input").focus();
  }

  function setBusy(busy) {
    $("send-btn").disabled = busy;
    $("chat-input").disabled = busy;
    $("stop-btn").classList.toggle("hidden", !busy);
    if (!busy) $("chat-input").focus();
  }

  async function send(override) {
    const input = $("chat-input");
    const text = (typeof override === "string" ? override : input.value).trim();
    if (!text || controller) return;
    if (typeof override !== "string") input.value = "";
    try {
      if (convId === null) convId = (await api("/api/chat/conversations", "POST")).id;
    } catch (e) { return say($("chat-status"), e.message); }
    if ($("messages").querySelector(".welcome")) $("messages").replaceChildren();

    if (typeof Speaker !== "undefined") Speaker.stop();   // yeni soru: eski okuma kesilir
    bubble("user", text);
    const answer = bubble("assistant", "");
    answer.node.classList.add("pending");
    say($("chat-status"), "Bilgi bankasında aranıyor…", "ok");
    setBusy(true);
    if (typeof Dinyo !== "undefined") Dinyo.set("thinking");
    controller = new AbortController();
    let gotCards = false, failed = false;

    try {
      const res = await fetch(`/api/chat/conversations/${convId}/stream`, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: { "X-Requested-With": "fetch", "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok) {
        let d = ""; try { d = (await res.json()).detail; } catch (_) {}
        if (res.status === 401) return location.reload();
        throw new Error(typeof d === "string" && d ? d : "İstek başarısız.");
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
          if (!block.startsWith("data: ")) continue;
          const ev = JSON.parse(block.slice(6));
          if (ev.type === "cards") {
            gotCards = true;
            if (typeof Dinyo !== "undefined") Dinyo.set("happy");
            for (const c of ev.cards) answer.box.append(card(c, true));
            say($("chat-status"), "", "ok");
            scrollDown();
          } else if (ev.type === "status") {
            say($("chat-status"), ev.text, "ok");
            if (typeof Dinyo !== "undefined" && /internet/i.test(ev.text)) Dinyo.set("searching");
          } else if (ev.type === "queue") {
            say($("chat-status"), `Sırada bekleniyor (sıranız: ${ev.position})…`, "ok");
          } else if (ev.type === "token") {
            say($("chat-status"), "");
            if (typeof Dinyo !== "undefined" && !gotCards) Dinyo.set("answering");
            answer.body.textContent += ev.text;
            scrollDown();
          } else if (ev.type === "error") throw new Error(ev.message);
        }
      }
      say($("chat-status"), "");
    } catch (e) {
      if (e.name === "AbortError") say($("chat-status"), "Durduruldu.", "ok");
      else { failed = true; say($("chat-status"), e.message); }
    } finally {
      answer.node.classList.remove("pending");
      if (!answer.body.textContent && !answer.box.children.length) answer.node.remove();
      controller = null;
      setBusy(false);
      if (typeof Dinyo !== "undefined") {      // karakterin tepkisi: buldu / bulamadı / hata
        const reply = answer.body.textContent || "";
        if (failed) Dinyo.set("sad", 5000);
        else if (/te[sş]ekk[uü]r|sa[gğ]\s?ol|eyvallah|harikas[ıi]n|[çc]ok iyi/i.test(text)) Dinyo.set("love", 5000);   // teşekkür: kalp gözler
        else if (gotCards) Dinyo.set("happy", 4500);
        else if (/bulamad|boş|aramamı ister/i.test(reply)) Dinyo.set("confused", 5000);
        else Dinyo.set("idle");
      }
      if (!failed && typeof Speaker !== "undefined" && Speaker.enabled() && document.body.contains(answer.node))
        Speaker.speak(Speaker.textOf(answer.node), answer.node.querySelector(".speak-btn"));   // sesli yanıt
      refreshList();
    }
  }

  function start() {
    if (started) { newChat(); return; }
    started = true;
    $("chat-form").addEventListener("submit", ev => { ev.preventDefault(); send(); });
    $("chat-input").addEventListener("keydown", ev => {
      if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); send(); }
    });
    $("stop-btn").addEventListener("click", () => controller && controller.abort());
    $("new-chat").addEventListener("click", newChat);
    newChat();
  }

  function refreshWelcome() { if ($("messages").querySelector(".welcome")) showWelcome(); }

  return { start, send, refreshWelcome, isBusy: () => controller !== null };
})();
