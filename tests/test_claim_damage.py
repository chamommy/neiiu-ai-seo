"""
Kalimat yang rusak SESUDAH klaimnya dicabut.

Penyapu klaim di generators/claim_guard.py sudah lama benar dalam hal
yang jadi tugasnya: ia menemukan janji berangka yang tidak bisa
dibuktikan pipeline dan mencabutnya. Yang belum benar apa yang
ditinggalkannya.

Terukur pada halaman yang benar-benar terbit 30 Agustus 2026, empat
bentuk kerusakan yang berbeda dan tidak satu pun tertangkap
pemeriksaan yang ada:

  1. Ekor kalimat yang dibuka kata penghubung
       ditulis : ... mencatat bahwa proses verifikasi hanya butuh 30 detik.
       terbit  : ... mencatat bahwa proses verifikasi.

  2. Kepala kalimat yang tinggal nama benda
       ditulis : Proses verifikasi hanya 2 menit, tanpa perlu mengunggah ...
       terbit  : Proses verifikasi, tanpa perlu mengunggah ...

  3. Penunjuk jam yang dibaca sebagai lama proses
       ditulis : Saya setor dari ponsel jam dua pagi dan saldo saya masuk
       terbit  : Saya setor dari ponsel dua pagi dan saldo saya masuk

  4. Angka bersatuan teknis yang tidak dilihat pola mana pun
       terbit  : berjalan lancar bahkan saat jaringan stabil di bawah 50 kbps

Nomor 1 dan 2 dua sisi dari satu soal: klaim bisa berdiri di ujung
kalimat atau di kepalanya, dan drop_dangling_clause cuma menjaga
ujung. Nomor 3 kebalikannya - penyapu yang bekerja padahal tidak ada
yang perlu disapu. Nomor 4 lubang di daftarnya.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.claim_guard import (
    cut_at_end,
    fabricated_claims,
    head_clause,
    scrub_text,
    sentence_survives,
)


class EkorKalimatYangTercabut(unittest.TestCase):
    """
    Kata penghubung menjanjikan sebuah pernyataan, dan pernyataannya
    persis yang dicabut.
    """

    PARAGRAF = (
        "Setiap pemain yang baru saja mulai bermain di ABECE mencatat "
        "bahwa proses verifikasi hanya butuh 30 detik. Tidak ada "
        "formulir panjang, tidak ada pengisian data yang mengganggu. "
        "Yang harus diisi cuma nomor ponsel dan kode verifikasi."
    )

    def test_kalimatnya_dibuang_utuh(self):
        hasil, jumlah = scrub_text(self.PARAGRAF)

        self.assertEqual(jumlah, 1)
        self.assertNotIn("mencatat bahwa proses verifikasi", hasil)

    def test_kalimat_lain_di_paragraf_yang_sama_tetap_berdiri(self):
        """
        Yang dibuang satu kalimat, bukan paragrafnya.
        """
        hasil, _ = scrub_text(self.PARAGRAF)

        self.assertIn("Tidak ada formulir panjang", hasil)
        self.assertIn("nomor ponsel dan kode verifikasi", hasil)

    def test_kalimat_utuh_berkata_penghubung_tidak_ikut_dibuang(self):
        """
        Yang membedakan bukan ada-tidaknya "bahwa" melainkan apakah
        ada yang dicabut dari belakangnya.
        """
        utuh = "Kami memastikan bahwa data pemain aman."

        self.assertEqual(scrub_text(utuh), (utuh, 0))

    def test_klaim_di_tengah_tidak_membuang_kalimatnya(self):
        """
        Bentuk yang sudah lama benar dan tidak boleh ikut berubah -
        keterangannya ada di sentence_survives.
        """
        hasil, jumlah = scrub_text(
            "Penarikan dana diproses dalam waktu kurang dari 5 menit "
            "setiap hari."
        )

        self.assertEqual(jumlah, 1)
        self.assertIn("Penarikan dana diproses", hasil)
        self.assertIn("setiap hari", hasil)


class KepalaKalimatYangTercabut(unittest.TestCase):
    JAWABAN = (
        "Anda bisa daftar di ABECE dengan membuka aplikasi atau situs "
        "melalui ponsel, lalu mengisi form dengan nomor telepon dan "
        "email yang aktif. Proses verifikasi hanya 2 menit, tanpa "
        "perlu mengunggah dokumen atau menunggu konfirmasi dari pihak "
        "ketiga. Setelah itu, sistem akan mengirimkan kode verifikasi "
        "ke nomor yang Anda masukkan."
    )

    def test_kalimatnya_dibuang_utuh(self):
        hasil, _ = scrub_text(self.JAWABAN)

        self.assertNotIn("Proses verifikasi, tanpa perlu", hasil)

    def test_kalimat_lain_tetap_berdiri(self):
        hasil, _ = scrub_text(self.JAWABAN)

        self.assertIn("Anda bisa daftar di ABECE", hasil)
        self.assertIn("mengirimkan kode verifikasi", hasil)

    def test_kepala_yang_masih_berpredikat_tidak_dibuang(self):
        """
        Ambangnya dua kata, dan itu yang memisahkan "Proses
        verifikasi" dari klausa yang benar-benar utuh.
        """
        teks = (
            "Saldo masuk dalam waktu kurang dari 2 menit, tanpa perlu "
            "menghubungi siapa pun di layanan pelanggan."
        )

        hasil, jumlah = scrub_text(teks)

        self.assertEqual(jumlah, 1)
        self.assertIn("Saldo masuk", hasil)

    def test_head_clause_membaca_klausa_pertama(self):
        self.assertEqual(head_clause("Proses verifikasi, tanpa perlu x"), "Proses verifikasi")
        self.assertEqual(head_clause("Tanpa koma sama sekali"), "Tanpa koma sama sekali")
        self.assertEqual(head_clause(""), "")

    def test_cut_at_end_membedakan_letak_potongan(self):
        self.assertTrue(cut_at_end("Aku pergi ke pasar pagi", "Aku pergi ke pasar."))
        self.assertFalse(cut_at_end("Aku pergi pagi ke pasar", "Aku pergi ke pasar."))
        self.assertFalse(cut_at_end("apa pun", ""))


class PenunjukJamBukanLamaProses(unittest.TestCase):
    def test_jam_berangka_di_belakangnya_tidak_dicabut(self):
        for teks in (
            "Saya setor dari ponsel jam dua pagi dan saldo saya masuk "
            "sebelum saya tutup aplikasi bank.",
            "Saya setor dari ponsel jam 2 pagi dan saldo saya masuk "
            "sebelum saya tutup aplikasi bank.",
        ):
            with self.subTest(teks=teks[:44]):
                self.assertEqual(scrub_text(teks), (teks, 0))

    def test_lama_proses_yang_benar_tetap_dicabut(self):
        """
        Kelonggaran ini tidak boleh membuka pintu yang dijaga.
        """
        _, jumlah = scrub_text(
            "Deposit diproses hanya dalam 3 detik saja."
        )

        self.assertEqual(jumlah, 1)

    def test_jam_ketersediaan_tetap_dibiarkan(self):
        teks = "Layanan bisa dihubungi 24 jam."

        self.assertEqual(scrub_text(teks), (teks, 0))


class AngkaBersatuanTeknis(unittest.TestCase):
    KALIMAT = (
        "Tampilan permainan berjalan lancar bahkan saat jaringan "
        "stabil di bawah 50 kbps."
    )

    def test_dicabut(self):
        hasil, jumlah = scrub_text(self.KALIMAT)

        self.assertEqual(jumlah, 1)
        self.assertNotIn("50 kbps", hasil)

    def test_ikut_dilaporkan_pemeriksa(self):
        """
        scrub_text MEMBUANG, fabricated_claims MELAPORKAN. Pola yang
        cuma dipasang di satu sisi menghasilkan audit yang melaporkan
        bersih atas halaman yang tidak.
        """
        self.assertTrue(fabricated_claims(self.KALIMAT))

    def test_satuan_lain_ikut(self):
        for teks in (
            "Unduhan cuma 15 MB saja.",
            "Waktu tanggapnya di bawah 40 ms.",
            "Permainannya berjalan di 60 fps.",
        ):
            with self.subTest(teks=teks):
                self.assertTrue(fabricated_claims(teks), teks)

    def test_harga_tidak_ikut_tersapu(self):
        """
        Harga barang memang boleh berdiri di halaman ini dan sudah
        punya jalurnya sendiri.
        """
        teks = "Kaosnya dijual Rp 150.000 per potong."

        self.assertEqual(scrub_text(teks), (teks, 0))


class AksaraThaiTidakIkutDihitungKata(unittest.TestCase):
    """
    Thai memberi spasi antar FRASA, bukan antar kata. Jebakan ini
    sudah pernah menjatuhkan seluruh kartu FAQ cadangan zona
    Thailand, dan dua pemeriksaan baru di sentence_survives
    dua-duanya menghitung kata dengan split().
    """

    def test_kalimat_thai_tetap_lolos(self):
        asli = "ฝากถอนรวดเร็ว ภายใน 5 นาที ทุกวัน"
        sisa = "ฝากถอนรวดเร็ว ทุกวัน"

        self.assertTrue(sentence_survives(asli, sisa))


if __name__ == "__main__":
    unittest.main()
