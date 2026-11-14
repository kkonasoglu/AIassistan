"""Bilgi bankası yönetimi: ekle, düzenle, sil/geri al, dışa aktar, arama testi, yetki.
Gerçek ChromaDB (geçici klasörde) + sahte embedding (anlamı kontrol edilebilir)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import knowledge, rag
from app.services import users as u

H = {"X-Requested-With": "fetch"}


def fake_embed(texts):
    """Konuya göre ortogonal vektörler: aynı konu mesafe 0, farklı konu mesafe 1."""
    out = []
    for t in texts:
        t = t.lower()
        out.append([1.0, 0.0, 0.0] if "şifre" in t else [0.0, 1.0, 0.0] if "imza" in t else [0.0, 0.0, 1.0])
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.data_dir = Path(self._tmp.name)
        rag.reset_cache()
        self.patches = [patch("app.services.knowledge.embed", side_effect=fake_embed),
                        patch("app.services.rag.embed", side_effect=fake_embed)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        rag.reset_cache()
        self._tmp.cleanup()


class KnowledgeService(Base):
    def test_add_and_list(self):
        rid = knowledge.add("KNK-204: Şifre hatalı", "1. Ayarlara gir\n2. Kaydet", "ayse")
        rec = knowledge.list_all()[0]
        self.assertEqual((rec["id"], rec["title"], rec["author"], rec["deleted"]),
                         (rid, "KNK-204: Şifre hatalı", "ayse", False))
        self.assertEqual(rec["solution"], "1. Ayarlara gir\n2. Kaydet")
        self.assertEqual(rag.count(), 1)

    def test_duplicate_title_rejected_case_and_space_insensitive(self):
        knowledge.add("KNK-204: Şifre hatalı", "çözüm", "ayse")
        for dup in ("knk-204:  ŞİFRE   hatalı", "KNK-204: Şifre hatalı "):
            with self.assertRaises(ValueError):
                knowledge.add(dup, "başka çözüm", "ayse")
        self.assertEqual(len(knowledge.list_all()), 1)

    def test_validation(self):
        for title, sol in (("", "x"), ("x", ""), ("   ", "  "), ("a" * (knowledge.MAX_TITLE + 1), "x"),
                           ("x", "a" * (knowledge.MAX_SOLUTION + 1))):
            with self.assertRaises(ValueError):
                knowledge.add(title, sol, "ayse")
        self.assertEqual(rag.count(), 0)

    def test_update_changes_record_and_reembeds(self):
        rid = knowledge.add("Eski başlık", "şifre çözümü", "ayse")
        self.assertEqual(len(rag.search("şifre sorunu")), 1)
        knowledge.update(rid, "Yeni başlık", "imza çözümü", "bob")
        rec = knowledge.list_all()[0]
        self.assertEqual((rec["title"], rec["solution"], rec["author"], rec["updated_by"]),
                         ("Yeni başlık", "imza çözümü", "ayse", "bob"))   # ekleyen aynı kalır
        self.assertEqual(rag.search("şifre sorunu"), [])                   # eski anlam artık bulunmaz
        self.assertEqual(rag.search("imza sorunu")[0]["title"], "Yeni başlık")  # yeni anlam bulunur

    def test_update_duplicate_of_other_record_rejected_but_own_title_ok(self):
        a = knowledge.add("A başlığı", "x", "ayse")
        knowledge.add("B başlığı", "y", "ayse")
        with self.assertRaises(ValueError):
            knowledge.update(a, "b başlığı", "x", "ayse")
        knowledge.update(a, "A başlığı", "x değişti", "ayse")           # kendi başlığı serbest
        with self.assertRaises(ValueError):
            knowledge.update("yok-boyle-id", "T", "S", "ayse")

    def test_delete_hides_everywhere_and_restore_brings_back(self):
        rid = knowledge.add("KNK-204: Şifre hatalı", "şifre çözümü", "ayse")
        knowledge.delete(rid, "ayse")
        self.assertEqual(knowledge.list_all(), [])
        self.assertEqual(rag.search("şifre sorunu"), [])
        self.assertEqual(rag.search("KNK-204 nedir"), [])               # kodla arama da bulmaz
        self.assertEqual(rag.count(), 0)
        gone = knowledge.list_all(include_deleted=True)
        self.assertEqual((len(gone), gone[0]["deleted"]), (1, True))    # kayıt silinmedi, gizlendi
        knowledge.restore(rid, "ayse")
        self.assertEqual(len(knowledge.list_all()), 1)
        self.assertEqual(rag.search("şifre sorunu")[0]["title"], "KNK-204: Şifre hatalı")

    def test_restore_blocked_if_active_record_has_same_title(self):
        rid = knowledge.add("Aynı başlık", "x", "ayse")
        knowledge.delete(rid, "ayse")
        knowledge.add("Aynı başlık", "yeni", "ayse")                    # silinmişle aynı başlık serbest
        with self.assertRaises(ValueError):
            knowledge.restore(rid, "ayse")

    def test_export_includes_deleted(self):
        a = knowledge.add("A", "x", "ayse")
        knowledge.add("B", "y", "ayse")
        knowledge.delete(a, "ayse")
        data = knowledge.export_all()
        self.assertEqual(data["count"], 2)
        self.assertEqual({r["title"]: r["deleted"] for r in data["records"]}, {"A": True, "B": False})
        json.dumps(data, ensure_ascii=False)                            # JSON'a çevrilebilir


class DebugSearch(Base):
    def test_modes(self):
        self.assertEqual(rag.debug_search("şifre")["mode"], "empty")
        knowledge.add("KNK-204: Şifre hatalı", "şifre çözümü", "ayse")
        knowledge.add("e-İmza sorunu", "imza çözümü", "ayse")
        code = rag.debug_search("KNK-204 nedir")
        self.assertEqual((code["mode"], code["rows"][0]["used"]), ("code", True))
        sem = rag.debug_search("şifre sorunu var")
        self.assertEqual(sem["mode"], "semantic")
        rows = {r["title"]: r for r in sem["rows"]}
        self.assertTrue(rows["KNK-204: Şifre hatalı"]["used"])
        self.assertFalse(rows["e-İmza sorunu"]["used"])                 # mesafe 1.0 > eşik
        self.assertEqual(sem["max_distance"], settings.max_distance)


class KnowledgeApi(Base):
    def setUp(self):
        super().setUp()
        u._fails.clear()
        self.stack = []
        self.admin = self._client()
        self.admin.post("/api/auth/setup", json={"username": "ayse", "password": "sifre123"})
        self.admin.post("/api/admin/users", json={"username": "bob", "password": "sifre123"})
        self.bob = self._client()
        self.bob.post("/api/auth/login", json={"username": "bob", "password": "sifre123"})

    def _client(self):
        c = TestClient(app, base_url="https://testserver", headers=H)
        c.__enter__()
        self.stack.append(c)
        return c

    def tearDown(self):
        for c in self.stack:
            c.__exit__(None, None, None)
        super().tearDown()

    def add(self, title="KNK-204: Şifre hatalı", solution="1. Ayarlara gir"):
        r = self.admin.post("/api/admin/knowledge", json={"title": title, "solution": solution})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def test_normal_user_and_anonymous_are_blocked_everywhere(self):
        rid = self.add()
        anon = self._client(); anon.cookies.clear()
        calls = [("get", "/api/admin/knowledge", None), ("get", "/api/admin/knowledge/export", None),
                 ("post", "/api/admin/knowledge", {"title": "t", "solution": "s"}),
                 ("put", f"/api/admin/knowledge/{rid}", {"title": "t", "solution": "s"}),
                 ("delete", f"/api/admin/knowledge/{rid}", None),
                 ("post", f"/api/admin/knowledge/{rid}/restore", None),
                 ("post", "/api/admin/knowledge/test", {"question": "q"})]
        for method, url, body in calls:
            kw = {"json": body} if body is not None else {}
            self.assertEqual(getattr(self.bob, method)(url, **kw).status_code, 403, f"user {method} {url}")
            self.assertEqual(getattr(anon, method)(url, **kw).status_code, 401, f"anon {method} {url}")
        self.assertEqual(len(knowledge.list_all()), 1)                   # hiçbiri işlem yapmadı
        self.assertEqual(knowledge.list_all()[0]["title"], "KNK-204: Şifre hatalı")

    def test_admin_full_cycle(self):
        rid = self.add()
        rows = self.admin.get("/api/admin/knowledge").json()
        self.assertEqual((rows[0]["title"], rows[0]["author"]), ("KNK-204: Şifre hatalı", "ayse"))
        self.assertEqual(self.admin.put(f"/api/admin/knowledge/{rid}",
                         json={"title": "KNK-204: Şifre", "solution": "yeni"}).status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/knowledge").json()[0]["solution"], "yeni")
        self.assertEqual(self.admin.delete(f"/api/admin/knowledge/{rid}").status_code, 200)
        self.assertEqual(self.admin.get("/api/admin/knowledge").json(), [])
        self.assertEqual(len(self.admin.get("/api/admin/knowledge?deleted=true").json()), 1)
        self.assertEqual(self.admin.post(f"/api/admin/knowledge/{rid}/restore").status_code, 200)
        self.assertEqual(len(self.admin.get("/api/admin/knowledge").json()), 1)

    def test_validation_errors_are_400(self):
        self.add()
        for body in ({"title": "", "solution": "x"}, {"title": "KNK-204: Şifre hatalı", "solution": "x"}):
            self.assertEqual(self.admin.post("/api/admin/knowledge", json=body).status_code, 400, body)
        self.assertEqual(self.admin.put("/api/admin/knowledge/yok",
                         json={"title": "t", "solution": "s"}).status_code, 400)

    def test_export_is_a_json_download(self):
        a = self.add("Birinci", "x"); self.add("İkinci", "y")
        self.admin.delete(f"/api/admin/knowledge/{a}")
        r = self.admin.get("/api/admin/knowledge/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        data = r.json()
        self.assertEqual(data["count"], 2)                               # silinen de yedekte
        self.assertEqual({x["title"] for x in data["records"]}, {"Birinci", "İkinci"})

    def test_search_test_endpoint(self):
        self.add()
        res = self.admin.post("/api/admin/knowledge/test", json={"question": "şifre sorunu var"}).json()
        self.assertEqual(res["mode"], "semantic")
        self.assertTrue(res["rows"][0]["used"])

    def test_ollama_down_gives_503_with_clear_message(self):
        with patch("app.services.knowledge.embed", side_effect=ConnectionError("down")):
            r = self.admin.post("/api/admin/knowledge", json={"title": "T", "solution": "S"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("Ollama", r.json()["detail"])
        self.assertEqual(knowledge.list_all(), [])                       # yarım kayıt kalmadı

    def test_chat_finds_record_added_through_admin_api(self):
        self.add("KNK-204: Şifre hatalı", "1. Ayarlara gir")
        c = self.admin.post("/api/chat/conversations").json()["id"]
        with patch.object(settings, "note_mode", "template"):
            r = self.admin.post(f"/api/chat/conversations/{c}/stream", json={"message": "knk204 hatası aldım"})
        ev = [json.loads(b[6:]) for b in r.text.split("\n\n") if b.startswith("data: ")]
        self.assertEqual(ev[0]["type"], "cards")
        self.assertEqual(ev[0]["cards"][0]["title"], "KNK-204: Şifre hatalı")


if __name__ == "__main__":
    unittest.main()
