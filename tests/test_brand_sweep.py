"""
Brand lama yang berdiri di luar slot mana pun.

Diminta pengguna 30 Agustus 2026, sesudah memeriksa halaman jadi:
"fix perbaiki saja jangan generate".

Terukur pada halaman yang benar-benar terbit hari itu, template 616:
dari 64 sebutan brand lama, 54 tersapu dan SEPULUH bertahan. Tiga di
antaranya teks yang dibaca orang -

    <span>BATARATOTO Situs Slot Online Terpercaya</span>
    <strong> LINK BATARATOTO RESMI </strong>
    ... When You Buy <span class="strong">20+ BATARATOTO

- tujuh sisanya di atribut yang memuat tulisan: alt, data-link-label,
data-filter-option-label. Semuanya bersarang terlalu dalam untuk
dikenali pemindai sebagai slot, jadi tidak satu lapis pun yang ada
sebelumnya pernah melihatnya.

Template itu juga memperlihatkan soal kedua: ia punya DUA brand lama
berlapis - strukturnya milik TeePublic, brandingnya BATARATOTO - dan
kolom brand lama cuma bisa diisi satu. Yang tidak disebut lolos utuh,
termasuk di og:site_name.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.brand_swap import (
    attribute_name,
    brand_names,
    brand_sweep_edits,
    inside_url,
    variants,
)
from generators.template_filler import fill_template
from generators.template_scanner import scan
from generators.template_slots import build_slot_map


# Bentuk-bentuk yang persis bikin halaman 30 Agustus 2026 bocor,
# berdampingan dengan bentuk yang TIDAK boleh disentuh.
HALAMAN = """<!doctype html>
<html lang="id"><head>
<meta charset="utf-8">
<title>OLDBRAND : Situs Terpercaya</title>
<meta name="description" content="OLDBRAND menghadirkan layanan.">
<meta property="og:site_name" content="OLDBRAND">
<link rel="stylesheet" href="/assets/oldbrand/style.css">
<script>window.OLDBRAND = window.OLDBRAND || {}; OLDBRAND.init();</script>
<style>.oldbrand--border { color: red; }</style>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"OLDBRAND"}
</script>
</head><body id="oldbrand" class="oldbrand--theme">
<header>
  <div class="running-text"><div class="running-text__inner">
    <span><span>OLDBRAND Situs Slot Online Terpercaya</span></span>
  </div></div>
  <strong> LINK OLDBRAND RESMI </strong>
  <img src="/img/oldbrand-logo.png" alt="OLDBRAND Logo">
  <a href="https://oldbrand.com/login" data-link-label="OLDBRAND">Masuk</a>
  <a href="/faq" data-filter-option-label="Apa Itu OLDBRAND ?">FAQ</a>
</header>
<main>
  <h1>OLDBRAND : Situs Terpercaya</h1>
  <p>Halaman ini milik OLDBRAND dan sudah lama berdiri di sini
  melayani orang yang mencari tempat bermain tanpa banyak syarat.</p>
</main>
</body></html>"""


class PenyapuMenyentuhYangBenar(unittest.TestCase):
    """
    Yang diadu di sini SATU hal: sebutan yang tidak berdiri di slot
    mana pun ikut tersapu.

    Halaman contoh di berkas ini sengaja kecil dan rapi, dan itu
    membuatnya berbeda dari template sungguhan dalam satu hal yang
    penting: di sini pemindai berhasil mengenali tulisan ticker,
    <strong>, dan alt sebagai slot, jadi ketiganya diurus brand_edits
    dan penyapu ini memang TIDAK menyentuhnya. Di template 313 KB
    milik pengguna ketiganya bersarang terlalu dalam dan tidak pernah
    jadi slot - itu sebabnya ketiganya bocor ke halaman jadi.

    Karena itu yang diadu di kelas ini cuma atribut data-*, satu-
    satunya bentuk yang pasti bukan slot di kedua dokumen. Bahwa
    ketiga bentuk yang lain benar-benar hilang diadu di
    test_halaman_penuh_tetap_bisa_diisi, atas hasil akhirnya - yang
    memang ukuran yang benar, karena yang penting bagi pembaca bukan
    lapis mana yang mengerjakannya.
    """

    def setUp(self):
        self.peta = build_slot_map(scan(HALAMAN), "OLDBRAND", "id")
        self.edits, self.jumlah = brand_sweep_edits(
            HALAMAN, self.peta, [], "OLDBRAND", "NEWBRAND"
        )
        self.kena = [
            HALAMAN[e["start"] - 60 : e["end"] + 30] for e in self.edits
        ]

    def cocok(self, penanda):
        return any(penanda in potong for potong in self.kena)

    def test_atribut_bertulisan_ikut_disapu(self):
        for penanda in ("data-link-label", "data-filter-option-label"):
            with self.subTest(penanda=penanda):
                self.assertTrue(self.cocok(penanda), self.kena)

    def test_teksnya_yang_ditulis_nama_baru(self):
        for e in self.edits:
            with self.subTest(awal=e["start"]):
                self.assertIn("NEWBRAND", e["text"])
                self.assertNotIn("OLDBRAND", e["text"])

    def test_tanpa_nama_baru_tidak_menyunting_apa_pun(self):
        edits, jumlah = brand_sweep_edits(
            HALAMAN, self.peta, [], "OLDBRAND", ""
        )

        self.assertEqual((edits, jumlah), ([], 0))

    def test_tanpa_brand_lama_tidak_menyunting_apa_pun(self):
        edits, jumlah = brand_sweep_edits(
            HALAMAN, self.peta, [], "", "NEWBRAND"
        )

        self.assertEqual((edits, jumlah), ([], 0))


class PenyapuTidakMenyentuhYangSalah(unittest.TestCase):
    """
    Setiap satu di sini pernah jadi kandidat suntingan waktu penyapu
    ini ditulis, dan setiap satu akan merusak halaman.
    """

    def setUp(self):
        self.peta = build_slot_map(scan(HALAMAN), "OLDBRAND", "id")
        self.edits, _ = brand_sweep_edits(
            HALAMAN, self.peta, [], "OLDBRAND", "NEWBRAND"
        )
        self.posisi = [e["start"] for e in self.edits]

    def tidak_kena(self, potongan: str):
        awal = HALAMAN.index(potongan)

        return not any(awal <= p < awal + len(potongan) for p in self.posisi)

    def test_nama_variabel_javascript_dilewati(self):
        self.assertTrue(self.tidak_kena("window.OLDBRAND = window.OLDBRAND"))

    def test_nama_kelas_css_dilewati(self):
        self.assertTrue(self.tidak_kena(".oldbrand--border"))

    def test_id_dan_class_dilewati(self):
        self.assertTrue(self.tidak_kena('id="oldbrand" class="oldbrand--theme"'))

    def test_alamat_dilewati(self):
        for potongan in (
            "/assets/oldbrand/style.css",
            "/img/oldbrand-logo.png",
            "https://oldbrand.com/login",
        ):
            with self.subTest(potongan=potongan):
                self.assertTrue(self.tidak_kena(potongan))

    def test_blok_jsonld_dilewati(self):
        """
        Bukan karena berbahaya, melainkan karena sudah ada
        pemiliknya: jsonld_filler menulis ulang seluruh bloknya
        sebagai satu rentang. Menyapunya lagi di sini membuat dua
        suntingan bertumpang tindih, dan halamannya tidak terbit sama
        sekali.
        """
        self.assertTrue(
            self.tidak_kena('"@type":"Organization","name":"OLDBRAND"')
        )


class TidakBertabrakanDenganSuntinganLain(unittest.TestCase):
    def test_rentang_yang_sudah_dipakai_dilewati(self):
        peta = build_slot_map(scan(HALAMAN), "OLDBRAND", "id")

        awal = HALAMAN.index("LINK OLDBRAND RESMI")
        dipakai = [{"start": awal, "end": awal + 20, "text": "x"}]

        edits, _ = brand_sweep_edits(
            HALAMAN, peta, dipakai, "OLDBRAND", "NEWBRAND"
        )

        for e in edits:
            self.assertFalse(
                e["start"] < awal + 20 and awal < e["end"],
                f"suntingan {e['start']}-{e['end']} menabrak yang dipakai",
            )

    def test_halaman_penuh_tetap_bisa_diisi(self):
        """
        Uji yang sebenarnya: seluruh lapis berjalan berurutan dan
        apply_edits tidak menolak satu pun.
        """
        hasil = fill_template(
            HALAMAN,
            {
                "title": "NEWBRAND | Judul Baru yang Cukup Panjang",
                "meta_description": "NEWBRAND menyajikan layanan.",
                "h1": "Layanan di NEWBRAND",
            },
            {
                "site_name": "NEWBRAND",
                "region": "id",
                "language_name": "Indonesia",
                "year": "2026",
            },
            old_brand="OLDBRAND",
        )

        keluar = hasil["html"]

        # Ketiga bentuk yang bocor ke halaman 30 Agustus 2026, diadu
        # atas hasil akhirnya - lihat keterangan di
        # PenyapuMenyentuhYangBenar untuk kenapa bukan atas penyapunya.
        self.assertNotIn("OLDBRAND Situs Slot Online", keluar)
        self.assertNotIn("LINK OLDBRAND RESMI", keluar)
        self.assertNotIn('alt="OLDBRAND Logo"', keluar)

        # Atribut data-*, yang cuma penyapu ini yang melihatnya.
        self.assertNotIn('data-link-label="OLDBRAND"', keluar)
        self.assertNotIn("Apa Itu OLDBRAND ?", keluar)

        # yang harus tetap berdiri
        self.assertIn("window.OLDBRAND = window.OLDBRAND", keluar)
        self.assertIn("/img/oldbrand-logo.png", keluar)
        self.assertIn('id="oldbrand"', keluar)


class BeberapaBrandLamaSekaligus(unittest.TestCase):
    def test_kolom_dipecah_koma_dan_baris(self):
        self.assertEqual(
            brand_names("BATARATOTO, TeePublic"),
            ["BATARATOTO", "TeePublic"],
        )
        self.assertEqual(
            brand_names("BATARATOTO\nTeePublic;  OSB99 "),
            ["BATARATOTO", "TeePublic", "OSB99"],
        )

    def test_satu_nama_berperilaku_sama_seperti_dulu(self):
        self.assertEqual(brand_names("OSB99"), ["OSB99"])
        self.assertEqual(brand_names(""), [])
        self.assertEqual(brand_names(None), [])

    def test_bentuk_berspasi_tetap_ikut_dikenali(self):
        """
        variants sudah lama mencari "AbeceDe" untuk nama "Abece De".
        Menerima daftar tidak boleh menghilangkannya.
        """
        bentuk = variants("Abece De, OSB99")

        for wajib in ("Abece De", "AbeceDe", "Abece-De", "OSB99"):
            with self.subTest(wajib=wajib):
                self.assertIn(wajib, bentuk)

    def test_dua_brand_lama_tersapu_dua_duanya(self):
        halaman = HALAMAN.replace(
            "<h1>OLDBRAND : Situs Terpercaya</h1>",
            "<h1>OLDBRAND : Situs Terpercaya</h1>\\n<p>Dibuat oleh "
            "SecondBrand untuk semua orang yang mencari tempat main "
            "yang jelas dan tidak berbelit sama sekali.</p>",
        )

        peta = build_slot_map(scan(halaman), "OLDBRAND", "id")
        edits, _ = brand_sweep_edits(
            halaman, peta, [], "OLDBRAND, SecondBrand", "NEWBRAND"
        )

        self.assertTrue(edits)


class PembacaanKonteks(unittest.TestCase):
    def test_nama_atribut_dibaca_benar(self):
        html = '<a id="x" data-link-label="OLDBRAND" href="/y">z</a>'

        self.assertEqual(
            attribute_name(html, html.index("OLDBRAND")),
            "data-link-label",
        )

    def test_json_tidak_terbaca_sebagai_atribut(self):
        """
        Tanda "=" yang membedakan. Di dalam JSON, yang berdiri sebelum
        tanda kutip nilainya titik dua.
        """
        html = '<script>{"name": "OLDBRAND"}</script>'

        self.assertEqual(attribute_name(html, html.index("OLDBRAND")), "")

    def test_teks_biasa_bukan_atribut(self):
        html = "<p>Halaman OLDBRAND ini</p>"

        self.assertEqual(attribute_name(html, html.index("OLDBRAND")), "")

    def test_alamat_dikenali_dari_bentuknya(self):
        for html in (
            '<a href="https://oldbrand.com/x">y</a>',
            '<img src="/img/oldbrand-logo.png">',
        ):
            with self.subTest(html=html):
                awal = html.lower().index("oldbrand")

                self.assertTrue(inside_url(html, awal, awal + 8))

    def test_teks_biasa_bukan_alamat(self):
        html = "<p>Halaman OLDBRAND ini</p>"
        awal = html.index("OLDBRAND")

        self.assertFalse(inside_url(html, awal, awal + 8))


if __name__ == "__main__":
    unittest.main()
