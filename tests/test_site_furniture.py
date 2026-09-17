"""
Perkakas situs bukan tempat menulis isi SEO.

Diminta pengguna 30 Agustus 2026: "bagian struktur template jangan di
ubah jangan rusak dan jangan di gantian bagian struktur nya".

Yang dilihatnya terukur di job 169, pada template TeePublic berbahasa
Inggris yang diisi jadi halaman berbahasa Indonesia. 79 tulisan tautan
berganti - dan bukan berganti bahasa, melainkan berganti maksud:

    "Log In"            -> "Main dari HP"
    "Create an Account" -> "Proses Tanpa Gangguan"
    "animals"           -> "Sistem Responsif"
    "anime"             -> "Layanan 24 Jam"
    "About TeePublic"   -> "Tampilan Realtime"

Menu yang tombol masuknya bertuliskan "Main dari HP" bukan menu yang
bahasanya diperbaiki; ia menu yang isinya ditukar.

Sebabnya satu baris. KEPT_ROLES sudah lama menyatakan menu, label,
keterangan gambar, dan sel tabel tidak pernah ditulis ulang AI - tapi
gerbangnya berbunyi `role in KEPT_ROLES and not salinan_asing`, dan
template berbahasa Inggris di halaman Indonesia membuat SETIAP
labelnya terbaca "salah bahasa". Jalan keluar itu menelan seluruh
aturannya.

Tidak memakai AI sama sekali.
"""

import unittest

from generators.template_scanner import scan
from generators.template_slots import KEPT_ROLES, build_slot_map


# Template berbahasa Inggris, diisi jadi halaman Indonesia. Bentuk
# yang persis bikin job 169 rusak.
INGGRIS = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>OLDBRAND : The Best Shirt Shop for Every Fan Out There</title>
<meta name="description" content="OLDBRAND sells shirts, hoodies and
stickers designed by independent artists from all over the world.">
</head><body>
<header>
  <nav>
    <a href="/c/animals">animals</a>
    <a href="/c/anime">anime</a>
    <a href="/c/television">television</a>
    <a href="/login">Log In</a>
    <a href="/register">Create an Account</a>
    <a href="/about">About OLDBRAND</a>
  </nav>
</header>
<main>
  <h1>The Best Shirt Shop for Every Fan Out There</h1>
  <h2>Why People Keep Coming Back Here</h2>
  <p>Every shirt in this shop is printed after the order comes in, so
  the design you picked is the design that gets made, and nothing sits
  in a warehouse waiting for someone to want it.</p>
  <p>Shipping is handled by the printer closest to the address you
  gave, which is why an order placed in the morning often reaches the
  door before the week is over without anyone paying extra.</p>
  <table>
    <tr><td>Size</td><td>XS</td></tr>
    <tr><td>Chest</td><td>34 in</td></tr>
  </table>
  <figure>
    <img src="/a.jpg" alt="Folded shirt">
    <figcaption>Folded shirt, front view</figcaption>
  </figure>
  <form>
    <label for="q">Name and Number is required</label>
    <input id="q">
  </form>
</main>
</body></html>"""


class PerkakasSitusDipertahankan(unittest.TestCase):
    def setUp(self):
        self.peta = build_slot_map(scan(INGGRIS), "OLDBRAND", "id")

        self.dipertahankan = [
            str(slot.get("current", "")).strip()
            for slot in self.peta["skipped"]
            if slot.get("kept")
        ]

        self.diisi = {
            peran: [
                str(slot.get("current", "")).strip()
                for slot in daftar
            ]
            for peran, daftar in self.peta["roles"].items()
        }

    # --- yang HARUS dipertahankan ---

    def test_menu_tidak_ikut_ditulis_ulang(self):
        for label in (
            "animals",
            "anime",
            "television",
            "Log In",
            "Create an Account",
        ):
            with self.subTest(label=label):
                self.assertIn(label, self.dipertahankan)

    def test_menu_tidak_masuk_daftar_yang_diminta_ke_ai(self):
        semua_diminta = [
            teks for daftar in self.diisi.values() for teks in daftar
        ]

        for label in ("animals", "anime", "Log In"):
            with self.subTest(label=label):
                self.assertNotIn(label, semua_diminta)

    def test_peran_perkakas_tidak_punya_satu_slot_pun(self):
        """
        Ini gerbangnya. Selama nav_label masih punya slot, ada 23
        tulisan menu yang berangkat ke model tiap run.
        """
        for peran in KEPT_ROLES:
            with self.subTest(peran=peran):
                self.assertEqual(
                    self.peta["roles"].get(peran, []),
                    [],
                    f"{peran} masih diminta ke AI",
                )

    def test_sel_tabel_dan_label_formulir_ikut_dipertahankan(self):
        for teks in ("Size", "XS", "Name and Number is required"):
            with self.subTest(teks=teks):
                self.assertIn(teks, self.dipertahankan)

    def test_keterangan_gambar_dipertahankan(self):
        self.assertIn("Folded shirt, front view", self.dipertahankan)

    # --- yang TETAP harus diisi ---

    def test_isi_halaman_tetap_diminta_ke_ai(self):
        """
        Pencabutan jalan keluar tidak boleh ikut membekukan isi.
        Judul, deskripsi, H1, heading, dan paragraf tetap ditulis
        ulang - itu memang tugas generatornya.
        """
        for peran in ("title", "meta_description", "h1", "paragraph"):
            with self.subTest(peran=peran):
                self.assertTrue(
                    self.peta["roles"].get(peran),
                    f"{peran} tidak ada slotnya",
                )

    def test_paragraf_berbahasa_inggris_tetap_ditulis_ulang(self):
        paragraf = self.diisi.get("paragraph", [])

        self.assertTrue(
            any("printed after the order" in p for p in paragraf),
            paragraf,
        )


class HalamanSebahasaTidakBerubah(unittest.TestCase):
    """
    Template yang bahasanya SUDAH sama dengan halaman tidak boleh
    ikut bergeser. Perilaku di jalur ini memang sudah benar sebelum
    perbaikan, dan yang diuji di sini bahwa ia tetap begitu.
    """

    INDONESIA = INGGRIS.replace(
        '<a href="/login">Log In</a>',
        '<a href="/login">Masuk</a>',
    ).replace(
        '<a href="/c/animals">animals</a>',
        '<a href="/c/animals">hewan</a>',
    )

    def test_menu_indonesia_juga_dipertahankan(self):
        peta = build_slot_map(scan(self.INDONESIA), "OLDBRAND", "id")

        kept = [
            str(s.get("current", "")).strip()
            for s in peta["skipped"]
            if s.get("kept")
        ]

        self.assertIn("Masuk", kept)
        self.assertIn("hewan", kept)


if __name__ == "__main__":
    unittest.main()
