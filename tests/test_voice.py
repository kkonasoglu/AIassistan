"""Bas-konuş: ses uç noktası ve konuşma tanıma servisi. Gerçek model yüklenmez."""
import glob
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import stt
from app.services import users as u

H = {"X-Requested-With": "fetch"}
AUDIO = b"\x1aE\xdf\xa3" + b"x" * 5000          # webm başlığına benzer sahte ses (içerik önemsiz)


def leftover_audio_files():
    return glob.glob(os.path.join(tempfile.gettempdir(), "ofis-ses-*"))


class VoiceApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        u._fails.clear()
        self.stack = []
        self.admin = self._client()
        self.admin.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})
        self.before = set(leftover_audio_files())

    def _client(self):
        c = TestClient(app, base_url="https://testserver", headers=H)
        c.__enter__()
        self.stack.append(c)
        return c

    def tearDown(self):
        for c in self.stack:
            c.__exit__(None, None, None)
        self._tmp.cleanup()

    def post(self, client=None, data=AUDIO, ctype="audio/webm", **kw):
        return (client or self.admin).post("/api/voice/transcribe", content=data,
                                           headers={"Content-Type": ctype}, **kw)

    def test_requires_login(self):
        anon = self._client(); anon.cookies.clear()
        self.assertEqual(self.post(anon).status_code, 401)

    def test_transcribes_and_returns_text(self):
        with patch("app.services.stt.transcribe", return_value="knk 204 hatası alıyorum") as t:
            r = self.post(ctype="audio/webm;codecs=opus")          # tarayıcı codec bilgisi de ekler
        self.assertEqual((r.status_code, r.json()), (200, {"text": "knk 204 hatası alıyorum"}))
        path = t.call_args.args[0]
        self.assertTrue(path.endswith(".webm"))
        self.assertFalse(os.path.exists(path))                    # ses dosyası işlem bitince silinir

    def test_standard_user_can_use_voice(self):
        self.admin.post("/api/admin/users", json={"username": "bob", "password": "sifre123"})
        bob = self._client()
        bob.post("/api/auth/login", json={"username": "bob", "password": "sifre123"})
        with patch("app.services.stt.transcribe", return_value="merhaba"):
            self.assertEqual(self.post(bob).json()["text"], "merhaba")

    def test_accepted_formats(self):
        with patch("app.services.stt.transcribe", return_value="x") as t:
            for ctype, ext in (("audio/webm", ".webm"), ("audio/ogg", ".ogg"), ("audio/mp4", ".mp4"),
                               ("audio/wav", ".wav")):
                self.assertEqual(self.post(ctype=ctype).status_code, 200, ctype)
                self.assertTrue(t.call_args.args[0].endswith(ext), ctype)

    def test_rejects_other_content_types(self):
        for ctype in ("text/plain", "application/json", "application/octet-stream", "image/png"):
            self.assertEqual(self.post(ctype=ctype).status_code, 415, ctype)

    def test_size_limit_is_enforced(self):
        with patch.object(settings, "stt_max_bytes", 2000), \
             patch("app.services.stt.transcribe") as t:
            self.assertEqual(self.post(data=b"x" * 5000).status_code, 413)
        t.assert_not_called()

    def test_tiny_recording_returns_empty_without_calling_model(self):
        with patch("app.services.stt.transcribe") as t:
            self.assertEqual(self.post(data=b"abc").json(), {"text": ""})
        t.assert_not_called()

    def test_silence_returns_empty_text(self):
        with patch("app.services.stt.transcribe", return_value=""):
            self.assertEqual(self.post().json(), {"text": ""})

    def test_model_unavailable_is_503_with_clear_message(self):
        with patch("app.services.stt.transcribe", side_effect=stt.ModelUnavailable("indirilemedi")):
            r = self.post()
        self.assertEqual(r.status_code, 503)
        self.assertIn("internete", r.json()["detail"])
        self.assertEqual(set(leftover_audio_files()), self.before)   # hata olsa da dosya kalmaz

    def test_undecodable_audio_is_400_and_file_removed(self):
        with patch("app.services.stt.transcribe", side_effect=RuntimeError("bozuk ses")):
            r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("bozuk ses", r.text)                        # iç hata ayrıntısı sızmaz
        self.assertEqual(set(leftover_audio_files()), self.before)

    def test_health_reports_stt_state(self):
        self.assertIn("stt_loaded", self.admin.get("/api/health").json())


class FakeModel:
    calls = []

    def transcribe(self, path, **kwargs):
        FakeModel.calls.append((path, kwargs))

        class Seg:
            def __init__(self, text): self.text = text
        return [Seg(" Merhaba "), Seg("dünya ")], None


class SttService(unittest.TestCase):
    def setUp(self):
        stt._model = None
        FakeModel.calls = []

    def tearDown(self):
        stt._model = None

    def test_uses_turkish_vad_and_joins_segments(self):
        with patch.object(stt, "_load", return_value=FakeModel()):
            text = stt.transcribe("a.webm")
        self.assertEqual(text, "Merhaba dünya")
        kwargs = FakeModel.calls[0][1]
        self.assertEqual(kwargs["language"], "tr")
        self.assertTrue(kwargs["vad_filter"])                         # sessizlikte uydurmayı önler
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertNotIn("hotwords", kwargs)                          # varsayılan: kapalı

    def test_hotwords_are_passed_when_configured(self):
        with patch.object(stt, "_load", return_value=FakeModel()), \
             patch.object(settings, "stt_hotwords", "konnektör e-Fatura"):
            stt.transcribe("a.webm")
        self.assertEqual(FakeModel.calls[0][1]["hotwords"], "konnektör e-Fatura")

    def test_model_is_loaded_once(self):
        with patch.object(stt, "_load", return_value=FakeModel()) as load:
            stt.transcribe("a.webm"); stt.transcribe("b.webm")
        self.assertEqual(load.call_count, 1)
        self.assertTrue(stt.is_loaded())

    def test_load_failure_becomes_model_unavailable_and_can_retry(self):
        with patch.object(stt, "_load", side_effect=OSError("internet yok")):
            with self.assertRaises(stt.ModelUnavailable):
                stt.transcribe("a.webm")
        self.assertFalse(stt.is_loaded())
        with patch.object(stt, "_load", return_value=FakeModel()):     # internet gelince tekrar dener
            self.assertEqual(stt.transcribe("a.webm"), "Merhaba dünya")


if __name__ == "__main__":
    unittest.main()
