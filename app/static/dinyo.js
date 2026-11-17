// Dinyo: sohbetin karşısındaki robot karakter. İki neon mavisi yuvarlak; fareyi ve YAZDIĞINIZ yeri izler,
// göz kırpar, düşünürken/cevap verirken/bulunca farklı tepki verir ve kullanıcıya ADIYLA hitap eder.
// Sohbet kodu yalnızca Dinyo.set("durum") çağırır; karakter yoksa/hata verirse sohbet etkilenmez.
const Dinyo = (() => {
  // Her durumun söylediği satır ({n} = kullanıcının adı)
  const LINES = {
    hello: "Merhaba {n}! Ben Dinyo.", idle: "Buradayım {n}, yazabilirsiniz.", typing: "{n}, sizi okuyorum…",
    thinking: "Düşünüyorum {n}…", searching: "İnternette bakıyorum {n}…", answering: "Cevaplıyorum {n}…",
    happy: "Buldum {n}!", confused: "Hmm {n}, bunu bulamadım…", sad: "Bir sorun oldu {n}…",
    listening: "Sizi dinliyorum {n}…",
  };
  const REACH = 14;               // yuvarlakların bakış yönünde kayabileceği en fazla piksel
  let root, face, say, eyes = [], mood = "idle", back = null, lastMove = 0, typingTimer = null, who = "";
  let canvas;

  function nameOf(username) {     // ayse -> Ayse (Türkçe i/ı kuralıyla)
    const u = (username || "").trim();
    return u ? u.charAt(0).toLocaleUpperCase("tr") + u.slice(1) : "";
  }

  function build(el) {
    root = el;
    root.classList.add("dinyo");
    face = document.createElement("div"); face.className = "face"; face.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 2; i++) {
      const eye = document.createElement("div"); eye.className = "eye " + (i ? "right" : "left");
      const dot = document.createElement("div"); dot.className = "dot";
      eye.append(dot); face.append(eye); eyes.push(eye);
    }
    say = document.createElement("div"); say.className = "say";
    root.append(face, say);
  }

  function look(dx, dy) {          // -1..1 aralığında bakış yönü
    root.style.setProperty("--lx", (dx * REACH).toFixed(1) + "px");
    root.style.setProperty("--ly", (dy * REACH * .8).toFixed(1) + "px");
  }

  function lookAt(x, y, full) {    // sayfadaki bir noktaya bak
    const r = face.getBoundingClientRect();
    const dx = x - (r.left + r.width / 2), dy = y - (r.top + r.height / 2), d = Math.hypot(dx, dy) || 1;
    const k = full ? 1 : Math.min(1, d / 220);                    // uzaktayken tam, yakındayken az kayar
    look(dx / d * k, dy / d * k);
  }

  function set(next, ms) {
    if (!root) return;
    clearTimeout(back);
    mood = next;
    root.dataset.mood = next === "hello" ? "happy" : next;
    const b = document.createElement("b"); b.textContent = "Dinyo";
    const s = document.createElement("span"); s.textContent = (LINES[next] || "").replace("{n}", who).replace(/\s+([!…,.])/g, "$1").replace(/, +\s*/g, ", ");
    say.replaceChildren(b, s);
    if (next === "idle") look(0, 0);
    if (["thinking", "searching", "answering"].includes(next)) look(0, 0);
    if (ms) back = setTimeout(() => set("idle"), ms);
  }

  // Yazarken: imlecin textarea içindeki yerini ölçüp oraya bak
  function caretPoint(input) {
    canvas = canvas || document.createElement("canvas");
    const cs = getComputedStyle(input), rect = input.getBoundingClientRect();
    const ctx = canvas.getContext("2d"); ctx.font = `${cs.fontSize} ${cs.fontFamily}`;
    const before = input.value.slice(0, input.selectionStart ?? input.value.length);
    const lines = before.split("\n"), inner = rect.width - 24;
    const w = ctx.measureText(lines[lines.length - 1]).width;
    const wraps = Math.floor(w / Math.max(inner, 1));
    const lh = parseFloat(cs.lineHeight) || 21;
    const row = Math.min(lines.length - 1 + wraps, 1);            // textarea 2 satır görünür
    return { x: rect.left + 12 + (w % Math.max(inner, 1)), y: rect.top + 10 + row * lh };
  }

  function onTyping(input) {
    if (["thinking", "searching", "answering", "listening"].includes(mood)) return;
    if (mood !== "typing") set("typing");
    const p = caretPoint(input);
    lookAt(p.x, p.y, true);
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => mood === "typing" && set("idle"), 2000);
  }

  function track(ev) {
    lastMove = Date.now();
    if (!root || ["thinking", "searching", "answering", "typing"].includes(mood)) return;
    lookAt(ev.clientX, ev.clientY, false);
  }

  function blink() {
    if (root && !["happy", "sad"].includes(root.dataset.mood)) {
      for (const e of eyes) e.classList.add("blink");
      setTimeout(() => eyes.forEach(e => e.classList.remove("blink")), 140);
    }
    setTimeout(blink, 2200 + Math.random() * 3800);
  }

  function wander() {              // fare ve klavye uzun süre kımıldamazsa yuvarlaklar etrafa bakar
    if (root && mood === "idle" && Date.now() - lastMove > 4000) look(Math.random() * 1.6 - 0.8, Math.random() - 0.5);
    setTimeout(wander, 2500 + Math.random() * 3000);
  }

  function init(username) {
    const el = document.getElementById("dinyo");
    if (!el || root) return;
    who = nameOf(username);
    build(el);
    set("hello", 3500);
    document.addEventListener("mousemove", track);
    const input = document.getElementById("chat-input");
    if (input) for (const t of ["input", "keyup", "click", "focus"])
      input.addEventListener(t, () => { if (t === "input" || input.value) onTyping(input); });
    blink(); wander();
  }

  return { init, set, name: () => who };
})();
