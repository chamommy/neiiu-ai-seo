"""
Giliran metadata memakai promptnya sendiri, bukan prompt halaman.

Jalur ramping untuk title sudah ada sejak job 93/94. Yang tidak ikut
waktu itu: meta description. Gerbangnya berbunyi `set(bagian) ==
{"title"}`, jadi deskripsi selalu berangkat membawa prompt seluruh
halaman - aturan paragraf, heading, FAQ, daftar, CTA, bank kata SERP,
dan pertanyaan kompetitor - untuk giliran yang tidak menulis satu pun
dari itu.

Terukur di run 30 Agustus 2026, permintaan yang cuma minta satu judul
dan satu deskripsi:

    giliran title (jalur ramping)   :  22 detik
    giliran deskripsi (jalur penuh) : 472 detik

    prompt giliran deskripsi : 11.811 token
    yang diminta             : satu kalimat 140-180 karakter

Tidak memakai AI sama sekali: yang diuji promptnya, bukan jawabannya.
"""

import unittest

from ai.neiiu_prompts import (
    build_meta_only_prompt,
    build_title_only_prompt,
    meta_history_block,
    meta_rules_block,
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

SPEC_META = {
    "meta_description": {
        "count": 1,
        "min_length": 140,
        "max_length": 180,
    }
}

SPEC_TITLE = {
    "title": {"count": 1, "min_length": 50, "max_length": 70}
}

SUDAH = {"title": ["ABECE # Togel Online Pengalaman Bermain Terbaik"]}


def brand():
    return build_brand("ABECE", "", "id", "", None, keyword="togel online")


class PromptDeskripsiRamping(unittest.TestCase):
    def setUp(self):
        self.sistem, self.minta = build_meta_only_prompt(
            analysis=ANALYSIS,
            brand=brand(),
            spec=SPEC_META,
            sudah=SUDAH,
        )

    def test_tetap_ramping(self):
        """
        Plafon mutlak, bukan perbandingan dengan prompt halaman.

        Prompt halaman penuh besarnya ikut template dan ikut hasil
        crawl, jadi membandingkan keduanya berarti uji yang lulus atau
        gagal tergantung situs mana yang kebetulan sedang ngerank.
        Yang dijaga di sini sifat yang tidak boleh hilang: prompt ini
        muat berkali-kali lipat di dalam context, berapa pun besar
        templatenya.

        Terukur waktu ditulis: 2.806 karakter, lawan 35.719 karakter
        lewat jalur penuh untuk permintaan yang sama.
        """
        ramping = len(self.sistem) + len(self.minta)

        self.assertLess(ramping, 6000, f"prompt deskripsi {ramping} karakter")

    def test_membawa_yang_dibutuhkan_deskripsi(self):
        for wajib in (
            "ABECE",
            "togel online",
            "140",
            "180",
            "meta_description",
        ):
            with self.subTest(wajib=wajib):
                self.assertIn(wajib, self.minta)

    def test_membawa_judul_yang_baru_ditulis(self):
        """
        Tanpa judulnya, deskripsi ditulis tanpa tahu sudut apa yang
        sedang dilanjutkan.
        """
        self.assertIn(SUDAH["title"][0], self.minta)
        self.assertIn("DILARANG mengulanginya", self.minta)

    def test_kata_khas_judul_disebut_satu_per_satu(self):
        """
        Melarang secara umum tidak menutup apa-apa - lihat
        kata_terlarang. Yang menutup adalah larangan yang menyebut
        nama.
        """
        self.assertIn("Pengalaman", self.minta + self.minta.title())
        self.assertIn("sudah terpakai di judul", self.minta)

    def test_melarang_kalimat_menggantung(self):
        """
        Deskripsi yang berhenti di tengah terbit apa adanya di hasil
        pencarian. Terukur pada run yang sama: "... cocok untuk
        pemain yang ingin."
        """
        self.assertIn("SATU KALIMAT PENUH SAMPAI SELESAI", self.minta)

    def test_TIDAK_membawa_aturan_halaman(self):
        """
        Ini yang membuatnya ramping.

        Yang diadu penanda yang benar-benar cuma ada di prompt halaman
        penuh - nama peran sebagai bidang JSON, dan tajuk bloknya.
        Kata "heading" sendirian tidak bisa dipakai: prompt ini memang
        menyebutnya, justru untuk mengatakan "tidak menulis heading".
        """
        for tidak_boleh in (
            "faq_question",
            "faq_answer",
            "review_text",
            "list_item",
            "card_title",
            "MENGISI TEMPLATE HALAMAN",
            "Topik yang wajib terbahas",
            "Title yang sedang ngerank",
        ):
            with self.subTest(tidak_boleh=tidak_boleh):
                self.assertNotIn(tidak_boleh, self.minta)

    def test_tidak_meminta_peran_selain_deskripsi(self):
        minta = self.minta[self.minta.index("YANG HARUS KAMU TULIS"):]

        self.assertIn("meta_description: 1 teks", minta)

        for peran in ("title", "h1", "paragraph", "heading"):
            with self.subTest(peran=peran):
                self.assertNotIn(f"{peran}: ", minta)

    def test_tanpa_judul_tetap_jalan(self):
        _, minta = build_meta_only_prompt(
            analysis=ANALYSIS,
            brand=brand(),
            spec=SPEC_META,
        )

        self.assertIn("meta_description", minta)
        self.assertNotIn("JUDUL HALAMAN INI", minta)

    def test_jalur_judul_tidak_ikut_berubah(self):
        """
        Mesin judul sudah disetel berkali-kali. Menambah jalur untuk
        deskripsi tidak boleh menggesernya sehuruf pun.
        """
        sistem, minta = build_title_only_prompt(
            analysis=ANALYSIS,
            brand=brand(),
            spec=SPEC_TITLE,
        )

        self.assertIn("SATU judul SEO", minta)
        self.assertNotIn("meta_description", minta)


class RiwayatDeskripsi(unittest.TestCase):
    def test_deskripsi_lama_disebut(self):
        blok = meta_history_block(
            {
                "meta_description": [
                    "ABECE menghadirkan togel online yang bisa dibuka "
                    "dari ponsel mana pun.",
                ]
            }
        )

        self.assertIn("DESKRIPSI YANG SUDAH KELUAR", blok)
        self.assertIn("menghadirkan togel online", blok)

    def test_pembuka_diadu_setelah_nama_situs(self):
        """
        Deskripsi di jalur ini SELALU dibuka nama situs. Kalau yang
        diadu kata pertama, seluruhnya sama dan tidak ada yang bisa
        dilarang.
        """
        blok = meta_history_block(
            {
                "meta_description": [
                    "ABECE menghadirkan togel online yang bisa dibuka "
                    "dari ponsel mana pun.",
                ]
            }
        )

        self.assertIn("menghadirkan togel online", blok)
        self.assertNotIn('"ABECE menghadirkan togel"', blok)

    def test_kosong_tidak_menyumbang_satu_baris_pun(self):
        self.assertEqual(meta_history_block(None), "")
        self.assertEqual(meta_history_block({}), "")
        self.assertEqual(meta_history_block({"meta_description": []}), "")


class AturanDeskripsi(unittest.TestCase):
    def test_menyebut_nama_situs_dan_keyword(self):
        aturan = meta_rules_block("ABECE", "togel online", "Indonesia")

        self.assertIn("ABECE", aturan)
        self.assertIn("togel online", aturan)
        self.assertIn("WAJIB DIBUKA NAMA SITUS", aturan)

    def test_melarang_angka_persen(self):
        self.assertIn(
            "JANGAN menulis angka persen",
            meta_rules_block("ABECE", "togel online"),
        )


if __name__ == "__main__":
    unittest.main()
