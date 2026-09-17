"""
Tiga perbaikan yang lahir dari hasil generate nyata, 22 Agustus 2026.

**Bahasa yang salah.** Slot yang teks lamanya berbahasa lain sengaja
dibuka untuk ditulis ulang - itu gunanya tanda "fresh" di spec. Yang
tidak diperhitungkan: model 4B yang diperlihatkan contoh berbahasa
Inggris kadang menjawab dalam bahasa Inggris juga. Yang terbit:

    Some users noted that the interface remains responsive even under
    weak network conditions.

Kalimat itu TIDAK ada di templatenya - model yang menulisnya.

**Dua janji yang didempetkan koma.** Yang terbit "BATARATOTO - Slot
Online Akses Cepat, Tidak Blokir". Koma di situ menjanjikan
kelanjutan yang tidak pernah datang, dan penilai judul menandainya
sebagai kalimat menggantung - nilainya tepat 1,00, jadi judulnya
ditolak berkali-kali lalu tetap terbit sebagai yang paling sedikit
bermasalah. Contoh milik pengguna memakai "&" untuk maksud yang sama.

**Kunci konfigurasi milik orang lain.** Payload analitik template 488
memuat `"brand": "Hey siriusly"` - nama DESAINER kaosnya. Diisi hanya
karena kuncinya bernama "brand", data yang dikirim ke sistem
pelacakan berubah jadi nama situs yang tidak ada hubungannya.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.content_planner import (
    drop_foreign_content,
    enforce_title_shape,
    join_two_promises,
    title_penalty,
)
from generators.brand_swap import normalize
from generators.script_text import script_edits
from generators.template_scanner import scan


class BahasaYangSalahDikosongkan(unittest.TestCase):
    def test_kalimat_inggris_dikosongkan(self):
        isi = {
            "paragraph": [
                "Anda bisa mengakses slot online di BATARATOTO dari ponsel.",
                "Some users noted that the interface remains responsive "
                "even under weak network conditions.",
            ]
        }

        hasil, jumlah = drop_foreign_content(isi, "id")

        self.assertEqual(jumlah, 1)
        self.assertEqual(hasil["paragraph"][1], "")

    def test_nomor_urut_tidak_bergeser(self):
        """
        Dikosongkan, BUKAN dihapus. Pasangan tanya-jawab dicocokkan
        lewat nomor urut, jadi menghapus satu butir menggeser seluruh
        pasangan sesudahnya.
        """
        isi = {
            "faq_answer": [
                "The system stays available around the clock every day.",
                "Anda bisa membuka halaman ini kapan saja dari ponsel.",
            ]
        }

        hasil, _ = drop_foreign_content(isi, "id")

        self.assertEqual(len(hasil["faq_answer"]), 2)
        self.assertEqual(hasil["faq_answer"][0], "")
        self.assertIn("kapan saja", hasil["faq_answer"][1])

    def test_kalimat_indonesia_tidak_disentuh(self):
        isi = {
            "paragraph": [
                "Pengguna yang sudah mencoba slot online di BATARATOTO "
                "menyebutkan aksesnya cepat.",
            ]
        }

        hasil, jumlah = drop_foreign_content(isi, "id")

        self.assertEqual(jumlah, 0)
        self.assertEqual(hasil["paragraph"], isi["paragraph"])

    def test_istilah_pendek_bukan_bahasa_asing(self):
        """
        "RTP Live Hari Ini" dan "Link Alternatif Resmi" memang bentuk
        yang diminta pengguna di remah dan judulnya.
        """
        isi = {"heading": ["RTP Live Hari Ini", "Link Alternatif Resmi"]}

        _, jumlah = drop_foreign_content(isi, "id")

        self.assertEqual(jumlah, 0)

    def test_zona_lain_tidak_dinilai_dengan_alat_indonesia(self):
        isi = {"paragraph": ["Some users noted that the interface works."]}

        _, jumlah = drop_foreign_content(isi, "th")

        self.assertEqual(jumlah, 0)


class DuaJanjiDisambungTanda(unittest.TestCase):
    def test_koma_tunggal_jadi_ampersand(self):
        self.assertEqual(
            join_two_promises("Slot Online Akses Cepat, Tidak Blokir"),
            "Slot Online Akses Cepat & Tidak Blokir",
        )

    def test_judul_yang_terbit_lolos_penilai(self):
        judul = enforce_title_shape(
            "BATARATOTO - Slot Online Akses Cepat, Tidak Blokir",
            "slot online",
            "BATARATOTO",
            70,
        )

        self.assertIn("&", judul)
        self.assertLess(title_penalty(judul, "slot online", "BATARATOTO"), 1.0)

    def test_tumpukan_tiga_janji_tidak_disamarkan(self):
        """
        Judul dengan dua koma adalah tumpukan, dan itu urusan
        clause_pile_score - bukan sesuatu yang boleh disembunyikan
        dengan mengganti tandanya.
        """
        teks = "Panduan Lengkap, Cara Daftar, dan Cara Main"

        self.assertEqual(join_two_promises(teks), teks)

    def test_ekor_panjang_bukan_janji_kedua(self):
        teks = "Slot Online, tempat semua orang bisa mencoba peruntungannya"

        self.assertEqual(join_two_promises(teks), teks)

    def test_yang_sudah_punya_kata_sambung_dibiarkan(self):
        teks = "RTP Live Hari Ini, dan Bocoran Pola"

        self.assertEqual(join_two_promises(teks), teks)


SKRIP_TOKO = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Situs Slot Resmi</title>
<script>
window.SEO_CONFIG = { BRAND: "OSB99", META_TITLE: "OSB99 | Situs Slot Resmi" };
window.analytics = { "brand": "Hey siriusly", "name": "Kaos Katun Combed" };
</script>
</head><body><h1>OSB99</h1></body></html>
"""


class KunciKonfigurasiMilikOrangLain(unittest.TestCase):
    def setUp(self):
        self.edits, _ = script_edits(
            scanned=scan(SKRIP_TOKO),
            html=SKRIP_TOKO,
            # Kuncinya bentuk ternormalkan dari teks lama, persis
            # seperti yang disusun template_filler.
            diganti={
                normalize("OSB99 | Situs Slot Resmi"): (
                    "RAJAWALI77 | RTP Live Hari Ini"
                ),
            },
            old_brand="OSB99",
            new_brand="RAJAWALI77",
            content={
                "title": "RAJAWALI77 | RTP Live Hari Ini",
                "meta_description": "RAJAWALI77 menghadirkan RTP live harian.",
            },
        )
        self.diganti = {item["current"]: item["text"] for item in self.edits}

    def test_nama_brand_lama_tetap_ditukar(self):
        self.assertEqual(self.diganti.get("OSB99"), "RAJAWALI77")

    def test_judul_lama_di_konfigurasi_ikut_berganti(self):
        self.assertEqual(
            self.diganti.get("OSB99 | Situs Slot Resmi"),
            "RAJAWALI77 | RTP Live Hari Ini",
        )

    def test_nama_desainer_di_kunci_brand_tidak_disentuh(self):
        self.assertNotIn("Hey siriusly", self.diganti)

    def test_nama_produk_toko_tidak_disentuh(self):
        self.assertNotIn("Kaos Katun Combed", self.diganti)


if __name__ == "__main__":
    unittest.main()
