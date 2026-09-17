"""
Satu kalimat tidak boleh dibaca dua kali di halaman yang sama.

Sampai 19 Agustus 2026 pengulangan hanya diperiksa DI DALAM satu
peran: paragraf dengan paragraf, ulasan dengan ulasan. Bentuk yang
paling sering dikeluhkan pembaca justru yang lain - satu kalimat
yang sama berdiri di deskripsi, di paragraf, lalu di ulasan - dan
justru karena tempatnya berbeda tidak ada satu pun pemeriksaan yang
keberatan.

Contoh di berkas uji ini bukan karangan. Semuanya disalin apa adanya
dari output/siam123-slot-gacor-20260819_054058/index.html, halaman
yang benar-benar terbit.
"""

import unittest

from generators.content_planner import (
    all_duplicates,
    cross_role_conflict,
    cross_role_duplicates,
    extend_content,
    same_opening_slots,
    short_roles,
)
from generators.final_verify import read_page, repeated_across_roles
from ai.neiiu_prompts import PROSE_REPEAT_ROLES, REPEAT_PRONE_ROLES


SPEC = {
    "meta_description": {"count": 1, "budgets": [180]},
    "paragraph": {"count": 4, "budgets": [300] * 4, "floors": [0] * 4},
    "faq_answer": {"count": 2, "budgets": [200] * 2, "floors": [0] * 2},
    "review_text": {"count": 2, "budgets": [200] * 2, "floors": [0] * 2},
}

DESKRIPSI = (
    "Pemain baru bisa daftar dengan QRIS langsung, tanpa perlu "
    "verifikasi tambahan. Setelah login, tampilan slot gacor sudah "
    "update sebelum pagi hari."
)


class CrossRoleDuplicates(unittest.TestCase):
    def test_paragraf_yang_menyalin_deskripsi_ketahuan(self):
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [
                "Pemain baru bisa daftar langsung dengan QRIS tanpa "
                "perlu verifikasi tambahan. Setelah login, tampilan "
                "slot gacor sudah update sebelum pagi hari.",
                "Daftar permainannya disusun menurut penyedia, jadi "
                "yang dicari bisa ditemukan tanpa menggulir jauh.",
                "Menu atas tetap terlihat waktu halaman digulir ke "
                "bagian yang lebih bawah.",
                "Setelah login, tampilan slot gacor sudah update "
                "sebelum pagi hari. Data ini tersedia saat masuk.",
            ],
            "faq_answer": [],
            "review_text": [],
        }

        self.assertEqual(
            cross_role_duplicates(SPEC, isi),
            {"paragraph": [0, 3]},
        )

    def test_ulasan_yang_mengulang_paragraf_ketahuan(self):
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [
                "Daftar permainannya disusun menurut penyedia, jadi "
                "yang dicari bisa ditemukan tanpa menggulir jauh.",
            ],
            "review_text": [
                "Halamannya terbuka cepat di jaringan biasa dan tidak "
                "ada bagian yang melompat waktu digulir ke bawah.",
                "Daftar permainannya disusun menurut penyedia, jadi "
                "yang dicari bisa ditemukan tanpa menggulir jauh.",
            ],
        }

        self.assertEqual(
            cross_role_duplicates(SPEC, isi)["review_text"],
            [1],
        )

    def test_kalimat_berbeda_tidak_pernah_dituduh(self):
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [
                "Daftar permainannya disusun menurut penyedia, jadi "
                "yang dicari bisa ditemukan tanpa menggulir jauh.",
                "Menu atas tetap terlihat waktu halaman digulir ke "
                "bagian yang lebih bawah, termasuk di layar kecil.",
            ],
            "review_text": [
                "Halamannya terbuka cepat di jaringan biasa dan tidak "
                "ada bagian yang melompat waktu digulir ke bawah.",
            ],
        }

        self.assertEqual(cross_role_duplicates(SPEC, isi), {})

    def test_kalimat_pendek_tidak_ikut_diadu(self):
        """
        "Daftar sekarang" memang wajar berdiri di beberapa tempat.
        """
        isi = {
            "meta_description": "Daftar sekarang.",
            "paragraph": ["Daftar sekarang.", "Daftar sekarang juga."],
        }

        self.assertEqual(cross_role_duplicates(SPEC, isi), {})

    def test_kembar_lintas_peran_masuk_daftar_minta_ulang(self):
        """
        Yang ketahuan harus bermuara ke mesin perbaikan yang sudah
        ada, bukan cuma jadi laporan.
        """
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [
                "Pemain baru bisa daftar dengan QRIS langsung, tanpa "
                "perlu verifikasi tambahan. Setelah login, tampilan "
                "slot gacor sudah update sebelum pagi hari.",
            ],
        }

        self.assertIn(0, short_roles(SPEC, isi).get("paragraph", []))

    def test_peran_di_luar_spec_tidak_pernah_diminta_ulang(self):
        """
        Nomor posisi yang dikembalikan bermuara ke gap_spec, yang
        membaca spec[role] langsung. Peran yang ada di isi tapi tidak
        diminta di spec akan menjatuhkan seluruh run dengan KeyError,
        di tengah langkah yang paling mahal.
        """
        spec = {"meta_description": {"count": 1, "budgets": [180]}}
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [DESKRIPSI],
        }

        self.assertEqual(cross_role_duplicates(spec, isi), {})
        self.assertEqual(short_roles(spec, isi), {})

    def test_deskripsi_tidak_pernah_jadi_yang_dikorbankan(self):
        """
        Title dan deskripsi berdiri paling depan di urutan peran,
        jadi yang diminta ulang selalu peran yang menyalinnya.
        """
        isi = {
            "meta_description": DESKRIPSI,
            "paragraph": [DESKRIPSI],
        }

        self.assertNotIn("meta_description", cross_role_duplicates(SPEC, isi))


class PutaranTerakhirIkutMengaduLintasPeran(unittest.TestCase):
    """
    Putaran terakhir sebelum isinya diserahkan ke perender dulu cuma
    memanggil duplicate_slots - kembar SEPERAN saja. Ia buta persis di
    tempat yang paling menentukan: sesudahnya model tidak dihubungi
    lagi.

    Terukur pada halaman yang benar-benar terbit,
    output/x7gaming88-slot-online-20260820_014659: dua kalimat
    deskripsi berdiri lagi utuh sebagai paragraf pertama. Putaran gap
    di awal memang memeriksanya, tapi teks itu baru bertabrakan
    SESUDAH penyapu klaim dan penyeragaman angka mengubah keduanya.
    """

    SPEC = {
        "meta_description": {"count": 1, "budgets": [180], "floors": [140]},
        "paragraph": {
            "count": 2,
            "budgets": [183, 182],
            "floors": [150, 150],
        },
    }

    DESC = (
        "X7GAMING88 menyediakan akses langsung ke slot online tanpa perlu "
        "login ulang. Setelah daftar, saldo langsung masuk."
    )

    ISI = {
        "meta_description": DESC,
        "paragraph": [
            "X7GAMING88 menyediakan akses langsung ke slot online tanpa "
            "perlu login ulang. Tidak ada langkah tambahan di sini.",
            "Pemain baru bisa mulai bermain slot online dengan satu klik.",
        ],
    }

    def test_daftar_gabungan_menangkap_keduanya(self):
        self.assertEqual(all_duplicates(self.SPEC, self.ISI), {"paragraph": [0]})

    def test_konflik_lintas_peran_terbaca_per_teks(self):
        self.assertTrue(
            cross_role_conflict(
                self.ISI["paragraph"][0], "paragraph", self.ISI
            )
        )
        self.assertFalse(
            cross_role_conflict(
                self.ISI["paragraph"][1], "paragraph", self.ISI
            )
        )

    def test_jawaban_berbeda_yang_lebih_pendek_tetap_dipakai(self):
        """
        Slot yang diminta ulang karena MENGULANG tidak boleh tunduk
        pada aturan "yang lebih panjang menang" - aturan itu dibuat
        untuk lubang kependekan.
        """
        sisa = {
            "paragraph": {
                "count": 1,
                "positions": [0],
                "budgets": [183],
                "floors": [150],
            }
        }

        beda = "Menu di halaman ini disusun menurut penyedia permainannya."

        hasil = extend_content(
            self.ISI, {"paragraph": [beda]}, self.SPEC, sisa
        )

        self.assertEqual(hasil["paragraph"][0], beda)

    def test_jawaban_yang_masih_mengulang_ditolak(self):
        sisa = {
            "paragraph": {
                "count": 1,
                "positions": [0],
                "budgets": [183],
                "floors": [150],
            }
        }

        masih = (
            "X7GAMING88 menyediakan akses langsung ke slot online tanpa "
            "perlu login ulang, dan begitu seterusnya di halaman ini."
        )

        hasil = extend_content(
            self.ISI, {"paragraph": [masih]}, self.SPEC, sisa
        )

        self.assertEqual(hasil["paragraph"][0], self.ISI["paragraph"][0])


class TeksTunggalDiBawahLantai(unittest.TestCase):
    """
    Judul dan deskripsi yang jatuh di bawah lantainya harus diminta
    ulang, bukan diterbitkan apa adanya.

    Yang membuatnya jatuh biasanya bukan model melainkan penyapu
    klaim, yang bekerja SESUDAH panjangnya ditegakkan grammar.
    Terukur pada halaman terbit
    output/wayangplay-slot-gacor-20260819_232939: satu kalimat dibuang
    penyapu, deskripsinya tinggal 93 karakter dari lantai 140, dan
    tidak satu pun tahap keberatan karena kolomnya toh tidak kosong.
    """

    SPEC = {
        "title": {"count": 1, "budgets": [70], "floors": [50]},
        "meta_description": {"count": 1, "budgets": [180], "floors": [140]},
    }

    def test_deskripsi_yang_tersapu_jadi_pendek_diminta_ulang(self):
        isi = {
            "title": "WAYANGPLAY # Slot Gacor Menyenangkan, Mainkan Mudah",
            "meta_description": (
                "Pemain baru bisa langsung mulai bermain slot gacor di "
                "WAYANGPLAY tanpa harus siapkan apa-apa."
            ),
        }

        self.assertEqual(
            short_roles(self.SPEC, isi),
            {"meta_description": [0]},
        )

    def test_title_kependekan_diminta_ulang(self):
        isi = {
            "title": "WAYANGPLAY # Slot Gacor",
            "meta_description": "H" * 150,
        }

        self.assertEqual(short_roles(self.SPEC, isi), {"title": [0]})

    def test_yang_sesuai_kontrak_dibiarkan(self):
        isi = {
            "title": "WAYANGPLAY # Slot Gacor dengan Navigasi yang Ringkas",
            "meta_description": "H" * 150,
        }

        self.assertEqual(short_roles(self.SPEC, isi), {})

    def test_slot_kosong_tetap_diminta_ulang_seperti_dulu(self):
        isi = {"title": "", "meta_description": "H" * 150}

        self.assertEqual(short_roles(self.SPEC, isi), {"title": [0]})

    def test_jawaban_susulan_yang_lebih_pendek_ditolak(self):
        """
        Giliran ulang yang menjawab lebih pendek lagi cuma menukar
        teks pendek dengan teks yang lebih pendek.
        """
        sisa = {
            "meta_description": {
                "count": 1,
                "positions": [0],
                "budgets": [180],
            }
        }

        pendek = (
            "Deskripsi yang tinggal 93 karakter sesudah satu kalimatnya "
            "dibuang penyapu klaim."
        )

        hasil = extend_content(
            {"meta_description": pendek},
            {"meta_description": "Lebih pendek lagi."},
            self.SPEC,
            sisa,
        )

        self.assertEqual(hasil["meta_description"], pendek)

    def test_jawaban_susulan_yang_lebih_panjang_dipakai(self):
        sisa = {
            "meta_description": {
                "count": 1,
                "positions": [0],
                "budgets": [180],
            }
        }

        panjang = (
            "Deskripsi baru yang panjangnya memenuhi lantai yang diminta "
            "pengguna untuk halaman ini, tanpa satu klaim pun."
        )

        hasil = extend_content(
            {"meta_description": "Pendek sekali."},
            {"meta_description": panjang},
            self.SPEC,
            sisa,
        )

        self.assertEqual(hasil["meta_description"], panjang)


class PromptMengingatkanProsa(unittest.TestCase):
    def test_paragraf_dan_deskripsi_ikut_diingatkan(self):
        """
        Akar masalahnya ada di prompt: giliran yang menulis paragraf
        tidak pernah diberi tahu paragraf dan deskripsi yang sudah
        ditulis giliran sebelumnya.
        """
        for peran in ("meta_description", "paragraph", "faq_answer"):
            self.assertIn(peran, PROSE_REPEAT_ROLES)

    def test_peran_label_tetap_diingatkan_seperti_dulu(self):
        for peran in ("nav_label", "faq_question", "review_text"):
            self.assertIn(peran, REPEAT_PRONE_ROLES)


class PengulanganDiHalamanJadi(unittest.TestCase):
    HALAMAN = """<!doctype html><html lang="id"><head>
    <title>SIAM123: Slot Gacor</title>
    <meta name="description" content="%s">
    </head><body>
    <h1>Slot Gacor di SIAM123</h1>
    <p>Pemain baru bisa daftar langsung dengan QRIS tanpa perlu
    verifikasi tambahan. Setelah login, tampilan slot gacor sudah
    update sebelum pagi hari.</p>
    <p>Daftar permainannya disusun menurut penyedia sehingga yang
    dicari bisa ditemukan tanpa menggulir seluruh halaman.</p>
    </body></html>""" % DESKRIPSI

    def test_terbaca_dari_html_jadi(self):
        temuan = repeated_across_roles(read_page(self.HALAMAN))

        self.assertTrue(temuan)
        self.assertIn("meta_description", temuan[0])
        self.assertIn("paragraph", temuan[0])

    def test_halaman_bersih_tidak_dilaporkan(self):
        bersih = self.HALAMAN.replace(
            "Pemain baru bisa daftar langsung dengan QRIS tanpa perlu\n"
            "    verifikasi tambahan. Setelah login, tampilan slot gacor sudah\n"
            "    update sebelum pagi hari.",
            "Menu bagian atas tetap terlihat waktu halaman digulir ke "
            "bawah, termasuk waktu dibuka lewat layar kecil.",
        )

        self.assertEqual(repeated_across_roles(read_page(bersih)), [])


if __name__ == "__main__":
    unittest.main()


class UlasanTidakBolehDibukaSama(unittest.TestCase):
    """
    Tiga ulasan yang sama-sama dibuka "Saya" terbaca sebagai tiga
    ulasan yang ditulis satu orang - dan memang begitu adanya.

    Aturannya sudah lama ada di prompt dan diikuti model kadang-kadang
    saja. Terukur pada halaman yang benar-benar terbit,
    output/wayangplay-slot-gacor-20260820_055457: ketiga ulasannya
    dibuka "Saya".
    """

    SPEC = {"review_text": {"count": 3, "budgets": [140] * 3, "floors": [120] * 3}}

    SAMA = {
        "review_text": [
            "Saya daftar pagi ini dan langsung bisa main tanpa hambatan.",
            "Saya coba dari luar kota, tampilannya tetap rapi di layar kecil.",
            "Menu penyedianya jelas, jadi tidak perlu menebak bagian mana.",
        ]
    }

    def test_ulasan_kedua_yang_membuka_sama_diminta_ulang(self):
        self.assertEqual(
            same_opening_slots(self.SPEC, self.SAMA),
            {"review_text": [1]},
        )

    def test_masuk_daftar_putaran_terakhir(self):
        self.assertEqual(
            all_duplicates(self.SPEC, self.SAMA)["review_text"],
            [1],
        )

    def test_pembuka_yang_sudah_berbeda_dibiarkan(self):
        beda = {
            "review_text": [
                self.SAMA["review_text"][0],
                self.SAMA["review_text"][2],
                "Tombol pentingnya mudah dijangkau jempol, tanpa mencari.",
            ]
        }

        self.assertEqual(same_opening_slots(self.SPEC, beda), {})

    def test_peran_lain_tidak_ikut_dituntut(self):
        """
        Label menu dan judul kartu memang wajar berbagi kata pertama.
        """
        spec = {"nav_label": {"count": 2, "budgets": [20, 20]}}
        isi = {"nav_label": ["Slot Gacor", "Slot Online"]}

        self.assertEqual(same_opening_slots(spec, isi), {})
