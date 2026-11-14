"""LLM servisi: Ollama ile konuşan tek yer.

Arayüz ve diğer servisler modele doğrudan değil, bu dosya üzerinden ulaşır.
"""
from collections.abc import Iterator

import ollama

from app.core.config import settings

_client = ollama.Client(host=settings.ollama_host)


def chat_stream(messages: list[dict], system: str | None = None,
                max_tokens: int | None = None) -> Iterator[str]:
    """Mesaj geçmişini modele gönderir, cevabı parça parça (kelime kelime) üretir.

    messages örneği: [{"role": "user", "content": "Merhaba"}]
    system: verilmezse varsayılan sistem talimatı kullanılır.
    max_tokens: cevabın üst sınırı (kısa notlar için; hem süreyi hem gevezeliği keser).
    """
    full = [{"role": "system", "content": system or settings.system_prompt}, *messages]
    options = {"temperature": settings.temperature}
    if max_tokens:
        options["num_predict"] = max_tokens
    for chunk in _client.chat(model=settings.llm_model, messages=full, stream=True,
                              keep_alive=settings.keep_alive, options=options):
        yield chunk["message"]["content"]


def complete_text(system: str, user: str, max_tokens: int = 700) -> str:
    """Akışsız, düz metin cevap (bilgiyi bölümlere ayırmak için). Sabit tohum: tekrarlanabilir."""
    resp = _client.chat(
        model=settings.llm_model, stream=False, keep_alive=settings.keep_alive,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        options={"temperature": 0.0, "num_predict": max_tokens, "seed": 42},
    )
    return resp["message"]["content"]


def status() -> dict:
    """Ollama çalışıyor mu, gerekli modeller indirilmiş mi?"""
    try:
        installed = {m.model for m in _client.list().models}
    except Exception:
        return {"ollama": False, "llm_ready": False, "embed_ready": False}

    def has(name: str) -> bool:
        return name in installed or f"{name}:latest" in installed

    return {"ollama": True, "llm_ready": has(settings.llm_model),
            "embed_ready": has(settings.embed_model)}


def embed(texts: list[str]) -> list[list[float]]:
    """Metinleri sayısal vektörlere çevirir (anlamca benzer metinler yakın vektör olur)."""
    return _client.embed(model=settings.embed_model, input=texts,
                         keep_alive=settings.keep_alive)["embeddings"]
