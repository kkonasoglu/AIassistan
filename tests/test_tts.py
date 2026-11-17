"""Sesli yanıt: metin hazırlama, ses servisi ve /api/voice/speak. Gerçek ses modeli yüklenmez."""
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import tts
from app.services import users as u

H = {"X-Requested-With": "fetch"}


class FakeVoice:
    calls = []

    def synthesize_wav(self, text, wav_file, syn_config=None, **kw):
        FakeVoice.calls.append((text, syn_config))
        wav_file.setnchannels(1); wav_file.setsampwidth(2); wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x01" * 2205)


class CleanForSpeech(unittest.TestCase):
    def test_error_codes_are_spelled_and_steps_numbered(self):
        t = tts.clean_for_speech("KNK-204 hatası:\n1. Ayarlara girin\n2. Şifreyi kontrol edin")
        self.assertIn("K N K, 204 hatası", t)
        self.assertIn("1. adım: Ayarlara girin", t)
        self.assertIn("2. adım: Şifreyi kontrol edin", t)

    def test_strips_markdown_urls_and_emoji(self):
        t = tts.clean_for_speech("**Önemli** `komut` https://example.com/x şunu yapın 😀")
        self.assertNotIn("*", t); self.assertNotIn("`", t); self.assertNotIn("http", t); self.assertNotIn("😀", t)
        self.assertIn("Önemli", t)

    def test_nothing_to_read_gives_empty(self):
        self.assertEqual(tts.clean_for_speech("  \n 😀 *** "), "")

    def test_long_text_is_cut_at_a_sentence_boundary(self):
        text = "Birinci cümle burada. " * 100
        t = tts.clean_for_speech(text, limit=100)
        self.assertLessEqual(len(t), 100)
        self.assertTrue(t.endswith("."))


class SynthService(unittest.TestCase):
    def setUp(self):
        tts._voice = None
        FakeVoice.calls = []

    def tearDown(self):
        tts._voice = None

    def test_returns_valid_wav_with_cleaned_text_and_speed(self):
        with patch.object(tts, "_load", return_value=FakeVoice()), patch.object(settings, "tts_length_scale", 1.2):
            data = tts.synthesize("KNK-204 hatası")
        import io
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual(w.getframerate(), 22050)
        text, cfg = FakeVoice.calls[0]
        self.assertEqual(text, "K N K, 204 hatası")
        self.assertEqual(cfg.length_scale, 1.2)

    def test_empty_speech_does_not_load_model(self):
        with patch.object(tts, "_load") as load:
            self.assertEqual(tts.synthesize("😀 ***"), b"")
        load.assert_not_called()

    def test_model_loaded_once_and_failure_is_retryable(self):
        with patch.object(tts, "_load", side_effect=OSError("internet yok")):
            with self.assertRaises(tts.ModelUnavailable):
                tts.synthesize("merhaba")
        self.assertFalse(tts.is_loaded())
        with patch.object(tts, "_load", return_value=FakeVoice()) as load:
            tts.synthesize("merhaba"); tts.synthesize("tekrar")
        self.assertEqual(load.call_count, 1)

    def test_default_voice_and_models_dir(self):
        self.assertEqual(settings.tts_voice, "tr_TR-dfki-medium")
        self.assertEqual(settings.tts_dir.name, "tts")


class SpeakApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        tts._voice = None
        self.c = TestClient(app, base_url="https://testserver", headers=H)
        self.c.__enter__()
        self.c.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})

    def tearDown(self):
        self.c.__exit__(None, None, None)
        tts._voice = None
        self._tmp.cleanup()

    def test_requires_login(self):
        anon = TestClient(app, base_url="https://testserver", headers=H)
        with anon:
            self.assertEqual(anon.post("/api/voice/speak", json={"text": "merhaba"}).status_code, 401)

    def test_returns_wav(self):
        with patch.object(tts, "_load", return_value=FakeVoice()):
            r = self.c.post("/api/voice/speak", json={"text": "Merhaba Kerem"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "audio/wav")
        self.assertTrue(r.content.startswith(b"RIFF"))
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_nothing_to_read_is_204(self):
        with patch.object(tts, "_load", return_value=FakeVoice()):
            self.assertEqual(self.c.post("/api/voice/speak", json={"text": "😀"}).status_code, 204)

    def test_model_unavailable_is_503(self):
        with patch.object(tts, "_load", side_effect=OSError("indirilemedi")):
            r = self.c.post("/api/voice/speak", json={"text": "merhaba"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("internete", r.json()["detail"])

    def test_disabled_is_404(self):
        with patch.object(settings, "tts_enabled", False):
            self.assertEqual(self.c.post("/api/voice/speak", json={"text": "merhaba"}).status_code, 404)

    def test_huge_text_rejected(self):
        with patch.object(tts, "_load", return_value=FakeVoice()):
            r = self.c.post("/api/voice/speak", json={"text": "a" * (settings.max_message_chars * 4 + 1)})
        self.assertEqual(r.status_code, 413)

    def test_health_reports_tts_state(self):
        h = self.c.get("/api/health").json()
        self.assertIn("tts_loaded", h); self.assertIn("tts_enabled", h)


if __name__ == "__main__":
    unittest.main()
