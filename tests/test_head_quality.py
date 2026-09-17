"""
Judul dan deskripsi yang unik dan menyebut sesuatu.

Diminta pengguna 30 Agustus 2026: "masih kurang unik dan kurang
menarik ... buat unik dan menarik ya untuk audience judi online".

Yang dilihatnya dua run berturut-turut atas keyword yang sama:

    run 1  ABECE # Togel online pengalaman bermain terbaik
           ABECE menyediakan akses langsung ke togel online ...
           Tidak perlu persiapan khusus, cocok untuk pemain yang ingin.

    run 2  ABECE # Togel Online untuk Pemain & Tanpa Pendaftaran
           ABECE menghadirkan togel online yang mudah diakses tanpa
           pendaftaran, dirancang khusus untuk pemain yang
           menginginkan keamanan dan kecepatan saat bermain, dengan
           sistem.

Tiga kerusakan yang berbeda, dan tidak satu pun disebabkan model
kehabisan ide:

  1. Kalimat yang berhenti di tengah. Dua sebab yang berbeda -
     run 1 mentok plafon 180 karakter, run 2 kehilangan ekornya
     waktu klaim tahun berdiri dicabut.
  2. Judul yang tidak menyebut apa pun. Ditolak tiga kali oleh
     vague_title_score, lalu terbit juga sebagai kandidat yang
     paling sedikit bermasalah.
  3. Frasa brosur di deskripsi. Tidak ada satu pun ukuran yang
     memeriksanya - judul punya vague_title_score sejak lama,
     deskripsi tidak punya apa-apa.

Tidak memakai AI sama sekali: yang diuji penyapu, penilai, dan
promptnya - bukan jawaban model.
"""

import unittest

from ai.neiiu_prompts import (
    build_meta_only_prompt,
    build_title_only_prompt,
    head_style_block,
)
from generators.claim_guard import scrub_text
from generators.content_planner import (
    brochure_score,
    description_penalty,
    finish_cut_description,
    HEAD_GOOD_ENOUGH,
    opening_repeat_score,
    title_penalty,
)
from services.neiiu_pipeline import build_brand


ANALYSIS = {
    "keyword": "togel online",
    "blueprint": {
        "target": {},
        "people_also_ask": [],
        "competitor_questions": [],
        "analyzed_pages": 2,
    },
    "pages": [],
    "serp": {"results": []},
}

SPEC_TITLE = {"title": {"count": 1, "min_length": 50, "max_length": 70}}
SPEC_META = {
    "meta_description": {
        "count": 1,
        "min_length": 140,
        "max_length": 180,
    }
}

# Deskripsi yang benar-benar terbit, huruf per huruf.
RUN1 = (
    "ABECE menyediakan akses langsung ke togel online dengan tampilan "
    "responsif dan proses penarikan yang diproses langsung. Tidak "
    "perlu persiapan khusus, cocok untuk pemain yang ingin."
)

RUN2 = (
    "ABECE menghadirkan togel online yang mudah diakses tanpa "
    "pendaftaran, dirancang khusus untuk pemain yang menginginkan "
    "keamanan dan kecepatan saat bermain, dengan sistem."
)

# Deskripsi yang menyebut hal yang bisa ditunjuk. Dipakai sebagai
# pembanding di hampir setiap uji di bawah: yang dijaga bukan cuma
# "yang buruk ditolak" melainkan "yang baik tidak ikut tertolak".
SEHAT = (
    "ABECE menyajikan togel online yang cair ke rekening tanpa antre, "
    "dan bisa dibuka dari HP tanpa aplikasi tambahan."
)


def brand(nama="ABECE", keyword="togel online", region="id"):
    return build_brand(nama, "", region, "", None, keyword=keyword)


class KlaimDicabutTanpaMemenggalKalimat(unittest.TestCase):
    """
    claim_guard sudah benar mencabut klaimnya. Yang salah sisanya.
    """

    KEPALA = (
        "ABECE menghadirkan togel online yang mudah diakses tanpa "
        "pendaftaran, dirancang khusus untuk pemain yang menginginkan "
        "keamanan dan kecepatan saat bermain, "
    )

    def test_ekor_kata_depan_ikut_dibuang(self):
        """
        Bentuk yang terbit: "sejak tahun 2015" dicabut, "dengan
        sistem" tertinggal, titiknya dipasang balik.
        """
        hasil, jumlah = scrub_text(self.KEPALA + "dengan sistem sejak tahun 2015.")

        self.assertEqual(jumlah, 1)
        self.assertNotIn("dengan sistem", hasil)
        self.assertTrue(hasil.rstrip().endswith("saat bermain."), hasil)

    def test_ekor_satu_kata_masih_tertutup(self):
        """
        Ambang lama tidak boleh hilang waktu yang baru dipasang.
        """
        hasil, _ = scrub_text(
            "Daftar dari HP, prosesnya selesai dalam dua detik."
        )

        self.assertNotIn("prosesnya", hasil)

    def test_kalimat_sehat_tidak_disentuh(self):
        for teks in (
            "Daftar dari HP, saldo masuk otomatis.",
            "ABECE menghadirkan togel online, tanpa aplikasi tambahan.",
            SEHAT,
        ):
            with self.subTest(teks=teks[:40]):
                self.assertEqual(scrub_text(teks), (teks, 0))

    def test_keterangan_yang_utuh_tetap_berdiri(self):
        """
        "dengan sistem otomatis 24 jam" tidak memuat klaim, jadi tidak
        ada yang dicabut dan tidak ada yang boleh dirapikan.
        """
        hasil, jumlah = scrub_text(self.KEPALA + "dengan sistem otomatis 24 jam.")

        self.assertEqual(jumlah, 0)
        self.assertIn("sistem otomatis 24 jam", hasil)


class DeskripsiMentokJatah(unittest.TestCase):
    """
    Grammar llama.cpp memaksa tanda kutip penutup di karakter ke-180,
    di mana pun kalimatnya sedang berada.
    """

    def test_yang_menyentuh_plafon_dirapikan(self):
        self.assertEqual(len(RUN1), 180)

        rapi = finish_cut_description(RUN1, 180)

        self.assertNotEqual(rapi, RUN1)
        self.assertNotIn("yang ingin", rapi)
        self.assertTrue(rapi.endswith("."), rapi)

    def test_yang_jauh_dari_plafon_tidak_disentuh(self):
        """
        Syarat inilah yang membuat dipotong=True boleh dipakai di
        dalam finish_cut_description. Tanpa syarat itu, deskripsi
        sehat ikut dipangkas keterangannya.
        """
        panjang = (
            "ABECE menghadirkan togel online dengan link alternatif "
            "yang bisa dibuka saat situs utama diblokir, deposit QRIS "
            "tanpa potongan."
        )

        self.assertLess(len(panjang), 180 - 2)
        self.assertEqual(finish_cut_description(panjang, 180), panjang)
        self.assertEqual(finish_cut_description(SEHAT, 180), SEHAT)

    def test_tanpa_plafon_tidak_melakukan_apa_pun(self):
        self.assertEqual(finish_cut_description(RUN1, 0), RUN1)

    def test_sisa_yang_terlalu_pendek_dibatalkan(self):
        """
        Kalau perapian menyisakan potongan, teks aslinya yang dipakai
        dan keputusannya diserahkan ke repair_short_slots - jalur yang
        memang punya bahan untuk menambal.
        """
        pendek = "ABECE menyediakan togel, dengan"

        self.assertEqual(
            finish_cut_description(pendek, len(pendek)),
            pendek,
        )

    def test_kosong_tidak_meledak(self):
        for nilai in (None, "", "   "):
            with self.subTest(nilai=repr(nilai)):
                self.assertEqual(finish_cut_description(nilai, 180), "")


class FrasaBrosurDitolak(unittest.TestCase):
    def test_dua_deskripsi_yang_terbit_kena(self):
        for nama, teks in (("run1", RUN1), ("run2", RUN2)):
            with self.subTest(run=nama):
                self.assertGreaterEqual(brochure_score(teks), 1.0)

    def test_deskripsi_yang_menyebut_sesuatu_lolos(self):
        self.assertEqual(brochure_score(SEHAT), 0.0)

    def test_satu_frasa_masih_ditoleransi(self):
        """
        Ambangnya dua, bukan satu. Satu frasa masih bisa berdiri di
        kalimat yang selebihnya menyebut sesuatu; dua sudah jadi
        kalimatnya sendiri.
        """
        satu = (
            "ABECE menyajikan togel online yang cair ke rekening "
            "tanpa antre, cocok untuk pemain yang main dari HP."
        )

        self.assertEqual(brochure_score(satu), 0.0)

    def test_kosong_tidak_meledak(self):
        for nilai in (None, "", "   "):
            with self.subTest(nilai=repr(nilai)):
                self.assertEqual(brochure_score(nilai), 0.0)

    def test_ikut_menolak_lewat_description_penalty(self):
        """
        Ukuran yang tidak terpasang di penilai tidak menolak apa pun.
        """
        nilai = description_penalty(
            RUN2, "togel online", "ABECE", judul="", riwayat=[], contoh=[]
        )

        self.assertGreaterEqual(nilai, 1.0)

    def test_deskripsi_sehat_tetap_lolos_penilai(self):
        nilai = description_penalty(
            SEHAT, "togel online", "ABECE", judul="", riwayat=[], contoh=[]
        )

        self.assertLess(nilai, 0.7)


class ContohGayaIkutKeJalurRamping(unittest.TestCase):
    """
    Modelnya dinilai atas berkas contoh milik pengguna - lewat
    vague_title_score dan style_copy_score - tapi tidak pernah
    dikirimi satu barisnya.
    """

    def test_judul_mendapat_contohnya(self):
        _, minta = build_title_only_prompt(
            analysis=ANALYSIS, brand=brand(), spec=SPEC_TITLE
        )

        self.assertIn("CONTOH JUDUL MILIK SITUS INI", minta)
        self.assertIn("JANGAN disalin", minta)

    def test_deskripsi_mendapat_contohnya(self):
        _, minta = build_meta_only_prompt(
            analysis=ANALYSIS, brand=brand(), spec=SPEC_META
        )

        self.assertIn("CONTOH DESKRIPSI MILIK SITUS INI", minta)

    def test_nama_brand_sudah_ditukar(self):
        blok = head_style_block("title", "togel online", "ABECE")

        self.assertNotIn("[ BRAND ]", blok)

    def test_tetap_ramping(self):
        """
        Contoh gaya ditambahkan, bukan prompt halaman penuh
        dikembalikan. Plafonnya sama seperti di test_head_prompts:
        prompt ini harus muat berkali-kali lipat di dalam context,
        berapa pun besar templatenya.

        Terukur waktu ditulis: judul 3.077 karakter, deskripsi 4.012 -
        lawan 35.719 lewat jalur penuh.
        """
        for nama, prompt in (
            (
                "title",
                build_title_only_prompt(
                    analysis=ANALYSIS, brand=brand(), spec=SPEC_TITLE
                ),
            ),
            (
                "meta",
                build_meta_only_prompt(
                    analysis=ANALYSIS, brand=brand(), spec=SPEC_META
                ),
            ),
        ):
            with self.subTest(prompt=nama):
                ukuran = len(prompt[0]) + len(prompt[1])

                self.assertLess(ukuran, 8000, f"{nama} {ukuran} karakter")

    def test_bahasa_lain_tidak_mendapat_contoh_indonesia(self):
        """
        Berkas contohnya seluruhnya bahasa Indonesia. Mengirimnya ke
        halaman Thai berarti meminta kalimat Thai yang menyalin
        susunan kalimat Indonesia - persis definisi kalimat hasil
        terjemahan.
        """
        self.assertEqual(
            head_style_block("title", "หวยออนไลน์", "ABECE", language_code="th"),
            "",
        )

    def test_bidang_lain_tidak_mendapat_contoh_judi(self):
        """
        Delapan baris tentang situs slot yang berdiri di prompt
        halaman toko sepatu mengajari model susunan kalimatnya
        SEKALIGUS kosakatanya.
        """
        self.assertEqual(
            head_style_block(
                "title", "toko sepatu", "ABECE", niche="generic"
            ),
            "",
        )

    def test_halaman_toko_sepatu_promptnya_bersih(self):
        _, minta = build_title_only_prompt(
            analysis={**ANALYSIS, "keyword": "toko sepatu"},
            brand=brand(keyword="toko sepatu"),
            spec=SPEC_TITLE,
        )

        self.assertNotIn("CONTOH JUDUL MILIK SITUS INI", minta)
        self.assertNotIn("JACKPOT", minta)


class PembukaTidakDiaduDiKataYangDiwajibkan(unittest.TestCase):
    """
    Penilai yang bertengkar dengan aturannya sendiri.

    meta_rules_block MEWAJIBKAN deskripsi dibuka nama situs lalu satu
    kata kerja dari daftar tertutup, dan keywordnya hampir selalu
    menyusul. Jadi tiga kata isi pertama setiap deskripsi berbentuk
    "<kata kerja> <keyword>" - dan dua di antaranya dipatok aturan,
    bukan dipilih model.

    Sampai 30 Agustus 2026 opening_repeat_score mengadu ketiganya apa
    adanya. Akibatnya setiap deskripsi berbunyi 1,00 terhadap
    deskripsi mana pun sebelumnya, setiap giliran menghabiskan seluruh
    jatah permintaan ulangnya, dan yang terbit "kandidat yang paling
    sedikit bermasalah" - dipilih oleh nilai yang seluruhnya derau.
    Peringatan itu berdiri di catatan SETIAP run.
    """

    LAMA = [
        "ABECE menghadirkan togel online yang mudah diakses tanpa "
        "pendaftaran, dirancang khusus untuk pemain."
    ]

    def test_kata_kerja_wajib_tidak_lagi_dihitung_pengulangan(self):
        beda = (
            "ABECE menyajikan togel online yang cair ke rekening tanpa "
            "antre, dan bisa dibuka dari HP tanpa aplikasi."
        )

        self.assertEqual(
            opening_repeat_score(beda, self.LAMA, "ABECE", "togel online"),
            0.0,
        )

    def test_tanpa_keyword_perilakunya_seperti_dulu(self):
        """
        Parameternya tambahan, bukan penggantian. Pemanggil lama yang
        tidak menyebut keyword mendapat angka yang sama persis seperti
        sebelum parameter itu ada.

        Yang diadu HEAD_GOOD_ENOUGH, bukan 1,0. Angka lamanya 0,995 -
        dua dari tiga kata sama, dibagi OPENING_LIMIT - dan itu memang
        di bawah 1,0. Tapi 1,0 bukan ambang yang menentukan apa pun di
        sini: yang memicu permintaan ulang HEAD_GOOD_ENOUGH, dan 0,995
        jauh melewatinya. Mengadu ke 1,0 akan membuat uji ini lulus
        atau gagal karena angka yang tidak dipakai siapa pun.
        """
        beda = (
            "ABECE menyajikan togel online yang cair ke rekening tanpa "
            "antre, dan bisa dibuka dari HP tanpa aplikasi."
        )

        self.assertGreater(
            opening_repeat_score(beda, self.LAMA, "ABECE"),
            HEAD_GOOD_ENOUGH,
        )

    def test_deskripsi_yang_benar_benar_beda_lolos(self):
        beda = (
            "ABECE menyajikan togel online yang cair ke rekening tanpa "
            "antre, dan bisa dibuka dari HP tanpa aplikasi."
        )

        self.assertLess(
            description_penalty(
                beda, "togel online", "ABECE", riwayat=self.LAMA
            ),
            0.7,
        )

    def test_pengulangan_persis_tetap_ditolak(self):
        """
        Kelonggaran ini tidak boleh membuka pintu yang dijaga.
        """
        self.assertGreaterEqual(
            description_penalty(
                self.LAMA[0], "togel online", "ABECE", riwayat=self.LAMA
            ),
            1.0,
        )

    def test_gagasan_sama_yang_cuma_diganti_kata_tetap_ditolak(self):
        mirip = (
            "ABECE menyediakan togel online yang mudah diakses tanpa "
            "pendaftaran, dirancang untuk pemain baru."
        )

        self.assertGreaterEqual(
            description_penalty(
                mirip, "togel online", "ABECE", riwayat=self.LAMA
            ),
            1.0,
        )


class JudulTidakIkutJadiLonggar(unittest.TestCase):
    """
    opening_words dipakai judul dan deskripsi bersama. Memperbaiki
    sisi deskripsi tidak boleh melemahkan sisi judul.
    """

    LAMA = ["ABECE # Togel Online untuk Pemain & Tanpa Pendaftaran"]

    def nilai(self, teks):
        return title_penalty(teks, "togel online", "ABECE", riwayat=self.LAMA)

    def test_judul_yang_sama_persis_ditolak(self):
        self.assertGreaterEqual(self.nilai(self.LAMA[0]), 1.0)

    def test_judul_yang_cuma_diacak_urutannya_ditolak(self):
        self.assertGreaterEqual(
            self.nilai("ABECE # Togel Online Tanpa Pendaftaran untuk Semua Pemain"),
            1.0,
        )

    def test_judul_yang_menyebut_hal_lain_lolos(self):
        self.assertLess(
            self.nilai(
                "ABECE | Link Alternatif Togel Online Saat Situs Utama Diblokir"
            ),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
