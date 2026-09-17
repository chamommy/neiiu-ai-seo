"""
Template adalah kontrak: yang bukan slot isi tidak boleh berubah.

Dibuktikan dua arah sekaligus, karena satu arah saja selalu bisa
dipenuhi dengan cara yang salah:

  1. Seluruh potongan beku terbawa apa adanya ke berkas jadi.
     Halaman yang membuang iklannya lulus arah kedua dengan mudah.
  2. Tidak satu pun teks pemilik template tersisa. Halaman yang
     tidak mengganti apa-apa lulus arah pertama dengan sempurna.

Tidak memakai AI sama sekali. Isinya ditulis di sini supaya yang
diuji benar-benar lapisan pengisi template, bukan mutu model.
"""

import unittest

from generators.final_verify import verify_pages
from generators.template_filler import derive_spec, fill_template
from generators.template_scanner import scan
from generators.template_slots import build_slot_map
from services.neiiu_pipeline import build_brand
from tests.fixtures import AMP, BEKU, LANDING, SISA_TEMPLATE


ISI = {
    "title": "WAYANGPLAY | Slot Gacor dengan Navigasi yang Ringkas",
    "meta_description": (
        "Halaman WAYANGPLAY menyusun daftar slot gacor dalam satu "
        "layar, lengkap dengan menu yang mudah ditelusuri dari ponsel "
        "maupun komputer meja."
    ),
    "h1": "Slot Gacor di WAYANGPLAY",
    "heading": ["Cara Menelusuri Daftarnya"],
    "paragraph": [
        "Daftar permainan disusun menurut penyedianya, jadi pembaca "
        "yang sudah punya nama incaran bisa langsung menuju baris "
        "yang dicari tanpa menggulir seluruh halaman lebih dulu.",
        "Menu bagian atas tetap terlihat waktu halaman digulir, "
        "sehingga perpindahan antarbagian tidak menuntut siapa pun "
        "kembali ke puncak halaman setiap kali ganti topik bacaan.",
    ],
    "faq_question": [
        "Bagaimana cara menemukan permainan tertentu di halaman ini?",
        "Apakah tampilannya berubah kalau dibuka lewat ponsel?",
    ],
    "faq_answer": [
        "Gunakan menu penyedia di bagian atas daftar, lalu telusuri "
        "baris yang muncul di bawahnya sampai menemukan namanya.",
        "Tata letaknya menyesuaikan lebar layar, dan urutan bagiannya "
        "tetap sama seperti waktu dibuka lewat komputer meja.",
    ],
    "review_text": [
        "Menu penyedianya jelas dan saya tidak perlu menebak-nebak "
        "bagian mana yang harus dibuka lebih dulu.",
        "Halamannya terbuka cepat di jaringan biasa dan tidak ada "
        "bagian yang melompat waktu digulir sampai bawah.",
        "Sempat bingung di layar kecil, tapi setelah itu urutan "
        "bagiannya mudah diikuti sampai selesai.",
    ],
    "breadcrumb": ["Beranda", "Slot", "Slot Gacor"],
}


class TemplateIntegrity(unittest.TestCase):
    def setUp(self):
        self.brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        self.landing = fill_template(
            html=LANDING,
            content=dict(ISI),
            brand=self.brand,
            old_brand="",
        )

        self.amp = fill_template(
            html=AMP,
            content=dict(ISI),
            brand=self.brand,
            old_brand="",
            is_amp=True,
        )

    def test_wilayah_beku_byte_identik(self):
        for label, potongan in BEKU:
            with self.subTest(bagian=label):
                self.assertIn(potongan, self.landing["html"], label)
                self.assertIn(potongan, self.amp["html"], label)

    def test_teks_pemilik_template_tersapu(self):
        for teks in SISA_TEMPLATE:
            with self.subTest(teks=teks):
                self.assertNotIn(teks, self.landing["html"])
                self.assertNotIn(teks, self.amp["html"])

    def test_di_luar_slot_tidak_bergeser_satu_byte_pun(self):
        """
        Pembuktian yang sesungguhnya: bukan mencari potongan tertentu,
        melainkan menyambung kembali SELURUH bagian di luar slot dan
        mengadunya dengan bagian yang sama dari template asli.
        """
        hasil = verify_pages(
            landing_html=self.landing["html"],
            amp_html=self.amp["html"],
            template_landing=LANDING,
            template_amp=AMP,
            landing_ranges=self.landing["ranges"],
            amp_ranges=self.amp["ranges"],
            brand="WAYANGPLAY",
            keyword="slot gacor",
            region="id",
        )

        berubah = [
            masalah
            for masalah in hasil["hard"]
            if "di luar slot" in masalah
        ]

        self.assertEqual(berubah, [])

    def test_jumlah_bagian_mengikuti_template(self):
        """
        Tidak ada bagian yang ditambah dan tidak ada yang dihapus.
        """
        for html in (self.landing["html"], self.amp["html"]):
            self.assertEqual(html.count("<blockquote"), 3)
            self.assertEqual(html.count("<h3"), 2)
            self.assertEqual(html.count("<h1"), 1)

        # Landing punya dua H2, AMP satu - persis seperti templatenya.
        self.assertEqual(self.landing["html"].count("<h2"), 2)
        self.assertEqual(self.amp["html"].count("<h2"), 1)

    def test_paragraf_tidak_pernah_ditambah(self):
        self.assertEqual(
            self.landing["html"].count("<p>"),
            LANDING.count("<p>"),
        )

    def test_isi_baru_benar_benar_terpasang(self):
        for html in (self.landing["html"], self.amp["html"]):
            self.assertIn("Slot Gacor di WAYANGPLAY", html)
            self.assertIn("Daftar permainan disusun menurut", html)

        # Judul bagian bebas hanya diuji di landing, dan itu bukan
        # kelonggaran: berkas AMP di fixture ini sengaja kehilangan
        # satu H2, sehingga satu-satunya H2 yang tersisa berdiri
        # sebagai judul blok FAQ. Judul blok ditulis Python, bukan
        # diminta ke AI - lihat BLOCK_HEADINGS - jadi menuntut judul
        # bebas muncul di sana berarti menuntut keterangan blok
        # diisi konten, yang justru dilarang.
        self.assertIn("Cara Menelusuri Daftarnya", self.landing["html"])
        self.assertIn("FAQ WAYANGPLAY", self.amp["html"])

    def test_slot_terbaca_sama_di_landing_dan_amp(self):
        """
        Kedua berkas berangkat dari SATU isi, jadi kepalanya sama.
        """
        hasil = verify_pages(
            landing_html=self.landing["html"],
            amp_html=self.amp["html"],
            template_landing=LANDING,
            template_amp=AMP,
            brand="WAYANGPLAY",
            keyword="slot gacor",
            region="id",
        )

        tidak_sinkron = [
            masalah
            for masalah in hasil["hard"]
            if "landing dan AMP berbeda" in masalah
        ]

        self.assertEqual(tidak_sinkron, [])

    def test_slot_yang_dikenali_tidak_menyentuh_iklan(self):
        """
        Blok iklan tidak boleh pernah masuk peta slot.
        """
        peta = build_slot_map(scan(LANDING), "", "id")
        spec = derive_spec(peta)

        # Jumlah slot yang dikenali harus sama dengan jumlah tempat
        # isi milik template - bukan lebih.
        self.assertEqual(spec["paragraph"]["count"], 2)
        self.assertEqual(spec["review_text"]["count"], 3)
        self.assertEqual(spec["faq_question"]["count"], 2)

        teks_slot = " ".join(
            str(contoh)
            for rule in spec.values()
            for contoh in (rule.get("samples") or [])
        )

        self.assertNotIn("Promo", teks_slot)
        self.assertNotIn("sponsor.invalid", teks_slot)


if __name__ == "__main__":
    unittest.main()
