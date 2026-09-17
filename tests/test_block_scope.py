"""
Judul yang diganti wajib membawa isinya sekalian.

Bug yang ditutup di sini tidak pernah menggagalkan satu run pun, dan
justru itu yang membuatnya bertahan lama: halamannya terbit, lulus
pemeriksa akhir, lalu berdiri dengan judul kartu yang membicarakan
keyword baru di atas paragraf yang masih membicarakan keyword pemilik
template sebelumnya.

Terukur di template 298 milik pengguna, dengan brand lama OSB99:

    <h4>Transparansi informasi</h4>      <- jadi slot, diganti
    <p>Setiap data yang ditampilkan ...  <- DILEWATI

Sebabnya scope_to_brand_block cuma mengenal satu tanda kepemilikan:
judul yang menyebut nama brand lama. Judul kartu seperti "Transparansi
informasi" tidak menyebut siapa-siapa, jadi paragraf di bawahnya
terhitung milik pemilik template - padahal judul di atasnya sudah
diganti NEIIU sendiri.

Aturan barunya berbunyi: paragraf ditulis ulang kalau judul di atasnya
ditulis ulang. Yang dijaganya arah sebaliknya - bagian yang judulnya
DIBIARKAN tetap membawa isinya sendiri. Itu diuji terpisah di sini,
karena menutup arah pertama dengan cara yang salah - "tulis ulang
semua paragraf" - lulus arah pertama dengan sempurna sekaligus
menimpa tulisan milik pemilik template.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_scanner import scan
from generators.template_slots import build_slot_map


def peta(html: str, brand_lama: str = ""):
    return build_slot_map(scan(html), brand_lama, "id")


def teks_slot(peta_slot: dict, peran: str) -> list[str]:
    return [
        " ".join(str(slot["current"]).split())
        for slot in peta_slot["roles"].get(peran, [])
    ]


def teks_dilewati(peta_slot: dict) -> list[str]:
    return [
        " ".join(str(slot.get("current") or "").split())
        for slot in peta_slot["skipped"]
    ]


# Kartu fitur: judulnya tidak menyebut nama brand mana pun, persis
# seperti di template nyata.
KARTU = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Deposit QRIS Instan Tanpa Menunggu Lama</title>
</head><body>
<h1>OSB99 - Deposit QRIS Instan</h1>

<div class="drow"><div class="dtext">
<h4>Transparansi informasi</h4>
<p>Setiap data yang ditampilkan memiliki sumber yang dapat diverifikasi oleh siapa saja.</p>
</div></div>

<div class="drow"><div class="dtext">
<h4>Keamanan akses</h4>
<p>Sistem keamanan yang andal melindungi pengunjung dari berbagai ancaman siber terbaru.</p>
</div></div>

<h2>Keunggulan OSB99</h2>
<p>Bagian ini memang menyebut nama brand lama di judulnya, jadi sejak dulu sudah ikut diganti.</p>
</body></html>
"""


# Halaman dengan bagian milik toko yang templatenya dipinjam. Judulnya
# ditandai data-neiiu-skip, jadi ia tidak jadi slot heading - dan
# karena judulnya dibiarkan, isinya pun harus dibiarkan.
TOKO = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<title>OSB99 | Deposit QRIS Instan Tanpa Menunggu Lama</title>
</head><body>
<h1>OSB99 - Deposit QRIS Instan</h1>

<h2 data-neiiu-skip>Koleksi Jersey Musim Ini</h2>
<p>Bahan utamanya poliester daur ulang dan waktu pengiriman dihitung terpisah dari waktu pemrosesan pesanan.</p>
<p>Setiap pesanan dikirim dari gudang resmi dengan nomor pelacakan yang bisa dipantau pembeli kapan saja.</p>

<h2>Keunggulan OSB99</h2>
<p>Bagian milik brand lama yang memang sudah ditulis ulang sejak dulu, tanpa perlu aturan baru.</p>
</body></html>
"""


class JudulDigantiMembawaIsinya(unittest.TestCase):
    def test_paragraf_di_bawah_judul_yang_diganti_ikut_diganti(self):
        hasil = peta(KARTU, "OSB99")

        paragraf = teks_slot(hasil, "paragraph")

        self.assertIn(
            "Setiap data yang ditampilkan memiliki sumber yang dapat "
            "diverifikasi oleh siapa saja.",
            paragraf,
        )
        self.assertIn(
            "Sistem keamanan yang andal melindungi pengunjung dari "
            "berbagai ancaman siber terbaru.",
            paragraf,
        )

    def test_judulnya_sendiri_memang_jadi_slot(self):
        """
        Syaratnya berlaku dua arah: kalau judulnya ternyata TIDAK
        diganti, aturan baru ini tidak punya alasan untuk jalan.
        """
        hasil = peta(KARTU, "OSB99")

        self.assertIn("Transparansi informasi", teks_slot(hasil, "heading"))
        self.assertIn("Keamanan akses", teks_slot(hasil, "heading"))

    def test_bagian_bernama_brand_lama_tetap_ikut(self):
        hasil = peta(KARTU, "OSB99")

        self.assertIn(
            "Bagian ini memang menyebut nama brand lama di judulnya, "
            "jadi sejak dulu sudah ikut diganti.",
            teks_slot(hasil, "paragraph"),
        )

    def test_tidak_satu_paragraf_pun_tertinggal(self):
        hasil = peta(KARTU, "OSB99")

        tertinggal = [
            teks
            for teks in teks_dilewati(hasil)
            if len(teks) >= 60
        ]

        self.assertEqual(tertinggal, [])


class IsiMilikTokoTetapDijaga(unittest.TestCase):
    def test_keterangan_produk_tidak_ikut_ditulis_ulang(self):
        hasil = peta(TOKO, "OSB99")

        paragraf = teks_slot(hasil, "paragraph")

        for kalimat in paragraf:
            self.assertNotIn("poliester daur ulang", kalimat)
            self.assertNotIn("nomor pelacakan", kalimat)

    def test_judul_yang_dibiarkan_tidak_jadi_slot_heading(self):
        """
        Inilah yang menjaga arah kedua: syarat barunya bergantung pada
        slot heading, jadi bagian yang judulnya dibiarkan tidak pernah
        ikut terseret.
        """
        hasil = peta(TOKO, "OSB99")

        self.assertNotIn(
            "Koleksi Jersey Musim Ini",
            teks_slot(hasil, "heading"),
        )

    def test_bagian_brand_lama_di_halaman_yang_sama_tetap_ikut(self):
        hasil = peta(TOKO, "OSB99")

        self.assertIn(
            "Bagian milik brand lama yang memang sudah ditulis ulang "
            "sejak dulu, tanpa perlu aturan baru.",
            teks_slot(hasil, "paragraph"),
        )


if __name__ == "__main__":
    unittest.main()
