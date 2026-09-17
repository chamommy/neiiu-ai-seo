"""
Pemeriksa terakhir harus menahan halaman yang salah, dan hanya itu.

Dua sisi diuji sama seriusnya. Pemeriksa yang menolak segalanya
sama tidak bergunanya dengan pemeriksa yang meloloskan segalanya -
yang pertama membuat generator tidak pernah menerbitkan apa pun,
yang kedua membuat pemeriksaannya sekadar hiasan.
"""

import re
import unittest

from generators.final_verify import brand_typos, thai_share, verify_pages


BAIK = """<!doctype html><html lang="id"><head>
<title>WAYANGPLAY | Slot Gacor dengan Navigasi Ringkas</title>
<meta name="description" content="Halaman WAYANGPLAY menyusun daftar
slot gacor dalam satu layar, lengkap dengan menu yang mudah ditelusuri
dari ponsel maupun komputer meja.">
<script type="application/ld+json">{"@context":"https://schema.org",
"@type":"WebPage","name":"WAYANGPLAY"}</script>
</head><body>
<h1>Slot Gacor di WAYANGPLAY</h1>
<p>Daftar permainan disusun menurut penyedianya, jadi pembaca yang
sudah punya nama incaran bisa langsung menuju baris yang dicari.</p>
<p>Menu bagian atas tetap terlihat waktu halaman digulir ke bawah,
termasuk waktu halaman dibuka lewat layar yang lebih kecil.</p>
</body></html>"""


def dengan(html: str, lama: str, baru: str) -> str:
    assert lama in html
    return html.replace(lama, baru)


class HalamanSehatLolos(unittest.TestCase):
    def test_tidak_ada_penahan(self):
        hasil = verify_pages(
            landing_html=BAIK,
            brand="WAYANGPLAY",
            keyword="slot gacor",
            region="id",
        )

        self.assertEqual(hasil["hard"], [])

    def test_fakta_terbaca_benar(self):
        fakta = verify_pages(landing_html=BAIK, brand="WAYANGPLAY")["facts"]

        self.assertEqual(fakta["h1"], "Slot Gacor di WAYANGPLAY")
        self.assertEqual(fakta["paragraphs"], 2)
        self.assertEqual(fakta["jsonld_blocks"], 1)


class MembacaMetaDariTemplateNyata(unittest.TestCase):
    """
    Meta description harus dibaca DARI TAG-NYA SENDIRI.

    Bug yang ditutup di sini menggagalkan satu run penuh atas template
    nyata 123 KB: atribut metanya ditulis terbalik (content dulu, name
    belakangan), dan pola lama - yang memakai (.*?) dengan DOTALL -
    melompati batas tag. Yang terbaca sebagai deskripsi adalah nilai
    viewport dari tag di atasnya, disambung sampai ke tag description
    yang jauh di bawahnya.

    Akibatnya bukan laporan yang meleset melainkan gerbang akhir yang
    menahan halaman untuk cacat yang tidak pernah ada.
    """

    URUTAN_TERBALIK = (
        "<html><head>"
        '<meta charset="utf-8"/>'
        '<meta content="width=device-width,initial-scale=1" name="viewport"/>'
        '<meta content="#E3000B" name="theme-color"/>'
        "<title>RAJAWALI77 @ Slot Deposit QRIS yang Ringkas</title>"
        '<meta content="Halaman RAJAWALI77 menyusun cara deposit QRIS '
        'dalam satu layar, lengkap dengan menu yang mudah ditelusuri "'
        'dari ponsel." name="description"/>'
        "</head><body><h1>Slot Deposit QRIS di RAJAWALI77</h1>"
        "<p>Menu bagian atas tetap terlihat waktu halaman digulir ke "
        "bawah, termasuk waktu dibuka lewat layar kecil.</p>"
        "</body></html>"
    )

    def test_deskripsi_terbaca_dari_tagnya_sendiri(self):
        from generators.final_verify import read_page

        halaman = read_page(self.URUTAN_TERBALIK)

        self.assertTrue(
            halaman["meta_description"].startswith("Halaman RAJAWALI77")
        )
        self.assertNotIn("viewport", halaman["meta_description"])
        self.assertNotIn("width=device-width", halaman["meta_description"])

    def test_tidak_menahan_halaman_yang_sehat(self):
        hasil = verify_pages(
            landing_html=self.URUTAN_TERBALIK,
            amp_html=self.URUTAN_TERBALIK,
            brand="RAJAWALI77",
            keyword="slot deposit qris",
            region="id",
        )

        self.assertEqual(hasil["hard"], [])


class HalamanCacatDitahan(unittest.TestCase):
    def periksa(self, html, amp="", **kunci):
        pilihan = {
            "brand": "WAYANGPLAY",
            "keyword": "slot gacor",
            "region": "id",
        }
        pilihan.update(kunci)

        return verify_pages(landing_html=html, amp_html=amp, **pilihan)

    def test_placeholder_belum_diganti(self):
        rusak = dengan(BAIK, "Slot Gacor di WAYANGPLAY", "Slot Gacor di {{brand}}")

        self.assertTrue(
            any("penanda" in x for x in self.periksa(rusak)["hard"])
        )

    def test_lorem_ipsum(self):
        rusak = dengan(BAIK, "Menu bagian atas", "Lorem ipsum dolor sit amet")

        self.assertTrue(
            any("lorem" in x.lower() for x in self.periksa(rusak)["hard"])
        )

    def test_brand_salah_ketik(self):
        rusak = dengan(BAIK, "Slot Gacor di WAYANGPLAY", "Slot Gacor di WAYANGPLAYY")

        self.assertTrue(
            any("ejaan brand" in x for x in self.periksa(rusak)["hard"])
        )

    def test_kata_biasa_yang_mirip_brand_tidak_dituduh(self):
        """
        Brand "WAYANGPLAY" tidak boleh membuat "wayang" dilaporkan.
        """
        aman = dengan(
            BAIK,
            "Menu bagian atas",
            "Tema wayang dipakai di beberapa bagian, dan menu atas",
        )

        self.assertEqual(
            [x for x in self.periksa(aman)["hard"] if "ejaan brand" in x],
            [],
        )

    def test_json_ld_rusak(self):
        rusak = dengan(BAIK, '"@type":"WebPage","name":"WAYANGPLAY"}', '"@type":')

        self.assertTrue(
            any("JSON-LD" in x for x in self.periksa(rusak)["hard"])
        )

    def test_title_landing_dan_amp_berbeda(self):
        amp = dengan(
            BAIK,
            "WAYANGPLAY | Slot Gacor dengan Navigasi Ringkas",
            "Judul Lain Milik Pemilik Template",
        )

        hasil = self.periksa(BAIK, amp)

        self.assertTrue(any("Title landing dan AMP" in x for x in hasil["hard"]))

    def test_h1_landing_dan_amp_berbeda(self):
        amp = dengan(BAIK, "Slot Gacor di WAYANGPLAY", "Halaman Lain WAYANGPLAY")

        self.assertTrue(
            any("H1 landing dan AMP" in x for x in self.periksa(BAIK, amp)["hard"])
        )

    def test_brand_hilang_sama_sekali(self):
        rusak = BAIK.replace("WAYANGPLAY", "SITUSLAIN")

        self.assertTrue(
            any("tidak ada satu pun" in x for x in self.periksa(rusak)["hard"])
        )

    def test_aksara_thai_bocor_ke_halaman_indonesia(self):
        rusak = dengan(
            BAIK,
            "Menu bagian atas tetap terlihat waktu halaman digulir ke bawah,",
            "เมนูด้านบนยังคงมองเห็นได้เมื่อเลื่อนหน้าลงไปด้านล่าง",
        )

        self.assertTrue(
            any("aksara Thai" in x for x in self.periksa(rusak)["hard"])
        )

    def test_halaman_thai_yang_berbahasa_indonesia(self):
        hasil = self.periksa(BAIK, region="th")

        self.assertTrue(
            any("tidak berbahasa Thai" in x for x in hasil["hard"])
        )

    def test_klaim_karangan(self):
        rusak = dengan(
            BAIK,
            "Menu bagian atas tetap terlihat waktu halaman digulir ke bawah,",
            "Semua pemain pasti menang di sini,",
        )

        self.assertTrue(
            any("klaim karangan" in x for x in self.periksa(rusak)["hard"])
        )

    def test_paragraf_hilang_padahal_template_punya(self):
        """
        Diadu dengan templatenya, bukan dengan anggapan bahwa setiap
        halaman pasti memakai <p>.
        """
        rusak = BAIK.replace("<p>", "<span>").replace("</p>", "</span>")

        hasil = verify_pages(
            landing_html=rusak,
            template_landing=BAIK,
            brand="WAYANGPLAY",
        )

        self.assertTrue(
            any("tidak memuat satu pun paragraf" in x for x in hasil["hard"])
        )

    def test_template_yang_memang_tidak_pakai_p_tidak_ditolak(self):
        """
        Template yang menaruh teks badannya di dalam <div> tidak
        bermasalah, dan menolaknya berarti menggagalkan generate
        sesudah seluruh isi selesai ditulis model.
        """
        tanpa_p = BAIK.replace("<p>", "<div>").replace("</p>", "</div>")

        hasil = verify_pages(
            landing_html=tanpa_p,
            template_landing=tanpa_p,
            brand="WAYANGPLAY",
        )

        self.assertEqual(hasil["hard"], [])

    def test_halaman_yang_hampir_kosong_tetap_ditahan(self):
        kosong = (
            "<html><head><title>WAYANGPLAY | Slot Gacor dengan Menu "
            'Ringkas</title><meta name="description" content="Deskripsi '
            'halaman WAYANGPLAY yang panjangnya memadai untuk dibaca '
            'sebagai meta description utuh di hasil pencarian Google."'
            "></head><body><h1>WAYANGPLAY</h1></body></html>"
        )

        hasil = verify_pages(landing_html=kosong, brand="WAYANGPLAY")

        self.assertTrue(
            any("hampir tanpa teks badan" in x for x in hasil["hard"])
        )

    def test_template_berubah_di_luar_slot(self):
        """
        Yang paling penting: berkas jadi yang menyentuh bagian beku
        ditahan, dibuktikan byte demi byte lewat rentang isian.
        """
        template = "<html><head><title>Lama</title></head><body>" \
            '<div class="ad" onclick="track()">iklan</div>' \
            "<p>Paragraf lama milik pemilik template di sini.</p>" \
            "</body></html>"

        rentang = [
            {
                "start": template.index("Paragraf lama"),
                "end": template.index("Paragraf lama") + len(
                    "Paragraf lama milik pemilik template di sini."
                ),
                "kind": "text",
                "text": "Paragraf baru yang ditulis untuk halaman ini saja.",
            }
        ]

        benar = (
            template[: rentang[0]["start"]]
            + rentang[0]["text"]
            + template[rentang[0]["end"] :]
        )

        # Yang jujur lolos.
        hasil = verify_pages(
            landing_html=benar,
            template_landing=template,
            landing_ranges=rentang,
        )

        self.assertEqual(
            [x for x in hasil["hard"] if "di luar slot" in x],
            [],
        )

        # Yang menyentuh iklan ditahan.
        rusak = benar.replace('onclick="track()"', "")

        hasil = verify_pages(
            landing_html=rusak,
            template_landing=template,
            landing_ranges=rentang,
        )

        self.assertTrue(any("di luar slot" in x for x in hasil["hard"]))

    def test_cacat_template_sendiri_tidak_menahan_terbit(self):
        """
        Yang sudah ada di template bukan karangan generator ini.
        Halaman tidak boleh ditolak karena kalimat pemilik template
        yang memang tidak pernah disentuh.
        """
        template = BAIK.replace(
            "<p>Menu bagian atas",
            "<p>Situs ini punya lebih dari 10.000 member aktif.</p><p>Menu bagian atas",
        )

        hasil = verify_pages(
            landing_html=template,
            template_landing=template,
            brand="WAYANGPLAY",
            keyword="slot gacor",
        )

        self.assertEqual(
            [x for x in hasil["hard"] if "klaim karangan" in x],
            [],
        )


class TemuanMilikTemplateTidakMenahan(unittest.TestCase):
    """
    Kalimat pemilik template tidak boleh menahan terbit - termasuk
    sesudah namanya ditukar, dan termasuk kalau kalimatnya terbelah
    tag di dalamnya.

    Keduanya terukur pada template nyata 123 KB. Slot yang tidak
    kebagian teks baru tetap kebagian penggantian NAMA, jadi kalimat
    "Jam OSB99 beroperasi setiap hari" terbit sebagai "Jam RAJAWALI77
    beroperasi setiap hari" - dan dicari apa adanya, kalimat itu tidak
    akan pernah ketemu di templatenya sendiri.
    """

    TEMPLATE = (
        "<html><head><title>OSB99 Deposit QRIS</title>"
        '<meta name="description" content="Deskripsi milik pemilik '
        'template yang panjangnya memadai untuk dibaca sebagai meta '
        'description utuh di hasil pencarian Google.">'
        "</head><body><h1>OSB99</h1>"
        "<p>Jam <b>OSB99</b> beroperasi setiap hari dan gacor terus "
        "sepanjang malam menurut pemilik template ini.</p>"
        "</body></html>"
    )

    def test_klaim_template_yang_namanya_ditukar_tidak_menahan(self):
        jadi = self.TEMPLATE.replace("OSB99", "RAJAWALI77")

        hasil = verify_pages(
            landing_html=jadi,
            template_landing=self.TEMPLATE,
            brand="RAJAWALI77",
            old_brand="OSB99",
        )

        self.assertEqual(
            [x for x in hasil["hard"] if "klaim karangan" in x],
            [],
        )

    def test_klaim_yang_benar_benar_baru_tetap_menahan(self):
        jadi = self.TEMPLATE.replace("OSB99", "RAJAWALI77").replace(
            "menurut pemilik template ini",
            "dan semua pemain pasti menang di sini",
        )

        hasil = verify_pages(
            landing_html=jadi,
            template_landing=self.TEMPLATE,
            brand="RAJAWALI77",
            old_brand="OSB99",
        )

        self.assertTrue(
            any("klaim karangan" in x for x in hasil["hard"])
        )


class SlotYangMemangTidakAdaDiAmp(unittest.TestCase):
    """
    Beda H1 yang MUSTAHIL disamakan tidak boleh menahan terbit.

    Terukur pada template nyata: H1 berkas AMP-nya ditulis
    "OSB99 <em>Login</em>" - teksnya terbelah tag di dalamnya, jadi ia
    tidak pernah masuk peta slot dan tidak ada isian yang bisa
    menyamakannya dengan H1 landing. Ditahan, template itu tidak akan
    pernah bisa dipakai sama sekali; padahal title dan deskripsinya
    sinkron sempurna.
    """

    LANDING = BAIK
    AMP = BAIK.replace(
        "<h1>Slot Gacor di WAYANGPLAY</h1>",
        "<h1>WAYANGPLAY <em>Login</em></h1>",
    )

    def test_ditahan_kalau_slotnya_memang_ada(self):
        hasil = verify_pages(
            landing_html=self.LANDING,
            amp_html=self.AMP,
            brand="WAYANGPLAY",
            amp_roles={"title", "meta_description", "h1", "paragraph"},
        )

        self.assertTrue(any("H1 landing dan AMP" in x for x in hasil["hard"]))

    def test_dicatat_kalau_template_amp_tidak_punya_slotnya(self):
        hasil = verify_pages(
            landing_html=self.LANDING,
            amp_html=self.AMP,
            brand="WAYANGPLAY",
            amp_roles={"title", "meta_description", "paragraph"},
        )

        self.assertEqual(hasil["hard"], [])
        self.assertTrue(any("H1 landing dan AMP" in x for x in hasil["soft"]))

    def test_title_yang_meleset_tetap_menahan(self):
        """
        Kelonggarannya sempit: hanya untuk peran yang memang tidak
        punya slot. Title tetap ditahan.
        """
        amp = self.AMP.replace(
            "WAYANGPLAY | Slot Gacor dengan Navigasi Ringkas",
            "Judul Lama Milik Pemilik Template",
        )

        hasil = verify_pages(
            landing_html=self.LANDING,
            amp_html=amp,
            brand="WAYANGPLAY",
            amp_roles={"title", "meta_description", "paragraph"},
        )

        self.assertTrue(
            any("Title landing dan AMP" in x for x in hasil["hard"])
        )


class CatatanBukanPenahan(unittest.TestCase):
    """
    Cacat yang cuma membuat halaman kurang enak dibaca dicatat, bukan
    menahan terbit. Menahan halaman karena judulnya meleset lima
    karakter berarti membuang seluruh isi yang sudah benar.
    """

    def test_title_kependekan_cuma_dicatat(self):
        rusak = dengan(
            BAIK,
            "WAYANGPLAY | Slot Gacor dengan Navigasi Ringkas",
            "WAYANGPLAY | Slot",
        )

        hasil = verify_pages(landing_html=rusak, brand="WAYANGPLAY")

        self.assertEqual(hasil["hard"], [])
        self.assertTrue(
            any("Title 17 kolom" in x for x in hasil["soft"])
        )

    def test_panjang_thai_diukur_dalam_kolom(self):
        """
        Aksara Thai menumpuk tanda vokal dan nada di atas atau di
        bawah huruf induknya, jadi tidak menambah lebar sedikit pun.
        Diukur dengan len(), deskripsi 171 kolom terbaca 213 karakter
        dan dilaporkan melanggar rentang yang sebenarnya dipenuhi.

        Teks di bawah ini disalin apa adanya dari halaman zona th
        yang benar-benar terbit,
        output/wayangplay-slot-gacor-20260820_005421.
        """
        desc = (
            "คุณสามารถเริ่มเล่น slot gacor ได้ทันทีบน WAYANGPLAY "
            "โดยไม่ต้องเตรียมอะไร แค่เปิดเว็บหรือแอป "
            "คุณก็สามารถเข้าสู่เกมได้ทันที ระบบจะแสดงเกมต่าง ๆ พร้อมกัน "
            "ไม่ต้องรอ ไม่ต้องคิด ช่วงนี้กำลังดี เข้าเล่นได้ทุกที่ ทุกเวลา."
        )

        halaman = (
            "<html><head><title>WAYANGPLAY # เล่น slot gacor ได้ทันที "
            "ไม่ต้องคิดมากเลยเลยวันนี้</title>"
            f'<meta name="description" content="{desc}">'
            "</head><body><h1>WAYANGPLAY เล่น slot gacor ได้ทันที</h1>"
            "<p>การเล่น slot gacor บน WAYANGPLAY ทำได้ทันที "
            "โดยไม่ต้องคิดมาก แค่เปิดเว็บหรือแอป "
            "คุณก็สามารถเข้าสู่เกมได้ทันที</p></body></html>"
        )

        self.assertGreater(len(desc), 180)

        hasil = verify_pages(
            landing_html=halaman,
            brand="WAYANGPLAY",
            keyword="slot gacor",
            region="th",
        )

        self.assertEqual(hasil["hard"], [])
        self.assertEqual(
            [x for x in hasil["soft"] if "di luar rentang" in x],
            [],
        )

    def test_deskripsi_yang_menyalin_title_dicatat(self):
        judul = "WAYANGPLAY | Slot Gacor dengan Navigasi Ringkas"
        rusak = re.sub(
            r'content="[^"]*"',
            f'content="{judul}"',
            BAIK,
            count=1,
        )

        hasil = verify_pages(landing_html=rusak, brand="WAYANGPLAY")

        self.assertEqual(hasil["hard"], [])
        self.assertTrue(
            any("hampir sama dengan title" in x for x in hasil["soft"])
        )

    def test_pengulangan_antar_peran_cuma_dicatat(self):
        rusak = dengan(
            BAIK,
            "<p>Menu bagian atas tetap terlihat waktu halaman digulir ke bawah,\n"
            "termasuk waktu halaman dibuka lewat layar yang lebih kecil.</p>",
            "<p>Daftar permainan disusun menurut penyedianya, jadi pembaca yang\n"
            "sudah punya nama incaran bisa langsung menuju baris yang dicari.</p>",
        )

        hasil = verify_pages(landing_html=rusak, brand="WAYANGPLAY")

        self.assertEqual(hasil["hard"], [])


class UkuranBantu(unittest.TestCase):
    def test_thai_share_mengabaikan_brand_dan_keyword(self):
        judul = "WAYANGPLAY สล็อตแตกง่าย slot gacor"

        self.assertGreater(thai_share(judul, "WAYANGPLAY", "slot gacor"), 0.9)

    def test_brand_typos_hanya_yang_benar_benar_mirip(self):
        teks = "WAYANGPLAYY dan WAYANGPLA di halaman wayang kulit biasa"

        self.assertEqual(
            brand_typos(teks, "WAYANGPLAY"),
            ["WAYANGPLA", "WAYANGPLAYY"],
        )

    def test_brand_pendek_tidak_diperiksa(self):
        """
        Nama tiga huruf terlalu mudah bertabrakan dengan kata biasa.
        """
        self.assertEqual(brand_typos("dan ada dana di sana", "ADA"), [])


if __name__ == "__main__":
    unittest.main()
