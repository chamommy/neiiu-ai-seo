"""
Teks yang dipotong harus tetap kalimat, bukan kalimat yang dipenggal.

Bug yang ditutup di sini terbit di berkas jadi
output/wayangplay-slot-gacor-20260819_225640/index.html:

    ditulis model : "... Akses langsung dari ponsel, tampilan
                    responsif, dan hasil kemenangan langsung muncul
                    di layar."                        (203 karakter)
    terbit        : "... Akses langsung dari ponsel, tampilan
                    responsif, dan hasil kemenangan." (178 karakter)

Kata terakhirnya kata benda, jadi seluruh penjaga kata gantung yang
sudah ada tidak keberatan. Yang dibaca orang di hasil pencarian
adalah kalimat yang berhenti sebelum mengatakan apa yang terjadi
pada kemenangannya.
"""

import unittest

from generators.template_filler import clean_line
from utils.text import drop_cut_tail


ASLI = (
    "Pemain baru bisa langsung mulai bermain slot gacor di WAYANGPLAY "
    "tanpa perlu menunggu atau merasa penasaran. Akses langsung dari "
    "ponsel, tampilan responsif, dan hasil kemenangan langsung muncul "
    "di layar."
)


class KlausaTerpenggalDibuang(unittest.TestCase):
    def test_deskripsi_yang_benar_benar_terbit(self):
        hasil = clean_line(ASLI, 180, "meta_description", floor=140)

        self.assertFalse(hasil.endswith("dan hasil kemenangan."))
        self.assertTrue(hasil.endswith("."))
        self.assertIn("tampilan responsif", hasil)

    def test_sisanya_masih_memenuhi_lantai_panjang(self):
        hasil = clean_line(ASLI, 180, "meta_description", floor=140)

        self.assertGreaterEqual(len(hasil), 140)
        self.assertLessEqual(len(hasil), 180)

    def test_daftar_yang_memang_berakhir_di_situ_tidak_disentuh(self):
        utuh = (
            "Halaman ini menyusun daftarnya menurut penyedia, jenis "
            "permainan, dan tingkat kesulitan."
        )

        self.assertEqual(drop_cut_tail(utuh, utuh), utuh)
        self.assertEqual(
            clean_line(utuh, 180, "meta_description", floor=0),
            utuh,
        )

    def test_potongan_di_luar_klausa_daftar_tidak_disentuh(self):
        panjang = (
            "Menu bagian atas tetap terlihat waktu halaman digulir sampai "
            "ke bagian paling bawah sekalipun, sehingga perpindahan "
            "antarbagian tidak menuntut siapa pun kembali ke puncak."
        )

        hasil = clean_line(panjang, 180, "meta_description", floor=140)

        self.assertIn("sehingga perpindahan", hasil)

    def test_tidak_membuang_sampai_tinggal_potongan_pendek(self):
        """
        Teks yang seluruhnya satu daftar tidak boleh habis dibuang.
        """
        daftar = "Cepat, mudah, dan sangat menyenangkan sekali dipakai"

        self.assertEqual(drop_cut_tail("Cepat, dan", daftar), "Cepat, dan")

    def test_lantai_menang_atas_kerapian(self):
        """
        Kalau membuang ekornya membuat teks jatuh di bawah lantai
        panjangnya, potongan aslinya yang dipakai. Lantai itu
        permintaan pengguna, bukan selera pipeline.
        """
        teks = (
            "Halaman ini dibuka cepat di ponsel, dan seluruh menunya "
            "tersusun rapi menurut penyedia permainan masing-masing."
        )

        hasil = clean_line(teks, 90, "meta_description", floor=80)

        self.assertGreaterEqual(len(hasil), 80)


if __name__ == "__main__":
    unittest.main()
