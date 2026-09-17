"""
Nama situs yang dipenggal model disatukan kembali.

Terukur pada halaman yang benar-benar terbit 21 Agustus 2026:

    BATARATOTO - Slot Online di BATARAT-TO-TO Akses Cepat, Tidak Blokir

Satu judul, dua sebutan nama situs, dan yang kedua bukan nama siapa
pun. Akibatnya berlipat, bukan satu:

  1. Halaman berdiri atas nama situs yang tidak ada — cacat yang sama
     dengan "SIAM12S" yang sudah pernah ditutup.
  2. Bentuk yang rusak tidak dikenali strip_brand_mentions, jadi ia
     lolos dari penyapu sebutan kedua dan judulnya menyebut nama situs
     dua kali.
  3. Lapis gema menyalinnya ke SELURUH halaman — di halaman itu, ke
     lima tempat sekaligus termasuk og:title dan alt gambar.

Pemulih ejaan yang sudah ada tidak pernah melihatnya, dan sebabnya di
tokenisasi: BRAND_CANDIDATE memotong per deretan huruf-angka, jadi
"BATARAT-TO-TO" masuk sebagai TIGA kata yang tidak satu pun mirip
"BATARATOTO".

Tidak memakai AI sama sekali.
"""

import unittest

from generators.brand_swap import restore_brand, restore_split_brand


class NamaDipenggalDisatukan(unittest.TestCase):
    def test_bentuk_yang_benar_benar_terbit(self):
        hasil, jumlah = restore_brand(
            "BATARATOTO - Slot Online di BATARAT-TO-TO Akses Cepat",
            "BATARATOTO",
            "slot online",
        )

        self.assertNotIn("BATARAT-TO-TO", hasil)
        self.assertEqual(hasil.count("BATARATOTO"), 2)
        self.assertEqual(jumlah, 1)

    def test_dipisah_spasi(self):
        hasil, _ = restore_brand("Main di BATARA TOTO", "BATARATOTO", "")

        self.assertIn("BATARATOTO", hasil)

    def test_dipisah_titik_tiap_huruf(self):
        hasil, _ = restore_brand("B.A.T.A.R.A.T.O.T.O buka", "BATARATOTO", "")

        self.assertIn("BATARATOTO buka", hasil)

    def test_dipisah_hubung(self):
        hasil, _ = restore_brand("Kunjungi WAYANG-PLAY", "WAYANGPLAY", "")

        self.assertIn("WAYANGPLAY", hasil)

    def test_angka_yang_dipisah_ikut_disatukan(self):
        hasil, _ = restore_brand("Buka RAJAWALI 77 sekarang", "RAJAWALI77", "")

        self.assertIn("RAJAWALI77", hasil)

    def test_nama_yang_sudah_benar_tidak_dihitung(self):
        hasil, jumlah = restore_brand(
            "Halaman BATARATOTO sudah benar", "BATARATOTO", ""
        )

        self.assertEqual(hasil, "Halaman BATARATOTO sudah benar")
        self.assertEqual(jumlah, 0)


class KalimatBiasaTidakDimakan(unittest.TestCase):
    def test_nama_berupa_frasa_umum_tidak_menabrak_kalimat(self):
        """
        Spasi adalah pemisah kata yang sah. Nama situs yang kebetulan
        berupa frasa umum akan memakan kalimat pembaca kalau huruf
        besar-kecilnya tidak ikut dituntut.
        """
        hasil, jumlah = restore_brand(
            "situs slot gacor hari ini", "SITUSSLOT", "slot gacor"
        )

        self.assertEqual(hasil, "situs slot gacor hari ini")
        self.assertEqual(jumlah, 0)

    def test_kata_biasa_yang_mirip_nama_tidak_disentuh(self):
        for teks, nama in (
            ("Wayang kulit itu seni", "WAYANGPLAY"),
            ("megawatt listrik", "MEGAWIN"),
        ):
            with self.subTest(teks=teks):
                self.assertEqual(restore_brand(teks, nama, "")[0], teks)

    def test_nama_pendek_tidak_dilayani(self):
        """
        Pola yang membolehkan pemisah di tiap sela terlalu longgar
        untuk nama tiga huruf — ambangnya sama dengan pemulihan ejaan.
        """
        hasil, jumlah = restore_split_brand("a b c dan seterusnya", "abc")

        self.assertEqual(hasil, "a b c dan seterusnya")
        self.assertEqual(jumlah, 0)


if __name__ == "__main__":
    unittest.main()
