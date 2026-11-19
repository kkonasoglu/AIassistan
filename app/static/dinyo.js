// Dinyo: sohbetin karşısındaki robot karakter. İki neon mavisi yuvarlak; fareyi ve YAZDIĞINIZ yeri izler,
// göz kırpar, düşünürken/cevap verirken/bulunca farklı tepki verir ve kullanıcıya ADIYLA hitap eder.
// Sohbet kodu yalnızca Dinyo.set("durum") çağırır; karakter yoksa/hata verirse sohbet etkilenmez.
const Dinyo = (() => {
  // Her durumun söylediği satır ({n} = kullanıcının adı)
  const LINES = {
    hello: "Merhaba {n}! Ben Dinyo.", idle: "Buradayım {n}, yazabilirsiniz.", typing: "{n}, sizi okuyorum…",
    thinking: "Düşünüyorum {n}…", searching: "İnternette bakıyorum {n}…", answering: "Cevaplıyorum {n}…",
    happy: "Buldum {n}!", confused: "Hmm {n}, bunu bulamadım…", sad: "Bir sorun oldu {n}…",
    listening: "Sizi dinliyorum {n}…", speaking: "Konuşuyorum {n}…", pet: "Hihi, gıdıklandım {n}!",
    sleep: "Zzz… (uyuyorum, dokunun uyanırım)", wake: "Ooo, uyandım {n}!",
    love: ["Ayy, ne tatlısınız {n}! 💙", "Rica ederim {n}, her zaman! 💙", "Sizin için buradayım {n}! 💙"],
    shy: ["Yeter ama {n}, kızardım!", "Hihi, utandım {n}…", "Dur dur, gülmekten ağlayacağım {n}!"],
  };
  // Boştayken ara sıra söylediği tatlı şeyler
  const CHATTER = ["Bir şey lazım olursa buradayım {n}.", "Gözüm sizde {n} 👀", "Bugün nasıl gidiyor {n}?",
                   "Hata kodunu yazın, ben bakarım {n}.", "Bana dokunursanız renk değiştiririm {n}!"];
  const PET_LINES = ["Hihi, gıdıklandım {n}!", "Ayy {n}, gıdık!", "Yine mi {n}? Hoşuma gidiyor!"];
  let petCount = 0, petReset = null;
  const SLEEP_MS = 5 * 60 * 1000; // bu kadar süre hiçbir şey yapılmazsa Dinyo uyur
  const BUSY = ["thinking", "searching", "answering", "speaking", "listening", "typing"];
  let lastAct = Date.now();
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
    face = document.createElement("div"); face.className = "face";
    face.setAttribute("role", "button"); face.tabIndex = 0;
    face.title = "Dokunun: tema rengi değişir";
    for (const side of ["l", "r"]) { const c = document.createElement("i"); c.className = "cheek " + side; face.append(c); }
    face.setAttribute("aria-label", "Dinyo'nun gözleri: dokunun, tema rengi değişir");
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
    if (next !== "sleep") lastAct = Date.now();   // sohbet tepkileri (düşünme, cevap...) de uykuyu geciktirir
    clearTimeout(back);
    mood = next;
    root.dataset.mood = next === "hello" ? "happy" : next;
    const b = document.createElement("b"); b.textContent = "Dinyo";
    let line = next === "hello" ? greeting() : LINES[next] || "";
    if (Array.isArray(line)) line = line[Math.floor(Math.random() * line.length)];
    const s = document.createElement("span"); s.textContent = line.replace("{n}", who).replace(/\s+([!…,.])/g, "$1").replace(/, +\s*/g, ", ");
    say.replaceChildren(b, s);
    if (next === "idle") look(0, 0);
    if (["thinking", "searching", "answering", "speaking"].includes(next)) look(0, 0);
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
    if (typeof Speaker !== "undefined" && Speaker.isPlaying()) Speaker.stop();   // yazmaya başlayınca asistan susar
    if (["thinking", "searching", "answering", "listening"].includes(mood)) return;
    if (mood !== "typing") set("typing");
    const p = caretPoint(input);
    lookAt(p.x, p.y, true);
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => mood === "typing" && set("idle"), 2000);
  }

  // Uyku: 5 dk etkileşim yoksa gözler kapanır; fare/klavye/dokunma ile uyanır
  function activity() {
    lastAct = Date.now();
    if (mood === "sleep") set("wake", 2500);
  }

  function napCheck() {
    if (root && mood !== "sleep" && !BUSY.includes(mood) && Date.now() - lastAct > SLEEP_MS
        && !(typeof Speaker !== "undefined" && Speaker.isPlaying())) {
      set("sleep");
      look(0, 0);
    }
    setTimeout(napCheck, 10000);
  }

  function track(ev) {
    lastMove = Date.now();
    if (!root || mood === "sleep" || ["thinking", "searching", "answering", "speaking", "typing"].includes(mood)) return;
    lookAt(ev.clientX, ev.clientY, false);
  }

  function blink() {
    if (root && !["happy", "sad", "sleep"].includes(root.dataset.mood)) {
      for (const e of eyes) e.classList.add("blink");
      setTimeout(() => eyes.forEach(e => e.classList.remove("blink")), 140);
    }
    setTimeout(blink, 2200 + Math.random() * 3800);
  }

  function wander() {              // fare ve klavye uzun süre kımıldamazsa yuvarlaklar etrafa bakar
    if (root && mood === "idle" && Date.now() - lastMove > 4000) look(Math.random() * 1.6 - 0.8, Math.random() - 0.5);
    setTimeout(wander, 2500 + Math.random() * 3000);
  }

  // Gözlere dokunma: gözler mutlu kısılır, tema rengi sıradakine geçer
  function pet() {
    const color = typeof Theme !== "undefined" ? Theme.next() : "";
    if (["thinking", "searching", "answering", "speaking", "listening"].includes(mood)) return;   // meşgulken yalnızca renk değişir
    petCount++;                                    // art arda dokunma: 3. dokunuşta utanır
    clearTimeout(petReset); petReset = setTimeout(() => { petCount = 0; }, 6000);
    if (petCount >= 3) { petCount = 0; set("shy", 2600); return; }
    set("pet", 2000);
    say.lastChild.textContent = PET_LINES[Math.floor(Math.random() * PET_LINES.length)].replace("{n}", who)
      .replace(/\s+([!…,.])/g, "$1");
    if (color) say.lastChild.textContent += ` (Renk: ${color})`;
  }

  function greeting() {            // günün saatine göre karşılama
    const h = new Date().getHours();
    const g = h < 6 ? "Gece çalışıyoruz demek" : h < 12 ? "Günaydın" : h < 18 ? "İyi günler" : "İyi akşamlar";
    return `${g} {n}! Ben Dinyo.`;
  }

  // Boşta tatlılıklar: ara sıra göz kırpar (tek göz) ve bir şeyler söyler
  function cute() {
    if (root && mood === "idle") {
      if (Math.random() < .5) {
        eyes[1].classList.add("wink");
        setTimeout(() => eyes[1].classList.remove("wink"), 450);
      } else {
        const l = CHATTER[Math.floor(Math.random() * CHATTER.length)];
        say.lastChild.textContent = l.replace("{n}", who).replace(/\s+([!…,.])/g, "$1");
      }
    }
    setTimeout(cute, 12000 + Math.random() * 14000);
  }

  function init(user) {
    const el = document.getElementById("dinyo");
    if (!el || root) return;
    who = nameOf(user && (user.call_name || user.username));
    build(el);
    face.addEventListener("click", pet);
    face.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pet(); } });
    set("hello", 3500);
    document.addEventListener("mousemove", track);
    for (const t of ["mousemove", "mousedown", "keydown", "touchstart", "wheel", "scroll"])
      document.addEventListener(t, activity, { passive: true, capture: true });
    napCheck(); setTimeout(cute, 15000);
    const input = document.getElementById("chat-input");
    if (input) for (const t of ["input", "keyup", "click", "focus"])
      input.addEventListener(t, () => { if (t === "input" || input.value) onTyping(input); });
    blink(); wander();
  }

  function rename(user) { who = nameOf(user.call_name || user.username); set(mood === "hello" ? "idle" : mood); }

  return { init, set, rename, name: () => who };
})();
