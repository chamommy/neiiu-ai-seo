"""
Template WAJIB, dan tidak ada jalan lain yang diam-diam dipakai.

Sampai 19 Agustus 2026 template yang dikosongkan membuat pipeline
merakit halamannya sendiri dari pustaka blok - layout, CSS, tombol,
popup, dan urutan bagiannya ditentukan program. Itu generator kedua
yang hidup di dalam yang pertama, dan halaman yang keluar dari sana
tidak pernah bisa dijanjikan "strukturnya persis template pilihanmu".

Yang diuji di sini bukan cuma bahwa jalur itu ditutup, melainkan
bahwa penutupnya berbicara: ditolak dengan sebab yang bisa dibaca,
di lapisan yang paling awal bisa mengatakannya.

Uji ini juga menjaga Template Library: unggah, pilih, ganti nama,
hapus, dan waktu ubah yang ikut bergerak.
"""

import shutil
import sqlite3
import unittest

from fastapi.testclient import TestClient

import web_app
from config import BASE_DIR
from database.neiiu_templates_db import TEMPLATE_DIR
from generators.brand_swap import brand_names
from services.neiiu_pipeline import PipelineError, run_neiiu
from tests.fixtures import AMP, LANDING


DB = BASE_DIR / "database" / "neiiu_ai.db"
NAMA_UJI = "zz_uji_kontrak"


class KontrakTemplate(unittest.TestCase):
    """
    Lapisan pipeline. Tidak menyentuh jaringan sama sekali: yang
    diuji berhenti sebelum satu permintaan SERP pun berangkat.
    """

    def test_tanpa_template_ditolak(self):
        with self.assertRaises(PipelineError) as kena:
            run_neiiu(keyword="slot gacor", brand_name="WAYANGPLAY")

        pesan = str(kena.exception)

        self.assertIn("Template belum dipilih", pesan)

    def test_pesannya_menyebut_jalan_keluarnya(self):
        with self.assertRaises(PipelineError) as kena:
            run_neiiu(keyword="slot gacor")

        self.assertIn("Template Library", str(kena.exception))

    def test_keyword_kosong_tetap_ditolak_lebih_dulu(self):
        with self.assertRaises(PipelineError) as kena:
            run_neiiu(keyword="   ")

        self.assertIn("Keyword", str(kena.exception))


class PustakaTemplate(unittest.TestCase):
    """
    Lapisan web, lewat endpoint yang benar-benar dipakai antarmuka.
    """

    @classmethod
    def setUpClass(cls):
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM users WHERE username = ?", (NAMA_UJI,))
        con.commit()

        cls.uid = int(
            con.execute(
                "INSERT INTO users (username, password_hash, role, "
                "token_balance, is_active, created_at) "
                "VALUES (?, 'x', 'user', 50, 1, '2026-08-19T00:00:00+00:00')",
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

        web_app.session_user = lambda request: cls.pengguna
        web_app.require_user = lambda request: cls.pengguna

        cls.client = TestClient(web_app.app)

    @classmethod
    def tearDownClass(cls):
        web_app.session_user = cls._session_asli
        web_app.require_user = cls._require_asli

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

    def unggah(self, nama="Template Uji", amp=True):
        berkas = {"landing": ("landing.html", LANDING, "text/html")}

        if amp:
            berkas["amp"] = ("amp.html", AMP, "text/html")

        return self.client.post(
            "/api/neiiu/templates",
            data={"name": nama},
            files=berkas,
        )

    def test_unggah_simpan_pilih_hapus(self):
        jawab = self.unggah("Pasangan Landing dan AMP")

        self.assertEqual(jawab.status_code, 200, jawab.text)

        nomor = jawab.json()["template_id"]

        daftar = self.client.get("/api/neiiu/templates").json()["templates"]
        punya = [x for x in daftar if x["id"] == nomor]

        self.assertEqual(len(punya), 1)
        self.assertEqual(punya[0]["name"], "Pasangan Landing dan AMP")
        self.assertGreater(punya[0]["landing_bytes"], 0)
        self.assertGreater(punya[0]["amp_bytes"], 0)

        # Slot yang dikenali ikut dilaporkan, supaya pemilihnya tahu
        # template ini bisa diisi apa saja.
        self.assertIn("paragraph", punya[0]["slot_summary"])

        hapus = self.client.delete(f"/api/neiiu/templates/{nomor}")

        self.assertEqual(hapus.status_code, 200, hapus.text)

        sisa = self.client.get("/api/neiiu/templates").json()["templates"]

        self.assertEqual([x for x in sisa if x["id"] == nomor], [])

    def test_ganti_nama_menggerakkan_waktu_ubah(self):
        nomor = self.unggah("Nama Awal").json()["template_id"]

        try:
            sebelum = [
                x
                for x in self.client.get("/api/neiiu/templates").json()[
                    "templates"
                ]
                if x["id"] == nomor
            ][0]

            self.assertIn("updated_at", sebelum)

            jawab = self.client.put(
                f"/api/neiiu/templates/{nomor}",
                data={"name": "Nama Baru"},
            )

            self.assertEqual(jawab.status_code, 200, jawab.text)

            sesudah = [
                x
                for x in self.client.get("/api/neiiu/templates").json()[
                    "templates"
                ]
                if x["id"] == nomor
            ][0]

            self.assertEqual(sesudah["name"], "Nama Baru")
            self.assertEqual(sesudah["created_at"], sebelum["created_at"])
            self.assertGreaterEqual(
                sesudah["updated_at"], sebelum["updated_at"]
            )
        finally:
            self.client.delete(f"/api/neiiu/templates/{nomor}")

    def test_template_tanpa_slot_ditolak(self):
        jawab = self.client.post(
            "/api/neiiu/templates",
            data={"name": "Kosong"},
            files={
                "landing": (
                    "landing.html",
                    "<html><body><div class='ad'>x</div></body></html>",
                    "text/html",
                )
            },
        )

        self.assertEqual(jawab.status_code, 400, jawab.text)
        self.assertIn("bagian isi", jawab.json()["detail"])

    def test_job_tanpa_template_ditolak_sebelum_token_dipotong(self):
        con = sqlite3.connect(DB)
        sebelum = con.execute(
            "SELECT token_balance FROM users WHERE id = ?", (self.uid,)
        ).fetchone()[0]
        con.close()

        jawab = self.client.post(
            "/api/neiiu/jobs",
            json={
                "keyword": "slot gacor",
                "brand_name": "WAYANGPLAY",
                "template_id": 0,
                "history_scope": "qa",
            },
        )

        self.assertEqual(jawab.status_code, 400, jawab.text)
        self.assertIn("Pilih template", jawab.json()["detail"])

        con = sqlite3.connect(DB)
        sesudah = con.execute(
            "SELECT token_balance FROM users WHERE id = ?", (self.uid,)
        ).fetchone()[0]
        jumlah_job = con.execute(
            "SELECT COUNT(*) FROM neiiu_jobs WHERE user_id = ?", (self.uid,)
        ).fetchone()[0]
        con.close()

        self.assertEqual(sesudah, sebelum)
        self.assertEqual(jumlah_job, 0)

    def test_brand_lama_yang_diisi_brand_baru_ditolak(self):
        """
        Kolom "Brand lama di dalam template" berisi nama pemilik
        template SEBELUMNYA. Diisi dengan brand baru, penyapunya tidak
        menemukan apa pun - dan itu baru ketahuan belasan menit
        kemudian, dari halaman yang terbit dengan dua brand sekaligus.
        """
        nomor = self.unggah("Untuk Uji Brand Lama").json()["template_id"]

        try:
            jawab = self.client.post(
                "/api/neiiu/jobs",
                json={
                    "keyword": "slot gacor",
                    "brand_name": "WAYANGPLAY",
                    "template_brand": "wayangplay",
                    "template_id": nomor,
                    "history_scope": "qa",
                },
            )

            self.assertEqual(jawab.status_code, 400, jawab.text)
            self.assertIn("Brand lama", jawab.json()["detail"])
        finally:
            self.client.delete(f"/api/neiiu/templates/{nomor}")

    def test_brand_baru_yang_bersembunyi_di_daftar_ikut_ditolak(self):
        """
        Kolomnya sekarang boleh memuat beberapa nama dipisah koma -
        template bekas sering berlapis. Perbandingan atas SELURUH isi
        kolom akan meloloskan "WAYANGPLAY, TeePublic" untuk brand baru
        "WAYANGPLAY": salah isi yang persis sama, cuma bersembunyi di
        belakang nama kedua.
        """
        nomor = self.unggah("Untuk Uji Brand Berlapis").json()["template_id"]

        try:
            jawab = self.client.post(
                "/api/neiiu/jobs",
                json={
                    "keyword": "slot gacor",
                    "brand_name": "WAYANGPLAY",
                    "template_brand": "wayangplay, TeePublic",
                    "template_id": nomor,
                    "history_scope": "qa",
                },
            )

            self.assertEqual(jawab.status_code, 400, jawab.text)
            self.assertIn("Brand lama", jawab.json()["detail"])
        finally:
            self.client.delete(f"/api/neiiu/templates/{nomor}")

    def test_daftar_yang_benar_tidak_ikut_tertolak(self):
        """
        Kebalikannya, diuji TANPA melewati endpoint.

        Mengirim permintaan yang sah ke /api/neiiu/jobs berarti job
        yang sah benar-benar dibuat dan dijalankan - lengkap dengan
        pencarian SERP, crawl, dan puluhan menit giliran model. Uji
        yang menunggunya bukan uji lambat melainkan uji yang tidak
        pernah selesai.

        Yang diadu di sini pemisah namanya, yaitu satu-satunya bagian
        yang berubah. Bahwa penolakannya sendiri masih bekerja sudah
        diadu lewat endpoint di dua uji di atas.
        """
        nama = [satu.casefold() for satu in brand_names("BATARATOTO, TeePublic")]

        self.assertNotIn("wayangplay", nama)
        self.assertIn("bataratoto", nama)
        self.assertIn("teepublic", nama)

    def test_template_milik_orang_lain_tidak_bisa_dipakai(self):
        jawab = self.client.post(
            "/api/neiiu/jobs",
            json={
                "keyword": "slot gacor",
                "brand_name": "WAYANGPLAY",
                # Nomor yang pasti bukan milik pengguna uji.
                "template_id": 999999,
                "history_scope": "qa",
            },
        )

        self.assertEqual(jawab.status_code, 404, jawab.text)


if __name__ == "__main__":
    unittest.main()
