"""Sohbet uç noktaları. Cevap SSE (Server-Sent Events) ile akar.

Akış (bilgi bankası açıkken):
  1. Arama yapılır (hata kodu varsa anında). Alakalı kayıt varsa `cards` olayıyla
     BİREBİR ve HEMEN gönderilir; kullanıcı modeli beklemez.
  2. Ardından model, kartların üstüne günlük dille kısa bir not yazar (`token` olayları).
  3. Kayıt yoksa: selamlaşma/teşekkür hazır cevapla, devam sorusu geçmişten, diğerleri
     "kayıt yok, internette aramamı ister misiniz?" diye sorulur; yalnızca "evet" denirse aranır (websearch).
     Model kendi bilgisinden uydurmaz; web sonuçları özetlenmeden birebir gösterilir.

Olay türleri (her biri `data: {json}` satırı):
  queue  {position}  -> not için sırada bekleniyor
  cards  {cards}     -> bilgi bankası kayıtları [{title, solution}]
  token  {text}      -> metnin yeni parçası
  done   {message_id}
  error  {message}
"""
import asyncio
import functools
import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import current_user
from app.core.config import settings
from app.services import (chat_store, intent, knowledge, learning, llm, llm_queue, memory,
                          notes, rag, websearch)
from app.services.users import User

router = APIRouter(prefix="/chat")


class MessageBody(BaseModel):
    message: str
    use_kb: bool = True


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _owned_or_404(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except chat_store.NotFound as e:
            raise HTTPException(404, str(e))
    return wrapper


@router.get("/conversations")
def list_conversations(user: User = Depends(current_user)):
    return chat_store.list_conversations(user.id)


@router.post("/conversations")
def create_conversation(user: User = Depends(current_user)):
    return {"id": chat_store.create_conversation(user.id)}


@router.get("/conversations/{conv_id}")
@_owned_or_404
def get_conversation(conv_id: int, user: User = Depends(current_user)):
    return chat_store.get_messages(user.id, conv_id)


@router.delete("/conversations/{conv_id}")
@_owned_or_404
def delete_conversation(conv_id: int, user: User = Depends(current_user)):
    chat_store.delete_conversation(user.id, conv_id)
    return {"ok": True}


async def _token_stream(messages: list[dict], system: str | None, stop: threading.Event,
                        max_tokens: int | None = None):
    """Bloklayan Ollama akışını ayrı iş parçacığında çalıştırıp async olarak verir."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def work():
        try:
            for piece in llm.chat_stream(messages, system, max_tokens=max_tokens):
                if stop.is_set():
                    break
                loop.call_soon_threadsafe(q.put_nowait, ("token", piece))
            loop.call_soon_threadsafe(q.put_nowait, ("end", None))
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, ("error", str(e)))

    loop.run_in_executor(None, work)
    while True:
        kind, value = await q.get()
        if kind == "token":
            yield value
        elif kind == "error":
            raise RuntimeError(value)
        else:
            return


@router.post("/conversations/{conv_id}/stream")
@_owned_or_404
def stream(conv_id: int, body: MessageBody, user: User = Depends(current_user)):
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Mesaj boş olamaz.")
    if len(text) > settings.max_message_chars:
        raise HTTPException(400, f"Mesaj en fazla {settings.max_message_chars} karakter olabilir.")

    chat_store.add_message(user.id, conv_id, "user", text)  # sahiplik de burada doğrulanır
    history = memory.window(user.id, conv_id)               # son mesaj = bu soru

    async def events():
        state = {"reply": "", "buffer": "", "cards": [], "saved": False}
        stop = threading.Event()
        loop = asyncio.get_running_loop()

        async def generate(messages, system, max_tokens=None, silent=False):
            """Modeli sıraya girerek çalıştırır; parçaları olay olarak verir.
            silent=True: parçalar gösterilmez, state["buffer"]'da toplanır (doğrulama için)."""
            position = llm_queue.position_if_wait()
            if position:  # beklemeye başlamadan önce kullanıcıya sırasını söyle
                yield _sse({"type": "queue", "position": position})
            async with llm_queue.slot():
                async for piece in _token_stream(messages, system, stop, max_tokens):
                    if silent:
                        state["buffer"] += piece
                    else:
                        state["reply"] += piece
                        yield _sse({"type": "token", "text": piece})

        def say(message: str) -> str:
            state["reply"] = message
            return _sse({"type": "token", "text": message})

        async def run(fn, *args):
            return await loop.run_in_executor(None, fn, *args)

        def previous_info() -> str:
            """"Bunu kaydet" tek başına yazıldıysa: konuşmadaki son uzun (bilgi içeren) mesaj."""
            for m in reversed(chat_store.recent_messages(user.id, conv_id, 12)[:-1]):
                if m["role"] == "user" and len(m["content"].split()) >= learning.MIN_WORDS:
                    stripped = intent.parse_learn_command(m["content"])
                    return stripped if stripped is not None else m["content"]
            return ""

        async def save_record(title: str, solution: str):
            """Kaydı bilgi bankasına ekler, kart + onay mesajı üretir."""
            await run(knowledge.add, title, solution, user.username)
            state["cards"] = [{"title": title, "solution": solution, "kind": "saved"}]
            yield _sse({"type": "cards", "cards": state["cards"]})
            yield say(f'Kaydedildi: "{title}". Artık sohbette aranabilir.')

        async def web_offer(fallback: str):
            """Bilgi bankasında cevap yok: önce "yok" de, internette aramayı SOR (kullanıcı onaylamadan aranmaz)."""
            if settings.web_search:
                yield say(f"{fallback} {settings.web_offer_question}")
            else:
                yield say(fallback)

        def pending_web_question() -> str | None:
            """Son asistan mesajı internet teklifiyse, teklife konu olan kullanıcı sorusunu döner."""
            if not settings.web_search:
                return None
            msgs = chat_store.recent_messages(user.id, conv_id, 4)   # son eleman = şimdiki mesaj
            if (len(msgs) >= 3 and msgs[-2]["role"] == "assistant"
                    and msgs[-2]["content"].endswith(settings.web_offer_question)
                    and msgs[-3]["role"] == "user"):
                return msgs[-3]["content"]
            return None

        async def web_search_now(question: str):
            """Kullanıcı "evet" dedi: ara, sonuçları birebir kart olarak göster."""
            yield _sse({"type": "status", "text": "İnternette aranıyor…"})
            results = await run(websearch.search, question)
            if not results:
                yield say(settings.web_failed_note.strip())
                return
            state["cards"] = [{"title": r["title"], "solution": r["snippet"], "url": r["url"],
                               "kind": "web"} for r in results]
            yield _sse({"type": "cards", "cards": state["cards"]})
            yield say(settings.web_note)

        async def learn(content: str):
            """Yalnızca admin: anlatılan bilgiyi düzenler, önizleme gösterir (veya doğrudan kaydeder)."""
            if not user.is_admin:   # yetki, rol veritabanından taze okunarak kontrol edilir
                yield say(settings.learn_denied_message)
                return
            if len(content.split()) < learning.MIN_WORDS:
                content = previous_info()
            if len(content.split()) < learning.MIN_WORDS:
                yield say(settings.learn_need_info_message)
                return
            position = llm_queue.position_if_wait()
            if position:
                yield _sse({"type": "queue", "position": position})
            yield _sse({"type": "status", "text": "Bilgi düzenleniyor…"})
            async with llm_queue.slot():
                s = await run(learning.structure, content)
            if await run(knowledge.title_exists, s["title"]):
                yield say(f'"{s["title"]}" başlığında bir kayıt zaten var. Mevcut kaydı '
                          "Bilgi bankası sayfasından düzenleyebilirsiniz.")
                return
            if not settings.learn_confirm:
                async for ev in save_record(s["title"], s["solution"]):
                    yield ev
                return
            await run(learning.save_draft, user.id, conv_id, s["title"], s["solution"])
            state["cards"] = [{"title": s["title"], "solution": s["solution"], "kind": "draft"}]
            yield _sse({"type": "cards", "cards": state["cards"]})
            yield say(settings.learn_preview_message if s["by"] == "ai"
                      else settings.learn_preview_basic_message)

        try:
            draft = await run(learning.get_draft, user.id, conv_id) if user.is_admin else None
            command = intent.parse_learn_command(text)
            web_q = await run(pending_web_question) if draft is None else None
            if draft and intent.is_cancel(text):
                await run(learning.clear_draft, conv_id)
                yield say("Tamam, kaydetmedim.")
            elif draft and intent.is_confirm(text):
                try:
                    async for ev in save_record(draft["title"], draft["solution"]):
                        yield ev
                    await run(learning.clear_draft, conv_id)
                except ValueError as e:      # örn. aynı başlık bu arada eklendi
                    await run(learning.clear_draft, conv_id)
                    yield say(str(e))
                except ConnectionError:      # Ollama kapalı: taslak korunur, tekrar denenebilir
                    yield say("Kaydedemedim: yerel yapay zeka servisi (Ollama) çalışmıyor. "
                              "Ollama'yı başlatıp tekrar \"kaydet\" yazın.")
            elif draft and intent.parse_title_override(text):
                title = intent.parse_title_override(text)
                if len(title) > knowledge.MAX_TITLE:
                    yield say(f"Başlık en fazla {knowledge.MAX_TITLE} karakter olabilir.")
                elif await run(knowledge.title_exists, title):
                    yield say(f'"{title}" başlığında bir kayıt zaten var, başka bir başlık yazın.')
                else:
                    await run(learning.save_draft, user.id, conv_id, title, draft["solution"])
                    state["cards"] = [{"title": title, "solution": draft["solution"], "kind": "draft"}]
                    yield _sse({"type": "cards", "cards": state["cards"]})
                    yield say(settings.learn_preview_basic_message)
            elif web_q and intent.is_web_yes(text):
                async for ev in web_search_now(web_q):
                    yield ev
            elif web_q and intent.is_web_no(text):
                yield say(settings.web_declined_message)
            elif command is not None:
                async for ev in learn(command):
                    yield ev
            elif not body.use_kb:  # serbest sohbet (bilgi bankası kapalı)
                async for ev in generate(history, None):
                    yield ev
            else:
                hits = await loop.run_in_executor(None, rag.search, text)
                if hits:
                    # 1) Kayıt HEMEN, birebir: model beklenmez
                    state["cards"] = [{"title": h["title"], "solution": h["solution"]} for h in hits]
                    yield _sse({"type": "cards", "cards": state["cards"]})
                    # 2) Kısa not. Varsayılan: hazır şablon, anında. "llm" modunda model yazar,
                    #    çıktı doğrulanır; geçersiz/başarısızsa şablona dönülür (kart zaten verildi)
                    note = None
                    if settings.note_mode == "llm":
                        note_msgs = [*history[:-1],
                                     {"role": "user", "content": rag.build_note_message(text, hits)}]
                        try:
                            async for ev in generate(note_msgs, settings.note_prompt,
                                                     settings.note_max_tokens, silent=True):
                                yield ev  # yalnızca "queue" olayı gelir
                            note = notes.clean_llm_note(state["buffer"], hits)
                        except Exception:
                            note = None
                    yield say(note or notes.template_note(hits))
                elif intent.smalltalk(text):
                    yield say(intent.personalize(intent.smalltalk(text), user.call_name))
                elif await loop.run_in_executor(None, rag.count) == 0:
                    # Kayıt bulunamamasının sebebi eşleşmeme değil, bankanın boş olması
                    async for ev in web_offer(settings.empty_kb_message):
                        yield ev
                elif any(m["role"] == "assistant" for m in history[:-1]) \
                        and memory.looks_like_followup(text):
                    # Devam sorusu ("3. adımı tekrar yaz"): önceki cevap zaten geçmişte
                    step = memory.step_from_previous(history[:-1], text)
                    if step:  # istenen adım önceki cevapta var: modele gerek yok
                        yield say(step)
                    else:
                        follow = [*history[:-1],
                                  {"role": "user", "content": f"{text}\n{settings.lang_reminder}"}]
                        async for ev in generate(follow, settings.followup_prompt):
                            yield ev
                else:
                    async for ev in web_offer(settings.no_kb_message):
                        yield ev

            mid = chat_store.add_message(user.id, conv_id, "assistant", state["reply"],
                                         [c["title"] for c in state["cards"]], state["cards"])
            state["saved"] = True
            yield _sse({"type": "done", "message_id": mid})
        except Exception as e:
            yield _sse({"type": "error", "message": f"Cevap üretilemedi: {e}"})
        finally:
            stop.set()  # istemci koptuysa modeli de durdur
            if (state["reply"] or state["cards"]) and not state["saved"]:
                try:  # yarım kalan cevabı da sakla
                    chat_store.add_message(user.id, conv_id, "assistant", state["reply"],
                                           [c["title"] for c in state["cards"]], state["cards"])
                except Exception:
                    pass

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no"})
