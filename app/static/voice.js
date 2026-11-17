// Bas-konuş: F8 tuşunu ya da mikrofon düğmesini BASILI TUTUN, bırakınca ses yazıya çevrilir.
// Ses yalnızca sunucuya gider (internete çıkmaz), kayıt sunucuda saklanmaz.
const Voice = (() => {
  const $ = id => document.getElementById(id);
  const MIN_MS = 500;      // bundan kısa basış kazara sayılır
  const MAX_MS = 60000;    // tek kayıt üst sınırı
  const KEY = "F8";   // Edge'de F9 "Okuyucu görünümü" ile çakışabilir
  let recorder = null, stream = null, chunks = [], t0 = 0, timer = null;
  let starting = false, wantStop = false, inited = false;

  const status = (text, kind) => say($("chat-status"), text, kind);

  function pickType() {
    for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
      if (MediaRecorder.isTypeSupported(t)) return t;
    }
    return "";
  }

  function setUi(recording) {
    $("mic-btn").classList.toggle("recording", recording);
    $("mic-btn").setAttribute("aria-pressed", recording ? "true" : "false");
  }

  function release() {
    if (stream) stream.getTracks().forEach(t => t.stop());   // tarayıcıdaki "mikrofon açık" simgesi kapanır
    stream = null;
  }

  async function start() {
    if (recorder || starting || Chat.isBusy()) return;
    if (!window.isSecureContext || !navigator.mediaDevices || !window.MediaRecorder)
      return status("Mikrofon için sayfayı https:// adresiyle açmanız gerekir.");
    starting = true; wantStop = false;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      starting = false;
      return status(e.name === "NotAllowedError"
        ? "Mikrofon izni verilmedi. Tarayıcının adres çubuğundaki izin simgesinden mikrofona izin verin."
        : "Mikrofon bulunamadı veya açılamadı.");
    }
    starting = false;
    if (wantStop) { release(); return; }   // izin penceresi beklerken tuş bırakıldı
    const type = pickType();
    recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = [];
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = onStop;
    recorder.start();
    t0 = Date.now();
    setUi(true);
    if (typeof Dinyo !== "undefined") Dinyo.set("listening");
    status("🎙 Dinliyorum… bırakınca yazıya çevrilir.", "ok");
    timer = setTimeout(stop, MAX_MS);
  }

  function stop() {
    wantStop = true;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }

  async function onStop() {
    clearTimeout(timer);
    const ms = Date.now() - t0;
    const type = (recorder && recorder.mimeType) || "audio/webm";
    recorder = null;
    release();
    setUi(false);
    if (typeof Dinyo !== "undefined") Dinyo.set(ms < MIN_MS ? "idle" : "thinking");
    if (ms < MIN_MS) return status("Çok kısa. Konuşurken tuşu basılı tutun.");
    const blob = new Blob(chunks, { type });
    chunks = [];
    status("Yazıya çevriliyor…", "ok");
    try {
      const res = await fetch("/api/voice/transcribe", {
        method: "POST", credentials: "same-origin", body: blob,
        headers: { "X-Requested-With": "fetch", "Content-Type": type.split(";")[0] },
      });
      let data = null; try { data = await res.json(); } catch (_) {}
      if (res.status === 401) return location.reload();
      if (!res.ok) throw new Error((data && typeof data.detail === "string" && data.detail) || "Ses yazıya çevrilemedi.");
      const text = (data.text || "").trim();
      if (!text) { if (typeof Dinyo !== "undefined") Dinyo.set("confused", 4000); return status("Ses anlaşılamadı. Biraz daha yüksek ve yakın konuşup tekrar deneyin."); }
      const input = $("chat-input");
      input.value = input.value.trim() ? input.value.trim() + " " + text : text;
      status("");
      if (!$("auto-send").checked && typeof Dinyo !== "undefined") Dinyo.set("idle");
      if ($("auto-send").checked) Chat.send(); else input.focus();
    } catch (e) {
      if (typeof Dinyo !== "undefined") Dinyo.set("sad", 4000);
      status(e.message);
    }
  }

  function init() {
    if (inited) return;
    inited = true;
    const btn = $("mic-btn");
    if (!window.isSecureContext || !navigator.mediaDevices) {
      btn.disabled = true;
      btn.title = "Mikrofon için sayfayı https:// adresiyle açın";
    }
    // Düğme: basılı tut (fare, dokunmatik, kalem)
    btn.addEventListener("pointerdown", ev => { ev.preventDefault(); btn.setPointerCapture(ev.pointerId); start(); });
    for (const t of ["pointerup", "pointercancel"]) btn.addEventListener(t, stop);
    btn.addEventListener("contextmenu", ev => ev.preventDefault());
    // Klavye: F8'i basılı tut (sayfa açıkken, imleç nerede olursa olsun)
    document.addEventListener("keydown", ev => {
      if (ev.key === KEY && !ev.repeat) { ev.preventDefault(); start(); } else if (ev.key === KEY) ev.preventDefault();
    });
    document.addEventListener("keyup", ev => { if (ev.key === KEY) { ev.preventDefault(); stop(); } });
    window.addEventListener("blur", stop);   // pencere değişirse kayıt takılı kalmasın
  }

  return { init };
})();
