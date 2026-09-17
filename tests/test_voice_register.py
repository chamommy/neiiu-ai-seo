"""
Halaman ini setengah resmi: tidak kaku, tidak santai.

Diminta pengguna 21 Agustus 2026, atas halaman BATARATOTO yang
benar-benar terbit - sembilan kalimatnya dibuka "Kamu bisa ..." dan
satu jawaban FAQ ditutup "sistem akan membuat akun untukmu".
Kalimatnya: "bahasa yang tidak kaku, formal tapi tidak terlalu formal
dan jangan menggunakan bahasa yang santai".

Dua lapis menegakkannya, dan keduanya diuji di sini:

  1. Aturan di prompt - yang dulu justru MENYURUH memakai "nggak",
     "udah", "bikin", dan menulis contohnya dengan "kamu".
  2. Penyapu di Python, karena aturan prompt untuk model 4B diikuti
     kadang-kadang saja.

Lapis ketiga ikut diuji: contoh gaya yang diperlihatkan ke model tidak
boleh memakai bentuk yang dilarang aturannya sendiri. Model kecil
meniru contohnya, bukan aturannya.

Tidak memakai AI sama sekali.
"""

import unittest

from ai.language_rules import BANNED_PHRASES_ID, voice_rules
from ai.neiiu_prompts import CASUAL_FILTER, load_style_examples
from utils.spelling import fix_content_register, fix_register


class PenyapuRagamBahasa(unittest.TestCase):
    def test_sapaan_santai_dinaikkan(self):
        hasil = fix_register(
            "Kamu bisa mulai bermain slot online langsung dari HP.",
            {"BATARATOTO"},
        )

        self.assertIn("Anda bisa", hasil)
        self.assertNotIn("Kamu", hasil)

    def test_akhiran_milik_ikut_dinaikkan(self):
        hasil = fix_register(
            "Sistem akan membuat akun untukmu setelah data terkirim.",
            set(),
        )

        self.assertIn("untuk Anda", hasil)
        self.assertNotIn("untukmu", hasil)

    def test_kata_gaul_dibakukan(self):
        hasil = fix_register("Prosesnya nggak ribet dan udah otomatis.", set())

        self.assertIn("tidak", hasil)
        self.assertIn("sudah", hasil)
        self.assertNotIn("nggak", hasil)

    def test_kata_biasa_tidak_ikut_disentuh(self):
        """
        "langsung", "tinggal", "cukup" bukan bahasa gaul. Ikut disapu,
        yang tersisa justru bahasa kaku - kebalikan dari yang diminta.
        """
        kalimat = "Anda tinggal memindai kode, lalu langsung bermain."

        self.assertEqual(fix_register(kalimat, set()), kalimat)

    def test_nama_situs_tidak_pernah_disentuh(self):
        """
        Nama situs boleh saja berbunyi seperti kata gaul. Membetulkannya
        berarti menerbitkan halaman atas nama situs yang tidak ada.
        """
        hasil = fix_register("GACORBANGET buka setiap hari.", {"GACORBANGET"})

        self.assertIn("GACORBANGET", hasil)

    def test_seluruh_isi_disapu_sekaligus(self):
        isi = {
            "title": "BATARATOTO | RTP Live Hari Ini",
            "paragraph": [
                "Kamu bisa melihat angkanya di layar.",
                "Prosesnya nggak lama.",
            ],
            "_keyword": "kamu",
        }

        hasil, jumlah = fix_content_register(isi, "slot online", "BATARATOTO")

        # Dua paragraf berubah; judulnya sudah bersih sejak awal.
        self.assertEqual(jumlah, 2)
        self.assertEqual(hasil["title"], isi["title"])
        self.assertIn("Anda bisa", hasil["paragraph"][0])
        self.assertIn("tidak lama", hasil["paragraph"][1])

    def test_peran_berawalan_garis_bawah_dilewati(self):
        """
        Isinya penanda untuk riwayat, bukan teks yang terbit.
        """
        isi = {"_keyword": "kamu"}

        hasil, _ = fix_content_register(isi, "", "")

        self.assertEqual(hasil["_keyword"], "kamu")


class AturanPromptSejalan(unittest.TestCase):
    def test_prompt_tidak_lagi_menyuruh_bahasa_gaul(self):
        aturan = voice_rules("id")

        self.assertIn("DILARANG karena terlalu santai", aturan)
        self.assertIn('Sapa pembaca dengan "Anda"', aturan)

    def test_daftar_frasa_terlarang_ikut_ke_prompt(self):
        aturan = voice_rules("id")

        for frasa in ("di era digital", "bukan sekadar"):
            with self.subTest(frasa=frasa):
                self.assertIn(frasa, aturan)
                self.assertIn(frasa, BANNED_PHRASES_ID)

    def test_zona_thailand_tidak_ikut_berubah(self):
        """
        Daftar kata gaulnya seluruhnya Indonesia. Ikut terkirim ke
        halaman Thai, ia cuma memakan context.
        """
        self.assertNotIn("DILARANG karena terlalu santai", voice_rules("th"))


class ContohGayaSejalanDenganAturan(unittest.TestCase):
    def test_contoh_paragraf_tidak_memakai_bahasa_gaul(self):
        for contoh in load_style_examples("paragraph"):
            with self.subTest(contoh=contoh[:40]):
                self.assertIsNone(CASUAL_FILTER.search(contoh))

    def test_contoh_paragraf_tidak_memakai_frasa_terlarang(self):
        """
        Aturan yang melarang sebuah bentuk lalu menyodorkan contoh yang
        memakainya membatalkan dirinya sendiri.
        """
        for contoh in load_style_examples("paragraph"):
            for frasa in ("di era digital", "bukan sekadar"):
                with self.subTest(contoh=contoh[:30], frasa=frasa):
                    self.assertNotIn(frasa, contoh.casefold())


if __name__ == "__main__":
    unittest.main()
