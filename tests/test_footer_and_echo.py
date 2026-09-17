"""
Footer dibiarkan; judul lama diganti di mana pun ia berdiri.

Dua permintaan pengguna 21 Agustus 2026, keduanya atas halaman
BATARATOTO yang benar-benar terbit.

**Footer.** "untuk bagian footer jangan ubah bila tidak menyangkut
brand jika footer adalah bagian bawaan dari iklan template maka jangan
ubah apapun." Template 488 tidak punya satu pun tag <footer>; kolom
footernya ditandai class 'm-footer-links' dan 'm-foot__links-section'.
Karena pembekuan cuma membaca TAG, seluruh kolom footer toko ikut
ditulis ulang - judul kolomnya "Support", "About Us", "Explore",
"Artists", "Follow Us", "We Accept" terbit sebagai "Pengalaman",
"Sistem Stabil", "Pemain Aktif", "Pilihan Banyak", "Keamanan Tinggi",
"Main Tanpa Batas".

**Judul yang kembar.** "setiap kalimat tersebut akan di ubah oleh
kalimat terbaru yang sudah di buat oleh AI". Lapis gema sudah ada,
tapi ia cuma menyamakan yang kembar PERSIS. Dari tujuh kemunculan
judul lama di halaman itu, dua bertahan - keduanya berbentuk
alt='<judul lama> by Hey siriusly', judul yang sama persis dengan
empat kata keterangan pemilik gambar di belakangnya.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_filler import fill_template
from generators.template_scanner import scan
from generators.template_slots import build_slot_map
from services.neiiu_pipeline import build_brand


FOOTER_DIV = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Situs Slot Resmi dengan Koleksi Game Terpercaya</title>
</head><body>
<h1>OSB99 - Situs Slot</h1>
<h2>Keunggulan OSB99</h2>
<p>Bagian isi milik brand lama yang memang sudah ditulis ulang sejak dulu tanpa aturan baru.</p>

<div class="m-footer-links m-footer-section">
  <div class="link-collection m-foot__links-section">
    <h4>Support</h4>
    <a href="/order">Order Status</a>
    <p>Hubungi tim kami setiap hari kerja untuk pertanyaan seputar pesanan Anda.</p>
  </div>
  <div class="link-collection">
    <h4>About Us</h4>
    <a href="/about">Our Story</a>
  </div>
</div>
</body></html>
"""


def peta(html: str, brand_lama: str = "OSB99"):
    return build_slot_map(scan(html), brand_lama, "id")


def teks_peran(peta_slot: dict, peran: str) -> list[str]:
    return [
        " ".join(str(slot["current"]).split())
        for slot in peta_slot["roles"].get(peran, [])
    ]


class FooterDibiarkan(unittest.TestCase):
    def setUp(self):
        self.peta = peta(FOOTER_DIV)

    def test_judul_kolom_footer_tidak_jadi_slot(self):
        heading = teks_peran(self.peta, "heading")

        self.assertNotIn("Support", heading)
        self.assertNotIn("About Us", heading)

    def test_paragraf_footer_tidak_jadi_slot(self):
        paragraf = teks_peran(self.peta, "paragraph")

        for teks in paragraf:
            self.assertNotIn("Hubungi tim kami", teks)

    def test_isi_di_luar_footer_tetap_ditulis_ulang(self):
        """
        Pembekuan yang kelebihan tangkap sama merugikannya dengan yang
        kekurangan tangkap.
        """
        paragraf = teks_peran(self.peta, "paragraph")

        self.assertTrue(
            any("Bagian isi milik brand lama" in teks for teks in paragraf),
            paragraf,
        )
        self.assertIn("Keunggulan OSB99", teks_peran(self.peta, "heading"))

    def test_nama_brand_di_footer_tetap_berganti(self):
        """
        "jangan ubah BILA TIDAK MENYANGKUT BRAND" - yang menyangkut
        brand tetap berganti, lewat lapis nama yang menyapu seluruh
        halaman termasuk bagian beku.
        """
        html = FOOTER_DIV.replace(
            "<h4>About Us</h4>",
            "<h4>About Us</h4>\n    <p>OSB99 melayani pesanan setiap hari.</p>",
        )

        hasil = fill_template(
            html=html,
            content={
                "title": "RAJAWALI77 | RTP Live Hari Ini & Pola Slot Gacor",
                "h1": "Situs Slot di RAJAWALI77",
                "heading": ["Alasan Memilih RAJAWALI77"],
                "paragraph": [
                    "Halaman ini merangkum jadwal dan cara membaca "
                    "angkanya dalam satu layar supaya mudah ditelusuri."
                ],
            },
            brand=build_brand(
                "RAJAWALI77", "", "id", "", None, keyword="situs slot"
            ),
            old_brand="OSB99",
        )

        self.assertIn("RAJAWALI77 melayani pesanan", hasil["html"])
        self.assertNotIn("OSB99 melayani pesanan", hasil["html"])

        # Kata-kata footernya sendiri tidak berubah.
        self.assertIn("<h4>Support</h4>", hasil["html"])
        self.assertIn("Order Status", hasil["html"])


ALT_BERKREDIT = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 : Situs Slot Eksklusif dengan Koleksi Game Terpercaya</title>
</head><body>
<h1>OSB99 - Situs Slot</h1>
<img src="/a.png" alt="OSB99 : Situs Slot Eksklusif dengan Koleksi Game Terpercaya by Hey siriusly">
<img src="/b.png" alt="OSB99 : Situs Slot Eksklusif dengan Koleksi Game Terpercaya">
<h2>Keunggulan OSB99</h2>
<p>Bagian isi milik brand lama yang memang sudah ditulis ulang sejak dulu tanpa aturan baru.</p>
</body></html>
"""


class JudulLamaDigantiDiManaPun(unittest.TestCase):
    def setUp(self):
        self.judul_baru = "RAJAWALI77 | RTP Live Hari Ini & Pola Slot Gacor"

        self.hasil = fill_template(
            html=ALT_BERKREDIT,
            content={
                "title": self.judul_baru,
                "h1": "Situs Slot di RAJAWALI77",
                "heading": ["Alasan Memilih RAJAWALI77"],
                "paragraph": [
                    "Halaman ini merangkum jadwal dan cara membaca "
                    "angkanya dalam satu layar supaya mudah ditelusuri."
                ],
            },
            brand=build_brand(
                "RAJAWALI77", "", "id", "", None, keyword="situs slot"
            ),
            old_brand="OSB99",
        )

    def test_tidak_ada_sisa_judul_lama(self):
        self.assertNotIn(
            "OSB99 : Situs Slot Eksklusif dengan Koleksi Game Terpercaya",
            self.hasil["html"],
        )

    def test_judul_baru_dipakai_di_kedua_gambar(self):
        # Dibandingkan dalam bentuk TERBIT, bukan bentuk yang dikirim:
        # "&" di dalam atribut ditulis sebagai &amp;, dan itu memang
        # yang benar. Membandingkan dengan bentuk kirim membuat uji ini
        # menuntut HTML yang justru rusak.
        terbit = self.judul_baru.replace("&", "&amp;")

        self.assertEqual(self.hasil["html"].count(terbit), 3)

    def test_keterangan_pemilik_gambar_tetap_berdiri(self):
        """
        Yang ditukar cuma potongan judulnya. "by Hey siriusly" menyebut
        pemilik gambar - ia bukan bagian dari judul halaman.
        """
        self.assertIn("by Hey siriusly", self.hasil["html"])


if __name__ == "__main__":
    unittest.main()
