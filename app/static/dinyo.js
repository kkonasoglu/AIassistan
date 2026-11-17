// Dinyo: sohbetin karşısındaki karakter. İki göz; fareyi izler, göz kırpar, olaylara tepki verir.
// Sohbet kodu yalnızca Dinyo.set("durum") çağırır; karakter yoksa/hata verirse sohbet etkilenmez.
const Dinyo = (() => {
  const LINES = {
    idle: "Buradayım, yazabilirsiniz.", typing: "Sizi okuyorum…", thinking: "Düşünüyorum…",
    searching: "İnternette bakıyorum…", happy: "Buldum!", confused: "Hmm, bunu bulamadım…",
    sad: "Bir sorun oldu…", listening: "Sizi dinliyorum…", hello: "Merhaba! Ben Dinyo.",
  };
  const MAX_X = 11, MAX_Y = 13;
  let root, say, eyes = [], mood = "idle", back = null, lastMove = 0, typingTimer = null;

  function build(el) {
    root = el;
    root.classList.add("dinyo");
    const face = document.createElement("div"); face.className = "face"; face.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 2; i++) {
      const eye = document.createElement("div"); eye.className = "eye " + (i ? "right" : "left");
      const pupil = document.createElement("div"); pupil.className = "pupil";
      const lid = document.createElement("div"); lid.className = "lid";
      const cheek = document.createElement("div"); cheek.className = "cheek";
      eye.append(pupil, lid, cheek); face.append(eye); eyes.push({ eye, pupil });
    }
    say = document.createElement("div"); say.className = "say";
    root.append(face, say);
    set("hello", 3000);
  }

  function look(dx, dy) {          // -1..1 aralığında bakış yönü
    for (const { pupil } of eyes) pupil.style.transform = `translate(${dx * MAX_X}px, ${dy * MAX_Y}px)`;
  }

  function set(next, ms) {
    if (!root) return;
    clearTimeout(back);
    mood = next;
    root.dataset.mood = next === "hello" ? "happy" : next;
    say.replaceChildren();
    const name = document.createElement("b"); name.textContent = "Dinyo";
    const line = document.createElement("span"); line.textContent = LINES[next] || "";
    say.append(name, line);
    if (next === "typing") look(0, 1); else if (next === "idle") look(0, 0);
    if (ms) back = setTimeout(() => set("idle"), ms);
  }

  function track(ev) {
    lastMove = Date.now();
    if (!root || ["thinking", "searching"].includes(mood)) return;   // bu durumlarda gözler kendi başına gezinir
    const r = root.querySelector(".face").getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const dx = ev.clientX - cx, dy = ev.clientY - cy, d = Math.hypot(dx, dy) || 1;
    const k = Math.min(1, d / 220);                                  // uzaktayken tam, yakındayken az kayar
    look(dx / d * k, dy / d * k);
  }

  function blink() {
    if (root && root.dataset.mood !== "happy") {
      for (const { eye } of eyes) eye.classList.add("blink");
      setTimeout(() => eyes.forEach(({ eye }) => eye.classList.remove("blink")), 130);
    }
    setTimeout(blink, 2200 + Math.random() * 3800);
  }

  function wander() {              // fare uzun süre kımıldamazsa gözler etrafa bakar
    if (root && mood === "idle" && Date.now() - lastMove > 4000) look(Math.random() * 1.6 - 0.8, Math.random() - 0.5);
    setTimeout(wander, 2500 + Math.random() * 3000);
  }

  function init() {
    const el = document.getElementById("dinyo");
    if (!el || root) return;
    build(el);
    document.addEventListener("mousemove", track);
    const input = document.getElementById("chat-input");
    if (input) input.addEventListener("input", () => {
      if (mood === "thinking" || mood === "searching" || mood === "listening") return;
      set("typing");
      clearTimeout(typingTimer);
      typingTimer = setTimeout(() => mood === "typing" && set("idle"), 1800);
    });
    blink(); wander();
  }

  return { init, set };
})();
