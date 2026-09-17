"""
Bahasa: tidak kaku, dan bukan salinan halaman orang lain.

Diminta pengguna 30 Agustus 2026: "bahasa yang di gunakan terlalu
kaku; buat bahasanya menjadi 100% human, unik tidak copyright dan
anti plagiat atau copas dari situs lain dan buat mengalir".

Tiga lapis menegakkannya, dan ketiganya diuji di sini:

  1. Penyapu bentuk surat dinas. Sisi kaku dari ragam bahasa. Sampai
     hari itu hanya ada penyapu sisi santai - CASUAL_WORDS - dan
     tidak ada apa pun yang menurunkan yang terlalu kaku, padahal
     daftar kata kakunya sudah lama ditulis di prompt.
  2. Penjaga salinan. Bacaan halaman pesaing memang sengaja dikirim
     ke model supaya ia tahu topik apa yang perlu dibahas, dan
     justru karena dikirim ia bisa disalin.
  3. Aturan bunyi tulisan yang menyebutkan keduanya, karena penyapu
     tanpa aturan berarti model terus menghasilkan yang harus disapu.

Tidak memakai AI sama sekali.
"""

import unittest

from ai.language_rules import voice_rules
from ai.niche import capability_lines, faq_topic_rules, field_label
from services.neiiu_pipeline import build_brand
from generators.plagiarism_guard import (
    NGRAM,
    copied_run,
    has_sources,
    near_copy,
    scrub_copied,
    source_index,
    strip_copied,
)
from utils.spelling import fix_content_stiffness, fix_stiffness


# Satu halaman pesaing, dalam bentuk yang benar-benar dipakai
# pipeline: analysis["pages"] dengan digest di dalamnya.
PESAING = {
    "pages": [
        {
            "status": "ok",
            "title": "Panduan Deposit Cepat untuk Pemain Baru di Situs Slot",
            "meta_description": (
                "Keterangan singkat milik halaman pesaing yang isinya "
                "menjelaskan cara deposit dari awal sampai selesai."
            ),
            "serp_snippet": "",
            "digest": {
                "deep": True,
                "lead": (
                    "Proses deposit di situs ini dimulai dengan membuka "
                    "menu setor dana yang ada di pojok kanan atas "
                    "halaman utama."
                ),
                "key_paragraphs": [
                    "Setelah nominal diisi, sistem akan menampilkan "
                    "nomor rekening tujuan beserta batas waktu "
                    "pembayaran yang berlaku untuk transaksi itu."
                ],
                "faq": [
                    {
                        "question": (
                            "Berapa lama dana masuk setelah transfer "
                            "berhasil dilakukan dari bank?"
                        ),
                        "answer": (
                            "Dana biasanya masuk dalam hitungan menit "
                            "selama nominal yang dikirim sama persis "
                            "dengan yang tertulis di layar."
                        ),
                    }
                ],
                "outline": [
                    {"level": 2, "heading": "Cara Deposit"},
                ],
            },
        }
    ]
}


class PenyapuKaku(unittest.TestCase):
    def test_frasa_surat_dinas_diturunkan(self):
        hasil = fix_stiffness(
            "Dengan demikian, pengguna senantiasa memperoleh akses."
        )

        self.assertIn("Jadi", hasil)
        self.assertIn("selalu", hasil)
        self.assertNotIn("Dengan demikian", hasil)
        self.assertNotIn("senantiasa", hasil)

    def test_frasa_pengisi_dibuang(self):
        hasil = fix_stiffness(
            "Adapun proses pendaftarannya selesai dalam beberapa menit."
        )

        self.assertNotIn("Adapun", hasil)
        self.assertTrue(
            hasil.startswith("Proses"),
            hasil,
        )

    def test_huruf_besar_dipulihkan(self):
        """
        Frasa pembuka yang dibuang meninggalkan huruf kecil di awal
        kalimat, dan itu lebih kelihatan daripada frasa yang tadi
        dibuang.
        """
        hasil = fix_stiffness("Adapun halaman ini dibuat untuk pemula.")

        self.assertEqual(hasil[0], "H")

    def test_frasa_panjang_menang_atas_yang_pendek(self):
        hasil = fix_stiffness("Namun demikian, layanannya tetap jalan.")

        self.assertIn("Meski begitu", hasil)

    def test_kata_baku_biasa_tidak_disentuh(self):
        """
        "dapat", "tersebut", dan "melakukan" bukan bahasa surat dinas.
        Ikut disapu, yang tersisa justru kalimat yang ditulis ulang
        tanpa ada masalahnya.
        """
        asli = (
            "Fitur tersebut dapat digunakan kapan saja dan pengguna "
            "melakukan penarikan sendiri."
        )

        self.assertEqual(fix_stiffness(asli), asli)

    def test_potongan_kata_tidak_ikut(self):
        """
        "guna" jadi "untuk" hanya sebagai kata berdiri sendiri.
        "berguna", "menggunakan", dan "kegunaan" harus utuh.
        """
        asli = "Fitur ini berguna dan menggunakan koneksi biasa."

        self.assertEqual(fix_stiffness(asli), asli)

    def test_kosong_dan_bukan_teks_aman(self):
        self.assertEqual(fix_stiffness(""), "")
        self.assertEqual(fix_stiffness(None), None)
        self.assertEqual(fix_stiffness(12), 12)

    def test_nama_brand_dilindungi(self):
        hasil = fix_stiffness("Apabila ADAPUN sudah dibuka.", {"ADAPUN"})

        self.assertIn("ADAPUN", hasil)
        self.assertIn("Kalau", hasil)

    def test_seluruh_isi_disapu_sekaligus(self):
        isi = {
            "h1": "Adapun Halaman Ini",
            "paragraph": [
                "Dengan demikian prosesnya cepat.",
                "Kalimat ini sudah wajar dan tidak perlu diubah.",
            ],
            "_riwayat": ["Adapun ini penanda, bukan teks terbit."],
        }

        hasil, jumlah = fix_content_stiffness(isi)

        self.assertEqual(jumlah, 2)
        self.assertNotIn("Adapun", hasil["h1"])
        self.assertIn("Jadi", hasil["paragraph"][0])
        self.assertEqual(hasil["paragraph"][1], isi["paragraph"][1])

        # Peran berawalan garis bawah tidak disentuh.
        self.assertEqual(hasil["_riwayat"], isi["_riwayat"])


class BahanPembanding(unittest.TestCase):
    def test_kumpulan_tersusun(self):
        index = source_index(PESAING)

        self.assertTrue(has_sources(index))
        self.assertGreater(index["sources"], 0)

    def test_tanpa_halaman_tidak_ada_bahan(self):
        self.assertFalse(has_sources(source_index({})))
        self.assertFalse(has_sources(source_index({"pages": []})))

    def test_judul_bagian_terlalu_pendek_tidak_ikut(self):
        """
        "Cara Deposit" dipakai ratusan halaman satu bidang tanpa satu
        pun menyalin yang lain.
        """
        index = source_index(PESAING)

        self.assertEqual(copied_run("Cara Deposit", index), "")


class PenjagaSalinan(unittest.TestCase):
    def setUp(self):
        self.index = source_index(PESAING)

    def test_kalimat_disalin_utuh_tertangkap(self):
        kalimat = (
            "Proses deposit di situs ini dimulai dengan membuka menu "
            "setor dana yang ada di pojok kanan atas halaman utama."
        )

        potongan = copied_run(kalimat, self.index)

        self.assertTrue(potongan)
        self.assertGreaterEqual(len(potongan.split()), NGRAM)

    def test_kalimat_sendiri_lolos(self):
        kalimat = (
            "Tombol setor ada di bilah bawah waktu halaman dibuka "
            "lewat ponsel, bukan di pojok layar seperti versi "
            "komputernya."
        )

        self.assertEqual(copied_run(kalimat, self.index), "")
        self.assertFalse(near_copy(kalimat, self.index))

    def test_frasa_bidang_yang_wajar_lolos(self):
        """
        Ambang delapan kata dipilih justru untuk ini. Halaman satu
        bidang wajar berbagi istilah; yang tidak wajar berbagi
        kalimat.
        """
        for wajar in (
            "Situs slot online terpercaya dengan pilihan permainan.",
            "Cara deposit dan penarikan dana di halaman ini.",
            "Dana biasanya masuk dalam hitungan menit saja.",
        ):
            with self.subTest(wajar=wajar):
                self.assertEqual(copied_run(wajar, self.index), "")

    def test_tiruan_yang_disela_satu_kata_tertangkap(self):
        """
        Bentuk yang lolos rangkaian delapan: kalimat ditiru utuh lalu
        satu kata di tengahnya diganti, sehingga tidak ada satu pun
        rangkaian delapan yang utuh sementara seluruh sisanya sama.
        """
        kalimat = (
            "Setelah nominal diisi, layar akan menampilkan nomor "
            "rekening tujuan beserta batas waktu pembayaran yang "
            "berlaku untuk transaksi itu."
        )

        self.assertTrue(near_copy(kalimat, self.index))

    def test_kalimat_pendek_tidak_dinilai_hampir_salinan(self):
        self.assertFalse(near_copy("Dana masuk cepat.", self.index))

    def test_kalimat_salinan_dibuang_sisanya_disimpan(self):
        teks = (
            "Proses deposit di situs ini dimulai dengan membuka menu "
            "setor dana yang ada di pojok kanan atas halaman utama. "
            "Di halaman ini tombolnya justru ada di bilah bawah."
        )

        bersih, jumlah, contoh = strip_copied(teks, self.index)

        self.assertEqual(jumlah, 1)
        self.assertTrue(contoh)
        self.assertIn("bilah bawah", bersih)
        self.assertNotIn("pojok kanan atas", bersih)

    def test_semua_salinan_jadi_kosong(self):
        """
        Kosong disengaja: yang kosong terdeteksi kependekan lalu
        diminta ulang ke model.
        """
        teks = (
            "Proses deposit di situs ini dimulai dengan membuka menu "
            "setor dana yang ada di pojok kanan atas halaman utama."
        )

        bersih, jumlah, _ = strip_copied(teks, self.index)

        self.assertEqual(bersih, "")
        self.assertEqual(jumlah, 1)

    def test_tanpa_bahan_tidak_membuang_apa_pun(self):
        teks = "Kalimat apa pun boleh berdiri kalau tidak ada pembanding."

        bersih, jumlah, _ = strip_copied(teks, source_index({}))

        self.assertEqual(bersih, teks)
        self.assertEqual(jumlah, 0)

    def test_seluruh_isi_disapu_sekaligus(self):
        isi = {
            "paragraph": [
                "Proses deposit di situs ini dimulai dengan membuka "
                "menu setor dana yang ada di pojok kanan atas halaman "
                "utama.",
                "Tombolnya di halaman ini justru ada di bilah bawah.",
            ],
            "_riwayat": [
                "Proses deposit di situs ini dimulai dengan membuka "
                "menu setor dana yang ada di pojok kanan atas halaman "
                "utama."
            ],
        }

        hasil, jumlah, contoh = scrub_copied(isi, self.index)

        self.assertEqual(jumlah, 1)
        self.assertTrue(contoh)
        self.assertEqual(hasil["paragraph"][0], "")
        self.assertEqual(hasil["paragraph"][1], isi["paragraph"][1])

        # Penanda riwayat tidak ikut disapu.
        self.assertEqual(hasil["_riwayat"], isi["_riwayat"])


class BidangDariKolomNiche(unittest.TestCase):
    """
    Kolom Niche menentukan ISI, bukan cuma jadi kata pencarian.

    Diminta pengguna 30 Agustus 2026: "Niche bukan hanya menggantikan
    keyword, Niche tuh buat isi alur nya".

    Sebelum ini, bidang di luar judi selalu jatuh ke aturan yang
    berbunyi "SEPUTAR TOPIK HALAMAN INI" - benar, tapi tidak menunjuk
    apa pun. Model 4B yang diberi aturan tanpa rujukan mengisi
    rujukannya sendiri dari bahan terdekat di prompt, dan bahan
    terdekat itu teks template. Hasilnya FAQ tentang bidang milik
    pemilik template.
    """

    def test_bidang_disebut_namanya_di_aturan_faq(self):
        aturan = faq_topic_rules("generic", "id", "toko sepatu")

        self.assertIn("SEPUTAR toko sepatu", aturan)
        self.assertNotIn("TOPIK HALAMAN INI", aturan)

    def test_bidang_ikut_ke_aturan_thai(self):
        aturan = faq_topic_rules("generic", "th", "ร้านรองเท้า")

        self.assertIn("ร้านรองเท้า", aturan)

    def test_judi_tidak_bergeser_sehuruf_pun(self):
        """
        Halaman judi yang dipakai pengguna sehari-hari sudah disetel
        berkali-kali. Ia tidak boleh berubah gara-gara bidang lain
        dibuat lebih pintar.
        """
        tanpa = faq_topic_rules("gambling", "id")

        for apa_pun in ("toko sepatu", "", "kursus", "{bidang}"):
            with self.subTest(apa_pun=apa_pun):
                self.assertEqual(
                    faq_topic_rules("gambling", "id", apa_pun),
                    tanpa,
                )

        self.assertIn("SEPUTAR SLOT", tanpa)

    def test_kesanggupan_judi_juga_tidak_bergeser(self):
        self.assertEqual(
            capability_lines("gambling", "id", "toko sepatu"),
            capability_lines("gambling", "id"),
        )

    def test_niche_kosong_jatuh_ke_kalimat_lama(self):
        aturan = faq_topic_rules("generic", "id", "")

        self.assertIn("topik halaman ini", aturan)

    def test_nama_bidang_dirapikan(self):
        self.assertEqual(field_label("  Kursus Bahasa Inggris  "), "Kursus Bahasa Inggris")
        self.assertEqual(field_label("slot gacor"), "slot gacor")
        self.assertEqual(field_label(""), "topik halaman ini")
        self.assertEqual(field_label(None), "topik halaman ini")

    def test_kurawal_tidak_bisa_disuntikkan(self):
        """
        Aturan ini disusun dengan str.format di tempat lain. Satu
        kurawal di dalam nama bidang mengubah teks yang diketik
        pengguna jadi lubang substitusi.
        """
        self.assertNotIn("{", field_label("nakal {bidang} {0}"))
        self.assertNotIn("}", field_label("nakal {bidang} {0}"))

    def test_nama_bidang_kepanjangan_dipotong_di_batas_kata(self):
        panjang = "toko sepatu olahraga lari maraton untuk pemula dan atlet profesional"
        hasil = field_label(panjang)

        self.assertLessEqual(len(hasil), 60)
        self.assertTrue(panjang.startswith(hasil), hasil)
        self.assertFalse(hasil.endswith(" "))

    def test_brand_membawa_bidang_yang_diketik(self):
        brand = build_brand("ABECE", "", "id", "", None, keyword="toko sepatu")

        self.assertEqual(brand["niche_text"], "toko sepatu")
        self.assertEqual(brand["niche"], "generic")

        judi = build_brand("ABECE", "", "id", "", None, keyword="slot gacor")

        self.assertEqual(judi["niche"], "gambling")
        self.assertEqual(judi["niche_text"], "slot gacor")


class AturanBunyi(unittest.TestCase):
    def test_aturan_indonesia_menyebut_yang_harus_dilakukan(self):
        aturan = voice_rules("id")

        self.assertIn("YANG HARUS DILAKUKAN", aturan)
        self.assertIn("NYAMBUNG KE KALIMAT SEBELUMNYA", aturan)
        self.assertIn("PEMBUKA PARAGRAF BERGANTI-GANTI", aturan)
        self.assertIn("SEBUT HAL YANG SPESIFIK", aturan)

    def test_aturan_indonesia_melarang_menyalin(self):
        self.assertIn("JANGAN MENYALIN KALIMAT", voice_rules("id"))

    def test_aturan_thai_ikut_diperbarui(self):
        """
        Aturan Thai ditulis DALAM bahasa Thai, bukan diterjemahkan.
        Aturan berbahasa Indonesia yang dikirim bersama perintah
        menulis Thai justru menyodorkan bentuk kalimat Indonesia.
        """
        aturan = voice_rules("th")

        self.assertIn("ห้ามลอกประโยค", aturan)
        self.assertNotIn("JANGAN MENYALIN KALIMAT", aturan)

    def test_larangan_lama_tidak_hilang(self):
        """
        Tiap larangan lahir dari keluhan yang bisa ditunjuk. Melonggar
        ke arah "mengalir" tidak boleh membatalkan satu pun.
        """
        aturan = voice_rules("id")

        for lama in (
            "di era digital",
            "bukan sekadar",
            "Anda",
            "nggak",
            "adapun",
        ):
            with self.subTest(lama=lama):
                self.assertIn(lama, aturan)


if __name__ == "__main__":
    unittest.main()
