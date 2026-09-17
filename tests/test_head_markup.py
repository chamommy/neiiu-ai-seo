"""
Dua hal yang dilaporkan pipeline sendiri di setiap run, lalu dibiarkan.

Halaman yang terbit 30 Agustus 2026 selesai dengan status success dan
seo_score 88, dan daftar "problems"-nya berisi dua baris yang sama
seperti run-run sebelumnya:

    Atribut lang belum ada di <html>.
    Schema FAQPage belum terpasang.

Dua-duanya benar, dan dua-duanya tidak pernah ada yang membetulkan -
seo_validator memang cuma memeriksa, tidak menambal. Template 616
membuka dengan <html data-theme='default'>, jadi tidak ada slot lang
yang bisa diisi lapis mana pun; dan ia tidak membawa FAQPage meski
halamannya menampilkan kartu tanya jawab.

Yang ditambahkan di sini dua sisipan, bentuknya sama dengan sisipan
blok Review yang sudah lama ada: satu atribut dan satu blok schema,
keduanya di titik yang jelas, tanpa satu tag pun yang dibuang atau
digeser.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_filler import (
    build_faq_block,
    fill_template,
    html_lang_edit,
)
from generators.template_scanner import scan


TANPA_LANG = """<!doctype html>
<html data-theme='default'><head>
<meta charset="utf-8">
<title>OLDBRAND : Situs Terpercaya</title>
<meta name="description" content="OLDBRAND menghadirkan layanan bagus.">
</head><body>
<h1>OLDBRAND : Situs Terpercaya</h1>
<p>Halaman ini milik OLDBRAND dan sudah lama berdiri di sini melayani
orang yang mencari tempat bermain tanpa banyak syarat yang berbelit.</p>
<div class="faq">
  <h3>Bagaimana cara daftar?</h3>
  <p>Buka situsnya lalu isi nomor telepon yang masih aktif dipakai.</p>
  <h3>Bisa dibuka dari ponsel?</h3>
  <p>Bisa, lewat browser ponsel tanpa memasang aplikasi apa pun lagi.</p>
</div>
</body></html>"""

DENGAN_LANG = TANPA_LANG.replace(
    "<html data-theme='default'>", '<html lang="en" data-theme=\'default\'>'
)

BRAND = {
    "site_name": "NEWBRAND",
    "region": "id",
    "language_name": "Indonesia",
    "html_lang": "id",
    "year": "2026",
}

ISI = {
    "title": "NEWBRAND | Judul Baru yang Panjangnya Cukup Sekali",
    "meta_description": "NEWBRAND menyajikan layanan yang bisa dipakai.",
    "h1": "Layanan di NEWBRAND",
    "faq_question": ["Bagaimana cara daftar?", "Bisa dibuka dari ponsel?"],
    "faq_answer": [
        "Buka situsnya lalu isi nomor telepon yang masih aktif dipakai.",
        "Bisa, lewat browser ponsel tanpa memasang aplikasi apa pun lagi.",
    ],
}


class AtributLang(unittest.TestCase):
    def test_ditambahkan_kalau_belum_ada(self):
        edit = html_lang_edit(scan(TANPA_LANG), "id")

        self.assertIsNotNone(edit)
        self.assertEqual(edit["text"], ' lang="id"')

    def test_disisipkan_tanpa_membuang_apa_pun(self):
        """
        Rentang kosong: start sama dengan end. Itu yang membuatnya
        tidak menggeser satu byte pun di luar titik sisipnya.
        """
        edit = html_lang_edit(scan(TANPA_LANG), "id")

        self.assertEqual(edit["start"], edit["end"])

    def test_tidak_ditambahkan_kalau_sudah_ada(self):
        """
        Yang sudah ada diisi build_edits lewat peran "lang".
        Menyisipkan yang kedua menghasilkan tag berisi dua atribut
        bernama sama.
        """
        self.assertIsNone(html_lang_edit(scan(DENGAN_LANG), "id"))

    def test_kode_kosong_tidak_menyisipkan_apa_pun(self):
        self.assertIsNone(html_lang_edit(scan(TANPA_LANG), ""))
        self.assertIsNone(html_lang_edit(scan(TANPA_LANG), None))

    def test_terpasang_di_halaman_jadi(self):
        keluar = fill_template(TANPA_LANG, ISI, BRAND, old_brand="OLDBRAND")

        self.assertIn('<html lang="id"', keluar["html"])

        # atribut lama tetap berdiri, tidak ditimpa
        self.assertIn("data-theme='default'", keluar["html"])

    def test_lang_yang_sudah_ada_tidak_jadi_dua(self):
        keluar = fill_template(DENGAN_LANG, ISI, BRAND, old_brand="OLDBRAND")

        self.assertEqual(keluar["html"].count("lang="), 1)


class BlokFAQPage(unittest.TestCase):
    def test_disusun_dari_tanya_jawab(self):
        blok = build_faq_block(ISI)

        self.assertIn("FAQPage", blok)
        self.assertIn("Bagaimana cara daftar?", blok)
        self.assertIn("nomor telepon yang masih aktif", blok)

    def test_tanpa_tanya_jawab_tidak_menghasilkan_apa_pun(self):
        for isi in ({}, {"faq_question": []}, {"faq_answer": ["x"]}):
            with self.subTest(isi=isi):
                self.assertEqual(build_faq_block(isi), "")

    def test_pertanyaan_tanpa_pasangannya_tidak_ikut(self):
        """
        zip berhenti di daftar terpendek, dan itu yang benar: entri
        Question tanpa acceptedAnswer bukan FAQPage yang lebih pendek,
        ia FAQPage yang tidak sah.
        """
        blok = build_faq_block(
            {
                "faq_question": ["Satu?", "Dua?", "Tiga?"],
                "faq_answer": ["Jawaban satu.", "Jawaban dua."],
            }
        )

        self.assertIn("Dua?", blok)
        self.assertNotIn("Tiga?", blok)

    def test_terpasang_di_halaman_jadi(self):
        keluar = fill_template(TANPA_LANG, ISI, BRAND, old_brand="OLDBRAND")

        self.assertEqual(keluar["html"].count("FAQPage"), 1)

    def test_tidak_dipasang_kalau_halaman_tidak_menampilkan_faq(self):
        """
        Schema FAQ untuk pertanyaan yang tidak terbaca di halaman
        adalah persis yang dilarang Google, dan hukumannya tindakan
        manual untuk seluruh situs - bukan cuma halaman itu.
        """
        tanpa_faq = TANPA_LANG[: TANPA_LANG.index('<div class="faq">')] + (
            "</body></html>"
        )

        keluar = fill_template(tanpa_faq, ISI, BRAND, old_brand="OLDBRAND")

        self.assertEqual(keluar["html"].count("FAQPage"), 0)

    def test_tidak_dipasang_dua_kali(self):
        """
        Template yang sudah membawa FAQPage sendiri diisi di tempat
        lewat jsonld_edits. Dua FAQPage di satu halaman membuat mesin
        pencari melihat dua daftar yang berbeda untuk halaman sama.
        """
        sudah_punya = TANPA_LANG.replace(
            "</head>",
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"FAQPage",'
            '"mainEntity":[{"@type":"Question","name":"Lama?",'
            '"acceptedAnswer":{"@type":"Answer","text":"Tidak."}}]}'
            "</script></head>",
        )

        keluar = fill_template(sudah_punya, ISI, BRAND, old_brand="OLDBRAND")

        self.assertEqual(keluar["html"].count('"@type":"FAQPage"')
                         + keluar["html"].count('"@type": "FAQPage"'), 1)


if __name__ == "__main__":
    unittest.main()
