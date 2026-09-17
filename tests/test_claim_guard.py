"""
Penyapu klaim tidak boleh merusak nama brand.

Bug yang ditutup di sini terbit di berkas AMP yang benar-benar jadi,
output/siam123-slot-gacor-20260819_054058/amp/index.html:

    "SIAM123 Pemain baru bisa daftar..."
      -> dilaporkan klaim "123 Pemain"
      -> disapu jadi "SIAM baru bisa daftar..."

Nama brand yang berakhir angka adalah bentuk paling umum di bidang
ini, dan penyapu klaim adalah lapis terakhir yang menyentuh teks -
tidak ada pemulih ejaan brand sesudahnya yang sempat memperbaikinya.

Perbaikannya UMUM, bukan daftar hitam nama brand: angka yang berdiri
di tengah token tidak pernah dibaca sebagai jumlah orang.
"""

import unittest

from generators.claim_guard import fabricated_claims, scrub_text


class BrandBerakhirAngka(unittest.TestCase):
    KALIMAT = (
        ("SIAM123 Pemain baru bisa daftar dengan QRIS langsung.", "SIAM123"),
        ("Bergabunglah dengan X7GAMING88 pemain aktif setiap hari.", "X7GAMING88"),
        ("JUHI88 pengguna baru langsung masuk ke halaman utama.", "JUHI88"),
        ("Tim TOTO4D member baru diarahkan ke panduan.", "TOTO4D"),
    )

    def test_tidak_dilaporkan_sebagai_klaim(self):
        for kalimat, brand in self.KALIMAT:
            with self.subTest(brand=brand):
                self.assertEqual(fabricated_claims(kalimat), [])

    def test_nama_brand_tetap_utuh_sesudah_disapu(self):
        for kalimat, brand in self.KALIMAT:
            with self.subTest(brand=brand):
                hasil, dibuang = scrub_text(kalimat)

                self.assertIn(brand, hasil)
                self.assertEqual(dibuang, 0)


class AngkaKaranganTetapDitangkap(unittest.TestCase):
    """
    Sisi sebaliknya. Perbaikan yang melumpuhkan penyapunya sendiri
    bukan perbaikan.
    """

    KALIMAT = (
        "Situs ini punya lebih dari 10.000 member aktif tiap bulan.",
        "Sudah 25 ribu pemain bergabung tahun ini.",
        "Ada 1.200 pengguna yang login hari ini.",
        "Kami menerima 5 penghargaan tahun lalu.",
        "Lebih dari 3 juta member sudah terdaftar di sini.",
    )

    def test_masih_ditangkap(self):
        for kalimat in self.KALIMAT:
            with self.subTest(kalimat=kalimat):
                self.assertTrue(fabricated_claims(kalimat))

    def test_angka_di_ujung_brand_tidak_menutupi_klaim_di_kalimat_sama(self):
        kalimat = (
            "SIAM123 sudah dipakai lebih dari 10.000 member aktif."
        )

        temuan = fabricated_claims(kalimat)

        self.assertTrue(temuan)
        self.assertIn("SIAM123", scrub_text(kalimat)[0])


class KlaimLainTidakIkutLonggar(unittest.TestCase):
    """
    Yang memang harus tetap ditahan - lihat keputusan pengguna 13
    Agustus 2026: brand boleh percaya diri, tapi janji pembaca
    menang dan angka karangan tidak.
    """

    def test_janji_kemenangan(self):
        self.assertTrue(fabricated_claims("Semua pemain pasti menang."))

    def test_rtp_berangka(self):
        self.assertTrue(fabricated_claims("RTP hari ini mencapai 98,7%."))

    def test_nominal_kemenangan(self):
        self.assertTrue(
            fabricated_claims("Saya menang 5 juta tadi malam di sini.")
        )

    def test_jadwal_keberuntungan(self):
        self.assertTrue(
            fabricated_claims("Jam 3 sore paling gacor untuk main.")
        )


if __name__ == "__main__":
    unittest.main()
