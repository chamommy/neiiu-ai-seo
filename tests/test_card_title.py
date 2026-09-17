"""
Kata di dalam judul adalah bagian dari judul, bukan judul kartu.

Judul kartu keunggulan dikenali dari letaknya: teks pendek yang
berdiri tepat sebelum sebuah paragraf, sekedalaman dengannya. Tiga
syarat itu juga dipenuhi sesuatu yang sama sekali bukan judul kartu -
sepotong kata yang ditebalkan atau dimiringkan DI DALAM judul halaman.

Terukur di berkas AMP template 298 milik pengguna:

    <h1 class="hero-title">OSB99 <em>Login</em></h1>
    <p class="lead">OSB99 memberikan kemudahan deposit QRIS ...</p>

"Login" pendek, berdiri tepat sebelum paragraf itu, dan sekedalaman
dengannya - jadi ia diangkat jadi judul kartu lalu diisi satu kalimat
judul kartu utuh. Yang terbit: judul besar halaman berbunyi "NEWBRAND
<em>kalimat sepanjang satu baris</em>".

Penjaga yang sudah ada cuma membaca tag simpulnya sendiri, dan tag
simpul ini <em>, bukan <h1>. Yang membedakannya jalur simpul itu.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_scanner import scan
from generators.template_slots import build_slot_map


# Judul halaman yang sebagian katanya dimiringkan, persis seperti di
# berkas AMP template 298.
JUDUL_TERBELAH = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Deposit QRIS Instan Tanpa Menunggu Lama</title>
</head><body>
<h1 class="hero-title">OSB99 <em>Login</em></h1>
<p class="lead">OSB99 memberikan kemudahan deposit QRIS instan hanya dalam satu detik saja.</p>
</body></html>
"""


# Kartu keunggulan yang sesungguhnya: judul pendek yang ditebalkan,
# berdiri di luar judul mana pun, diikuti keterangannya.
KARTU_SUNGGUHAN = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Deposit QRIS Instan Tanpa Menunggu Lama</title>
</head><body>
<h1>OSB99 - Deposit QRIS Instan</h1>
<h2>Keunggulan OSB99</h2>
<div class="card">
<strong>1. Deposit QRIS 1 Detik</strong>
<span>Proses deposit berlangsung cepat tanpa menunggu konfirmasi manual dari siapa pun.</span>
</div>
</body></html>
"""


def peran_dari(html: str, teks: str) -> str | None:
    """
    Peran yang didapat sepotong teks tertentu, atau None kalau dilewati.
    """
    peta = build_slot_map(scan(html), "OSB99", "id")

    for peran, daftar in peta["roles"].items():
        for slot in daftar:
            if " ".join(str(slot["current"]).split()) == teks:
                return peran

    return None


class KataDiDalamJudulTidakDiangkat(unittest.TestCase):
    def test_kata_yang_dimiringkan_di_dalam_h1_bukan_judul_kartu(self):
        self.assertNotEqual(
            peran_dari(JUDUL_TERBELAH, "Login"),
            "card_title",
        )

    def test_nama_brand_di_judul_yang_sama_tetap_diganti(self):
        """
        Yang dijaga cuma pengangkatan perannya. Bagian judul tetap
        kebagian penggantian nama seperti bagian judul lainnya - kalau
        ini ikut mati, perbaikannya menutup satu lubang sambil membuka
        yang lain.
        """
        self.assertEqual(
            peran_dari(JUDUL_TERBELAH, "OSB99"),
            "brand",
        )


class KartuSungguhanTetapDiangkat(unittest.TestCase):
    def test_judul_kartu_di_luar_judul_halaman_tetap_jadi_slot(self):
        self.assertEqual(
            peran_dari(KARTU_SUNGGUHAN, "1. Deposit QRIS 1 Detik"),
            "card_title",
        )

    def test_keterangannya_tetap_jadi_paragraf(self):
        self.assertEqual(
            peran_dari(
                KARTU_SUNGGUHAN,
                "Proses deposit berlangsung cepat tanpa menunggu "
                "konfirmasi manual dari siapa pun.",
            ),
            "paragraph",
        )


if __name__ == "__main__":
    unittest.main()
