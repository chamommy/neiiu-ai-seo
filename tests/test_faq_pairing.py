"""
Tiap jawaban FAQ wajib punya pertanyaan yang berdiri di atasnya.

Cacat yang ditutup di sini yang paling terlihat pembaca: **ditanya A
dijawab Z**. Terukur di halaman BATARATOTO yang terbit 21 Agustus
2026:

    Q: Mengapa BATARATOTO Menjadi Situs Slot Pilihan Banyak Pemain?
    A: Setelah kamu masuk ke akun, kamu bisa memilih jenis slot ...

Mesin pemasangan sudah ada sejak sebelumnya dan ia memasangkan
jawaban ke-N dengan pertanyaan ke-N. Itu benar SELAMA kedua daftarnya
sama panjang dan sejajar. Di template 488 keduanya tidak sejajar sama
sekali, karena dua hal sekaligus:

  1. <h4>Product Quality</h4> - judul bagian mutu produk milik toko -
     berdiri di dalam <div class="...-and-faqs">, jadi penanda FAQ
     mengenainya dan ia terbaca sebagai pertanyaan.
  2. Pertanyaan yang SUNGGUHAN ditulis sebagai akordeon di dalam
     <button>, dan tidak pernah jadi slot sama sekali.

Hasilnya satu "pertanyaan" palsu dan tiga "jawaban": dua jawaban
terakhir ditulis tanpa pernah melihat pertanyaan apa pun.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_filler import derive_spec
from generators.template_scanner import scan
from generators.template_slots import build_slot_map


# Bentuk akordeon: pertanyaannya di dalam <button>, jawabannya
# menyusul. Persis bentuk template 488.
AKORDEON = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Situs Slot Eksklusif dengan Koleksi Game Terpercaya</title>
</head><body>
<h1>OSB99 - Situs Slot</h1>

<div class="m-product-info-and-faqs">
  <h4>Product Quality</h4>
  <p>Our Production Team establishes the highest quality standards for every product sold here.</p>

  <button class="accordion"><div>Mengapa OSB99 Menjadi Situs Slot Pilihan Banyak Pemain?</div></button>
  <span>OSB99 hadir sebagai situs slot eksklusif yang menyediakan koleksi permainan lengkap setiap hari.</span>

  <button class="accordion"><div>Apa Saja Pilihan Game yang Tersedia di OSB99?</div></button>
  <p>OSB99 menghadirkan koleksi permainan slot yang beragam dari berbagai provider ternama di Indonesia.</p>
</div>
</body></html>
"""


def peta(html: str, brand_lama: str = "OSB99"):
    return build_slot_map(scan(html), brand_lama, "id")


class TiapJawabanPunyaPertanyaan(unittest.TestCase):
    def setUp(self):
        self.peta = peta(AKORDEON)

    def test_jumlah_tanya_dan_jawab_sama(self):
        tanya = self.peta["roles"].get("faq_question", [])
        jawab = self.peta["roles"].get("faq_answer", [])

        self.assertEqual(len(tanya), len(jawab))
        self.assertEqual(len(tanya), 2)

    def test_pertanyaan_akordeon_ikut_ditulis_ulang(self):
        """
        Pertanyaan di dalam <button> dulu tidak pernah jadi slot, jadi
        halaman terbit dengan pertanyaan milik pemilik template di atas
        jawaban yang seluruhnya baru.
        """
        tanya = [
            " ".join(str(slot["current"]).split())
            for slot in self.peta["roles"].get("faq_question", [])
        ]

        self.assertIn(
            "Mengapa OSB99 Menjadi Situs Slot Pilihan Banyak Pemain?",
            tanya,
        )
        self.assertIn(
            "Apa Saja Pilihan Game yang Tersedia di OSB99?",
            tanya,
        )

    def test_judul_bagian_yang_bukan_pertanyaan_tidak_dihitung(self):
        tanya = [
            " ".join(str(slot["current"]).split())
            for slot in self.peta["roles"].get("faq_question", [])
        ]

        self.assertNotIn("Product Quality", tanya)

    def test_jawaban_tanpa_pertanyaan_diturunkan_jadi_paragraf(self):
        paragraf = [
            " ".join(str(slot["current"]).split())
            for slot in self.peta["roles"].get("paragraph", [])
        ]

        self.assertEqual(self.peta["faq_unpaired"], 1)
        self.assertTrue(
            any("Our Production Team" in teks for teks in paragraf),
            paragraf,
        )

    def test_tiap_jawaban_membawa_bunyi_pertanyaannya(self):
        """
        Ini yang dipakai prompt kalau pertanyaannya tidak bisa diangkat
        jadi slot - misalnya karena berdiri di footer atau di iklan.
        """
        for slot in self.peta["roles"].get("faq_answer", []):
            with self.subTest(posisi=slot["start"]):
                self.assertTrue(str(slot.get("asks") or "").endswith("?"))

    def test_pasangannya_benar_bukan_sekadar_berurutan(self):
        jawab = sorted(
            self.peta["roles"].get("faq_answer", []),
            key=lambda slot: slot["start"],
        )

        self.assertIn("Mengapa", jawab[0]["asks"])
        self.assertIn("Apa Saja", jawab[1]["asks"])


class PasanganIkutKeSpec(unittest.TestCase):
    def test_spec_membawa_daftar_pertanyaan(self):
        spec = derive_spec(peta(AKORDEON))

        tanya = spec.get("faq_answer", {}).get("asks")

        self.assertEqual(len(tanya or []), 2)
        self.assertIn("Mengapa", tanya[0])
        self.assertIn("Apa Saja", tanya[1])


if __name__ == "__main__":
    unittest.main()
