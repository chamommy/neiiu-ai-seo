"""
Alamat halaman: canonical, amphtml, dan tujuan tombol login/daftar.

Yang dibuktikan di sini ada dua sisi, dan sisi pertama yang paling
penting:

  1. KOSONG BERARTI TIDAK DISENTUH. Job yang tidak mengisi satu pun
     kolom alamat harus menghasilkan berkas yang alamatnya sama persis
     dengan template unggahan - tidak ada canonical yang dikarang,
     tidak ada baris yang ditambahkan, tidak ada tombol yang
     dialihkan. Ini yang dulu dilanggar: kolom domain yang dikosongkan
     jatuh ke SITE_BASE_URL, yang bawaannya "https://example.com".

  2. Yang diisi benar-benar terpasang, dan hanya di tempat yang benar.
     Kolom yang diisi lalu tidak mengubah apa pun adalah kolom yang
     berbohong - dan kolom "tujuan tombol" persis begitu selama ini
     untuk template yang lengkap: nilainya cuma sampai ke
     generators/blocks.py, yang tidak pernah dipakai kalau template
     AMP-nya diunggah.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.page_links import (
    UnsafeLinkUrl,
    clean_link,
    clean_links,
    cocok_cta,
    link_edits,
)
from generators.final_verify import verify_pages
from generators.template_assets import asset_edits
from generators.template_filler import fill_template
from generators.template_scanner import apply_edits, scan
from services.neiiu_pipeline import build_brand
from tests.fixtures import AMP, LANDING


# Template kecil yang memuat setiap bentuk tombol yang harus
# dibedakan. Ditulis di sini, bukan di fixtures bersama, karena
# seluruh isinya jebakan untuk satu berkas ini saja.
TOMBOL = """<!doctype html>
<html><head>
<meta charset="utf-8">
<link rel="canonical" href="https://pemilik-lama.example/slot/">
<title>Halaman Lama</title>
</head><body>
<header>
  <a class="btn-masuk" href="https://pemilik-lama.example/login">Login</a>
  <a href="https://pemilik-lama.example/reg"><span>Daftar</span></a>
  <a class="signup-ikon" href="https://pemilik-lama.example/s"><svg></svg></a>
</header>
<a href="#daftar">Daftar di bawah</a>
<a href="javascript:void(0)">Login</a>
<a href="https://pemilik-lama.example/artikel">Baca panduan daftar akun
baru supaya tidak salah langkah waktu mengisi datanya sampai selesai</a>
<a href="https://pemilik-lama.example/kontak">Hubungi Kami</a>
<div class="ad" data-slot="x">
  <a href="https://sponsor.invalid/promo">Daftar Sekarang</a>
</div>
<a data-neiiu="daftar" href="https://pemilik-lama.example/aneh">Gabung Yuk</a>
</body></html>"""


THAI = """<!doctype html>
<html><head><meta charset="utf-8"><title>x</title></head><body>
<a href="https://lama.example/a">เข้าสู่ระบบ</a>
<a href="https://lama.example/b">สมัครสมาชิก</a>
<a href="https://lama.example/c">ติดต่อเรา</a>
</body></html>"""


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


def terapkan(html: str, links: dict):
    """
    Menjalankan link_edits lalu menerapkannya, seperti fill_template.
    """
    scanned = scan(html)
    edits, swaps, tambahan, catatan = link_edits(scanned, html, links)

    return apply_edits(html, edits), swaps, tambahan, catatan


class BentukAlamat(unittest.TestCase):
    def test_kosong_tetap_kosong(self):
        self.assertEqual(clean_link(""), "")
        self.assertEqual(clean_link("   "), "")
        self.assertEqual(clean_links({}), {})
        self.assertEqual(clean_links(None), {})

    def test_alamat_penuh_dan_relatif_diterima(self):
        self.assertEqual(
            clean_link("https://a.id/x/"),
            "https://a.id/x/",
        )
        self.assertEqual(clean_link("/daftar"), "/daftar")

    def test_alamat_ngawur_ditolak(self):
        for buruk in (
            "javascript:alert(1)",
            "brandmu.com",
            'https://a.id/" onload="x',
            "https://a.id/ ada spasi",
        ):
            with self.subTest(buruk=buruk):
                with self.assertRaises(UnsafeLinkUrl):
                    clean_link(buruk, "canonical")

    def test_pesan_menyebut_kolomnya(self):
        with self.assertRaises(UnsafeLinkUrl) as kena:
            clean_link("bukan alamat", "canonical")

        self.assertIn("canonical", str(kena.exception))


class KosongTidakMenyentuh(unittest.TestCase):
    """
    Sisi yang paling penting. Lihat keterangan di kepala berkas.
    """

    def test_tanpa_kolom_tidak_ada_edit(self):
        hasil, swaps, tambahan, catatan = terapkan(TOMBOL, {})

        self.assertEqual(hasil, TOMBOL)
        self.assertEqual(swaps, [])
        self.assertEqual(tambahan, {})
        self.assertEqual(catatan, [])

    def test_none_sama_dengan_kosong(self):
        scanned = scan(TOMBOL)

        self.assertEqual(
            link_edits(scanned, TOMBOL, {})[0],
            link_edits(scanned, TOMBOL, {})[0],
        )

    def test_fill_template_tanpa_alamat_tidak_menambah_amphtml(self):
        brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        hasil = fill_template(
            html=LANDING,
            content=dict(ISI),
            brand=brand,
            old_brand="",
        )["html"]

        self.assertNotIn("amphtml", hasil)
        self.assertNotIn("example.com", hasil)

    def test_fill_template_tanpa_alamat_tidak_mengubah_tautan(self):
        brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        hasil = fill_template(
            html=LANDING,
            content=dict(ISI),
            brand=brand,
            old_brand="",
            links={},
        )["html"]

        # Tautan sponsor di dalam blok iklan adalah yang paling tajam:
        # kalau lapis tautan salah menyapu, ia yang hilang duluan.
        self.assertIn("https://sponsor.invalid/promo?ref=abc", hasil)


class Canonical(unittest.TestCase):
    def test_diganti_di_tempat(self):
        hasil, swaps, tambahan, _ = terapkan(
            TOMBOL,
            {"canonical": "https://baru.id/slot-gacor/"},
        )

        self.assertIn(
            '<link rel="canonical" href="https://baru.id/slot-gacor/">',
            hasil,
        )
        self.assertNotIn("pemilik-lama.example/slot/", hasil)

        # Tidak ada tag yang ditambahkan: templatenya sudah punya.
        self.assertEqual(tambahan, {})
        self.assertEqual(len(swaps), 1)

    def test_ditambahkan_kalau_template_belum_punya(self):
        hasil, _, tambahan, catatan = terapkan(
            THAI,
            {"canonical": "https://baru.id/x/"},
        )

        self.assertIn(
            '<link rel="canonical" href="https://baru.id/x/">',
            hasil,
        )
        self.assertEqual(tambahan, {"link": 1})
        self.assertTrue(any("ditambahkan" in c for c in catatan))

    def test_disisipkan_sebelum_penutup_head(self):
        hasil, _, _, _ = terapkan(THAI, {"canonical": "https://baru.id/x/"})

        self.assertLess(hasil.index("rel=\"canonical\""), hasil.index("</head>"))

    def test_ampersand_di_alamat_di_escape(self):
        hasil, _, _, _ = terapkan(
            THAI,
            {"canonical": "https://baru.id/x?a=1&b=2"},
        )

        self.assertIn("a=1&amp;b=2", hasil)


class Amphtml(unittest.TestCase):
    def test_ditambahkan_ke_head(self):
        hasil, _, tambahan, _ = terapkan(
            TOMBOL,
            {"amphtml": "https://baru.id/slot/amp/"},
        )

        self.assertIn(
            '<link rel="amphtml" href="https://baru.id/slot/amp/">',
            hasil,
        )
        self.assertEqual(tambahan, {"link": 1})

    def test_tanpa_head_dilaporkan_bukan_dipaksakan(self):
        potongan = "<div><a href='/x'>y</a></div>"

        hasil, _, tambahan, catatan = terapkan(
            potongan,
            {"amphtml": "https://baru.id/amp/"},
        )

        self.assertEqual(hasil, potongan)
        self.assertEqual(tambahan, {})
        self.assertTrue(any("</head>" in c for c in catatan))


class TombolAjakan(unittest.TestCase):
    def setUp(self):
        self.hasil, self.swaps, _, self.catatan = terapkan(
            TOMBOL,
            {"cta": "https://tujuan-baru.id/"},
        )

    def test_tombol_bertulisan_diarahkan(self):
        self.assertIn(
            '<a class="btn-masuk" href="https://tujuan-baru.id/">Login</a>',
            self.hasil,
        )
        self.assertIn(
            '<a href="https://tujuan-baru.id/"><span>Daftar</span></a>',
            self.hasil,
        )

    def test_tombol_bergambar_dikenali_dari_class(self):
        self.assertIn(
            '<a class="signup-ikon" href="https://tujuan-baru.id/">',
            self.hasil,
        )

    def test_penanda_pengguna_menang(self):
        self.assertIn(
            '<a data-neiiu="daftar" href="https://tujuan-baru.id/">',
            self.hasil,
        )

    def test_tautan_dalam_halaman_dilewati(self):
        self.assertIn('<a href="#daftar">Daftar di bawah</a>', self.hasil)

    def test_javascript_dilewati(self):
        self.assertIn('<a href="javascript:void(0)">Login</a>', self.hasil)

    def test_kalimat_panjang_bukan_tombol(self):
        self.assertIn("pemilik-lama.example/artikel", self.hasil)

    def test_tautan_biasa_tidak_disentuh(self):
        self.assertIn("pemilik-lama.example/kontak", self.hasil)

    def test_tombol_di_dalam_iklan_tidak_disentuh(self):
        self.assertIn("https://sponsor.invalid/promo", self.hasil)

    def test_jumlahnya_dilaporkan(self):
        self.assertEqual(len(self.swaps), 4)
        self.assertTrue(
            any("4 tombol" in c for c in self.catatan), self.catatan
        )

    def test_tanpa_tombol_dilaporkan_apa_adanya(self):
        _, swaps, _, catatan = terapkan(
            THAI.replace("เข้าสู่ระบบ", "หน้าแรก").replace(
                "สมัครสมาชิก", "เกี่ยวกับเรา"
            ),
            {"cta": "https://tujuan-baru.id/"},
        )

        self.assertEqual(swaps, [])
        self.assertTrue(any("Tidak ada" in c for c in catatan))


class KosakataTombol(unittest.TestCase):
    """
    Daftar kata tombol, diadu ke tulisan tombol yang benar-benar ada
    di template pengguna (template 488) dan di template Thai.

    Dua barisnya lahir dari pengujian itu: tombol utama template
    tertulis "BUAT AKUN", dan tidak satu pun kata di daftar
    sebelumnya menyentuhnya. Kolom tujuan tombol terisi, tombol
    pendaftaran paling atas tidak berpindah, dan tidak ada yang
    melaporkan apa pun.
    """

    def test_tulisan_tombol_dikenali(self):
        for teks in (
            "BUAT AKUN",
            "Create an Account",
            "Create Account",
            "LOGIN",
            "REGISTER",
            "Log In",
            "Sign-Up",
            "SignUp",
            "DAFTAR",
            "Registrasi",
            "Gabung Sekarang",
            "BATARATOTO LOGIN",
            "เข้าสู่ระบบ",
            "สมัครสมาชิก",
        ):
            with self.subTest(teks=teks):
                self.assertTrue(cocok_cta(teks), teks)

    def test_tautan_biasa_tidak_dikenali(self):
        for teks in (
            "Shop All Designs",
            "Size Chart",
            "Contact Us",
            "Privacy Policy",
            "Order Status",
            "Kids T-Shirts",
            "Tag Directory",
            "Coupon Codes",
            "Free Shipping",
            "About Us",
            "Careers",
            "Newest Designers",
            "ติดต่อเรา",
        ):
            with self.subTest(teks=teks):
                self.assertFalse(cocok_cta(teks), teks)

    def test_potongan_kata_tidak_ikut(self):
        """
        "masuk" tidak boleh menangkap "termasuk", dan "daftar" tidak
        boleh menangkap "pendaftaran" sebagai potongan tengah kata.
        """
        self.assertFalse(cocok_cta("Termasuk ongkos kirim"))
        self.assertFalse(cocok_cta("Registrasi"[2:]))


class AnchorBukanGambar(unittest.TestCase):
    """
    href milik <a> ikut dipindai sejak tujuan tombol bisa ditukar.
    Yang tidak boleh ikut: penentu peran GAMBAR, yang membaca penanda
    data-neiiu paling dulu dan tidak peduli tagnya apa.
    """

    def test_anchor_bertanda_logo_tidak_kebagian_alamat_gambar(self):
        html = (
            '<html><body><header>'
            '<a data-neiiu="logo" href="/beranda">'
            '<img src="/logo-lama.png" alt="Logo"></a>'
            "</header></body></html>"
        )

        scanned = scan(html)

        gambar, _, _ = asset_edits(
            scanned,
            {"logo": "https://cdn.example/logo-baru.png"},
        )

        for edit in gambar:
            self.assertNotEqual(
                edit["tag"],
                "a",
                "alamat gambar ditulis ke dalam href tombol",
            )

    def test_gambar_di_dalamnya_tetap_berganti(self):
        html = (
            '<html><body><header>'
            '<a data-neiiu="logo" href="/beranda">'
            '<img src="/logo-lama.png" alt="Logo"></a>'
            "</header></body></html>"
        )

        scanned = scan(html)

        gambar, _, _ = asset_edits(
            scanned,
            {"logo": "https://cdn.example/logo-baru.png"},
        )

        hasil = apply_edits(html, gambar)

        self.assertIn('src="https://cdn.example/logo-baru.png"', hasil)
        self.assertIn('href="/beranda"', hasil)


class TombolThai(unittest.TestCase):
    def test_kata_thai_dikenali(self):
        hasil, swaps, _, _ = terapkan(
            THAI,
            {"cta": "https://tujuan-baru.id/"},
        )

        self.assertEqual(len(swaps), 2)
        self.assertIn(
            '<a href="https://tujuan-baru.id/">เข้าสู่ระบบ</a>',
            hasil,
        )
        self.assertIn("lama.example/c", hasil)


class LewatPengisiTemplate(unittest.TestCase):
    """
    Sampai ke fill_template, tempat pemeriksa struktur berjalan.

    Ini yang membuktikan alamat baru tidak dibatalkan template_guard:
    tanpa daftar swaps yang benar, canonical yang berhasil ditukar
    dilaporkan sebagai "atribut elemen berubah" lalu SELURUH hasil
    isian ditolak.
    """

    def test_alamat_terpasang_dan_struktur_lolos(self):
        brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        hasil = fill_template(
            html=LANDING,
            content=dict(ISI),
            brand=brand,
            old_brand="",
            links={
                "canonical": "https://wayangplay.id/slot-gacor/",
                "amphtml": "https://wayangplay.id/slot-gacor/amp/",
            },
        )

        html = hasil["html"]

        self.assertIn(
            'rel="canonical" href="https://wayangplay.id/slot-gacor/"',
            html,
        )
        self.assertIn(
            'rel="amphtml" href="https://wayangplay.id/slot-gacor/amp/"',
            html,
        )

        # Iklan dan tautan sponsor tetap utuh.
        self.assertIn("https://sponsor.invalid/promo?ref=abc", html)
        self.assertIn('data-slot="top"', html)

    def test_pemeriksa_akhir_menerima_link_yang_disisipkan(self):
        """
        Gerbang terakhir sebelum berkas ditulis ke disk.

        fill_template punya pemeriksa sendiri, tapi yang memutuskan
        halaman boleh terbit atau tidak adalah verify_pages - dan ia
        membandingkan berkas jadi dengan template asli sekali lagi,
        atas teks yang PERSIS akan mendarat di disk. Satu baris
        <link> yang ditambahkan ke dalam <head> adalah byte yang
        tidak ada di template, jadi kalau rentangnya tidak ikut
        dilaporkan, seluruh run berhenti dengan "gagal pemeriksaan
        akhir" - sesudah belasan menit terpakai.
        """
        brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        alamat = {
            "canonical": "https://wayangplay.id/slot-gacor/",
            "amphtml": "https://wayangplay.id/slot-gacor/amp/",
            "cta": "https://daftar.wayangplay.id/",
        }

        landing = fill_template(
            html=LANDING,
            content=dict(ISI),
            brand=brand,
            old_brand="",
            links=alamat,
        )

        amp = fill_template(
            html=AMP,
            content=dict(ISI),
            brand=brand,
            old_brand="",
            is_amp=True,
            links={
                peran: nilai
                for peran, nilai in alamat.items()
                if peran != "amphtml"
            },
        )

        hasil = verify_pages(
            landing_html=landing["html"],
            amp_html=amp["html"],
            template_landing=LANDING,
            template_amp=AMP,
            landing_ranges=landing["ranges"],
            amp_ranges=amp["ranges"],
            brand="WAYANGPLAY",
            old_brand="",
            keyword="slot gacor",
            region="id",
        )

        self.assertEqual(hasil["hard"], [], hasil["hard"])

        # Berkas AMP tidak menunjuk versi AMP-nya sendiri.
        self.assertNotIn("amphtml", amp["html"])


if __name__ == "__main__":
    unittest.main()
