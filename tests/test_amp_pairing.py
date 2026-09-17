"""
Landing dan AMP wajib berangkat dari SATU isi.

Dua jalur menghasilkan berkas AMP, dan keduanya harus sampai ke
tempat yang sama:

  1. Template AMP diunggah -> diisi dengan isi yang sama seperti
     landing.
  2. Template AMP tidak diunggah -> berkas AMP dirakit dari plan yang
     diturunkan dari isi yang sama itu juga.

Jalur kedua yang paling mudah lepas tanpa ketahuan: ia tidak
menyentuh template mana pun, jadi tidak ada perbandingan byte yang
akan menangkapnya. Yang menjaga cuma pemeriksaan ini.
"""

import unittest

from generators.amp_generator import generate_amp_page
from generators.final_verify import read_page, verify_pages
from generators.template_filler import fill_template
from services.neiiu_pipeline import (
    amp_fallback_addresses,
    build_brand,
    plan_from_template_content,
    template_canonical,
)
from tests.fixtures import LANDING
from tests.test_template_integrity import ISI


class AmpTanpaTemplateAmp(unittest.TestCase):
    def setUp(self):
        self.brand = build_brand(
            "WAYANGPLAY", "", "id", "", None, keyword="slot gacor"
        )

        isi = dict(ISI)
        isi["_keyword"] = "slot gacor"

        self.landing = fill_template(
            html=LANDING,
            content=isi,
            brand=self.brand,
            old_brand="",
        )

        plan = plan_from_template_content(
            isi, "slot gacor", self.brand, "id"
        )

        # Alamatnya diturunkan lewat penolong yang SAMA dengan yang
        # dipakai pipeline. Menuliskannya ulang di sini berarti yang
        # diuji tiruan alamatnya, bukan alamat yang benar-benar
        # terbit - dan tiruan itu yang pertama kali dipakai waktu uji
        # ini ditulis, lalu melaporkan "example.com bocor" untuk
        # jalur yang sebenarnya bersih.
        brand_amp, canonical, sendiri = amp_fallback_addresses(
            template_canonical(LANDING),
            self.brand,
        )

        self.amp = generate_amp_page(
            plan=plan,
            design={},
            brand=brand_amp,
            page_url=canonical,
            amp_url=sendiri,
        )

    def test_title_dan_deskripsi_sama_dengan_landing(self):
        kiri = read_page(self.landing["html"])
        kanan = read_page(self.amp)

        self.assertEqual(kiri["title"], kanan["title"])
        self.assertEqual(kiri["meta_description"], kanan["meta_description"])

    def test_h1_sama_dengan_landing(self):
        kiri = read_page(self.landing["html"])
        kanan = read_page(self.amp)

        self.assertEqual(kiri["h1"], kanan["h1"])

    def test_pemeriksa_akhir_meloloskan_pasangan_ini(self):
        hasil = verify_pages(
            landing_html=self.landing["html"],
            amp_html=self.amp,
            template_landing=LANDING,
            landing_ranges=self.landing["ranges"],
            brand="WAYANGPLAY",
            keyword="slot gacor",
            region="id",
        )

        self.assertEqual(hasil["hard"], [])

    def test_isi_faq_ikut_ke_berkas_amp(self):
        for pertanyaan in ISI["faq_question"]:
            self.assertIn(pertanyaan[:40], self.amp)

    def test_tidak_menyebut_alamat_karangan(self):
        """
        Berkas AMP rakitan dulu satu-satunya yang tetap memuat
        SITE_BASE_URL bawaan - "https://example.com" - padahal
        landing di sebelahnya sudah bersih.
        """
        self.assertNotIn("https://example.com", self.amp)


if __name__ == "__main__":
    unittest.main()
