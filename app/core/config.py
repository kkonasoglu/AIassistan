"""Uygulama ayarları.

Tüm "değiştirilebilir" değerler burada durur. Varsayılanlar proje klasörüne göredir,
böylece klasörü kopyalayınca her şey birlikte taşınır. Değiştirmek için proje
klasörüne bir .env dosyası koyun. Örnek:
    OFIS_LLM_MODEL=qwen2.5:7b
    OFIS_PORT=9443
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OFIS_", env_file=BASE_DIR / ".env")

    # --- Web sunucusu ---
    host: str = "0.0.0.0"          # tüm ağ kartlarını dinle (LAN erişimi)
    port: int = 8443
    max_concurrent_llm: int = 1    # aynı anda modele giden istek sayısı (CPU'da 1 önerilir)
    expected_users: int = 5        # bilgi amaçlı; kuyruk tasarımında kullanılacak

    # --- Konuşma tanıma (bas-konuş): faster-whisper, sunucuda, CPU ---
    stt_model: str = "small"       # tiny/base/small/medium. small: Türkçe için dengeli (6 sn ses ~3 sn)
    stt_language: str = "tr"
    stt_threads: int = 0           # 0 = otomatik
    stt_preload: bool = True       # sunucu açılırken modeli arka planda yükle (ilk kullanıcı beklemesin)
    stt_max_bytes: int = 8 * 1024 * 1024   # tek kayıt üst sınırı (~60 sn konuşma bundan çok küçüktür)
    # İsteğe bağlı: alan terimlerini tanımaya yardım eder, örn. "Mysoft konnektör e-Fatura e-İmza KNK".
    # Boş bırakıldı: Türkçe doğruluğu gerçek sesle test edilmeden ayarlanmamalı.
    stt_hotwords: str = ""
    stt_models_path: Path | None = None    # modelleri başka klasörde tutmak için; boşsa data/models

    # --- Sesli yanıt (metinden konuşmaya): Piper, sunucuda, CPU, çevrimdışı. Türkçe ERKEK ses ---
    # LİSANS: varsayılan ses CC BY-NC-SA 4.0 (ticari olmayan kullanım). Şirket içi kullanım için kullanıcı karar verir.
    tts_enabled: bool = True
    tts_voice: str = "tr_TR-dfki-medium"   # Piper ses adı (Hugging Face rhasspy/piper-voices); ilk kullanımda indirilir
    tts_length_scale: float = 1.0          # konuşma hızı: <1 hızlı, >1 yavaş
    tts_max_chars: int = 700               # tek seferde okunacak üst sınır (uzun cevaplar cümle sınırından kesilir)
    tts_preload: bool = True               # sunucu açılırken modeli arka planda yükle
    tts_models_path: Path | None = None    # boşsa data/models/tts

    # --- LLM ---
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:3b"
    system_prompt: str = (
        "Sen bir ofis destek asistanısın. Daima Türkçe, kısa ve adım adım cevap ver. "
        "Bilmediğin bir şeyi uydurma; bilmiyorsan bilmediğini söyle."
    )

    # --- RAG ---
    embed_model: str = "bge-m3"
    top_k: int = 4               # soru başına getirilecek kayıt sayısı
    # Eşikler az sayıda örnek kayıtla ölçüldü: alakalı sorular en fazla 0.40, alakasız ama
    # genel cümleler 0.457'ye kadar yaklaşabiliyor. Gerçek bilgi bankası dolunca admin
    # panelindeki "Arama testi" ile yeniden ayarlanmalı.
    max_distance: float = 0.45   # bundan uzak (alakasız) kayıtlar kullanılmaz
    source_margin: float = 0.08  # en iyi eşleşmeden bu kadar uzaktan fazla olan kayıtlar elenir
    temperature: float = 0.2     # düşük = daha tutarlı, kaynağa sadık cevap
    lang_reminder: str = "(Yanıtı yalnızca Türkçe yaz.)"
    # Bilgi bankasında alakalı kayıt bulunca kayıt BİREBİR ve ANINDA kart olarak gösterilir.
    # Model yalnızca kartın üstüne günlük dille kısa bir not yazar (adımları tekrar etmez).
    # Not: Uygun kayıt olup olmadığına arama kodu karar verir; modele "yoksa bulamadım de"
    # dedirtmiyoruz, 3B model bu cümleyle iyi kayıt varken bile reddediyordu.
    # note_mode: "template" = hazır, anında, risksiz not (varsayılan)
    #            "llm"      = model yazar, çıktı doğrulanır, geçersizse şablona dönülür
    # Canlı testte 3B model notta adımları tekrarladı, cümleyi yarıda kesti ve OLMAYAN
    # bir hata kodu uydurdu (KNK-205). Daha güçlü model gelince "llm" denenebilir.
    note_mode: str = "template"
    note_max_tokens: int = 90    # llm modunda not uzunluk sınırı
    note_prompt: str = (
        "Sen samimi bir ofis destek asistanısın. Daima TÜRKÇE yaz. Kullanıcıya günlük "
        "konuşma diliyle EN FAZLA 2 kısa cümlelik bir yönlendirme yaz: sorunu kısaca "
        "anladığını belirt ve altta gösterilen adımları sırayla denemesini söyle. "
        "Adımları ASLA tekrar yazma, liste yapma (adımlar ayrıca gösteriliyor). "
        "Yeni bilgi, tahmin veya ek öneri ekleme."
    )
    # Soru tek başına bilgi bankasında eşleşmiyor ama konuşmada önceki cevap varsa
    # (örn. "3. adımı tekrar yaz"): yalnızca konuşma geçmişine dayanılır.
    followup_prompt: str = (
        "Sen bir ofis destek asistanısın. Daima TÜRKÇE yaz. SADECE bu konuşmadaki "
        "önceki cevaplara dayanarak cevap ver. Soru önceki cevaplarla ilgili değilse "
        "veya cevap konuşmada yoksa tam olarak şunu yaz: 'Bilgi bankasında bu konuda "
        "kayıt bulamadım.' Kendi genel bilgini kullanma, tahmin yürütme."
    )
    keep_alive: str = "30m"  # model bu süre boyunca bellekte kalır (ilk cevap gecikmesi azalır)
    # --- Sohbetten öğrenme ("bunu kaydet"), yalnızca adminler ---
    learn_confirm: bool = True   # True: önce önizleme gösterilir, "evet/kaydet" ile onaylanır
                                 # False: komutla doğrudan kaydedilir (önerilmez: ses/model hatası riski)
    learn_denied_message: str = (
        "Bilgi bankasına kayıt ekleme yetkisi yalnızca yöneticilerdedir, bu yüzden bunu "
        "kaydetmedim. Bu bilgiyi bir yöneticiye iletebilirsiniz."
    )
    learn_need_info_message: str = (
        "Neyi kaydedeyim? Sorunu ve çözümü yazın, sonunda \"bunu kaydet\" deyin. "
        "(Örnek: \"KNK-500 yazıcı bağlanmıyor. Önce kabloyu kontrol et, sonra servisi "
        "yeniden başlat. Bunu kaydet.\")"
    )
    learn_preview_message: str = (   # yapay zeka düzenlediyse: uyarı daha güçlü
        "Kaydedilecek kaydı yapay zeka ile düzenledim. Lütfen başlığı ve adımları dikkatle "
        "kontrol edin, yapay zeka yanlış anlamış olabilir. Doğruysa \"kaydet\" yazın. "
        "Başlığı değiştirmek için \"başlık: yeni başlık\", vazgeçmek için \"iptal\" yazın."
    )
    learn_preview_basic_message: str = (   # anlatılan cümleler olduğu gibi düzenlendiyse
        "Kaydedilecek kaydı anlattığınız cümlelerden olduğu gibi düzenledim. Kontrol edin; "
        "doğruysa \"kaydet\" yazın. Başlığı değiştirmek için \"başlık: yeni başlık\", "
        "vazgeçmek için \"iptal\" yazın."
    )
    empty_kb_message: str = (
        "Bilgi bankası henüz boş, bu yüzden çözüm öneremiyorum. Bir yönetici bilgi "
        "bankasına kayıt ekledikten sonra yardımcı olabilirim."
    )
    no_kb_message: str = (
        "Bilgi bankasında bu konuda kayıt bulamadım. Sorunu farklı kelimelerle yazmayı "
        "deneyebilir ya da bu bilginin eklenmesini bir yöneticiden isteyebilirsiniz."
    )

    # --- İnternet araması (DuckDuckGo): bilgi bankasında cevap yoksa ÖNCE SORULUR, "evet" denirse aranır ---
    # Dışarı yalnızca temizlenmiş soru cümlesi gider. Tamamen offline kalmak için: OFIS_WEB_SEARCH=false
    web_search: bool = True
    web_results: int = 3
    web_timeout: int = 8
    web_region: str = "tr-tr"
    web_offer_question: str = "İnternette aramamı ister misiniz? (evet / hayır)"
    web_declined_message: str = "Tamam, internette aramadım. Sorunu farklı kelimelerle yazarak tekrar deneyebilirsiniz."
    web_failed_note: str = (   # arama denendi ama sonuç gelmedi (internet yok / DuckDuckGo yanıt vermedi)
        " İnternet araması da sonuç vermedi (bağlantı yok ya da arama servisi yanıt vermedi); "
        "biraz sonra tekrar deneyebilirsiniz."
    )
    web_note: str = (
        "İnternette şunları buldum. Bunlar şirket kaydı değil, genel kaynaklardır: "
        "uygulamadan önce kontrol edin."
    )

    # --- Sohbet hafızası (kısa süreli) ---
    history_turns: int = 6          # modele verilecek son soru-cevap çifti sayısı
    max_history_chars: int = 6000   # geçmiş bundan uzunsa en eskiler atılır
    max_message_chars: int = 4000   # tek mesajın üst sınırı

    # --- Klasörler (hepsi proje içinde: tek klasör kopyalayarak taşınır) ---
    data_dir: Path = BASE_DIR / "data"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def vectorstore_dir(self) -> Path:
        return self.data_dir / "vectorstore"

    @property
    def models_dir(self) -> Path:
        return self.stt_models_path or self.data_dir / "models"

    @property
    def tts_dir(self) -> Path:
        return self.tts_models_path or self.models_dir / "tts"

    @property
    def certs_dir(self) -> Path:
        return self.data_dir / "certs"


settings = Settings()
