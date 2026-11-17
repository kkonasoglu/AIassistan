# Proje Notları (başka bilgisayardan devam etmek için)

Bu dosya, projeyi başka bir PC'de (veya yeni bir Claude oturumunda) kaldığı yerden sürdürmek içindir.
Yeni oturumda Claude'a şunu söyleyin: **"NOTLAR.md ve README.md'yi oku, kaldığımız yerden devam edelim."**

## 1. Çalışma tarzı (çok önemli)
- Adım adım ilerle. Her büyük adımdan önce ne/neden/nasıl anlat, **kullanıcı onaylamadan sonraki adıma geçme**.
- Mentor gibi anlat. Türkçe yaz.
- Test et ve dürüst raporla: neyin doğrulandığını, neyin doğrulanmadığını açıkça söyle.
- Canlı testleri kullanıcının gerçek sunucusuna (8443) ve gerçek verisine dokunmadan, geçici veri klasörü + farklı portla (örn. 9443) yap.

## 2. Proje özeti
Tamamen yerel/offline ofis yapay zeka asistanı. Veri dışarı çıkmaz.
- Ofis içi ağda (LAN) web uygulaması: Python FastAPI + sade HTML/JS, HTTPS (kendi imzalı sertifika, mikrofon için gerekli), port 8443.
- Model: Ollama `qwen2.5:3b` (CPU), gömme modeli `bge-m3`. İlk PC: 15,9 GB RAM, Windows 11, GPU yok.
- Sunucu Windows varsayıldı. Docker / Windows servisi kararı ertelendi.
- Tek klasör, taşınabilir. Çalışma verisi `data/` içinde (git'e girmez).

## 3. Verilen kararlar
- Roller: `admin` / `user`. Yalnızca admin bilgi ekler/düzenler/siler. Silme = gizleme (geri alınabilir). Audit log YOK.
- Her zaman en az 1 aktif admin kalmalı; admin rolü devredilebilir.
- Dosya yükleme YOK. Bilgi yalnızca yetkili kişiyle girer: admin paneli veya sohbette "bunu kaydet".
- Bilgi, sistemin kendi veritabanında (ChromaDB) durur; klasöre dosya konmaz.
- Öğrenme akışı: admin "kaydet" der → sistem "Hata başlığı + adım adım çözüm" olarak düzenler → önizleme → admin onaylar → kaydedilir. Personel "kaydet" derse kaydedilmez, yetki uyarısı alır. (`OFIS_LEARN_CONFIRM=false` önizlemeyi kapatır, önerilmez.)
- Cevap davranışı: günlük dili anlasın; alakalı kayıt varsa **anında kart olarak birebir** göstersin; kayıt yoksa uydurmasın, "kayıt bulamadım" desin (bu durumda model hiç çağrılmaz).
- Kullanıcılar ve sohbet geçmişi SQLite'ta; her kullanıcının sohbeti kendine özel.

## 4. Yapılanlar (hepsi çalışır, 160 test geçti)
1. Klasör yapısı, kurulum (`setup.ps1`), HTTPS sertifikası.
2. Web uygulaması: giriş, roller, kullanıcı yönetimi (admin paneli), sohbet + akışlı cevap, sohbet geçmişi, LLM kuyruğu.
3. RAG: hata kodu birebir eşleşme + anlamsal arama, eşikler `max_distance=0.45`, `source_margin=0.08`.
4. Bilgi bankası yönetimi (`/knowledge.html`): ekle/düzenle/gizle/geri al/ara/JSON dışa aktar/Arama testi.
5. Sohbetten öğrenme ("bunu kaydet") + onay + yetki kontrolü.
7. **İnternet araması (DuckDuckGo):** kayıt yoksa "internette aramamı ister misiniz?" diye SORAR, yalnızca "evet" denirse arar (kullanıcı kararı; ilk sürüm otomatikti, sonra soruya çevrildi). Bekleyen soru konuşma geçmişinden bulunur (son asistan mesajı teklifle bitiyorsa). Kapalıyken (`OFIS_WEB_SEARCH=false`) soru da sorulmaz. Sonuçlar birebir "web" kartı, model çağrılmaz. Gizlilik: yalnızca temizlenmiş soru gider. Kapatma: `OFIS_WEB_SEARCH=false`. `app/services/websearch.py`. DuckDuckGo aralıklı boş/hata döner: bir kez yeniden dener, yine olmazsa "internet araması da sonuç vermedi" der (sessiz kalmaz). Anlık değerler (dolar kuru vb.) için sayı söylemez, kaynak kartları verir; sonuçları modele özetletmek bilinçli olarak YAPILMADI (3B model uyduruyor), daha güçlü modelle denenebilir.
6. **Bas-konuş (Whisper):** F8 tuşu veya 🎙 düğmesi basılı tut → sunucuda faster-whisper (`small`, CPU) → yazı → otomatik gönder. Ses geçici dosyada çözülür ve silinir.

## 5. Henüz doğrulanmayanlar (kullanıcı denemeli)
- Türkçe konuşma tanıma doğruluğu (test sesi İngilizceydi). Kötüyse: `OFIS_STT_HOTWORDS="Mysoft konnektör e-Fatura e-İmza KNK"` veya `OFIS_STT_MODEL=medium`.
- Tarayıcı arayüzü gerçek tarayıcıda (mikrofon izni, F8 basılı tutma) görülmedi.
- Eşikler gerçek bilgi bankasıyla ayarlanmadı → admin "Arama testi" ile ölç.
- Gerçek bilgi bankası şu an boş.

## 6. Yol haritası (onay bekliyor, sırayla)
1. ~~İnternet araması~~ (yapıldı, bkz. Yapılanlar 7).
2. Sunucuda otomatik başlatma (Windows servisi/Görev Zamanlayıcı; Docker kararı ertelendi), yedekleme/geri yükleme (JSON içe aktarma henüz yok).
3. Gerçek verilerle eşik ve hotword ayarı. Güçlü sunucuya geçince daha büyük model (`OFIS_LLM_MODEL=qwen2.5:7b`) ve gerekirse `OFIS_NOTE_MODE=llm`.

## 7. Başka PC'de kurulum
1. Python, Git, Ollama kur; `ollama pull qwen2.5:3b` ve `ollama pull bge-m3`.
2. `git clone` → `powershell -ExecutionPolicy Bypass -File setup.ps1`.
3. `Ofis Asistanı.bat` ile başlat; ilk açılışta admin hesabı oluşturulur. Whisper modeli ilk kullanımda iner (~460 MB, internet gerekir).
4. Eski verileri taşımak için eski PC'deki `data/` klasörünü kopyala (kullanıcılar, sohbetler, bilgi bankası). IP değiştiyse: `.venv\Scripts\python.exe -m scripts.make_cert --force`.
5. Diğer PC'ler için güvenlik duvarı kuralı: README'deki `New-NetFirewallRule ...` komutu.

- Arayüz: sade/kurumsal mavi, sohbet tüm ekranı kullanır, açık/koyu tema sisteme uyar. "Bilgi bankasından cevapla" kutusu kaldırıldı: bilgi bankası her zaman kullanılır (sunucudaki `use_kb=false` serbest sohbet yolu testler için duruyor, arayüz kullanmıyor).

## 8. Teknik tuzaklar
- Kodda değişiklik yapınca çalışan sunucu yeni kodu almaz: kapatıp `Ofis Asistanı.bat` ile yeniden aç ("yeni özellik çalışmıyor" şikâyetinin ilk nedeni budur). (tekrar düşülmesin)
- `av` paketi `>=14,<17` olmalı; av 19, faster-whisper ile uyumsuz.
- 3B model: notta adımları tekrarlıyor, kod uyduruyor → varsayılan `note_mode=template`. "Bulamazsam söyle" talimatı iyi kayıt varken bile reddettiriyor → karar kodda.
- Python/Bash heredoc içinde ters eğik çizgi bozuluyor; düzenlemeleri dosya düzenleme aracıyla yap.
- Testler: `.venv\Scripts\python.exe -m unittest discover -s tests -t .` (gerçek model/ağ gerektirmez; `tests/__init__.py` Whisper ön yüklemeyi kapatır).
- Kod haritası için README "Klasörler" bölümüne bakın; ayarların hepsi `app/core/config.py` içinde.
