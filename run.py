"""Sunucuyu başlatır:  .venv\\Scripts\\python.exe run.py  (veya start_server.bat)"""
import sys

import uvicorn

# Konsol kod sayfası Türkçe karakterleri yazamazsa çökmesin
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import settings  # noqa: E402
from app.services.certs import ensure_cert, local_ips

if __name__ == "__main__":
    crt, key = ensure_cert()
    print("\nOfis Asistanı sunucusu başlıyor. Ofis ağından şu adreslerden açılır:")
    for ip in local_ips():
        if ip != "127.0.0.1":
            print(f"   https://{ip}:{settings.port}")
    print(f"   https://localhost:{settings.port}  (bu bilgisayardan)")
    print("İlk girişte tarayıcı sertifika uyarısı verir (kendi imzalı sertifika): "
          "'Gelişmiş > Devam et' deyin.\nDurdurmak için Ctrl+C.\n")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port,
                ssl_certfile=str(crt), ssl_keyfile=str(key))
