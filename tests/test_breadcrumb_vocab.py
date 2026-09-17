"""
Remah navigasi menyatakan letak halaman, bukan menjual apa pun.

Diminta pengguna 21 Agustus 2026, atas remah yang benar-benar terbit
di halaman BATARATOTO:

    Beranda > Slot Online > Pengalaman Bermain > Slot Gacor

Kalimatnya: "pada bagian breadcrumble jangan melenceng dari pembahasan
situs slot; contohnya 'lihat hasil, verifikasi akun, tutup sesi, main
tanpa batas' saya tidak suka". Bentuk yang dia mau disebutkan sendiri:
brand, brand login, rtp brand, situs slot, situs brand, brand link,
link brand, rtp slot, alternatif brand, alternatif slot, slot online,
agen slot, link login.

Enam dari tiga belas bentuk itu memuat NAMA SITUS, dan itu membalik
aturan yang berlaku sebelumnya - "Nama Situs Tidak Masuk Remah
Navigasi" di NEIIU.md. Pembalikan itu ikut diuji di sini, supaya
tidak diam-diam dikembalikan oleh perbaikan lain.

Yang di luar bidang slot tidak ikut berubah: remah halaman generic
tetap disusun seperti sebelumnya, nama situs tetap dicabut.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.content_planner import (
    breadcrumb_allowed,
    normalize_breadcrumb,
)


KEYWORD = "slot online"
BRAND = "BATARATOTO"
H1 = "Slot Online di BATARATOTO"


def jalur(raw, niche="gambling"):
    return normalize_breadcrumb(
        raw,
        keyword=KEYWORD,
        h1=H1,
        brand_name=BRAND,
        region="id",
        niche=niche,
    )


class KosakataDitegakkan(unittest.TestCase):
    def test_tingkat_yang_menjual_ditukar(self):
        hasil = jalur(["Beranda", "Slot Online", "Pengalaman Bermain"])

        self.assertNotIn("Pengalaman Bermain", hasil)
        self.assertEqual(hasil[0], "Beranda")

    def test_contoh_yang_dikeluhkan_pengguna_tidak_lolos(self):
        for teks in (
            "Lihat Hasil",
            "Verifikasi Akun",
            "Tutup Sesi",
            "Main Tanpa Batas",
        ):
            with self.subTest(teks=teks):
                self.assertFalse(breadcrumb_allowed(teks, KEYWORD, BRAND))

    def test_bentuk_yang_diminta_pengguna_lolos(self):
        for teks in (
            "Situs Slot",
            "Slot Online",
            "RTP Slot",
            "Agen Slot",
            "Link Login",
            "Alternatif Slot",
            f"Situs {BRAND}",
            f"RTP {BRAND}",
            f"{BRAND} Login",
            f"Link {BRAND}",
        ):
            with self.subTest(teks=teks):
                self.assertTrue(breadcrumb_allowed(teks, KEYWORD, BRAND))

    def test_jalur_yang_seluruhnya_ditolak_tetap_punya_tingkat(self):
        """
        Remah yang cuma berisi "Beranda" tidak memberi tahu apa pun.
        """
        hasil = jalur(["Beranda", "Lihat Hasil", "Tutup Sesi"])

        self.assertGreaterEqual(len(hasil), 2)
        self.assertEqual(hasil[0], "Beranda")

        for tingkat in hasil[1:]:
            self.assertTrue(breadcrumb_allowed(tingkat, KEYWORD, BRAND))

    def test_tidak_ada_tingkat_kembar(self):
        """
        Yang terbit 21 Agustus 2026 berakhir "Slot Gacor > Slot Gacor".
        """
        hasil = jalur(["Beranda", "Lihat Hasil", "Verifikasi Akun", "Tutup Sesi"])

        kecil = [teks.casefold() for teks in hasil]

        self.assertEqual(len(kecil), len(set(kecil)))


class NamaSitusBolehIkut(unittest.TestCase):
    def test_tingkat_bernama_situs_tidak_dicabut(self):
        hasil = jalur(["Beranda", "Situs Slot", f"RTP {BRAND}"])

        self.assertIn(f"RTP {BRAND}", hasil)

    def test_halaman_di_luar_bidang_slot_tetap_mencabut_nama(self):
        """
        Pembalikan aturan hanya berlaku untuk halaman situs slot.
        """
        hasil = normalize_breadcrumb(
            ["Beranda", "Katalog", f"Koleksi {BRAND}"],
            keyword="jaket kulit",
            h1=f"Jaket Kulit di {BRAND}",
            brand_name=BRAND,
            region="id",
            niche="generic",
        )

        for tingkat in hasil:
            self.assertNotIn(BRAND, tingkat)


if __name__ == "__main__":
    unittest.main()
