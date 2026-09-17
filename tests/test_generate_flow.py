"""
Alur generate seperti yang benar-benar dikirim formulir.

Formulirnya dirombak 30 Agustus 2026: kolom "Target Keyword" jadi
"Niche", dan empat kolom brief - nada, jenis halaman, pembaca, keyword
pendukung - beserta URL halaman acuan dibuang dari layar. Yang diuji
di sini kontraknya, bukan tampilannya:

  1. Permintaan yang cuma membawa "niche" diterima, dan nilainya
     mendarat di kolom keyword - nama lama yang dipakai seluruh
     pipeline.
  2. Permintaan lama yang masih membawa "keyword" tetap diterima.
     Ada skrip di luar formulir yang memakainya, dan mengganti nama
     kolom di layar tidak boleh mematikannya.
  3. Alamat yang ngawur ditolak SEBELUM token dipotong dan sebelum
     job masuk antrean, bukan belasan menit kemudian.

Tidak menjalankan pipeline sama sekali: submit_job diganti fungsi
kosong, jadi tidak ada satu pun permintaan SERP yang berangkat dan
tidak ada model yang dipanggil.
"""

import shutil
import sqlite3
import unittest

from fastapi.testclient import TestClient

import web_app
from config import BASE_DIR
from database.neiiu_templates_db import TEMPLATE_DIR
from tests.fixtures import AMP, LANDING


DB = BASE_DIR / "database" / "neiiu_ai.db"
NAMA_UJI = "zz_uji_alur"


class AlurGenerate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM users WHERE username = ?", (NAMA_UJI,))
        con.commit()

        cls.uid = int(
            con.execute(
                "INSERT INTO users (username, password_hash, role, "
                "token_balance, is_active, created_at) "
                "VALUES (?, 'x', 'user', 50, 1, "
                "'2026-08-30T00:00:00+00:00')",
                (NAMA_UJI,),
            ).lastrowid
        )

        con.commit()
        con.close()

        cls.pengguna = {
            "id": cls.uid,
            "username": NAMA_UJI,
            "role": "user",
            "token_balance": 50,
            "is_active": 1,
        }

        cls._session_asli = web_app.session_user
        cls._require_asli = web_app.require_user
        cls._submit_asli = web_app.submit_job

        web_app.session_user = lambda request: cls.pengguna
        web_app.require_user = lambda request: cls.pengguna

        # Job dicatat di database tapi TIDAK dijalankan. Tanpa ini,
        # tiap uji melepas satu run pipeline sungguhan ke thread lain:
        # crawl sepuluh halaman, belasan menit, dan model yang
        # dipanggil berkali-kali.
        web_app.submit_job = lambda job_id: None

        cls.client = TestClient(web_app.app)

        jawab = cls.client.post(
            "/api/neiiu/templates",
            data={"name": "Template Alur"},
            files={
                "landing": ("landing.html", LANDING, "text/html"),
                "amp": ("amp.html", AMP, "text/html"),
            },
        )

        cls.template_id = jawab.json()["template_id"]

    @classmethod
    def tearDownClass(cls):
        web_app.session_user = cls._session_asli
        web_app.require_user = cls._require_asli
        web_app.submit_job = cls._submit_asli

        shutil.rmtree(TEMPLATE_DIR / str(cls.uid), ignore_errors=True)

        con = sqlite3.connect(DB)

        for tabel in ("neiiu_templates", "neiiu_jobs", "neiiu_used_text"):
            try:
                con.execute(
                    f"DELETE FROM {tabel} WHERE user_id = ?", (cls.uid,)
                )
            except sqlite3.Error:
                pass

        con.execute("DELETE FROM users WHERE id = ?", (cls.uid,))
        con.commit()
        con.close()

    def kirim(self, **kolom):
        badan = {
            "template_id": self.template_id,
            "region": "id",
            "city": "",
            "provider": "manual",
            "crawl": 1,
        }
        badan.update(kolom)

        return self.client.post("/api/neiiu/jobs", json=badan)

    def baris(self, job_id: int):
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row

        try:
            return con.execute(
                "SELECT * FROM neiiu_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        finally:
            con.close()

    # --- topik halaman ---

    def test_niche_diterima_dan_jadi_keyword(self):
        jawab = self.kirim(niche="slot gacor")

        self.assertEqual(jawab.status_code, 200, jawab.text)

        baris = self.baris(jawab.json()["job_id"])

        self.assertEqual(baris["keyword"], "slot gacor")

    def test_keyword_lama_masih_diterima(self):
        jawab = self.kirim(keyword="slot online")

        self.assertEqual(jawab.status_code, 200, jawab.text)
        self.assertEqual(
            self.baris(jawab.json()["job_id"])["keyword"],
            "slot online",
        )

    def test_niche_menang_atas_keyword(self):
        jawab = self.kirim(niche="yang diketik", keyword="yang lama")

        self.assertEqual(jawab.status_code, 200, jawab.text)
        self.assertEqual(
            self.baris(jawab.json()["job_id"])["keyword"],
            "yang diketik",
        )

    def test_keduanya_kosong_ditolak(self):
        jawab = self.kirim()

        self.assertEqual(jawab.status_code, 400)
        self.assertIn("Niche", jawab.json()["detail"])

    # --- alamat halaman ---

    def test_alamat_tersimpan(self):
        jawab = self.kirim(
            niche="slot gacor",
            canonical_url="https://brandmu.id/slot-gacor/",
            amphtml_url="https://brandmu.id/slot-gacor/amp/",
            cta_url="https://daftar.brandmu.id/",
        )

        self.assertEqual(jawab.status_code, 200, jawab.text)

        baris = self.baris(jawab.json()["job_id"])

        self.assertEqual(
            baris["canonical_url"],
            "https://brandmu.id/slot-gacor/",
        )
        self.assertEqual(
            baris["amphtml_url"],
            "https://brandmu.id/slot-gacor/amp/",
        )
        self.assertEqual(baris["cta_url"], "https://daftar.brandmu.id/")

    def test_alamat_kosong_tersimpan_kosong(self):
        jawab = self.kirim(niche="slot gacor")

        baris = self.baris(jawab.json()["job_id"])

        self.assertEqual(baris["canonical_url"], "")
        self.assertEqual(baris["amphtml_url"], "")

    def test_canonical_ngawur_ditolak(self):
        jawab = self.kirim(niche="slot gacor", canonical_url="brandmu.id")

        self.assertEqual(jawab.status_code, 400)
        self.assertIn("canonical", jawab.json()["detail"])

    def test_cta_javascript_ditolak(self):
        jawab = self.kirim(
            niche="slot gacor",
            cta_url="javascript:alert(1)",
        )

        self.assertEqual(jawab.status_code, 400)

    def test_alamat_ngawur_tidak_memotong_token(self):
        con = sqlite3.connect(DB)
        sebelum = con.execute(
            "SELECT token_balance FROM users WHERE id = ?", (self.uid,)
        ).fetchone()[0]
        con.close()

        self.kirim(niche="slot gacor", canonical_url="bukan alamat")

        con = sqlite3.connect(DB)
        sesudah = con.execute(
            "SELECT token_balance FROM users WHERE id = ?", (self.uid,)
        ).fetchone()[0]
        con.close()

        self.assertEqual(sebelum, sesudah)

    # --- kolom brief yang dibuang dari formulir ---

    def test_tanpa_brief_tetap_diterima(self):
        """
        Formulir tidak lagi mengirim tone, page_purpose,
        target_audience, dan secondary_keywords. Keempatnya harus
        tetap punya bawaan yang sah di sisi server.
        """
        jawab = self.kirim(niche="slot gacor")

        self.assertEqual(jawab.status_code, 200, jawab.text)

        baris = self.baris(jawab.json()["job_id"])

        self.assertEqual(baris["target_audience"], "")
        self.assertEqual(baris["secondary_keywords"], "")
        self.assertEqual(baris["page_purpose"], "")


if __name__ == "__main__":
    unittest.main()
