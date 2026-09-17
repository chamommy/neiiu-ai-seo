"""
H1 adalah kalimat pembuka halaman, bukan judul kedua.

Bug yang ditutup di sini terbit di atas template NYATA,
output/rajawali77-slot-deposit-qris-20260820_041334:

    title : RAJAWALI77 @ Slot Deposit QRIS untuk Pemain yang Ingin Cepat
    h1    : RAJAWALI77 Slot Deposit QRIS untuk Pemain yang Ingin Cepat

Dua baris itu berdiri berurutan - satu di hasil pencarian, satu di
halaman - dan pembaca membaca kalimat yang sama dua kali. Penegak
bentuk H1 sudah ada sejak sebelumnya, tapi ia cuma menutup dua bentuk:
H1 yang memakai tanda pisah gaya judul, dan H1 yang isinya cuma nama
situs plus keyword. Bentuk ketiga - H1 yang punya keterangan sendiri,
tapi keterangan itu persis keterangan judulnya - lolos keduanya.
"""

import unittest

from generators.content_planner import enforce_h1_shape, ensure_template_identity


JUDUL = "RAJAWALI77 @ Slot Deposit QRIS untuk Pemain yang Ingin Cepat"
KEYWORD = "slot deposit qris"
BRAND = "RAJAWALI77"


class H1BukanJudulKedua(unittest.TestCase):
    def test_h1_yang_menyalin_judul_disusun_ulang(self):
        h1 = "RAJAWALI77 Slot Deposit QRIS untuk Pemain yang Ingin Cepat"

        hasil = enforce_h1_shape(h1, KEYWORD, BRAND, 80, "id", title=JUDUL)

        self.assertNotEqual(hasil, h1)
        self.assertIn(BRAND, hasil)
        self.assertIn("Deposit Qris", hasil)

    def test_h1_yang_punya_isi_sendiri_tidak_disentuh(self):
        h1 = "Cara Scan QRIS di RAJAWALI77 dalam Tiga Langkah"

        self.assertEqual(
            enforce_h1_shape(h1, KEYWORD, BRAND, 80, "id", title=JUDUL),
            h1,
        )

    def test_h1_label_tetap_disusun_ulang_seperti_dulu(self):
        h1 = "RAJAWALI77 # Slot Deposit QRIS"

        hasil = enforce_h1_shape(h1, KEYWORD, BRAND, 80, "id", title=JUDUL)

        self.assertNotIn("#", hasil)
        self.assertIn(BRAND, hasil)

    def test_tanpa_judul_perilakunya_sama_seperti_sebelumnya(self):
        """
        Pemanggil lama yang tidak mengirim judul tidak berubah
        perilakunya sama sekali.
        """
        h1 = "RAJAWALI77 Slot Deposit QRIS untuk Pemain yang Ingin Cepat"

        self.assertEqual(
            enforce_h1_shape(h1, KEYWORD, BRAND, 80, "id"),
            h1,
        )

    def test_h1_yang_ditulis_di_giliran_lain_tetap_tertangkap(self):
        """
        Title dan H1 tidak selalu jatuh di giliran yang sama. Kalau H1
        ditulis di giliran yang tidak memuat title, penegaknya tidak
        punya judul untuk diadu - dan H1 yang isinya persis judul
        lolos tanpa ada yang keberatan.

        Yang menutupnya penegakan ULANG di ujung, sesudah seluruh
        giliran selesai dan judulnya sudah final. Uji ini meniru
        keadaan itu: giliran H1 tanpa title, lalu penegakan ujung
        dengan keduanya.
        """
        spec_h1 = {"h1": {"count": 1, "max_length": 80, "max_length_any": 80}}
        spec_kepala = {
            "title": {"count": 1, "max_length": 70, "max_length_any": 70},
            "h1": {"count": 1, "max_length": 80, "max_length_any": 80},
        }

        # Giliran yang cuma menulis H1: tidak ada judul untuk diadu,
        # jadi H1-nya lolos apa adanya.
        sendiri = ensure_template_identity(
            {"h1": "RAJAWALI77 Slot Deposit QRIS untuk Pengguna Smartphone"},
            spec_h1,
            KEYWORD,
            BRAND,
        )

        self.assertIn("untuk Pengguna Smartphone", sendiri["h1"])

        # Penegakan di ujung, sesudah judulnya ada.
        akhir = ensure_template_identity(
            {
                "title": (
                    "RAJAWALI77 @ Slot Deposit QRIS untuk Pengguna "
                    "Smartphone"
                ),
                "h1": sendiri["h1"],
            },
            spec_kepala,
            KEYWORD,
            BRAND,
        )

        self.assertNotIn("untuk Pengguna Smartphone", akhir["h1"])
        self.assertIn(BRAND, akhir["h1"])

    def test_lewat_jalur_yang_benar_benar_dipakai(self):
        """
        Diuji lewat ensure_template_identity, bukan cuma lewat
        penegaknya, supaya urutan peran ikut terbukti: title harus
        sudah ditegakkan sebelum H1 diadu dengannya.
        """
        spec = {
            "title": {"count": 1, "max_length": 70, "max_length_any": 70},
            "h1": {"count": 1, "max_length": 80, "max_length_any": 80},
        }

        isi = {
            "title": "RAJAWALI77 @ Slot Deposit QRIS untuk Pemain yang Ingin Cepat",
            "h1": "RAJAWALI77 Slot Deposit QRIS untuk Pemain yang Ingin Cepat",
        }

        hasil = ensure_template_identity(isi, spec, KEYWORD, BRAND)

        self.assertNotEqual(
            hasil["h1"].casefold(),
            hasil["title"].replace(" @ ", " ").casefold(),
        )


if __name__ == "__main__":
    unittest.main()
