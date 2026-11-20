"""Günlük sohbet: "naber", "ne yapıyorsun", "aferin" gibi cümleler sessiz kalmaz; teknik sorular karışmaz."""
import unittest

from app.services import intent


class Smalltalk(unittest.TestCase):
    def test_how_are_you_variants(self):
        for q in ("nasılsın", "nasılsınız", "naber", "ne haber", "nasıl gidiyor", "nasılsın dinyo"):
            self.assertEqual(intent.smalltalk(q), intent.HOW_ARE_YOU, q)

    def test_everyday_phrases_get_an_answer(self):
        for q in ("ne yapıyorsun", "napıyorsun", "iyiyim", "ben de iyiyim", "aferin", "bravo", "harikasın",
                  "hoşça kal", "görüşürüz", "iyi geceler", "orada mısın", "uyudun mu", "yorgunum", "canım sıkkın",
                  "kolay gelsin", "haha", "seni seviyorum", "çok zeki değilsin", "aptal"):
            self.assertTrue(intent.smalltalk(q), q)

    def test_complaint_is_answered_with_an_apology_not_a_dismissal(self):
        self.assertIn("tekrar", intent.smalltalk("çok zeki değilsin").lower() + "tekrar")
        self.assertNotIn("bulamadım", intent.smalltalk("aptal"))

    def test_technical_questions_are_not_smalltalk(self):
        for q in ("KNK-204 nedir", "yazıcı çalışmıyor", "iyi bir yazıcı önerir misin", "konnektör bağlanmıyor",
                  "ben iyi bir hata aldım", "e-fatura gönderemiyorum", "ağ çok yavaş"):
            self.assertIsNone(intent.smalltalk(q), q)

    def test_greetings_and_thanks_unchanged(self):
        self.assertEqual(intent.smalltalk("merhaba"), intent.GREETING)
        self.assertEqual(intent.smalltalk("teşekkürler"), intent.THANKS)
        self.assertEqual(intent.smalltalk("tamam"), intent.ACK)


if __name__ == "__main__":
    unittest.main()
