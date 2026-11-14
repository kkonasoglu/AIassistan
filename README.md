# Ofis Asistanı

Ofis içi yerel ağda (LAN) çalışan, tamamen offline, bilgi bankalı yapay zeka asistanı.
Python + FastAPI + sade HTML/JS arayüz. Dışarıya veri göndermez.

## Çalıştırma
1. İlk kurulumda (veya klasörü yeni bilgisayara kopyalayınca): `powershell -ExecutionPolicy Bypass -File setup.ps1`
2. Ollama kurulu olmalı: `ollama pull qwen2.5:3b` ve `ollama pull bge-m3`
3. `Ofis Asistanı.bat` (sunucuyu başlatır, tarayıcıyı açar) veya `start_server.bat` (sunucu penceresi görünür)
4. Diğer bilgisayarlar için (yönetici PowerShell, bir kez):
   `New-NetFirewallRule -DisplayName "Ofis Asistani" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Private`
5. Ağdaki bilgisayarlardan `https://<sunucu-ip>:8443` (ilk girişte sertifika uyarısı: kendi imzalı sertifika).
   Sunucunun IP'si değişirse: `.venv\Scripts\python.exe -m scripts.make_cert --force`

## Nasıl çalışır
- Bilgi, sistemin **kendi veritabanında** durur (`data/vectorstore`, ChromaDB). Klasöre dosya konmaz;
  kayıtları yalnızca adminler ekler/düzenler/siler: sohbet ekranında **Bilgi bankası** düğmesi
  (`/knowledge.html`). Silme gizlemedir, "Silinenleri göster" ile geri alınır. **JSON dışa aktar** yedek
  ve taşıma içindir. **Arama testi** gerçek bir cümlenin hangi kayıtla ve hangi mesafeyle eşleştiğini gösterir.
- Soru gelince: hata kodu varsa birebir eşleşme, yoksa anlamsal arama. Alakalı kayıt **anında kart olarak,
  birebir** gösterilir; üstüne kısa bir not eklenir (varsayılan hazır şablon, `OFIS_NOTE_MODE=llm` ile model).
- **Sohbetten öğrenme (yalnızca admin):** Admin sohbette bilgiyi anlatıp "bunu kaydet" der (ya da önce anlatır,
  sonra sadece "kaydet" yazar). Sistem metni başlık + numaralı adımlara böler, önizleme gösterir; admin "kaydet"
  (veya "evet") deyince bilgi bankasına eklenir, "iptal" derse atılır, kaydetmeden önce "başlık: yeni başlık"
  ile başlığı düzeltebilir. Standart kullanıcı "kaydet" derse yetki uyarısı alır, hiçbir şey kaydedilmez.
  Model metni yeniden yazmaz, yalnızca bölme noktalarını söyler; çıktıdan bölme işaretleri çıkarılınca özgün
  metin aynen elde edilmiyorsa (kelime eklenmiş/atılmış/değişmişse) reddedilip kural tabanlı düzenlemeye dönülür.
  `OFIS_LEARN_CONFIRM=false` önizlemeyi kapatır (önerilmez).
- **Bas-konuş:** Sohbet ekranında **F8** tuşunu (veya 🎙 düğmesini) basılı tutup konuşun, bırakınca ses sunucuda
  (faster-whisper, CPU, çevrimdışı) yazıya çevrilir ve gönderilir. Ses geçici dosyada çözülür ve hemen silinir,
  hiçbir yere gönderilmez. Mikrofon için sayfa `https://` ile açılmalı. Model (`small`, ~460 MB) ilk kullanımda
  indirilir (internet gerekir) ve `data/models` altına kaydedilir. Ayarlar: `OFIS_STT_MODEL` (base: daha hızlı,
  medium: daha doğru), `OFIS_STT_HOTWORDS` (alan terimleri). Sesle de "bunu kaydet" denebilir; yetki ve onay akışı aynıdır.
- Alakalı kayıt yoksa model kendi bilgisinden cevap **uydurmaz**: "kayıt bulamadım" der.
  Selamlaşma/teşekkür ve "3. adımı tekrar yaz" gibi devam soruları kodla anında cevaplanır.
- Hesaplar SQLite'ta (argon2), roller `admin`/`user`, en az 1 aktif admin kuralı. Sohbetler kullanıcıya özeldir.

> Devam notları, kararlar ve yol haritası: [NOTLAR.md](NOTLAR.md)

## Klasörler
- `app/api/` HTTP uç noktaları, `app/services/` iş mantığı, `app/db/` SQLite, `app/static/` arayüz
- `data/` tüm çalışma verisi (veritabanı, vektör deposu, sertifika): taşırken bu klasör de gider
- `tests/` otomatik testler: `.venv\Scripts\python.exe -m unittest discover tests`
- `scripts/` yardımcı betikler (`seed_example`: örnek kayıtları yükler, `make_cert`)

## Ayarlar
`.env` dosyasıyla değişir (öneki `OFIS_`), örnek: `OFIS_LLM_MODEL=qwen2.5:7b`, `OFIS_PORT=9443`.
Tüm ayarlar `app/core/config.py` içinde.
