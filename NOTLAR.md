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

## 4. Yapılanlar (hepsi çalışır, 196 test geçti)
1. Klasör yapısı, kurulum (`setup.ps1`), HTTPS sertifikası.
2. Web uygulaması: giriş, roller, kullanıcı yönetimi (admin paneli), sohbet + akışlı cevap, sohbet geçmişi, LLM kuyruğu.
3. RAG: hata kodu birebir eşleşme + anlamsal arama, eşikler `max_distance=0.45`, `source_margin=0.08`.
4. Bilgi bankası yönetimi (`/knowledge.html`): ekle/düzenle/gizle/geri al/ara/JSON dışa aktar/Arama testi.
5. Sohbetten öğrenme ("bunu kaydet") + onay + yetki kontrolü.
7. **İnternet araması (DuckDuckGo):** kayıt yoksa "internette aramamı ister misiniz?" diye SORAR, yalnızca "evet" denirse arar (kullanıcı kararı; ilk sürüm otomatikti, sonra soruya çevrildi). Bekleyen soru konuşma geçmişinden bulunur (son asistan mesajı teklifle bitiyorsa). Kapalıyken (`OFIS_WEB_SEARCH=false`) soru da sorulmaz. Sonuçlar birebir "web" kartı, model çağrılmaz. Gizlilik: yalnızca temizlenmiş soru gider. Kapatma: `OFIS_WEB_SEARCH=false`. `app/services/websearch.py`. DuckDuckGo aralıklı boş/hata döner: bir kez yeniden dener, yine olmazsa "internet araması da sonuç vermedi" der (sessiz kalmaz). Anlık değerler (dolar kuru vb.) için sayı söylemez, kaynak kartları verir; sonuçları modele özetletmek bilinçli olarak YAPILMADI (3B model uyduruyor), daha güçlü modelle denenebilir.
6. **Bas-konuş (Whisper):** F8 tuşu veya 🎙 düğmesi basılı tut → sunucuda faster-whisper (`small`, CPU) → yazı → otomatik gönder. Ses geçici dosyada çözülür ve silinir.

8. **Sesli yanıt (TTS):** Piper (`app/services/tts.py`, `POST /api/voice/speak` → WAV), Türkçe erkek ses `tr_TR-dfki-medium` (F0 ölçümü ~105 Hz = erkek), 9,6 sn cevap ~0,6 sn'de üretilir. Önyüz `app/static/speak.js` (`Speaker`): "Sesli yanıt" kutusu (localStorage `dinyo-speak`), cevaplarda 🔊, yeni soru/yazma/mikrofon sustirir, Dinyo `speaking` durumu. Hata kodları okunurken harf harf (KNK-204 → "K N K, 204"), adımlar "1. adım:" diye okunur (telaffuz gerçek kulakla DOĞRULANMADI).

9. **Emir/komut anlama:** `app/services/commands.py` (kodla, model yok). Kesin komutlar (`quick_reply`: söyle/de ki/şunu söyle:, sen kimsin, adımı söyle, ne yapabilirsin, yardım et, saat kaç, bugün günlerden ne, tekrar et) bilgi bankasından ÖNCE; belirsiz biçimler (`weak_say`: "X de", "X yaz", en çok 6 sözcük, bağlaç içermez) YALNIZCA bilgi bankası eşleşmesi yokken ve selamlaşmadan ÖNCE denenir ("merhaba de" selamlaşma sanılmasın). Devam soruları (`memory.looks_like_followup`) komut sayılmaz. Serbest komutlar için ("şaka yap", "çevir") model kullanımı bilerek EKLENMEDİ (3B model uyduruyor); istenirse sınırlı bir "komut modu" eklenebilir.

## 5. Henüz doğrulanmayanlar (kullanıcı denemeli)
- **SES LİSANSI (karar kullanıcıda):** varsayılan ses modeli (dfki) **CC BY-NC-SA 4.0** = ticari olmayan kullanım. Şirket içi destek aracında kullanmanın bu kapsama girip girmediğine kullanıcı/şirket karar vermeli; sorunluysa `OFIS_TTS_VOICE` ile başka Piper sesi, `OFIS_TTS_ENABLED=false` ile kapatma, ya da Windows'un yerleşik sesi (örn. Microsoft Tolga) tarayıcı `speechSynthesis` ile alternatif yazılabilir. Model repoya KONMAZ (data/models gitignore), kullanıcı sunucuda kendi indirir.
- Sesin Türkçe telaffuz kalitesi (özellikle KNK-204, e-Fatura gibi terimler) gerçek kulakla denenmedi; yalnız perde (erkek) ve hız ölçüldü.
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

- **Ad: "Teknik Destek Asistanı Dinyo".** Arayüz tek tema: SİYAH (cyan vurgu). Karakter "Dinyo" = `app/static/dinyo.js`: robot, iki neon mavisi yuvarlak (göz/gözbebeği yok). Fareyi ve textarea'daki imleç konumunu izler, göz kırpar; durumlar idle/typing/thinking/searching/answering/happy/confused/sad/listening, `Dinyo.set(durum, ms)` ile chat.js/voice.js tetikler. Kullanıcıya GERÇEK adıyla hitap eder: `users.display_name` sütunu (eski veritabanına otomatik eklenir; `User.call_name` = görünen adın ilk sözcüğü, yoksa kullanıcı adı); kurulumda, ilk girişte (pencere, oturumda bir kez), sağ üst addan ya da admin panelinden girilir; sunucuda selamlaşma cevaplarına `intent.personalize` ad ekler. Gözlere tıklama = mutlu kısılma + tema rengi değişimi (`Theme` in app.js, localStorage `dinyo-color`). DİKKAT: `const Dinyo/Theme` pencerede `window.Dinyo` olarak GÖRÜNMEZ; varlık kontrolü `typeof Dinyo !== "undefined"` ile yapılır (`window.Dinyo` yazılırsa tepkiler sessizce çalışmaz; bu hata yaşandı). Sol sohbet paneli ☰ ile açılır/kapanır (localStorage `dinyo-side`). Klasör/bat dosyası adları ("Ofis Asistanı.bat") bilerek değiştirilmedi. Sohbet tüm ekranı kullanır. "Bilgi bankasından cevapla" kutusu kaldırıldı: bilgi bankası her zaman kullanılır (sunucudaki `use_kb=false` serbest sohbet yolu testler için duruyor, arayüz kullanmıyor).

## 8. Teknik tuzaklar
- Kodda değişiklik yapınca çalışan sunucu yeni kodu almaz: kapatıp `Ofis Asistanı.bat` ile yeniden aç ("yeni özellik çalışmıyor" şikâyetinin ilk nedeni budur). (tekrar düşülmesin)
- `av` paketi `>=14,<17` olmalı; av 19, faster-whisper ile uyumsuz.
- 3B model: notta adımları tekrarlıyor, kod uyduruyor → varsayılan `note_mode=template`. "Bulamazsam söyle" talimatı iyi kayıt varken bile reddettiriyor → karar kodda.
- Python/Bash heredoc içinde ters eğik çizgi bozuluyor; düzenlemeleri dosya düzenleme aracıyla yap.
- Testler: `.venv\Scripts\python.exe -m unittest discover -s tests -t .` (gerçek model/ağ gerektirmez; `tests/__init__.py` Whisper ön yüklemeyi kapatır).
- Kod haritası için README "Klasörler" bölümüne bakın; ayarların hepsi `app/core/config.py` içinde.

10. **Tatlı tepkiler + ses seçimi:** Dinyo uyku modu (5 dk), utanma/kalp göz/göz kırpma/boşta konuşma (`dinyo.js`). Ses seçimi Erkek/Kadın: kadın = aynı dfki modeli, perde `OFIS_TTS_FEMALE_PITCH` (1.4) kat yükseltilir (gerçek kadın Türkçe çevrimdışı ses bulunamadı; F0 ~110 -> ~155 Hz). Tercih tarayıcıda (dinyo-voice).
