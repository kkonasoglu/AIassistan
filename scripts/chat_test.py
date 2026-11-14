"""Terminalden LLM testi. Çalıştırma (proje klasöründen):
    C:\\venvs\\ofis\\Scripts\\python.exe -m scripts.chat_test
"""
import sys

from app.services.llm import chat_stream

sys.stdout.reconfigure(encoding="utf-8")

history: list[dict] = []
print("Ofis Asistanı terminal testi. Çıkmak için boş satır + Enter.\n")
while True:
    user = input("Sen: ").strip()
    if not user:
        break
    history.append({"role": "user", "content": user})
    print("Asistan: ", end="", flush=True)
    reply = ""
    for piece in chat_stream(history):
        print(piece, end="", flush=True)
        reply += piece
    print("\n")
    history.append({"role": "assistant", "content": reply})
