"""Arama mantığı testleri (sahte ChromaDB ve embedding ile)."""
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import rag


class FakeCollection:
    def __init__(self, docs):  # docs: [(başlık, mesafe)] yakından uzağa
        self.docs = docs

    def count(self, **kw):
        return len(self.docs)

    def query(self, **kw):
        return {"documents": [[f"{t}\n\nçözüm" for t, _ in self.docs]],
                "metadatas": [[{"title": t} for t, _ in self.docs]],
                "distances": [[d for _, d in self.docs]]}

    def get(self, where_document=None, **kw):
        needle = where_document["$contains"]
        found = [(t, f"{t}\n\nçözüm") for t, _ in self.docs if needle in f"{t}\n\nçözüm"]
        return {"documents": [d for _, d in found], "metadatas": [{"title": t} for t, _ in found]}


class Search(unittest.TestCase):
    def run_search(self, docs, query="soru"):
        with patch.object(rag, "collection", return_value=FakeCollection(docs)), \
             patch.object(rag, "embed", return_value=[[0.0]]):
            return rag.search(query)

    def test_far_documents_are_dropped(self):
        hits = self.run_search([("A", 0.30), ("B", 0.80)])
        self.assertEqual([h["title"] for h in hits], ["A"])

    def test_threshold_rejects_followup_like_noise(self):
        # Ölçülen: "3. adımı tekrar yaz" en iyi 0.544, "pizza" 0.66 -> kaynak sayılmamalı
        self.assertEqual(self.run_search([("A", 0.544)]), [])
        self.assertEqual(self.run_search([("A", 0.66)]), [])

    def test_relative_margin_drops_noise_but_keeps_close_ties(self):
        hits = self.run_search([("A", 0.33), ("B", 0.36), ("C", 0.47)])
        self.assertEqual([h["title"] for h in hits], ["A", "B"])
        # Ölçülen gerçek durum: KNK-204 sorusunda 0.353 / 0.466 / 0.467
        hits = self.run_search([("KNK-204", 0.353), ("KNK-310", 0.466), ("KNK-101", 0.467)])
        self.assertEqual([h["title"] for h in hits], ["KNK-204"])

    def test_empty_collection(self):
        self.assertEqual(self.run_search([]), [])


class ErrorCodeMatch(unittest.TestCase):
    DOCS = [("KNK-101: bağlantı", 0.6), ("KNK-310: şema", 0.65), ("KNK-204: şifre", 0.7)]

    def run_search(self, query, docs=None):
        with patch.object(rag, "collection", return_value=FakeCollection(docs or self.DOCS)), \
             patch.object(rag, "embed", side_effect=AssertionError("kod eşleşince embedding gerekmez")):
            return rag.search(query)

    def test_code_in_question_finds_record_even_if_semantically_far(self):
        # Ölçülen sorun: "KNK-310 nedir" -> anlamsal aramada doğru kayıt birinci çıkmıyordu
        self.assertEqual([h["title"] for h in self.run_search("KNK-310 nedir")], ["KNK-310: şema"])

    def test_code_normalization(self):
        for q in ("knk-310 ne", "knk310 hatası", "KNK 310?".replace(" ", "")):
            self.assertEqual([h["title"] for h in self.run_search(q)], ["KNK-310: şema"], q)

    def test_space_separated_code_as_people_really_type_it(self):
        # Gerçek kullanımda görülen: "knk 204 hatası alıyorum" kod olarak algılanmıyordu
        for q in ("knk 204 hatası alıyorum", "KNK 310 nedir", "Knk  101"):
            hits = self.run_search(q)
            self.assertEqual(len(hits), 1, q)
        self.assertEqual(self.run_search("knk 204 hatası alıyorum")[0]["title"], "KNK-204: şifre")

    def test_false_positive_code_falls_back_to_semantic_search(self):
        # "Office 365" kod gibi görünür ama hiçbir kayıtta yok: anlamsal aramaya düşmeli
        with patch.object(rag, "collection", return_value=FakeCollection([("A", 0.3)])), \
             patch.object(rag, "embed", return_value=[[0.0]]) as e:
            self.assertEqual(rag.search("Office 365 sorunu")[0]["title"], "A")
        e.assert_called_once()

    def test_title_match_preferred_over_mention_in_body(self):
        docs = [("KNK-204: şifre", 0.5), ("KNK-101: bağlantı", 0.5)]
        docs[1] = ("KNK-101: bağlantı", 0.5)
        with patch.object(rag, "collection", return_value=FakeCollection(docs)):
            col = rag.collection()
        # KNK-204 yalnızca KNK-101'in gövdesinde geçiyormuş gibi kur
        class Col(FakeCollection):
            def get(self, where_document=None, **kw):
                return {"documents": ["KNK-101: bağlantı\n\nbazen KNK-204 de görülür", "KNK-204: şifre\n\nçözüm"],
                        "metadatas": [{"title": "KNK-101: bağlantı"}, {"title": "KNK-204: şifre"}]}
        with patch.object(rag, "collection", return_value=Col(docs)):
            hits = rag.search("KNK-204 nedir")
        self.assertEqual([h["title"] for h in hits], ["KNK-204: şifre"])

    def test_question_without_code_uses_semantic_search(self):
        with patch.object(rag, "collection", return_value=FakeCollection([("A", 0.3)])), \
             patch.object(rag, "embed", return_value=[[0.0]]) as e:
            self.assertEqual(rag.search("şifre hatalı")[0]["title"], "A")
        e.assert_called_once()

    def test_non_code_tokens_are_not_treated_as_codes(self):
        for q in ("IPv4 adresi", "C62 birim kodu", "2. adım", "e-imza takılı"):
            self.assertEqual(rag._CODE_RE.findall(q), [], q)


class PromptBuilding(unittest.TestCase):
    def test_note_message_ends_with_language_reminder(self):
        msg = rag.build_note_message("soru?", [{"text": "T\n\nçözüm", "title": "T", "distance": 0.1}])
        self.assertIn("BULUNAN KAYIT:", msg)
        self.assertIn("KULLANICININ MESAJI: soru?", msg)
        self.assertTrue(msg.endswith(settings.lang_reminder))

    def test_hit_carries_solution_for_the_card(self):
        meta = {"title": "KNK-204: şifre", "solution": "1. Ayarlara gir"}
        h = rag._hit("KNK-204: şifre\n\n1. Ayarlara gir", meta, 0.2)
        self.assertEqual((h["title"], h["solution"]), ("KNK-204: şifre", "1. Ayarlara gir"))
        # metadata'da çözüm yoksa metinden türetilir
        h = rag._hit("Başlık\n\nçözüm metni", {"title": "Başlık"}, 0.2)
        self.assertEqual(h["solution"], "çözüm metni")


if __name__ == "__main__":
    unittest.main()
