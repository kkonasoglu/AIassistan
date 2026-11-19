// Sesli yanıt: cevabı sunucudaki Türkçe erkek sesle okutur (metin sunucuda sese çevrilir, dışarı çıkmaz).
// "Sesli yanıt" kutusu açıksa her cevap otomatik okunur; her cevaptaki 🔊 düğmesiyle tek tek de okutulabilir.
const Speaker = (() => {
  const KEY = "dinyo-speak";
  let audio = null, url = null, ticket = 0, playing = false;

  const dinyo = (mood, ms) => { if (typeof Dinyo !== "undefined") Dinyo.set(mood, ms); };
  const note = (text) => { const s = document.getElementById("chat-status"); if (s) say(s, text); };

  function gender() {
    const s = document.getElementById("voice-gender");
    return s && s.value === "female" ? "female" : "male";
  }

  function enabled() {
    const box = document.getElementById("speak-on");
    return !!(box && box.checked);
  }

  // Balondaki okunacak metin: üstteki not + bilgi bankası kartları (başlık ve adımlar).
  // İnternet sonuçları ve onay bekleyen taslaklar okunmaz (uzun/doğrulanmamış).
  function textOf(node) {
    const parts = [];
    const t = node.querySelector(".text");
    if (t && t.textContent.trim()) parts.push(t.textContent.trim());
    for (const c of node.querySelectorAll(".kb-card")) {
      if (c.classList.contains("web") || c.classList.contains("draft")) continue;
      const title = c.querySelector(".kb-title"), sol = c.querySelector(".kb-solution");
      if (title) parts.push(title.textContent.trim() + ".");
      if (sol) parts.push(sol.textContent.trim());
    }
    return parts.join("\n");
  }

  function cleanup() {
    if (audio) { audio.onended = audio.onerror = null; audio.pause(); audio = null; }
    if (url) { URL.revokeObjectURL(url); url = null; }
  }

  function stop() {
    ticket++;                                   // yoldaki (henüz inmemiş) ses isteği de iptal olur
    const was = playing;
    playing = false;
    cleanup();
    document.querySelectorAll(".speak-btn.on").forEach(b => b.classList.remove("on"));
    if (was) dinyo("idle");
  }

  async function speak(text, button) {
    stop();
    text = (text || "").trim();
    if (!text) return;
    const mine = ++ticket;
    if (button) button.classList.add("on");
    try {
      const res = await fetch("/api/voice/speak", {
        method: "POST", credentials: "same-origin",
        headers: { "X-Requested-With": "fetch", "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: gender() }),
      });
      if (mine !== ticket) return;
      if (res.status === 204) { if (button) button.classList.remove("on"); return; }
      if (!res.ok) {
        let d = ""; try { d = (await res.json()).detail; } catch (_) {}
        throw new Error(typeof d === "string" && d ? d : "Ses üretilemedi.");
      }
      const blob = await res.blob();
      if (mine !== ticket) return;
      url = URL.createObjectURL(blob);
      audio = new Audio(url);
      audio.onended = () => stop();
      audio.onerror = () => { stop(); note("Ses çalınamadı."); };
      playing = true;
      dinyo("speaking");
      await audio.play();
    } catch (e) {
      if (mine !== ticket) return;
      stop();
      note(e.name === "NotAllowedError" ? "Tarayıcı sesi engelledi. Cevaptaki 🔊 düğmesine basın." : e.message);
    }
  }

  const toggle = (node, button) => (playing && button && button.classList.contains("on")) ? stop() : speak(textOf(node), button);

  function init() {
    const box = document.getElementById("speak-on");
    if (!box) return;
    try { box.checked = localStorage.getItem(KEY) !== "off"; } catch (_) { box.checked = true; }
    box.addEventListener("change", () => {
      try { localStorage.setItem(KEY, box.checked ? "on" : "off"); } catch (_) {}
      if (!box.checked) stop();
    });
    const btn = document.getElementById("voice-menu-btn"), panel = document.getElementById("voice-panel");
    if (btn && panel) {                                   // ⚙ düğmesi: ses ayarları penceresi
      const close = () => { panel.classList.add("hidden"); btn.setAttribute("aria-expanded", "false"); };
      btn.addEventListener("click", ev => {
        ev.stopPropagation();
        const open = panel.classList.toggle("hidden") === false;
        btn.setAttribute("aria-expanded", String(open));
      });
      document.addEventListener("click", ev => { if (!panel.contains(ev.target)) close(); });
      document.addEventListener("keydown", ev => { if (ev.key === "Escape") close(); });
    }
    const sel = document.getElementById("voice-gender");
    if (sel) {
      try { sel.value = localStorage.getItem("dinyo-voice") === "female" ? "female" : "male"; } catch (_) {}
      sel.addEventListener("change", () => {
        try { localStorage.setItem("dinyo-voice", sel.value); } catch (_) {}
        stop();
        if (typeof Dinyo !== "undefined") Dinyo.set("happy", 2500);
        speak(sel.value === "female" ? "Merhaba! Şimdi böyle konuşuyorum." : "Merhaba! Şimdi böyle konuşuyorum.");   // deneme
      });
    }
  }

  return { init, enabled, speak, stop, toggle, textOf, isPlaying: () => playing };
})();
