"""
Pembaca gaya dari halaman acuan yang ditentukan pengguna.

Bedanya dengan `template_extractor`: modul itu mencari halaman
acuan sendiri dari hasil SERP dan dipakai untuk menyusun blueprint
metrik. Modul ini dipakai untuk hal yang berbeda — pengguna
menunjuk sendiri beberapa halaman yang desainnya ia suka, lalu
NEIIU membaca *gaya visual dan komponennya*, bukan strukturnya.

Yang diambil hanya keputusan desain yang tidak bisa dihakciptakan:
angka warna, nama font, besar radius, dan komponen apa saja yang
dipakai halaman itu. Teks, HTML, dan CSS mereka tidak pernah ikut
tersalin — seluruh halaman baru dirakit ulang dari pustaka blok
milik NEIIU sendiri.

Hasilnya disebut "DNA desain", dan dipakai `blocks.py` untuk
memutuskan blok mana yang dipasang serta `theme.py` untuk
menurunkan palet warnanya.
"""

import re
from statistics import median
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from generators.template_extractor import (
    collect_css,
    default_palette,
    extract_fonts,
    extract_palette,
    extract_radius,
    extract_structure,
)


# Komponen yang bisa dikenali dan punya padanan blok di blocks.py.
# Kunci di sini dipakai apa adanya sebagai nama blok, jadi menambah
# komponen baru berarti menambah entri di kedua berkas.
COMPONENT_NAMES = (
    "navbar",
    "floatbar",
    "popup",
    "cta_duo",
    "ratings",
    "testimoni",
    "tags",
    "footer_sitemap",
)


# Kata yang menandai tombol ajakan di halaman bergaya ini. Dicocokkan
# ke teks tautan, bukan ke nama kelas CSS, karena nama kelas hasil
# build tool modern sudah teracak dan tidak berarti apa-apa.
LOGIN_WORDS = ("login", "masuk", "log in", "sign in", "เข้าสู่ระบบ")
REGISTER_WORDS = ("daftar", "register", "sign up", "join", "สมัคร")

PROMO_WORDS = (
    "promo",
    "bonus",
    "live chat",
    "livechat",
    "link alternatif",
    "rtp",
    "deposit",
)


def _classes(node) -> str:
    """
    Menggabungkan class dan id satu node jadi satu teks kecil.

    Dipakai untuk pencocokan pola. `class` bisa berupa daftar atau
    teks tergantung cara BeautifulSoup mengurainya, jadi keduanya
    diratakan lebih dulu.
    """
    raw = node.get("class") or []

    if isinstance(raw, str):
        raw = [raw]

    return " ".join([*raw, str(node.get("id") or "")]).lower()


def _link_texts(soup: BeautifulSoup) -> list[str]:
    return [
        anchor.get_text(" ", strip=True).lower()
        for anchor in soup.find_all("a")
    ]


def _has_word(texts: list[str], words: tuple[str, ...]) -> bool:
    return any(
        word in text
        for text in texts
        for word in words
    )


def detect_components(
    soup: BeautifulSoup,
    css_text: str,
) -> dict[str, bool]:
    """
    Menebak komponen apa saja yang dipakai satu halaman acuan.

    Semua penilaian di sini berbasis bukti ganda: nama kelas saja
    tidak pernah cukup, karena kelas seperti "modal" sering ikut
    terbawa framework tanpa benar-benar dipakai. Yang dihitung
    adalah nama kelas yang cocok DAN isi yang masuk akal untuk
    komponen itu.
    """
    css = css_text.lower()
    links = _link_texts(soup)

    fixed_bottom = bool(
        re.search(
            r"position\s*:\s*fixed[^}]{0,300}?bottom\s*:",
            css,
        )
        or re.search(
            r"bottom\s*:[^}]{0,300}?position\s*:\s*fixed",
            css,
        )
    )

    found: dict[str, bool] = {name: False for name in COMPONENT_NAMES}

    for node in soup.find_all(["div", "nav", "section", "aside", "ul"]):
        name = _classes(node)

        if not name:
            continue

        anchors = node.find_all("a")

        if (
            re.search(r"(float|sticky|fixed|bottom)[-_ ]?(menu|nav|bar)", name)
            or (fixed_bottom and re.search(r"(float|bottom)[-_ ]?menu", name))
        ) and len(anchors) >= 3:
            found["floatbar"] = True

        if re.search(r"(popup|modal|overlay|lightbox)", name):
            # Popup asli selalu punya jalan keluar. Tanpa tombol
            # tutup, yang cocok biasanya cuma wadah kosong milik
            # framework yang tidak pernah tampil.
            has_close = bool(
                node.find(
                    attrs={"class": re.compile(r"close", re.I)},
                )
                or node.find(attrs={"onclick": True})
            )

            if has_close or len(anchors) >= 1:
                found["popup"] = True

        if re.search(r"(review|testimon|ulasan|rating[-_ ]?card)", name):
            found["testimoni"] = True

        if re.search(r"(tag|pill|chip|badge|related)", name) and (
            len(anchors) >= 5
        ):
            short = [
                anchor
                for anchor in anchors
                if len(anchor.get_text(" ", strip=True)) <= 32
            ]

            if len(short) >= 5:
                found["tags"] = True

    header = soup.find("header") or soup.find("nav")

    if header is not None:
        head_links = [
            text
            for text in _link_texts(header)
            if 0 < len(text) <= 40
        ]

        if len(head_links) >= 4:
            found["navbar"] = True

    footer = soup.find("footer")

    if footer is not None:
        if len(footer.find_all("a")) >= 8 and len(
            footer.find_all(["h2", "h3", "h4", "strong"])
        ) >= 2:
            found["footer_sitemap"] = True

    if _has_word(links, LOGIN_WORDS) and _has_word(links, REGISTER_WORDS):
        found["cta_duo"] = True

    if not found["floatbar"] and fixed_bottom and _has_word(
        links,
        PROMO_WORDS,
    ):
        found["floatbar"] = True

    body_text = soup.get_text(" ", strip=True).lower()

    if re.search(r"\d[.,]\d\s*(out of|dari|/)\s*5", body_text):
        found["ratings"] = True

    if not found["testimoni"] and re.search(
        r"(testimoni|ulasan (member|pengguna)|apa kata)",
        body_text,
    ):
        found["testimoni"] = True

    return found


def read_reference(url: str, fetch_external_css: bool = True) -> dict:
    """
    Membaca gaya satu halaman acuan.

    Tidak pernah melempar. Halaman acuan sering menolak request atau
    sudah mati, dan itu bukan alasan untuk menggagalkan seluruh
    pembuatan halaman — sumber yang gagal cukup dicatat lalu
    dilewati.
    """
    from crawler.crawler import fetch_page

    entry = {
        "url": url,
        "domain": urlparse(url).netloc.lower(),
        "ok": False,
        "error": "",
        "palette": {},
        "fonts": [],
        "radius": 0,
        "components": {},
        "section_types": [],
    }

    try:
        crawl = fetch_page(url)
    except Exception as error:
        entry["error"] = str(error)
        return entry

    try:
        soup = BeautifulSoup(crawl["html"], "html.parser")

        css_text = collect_css(
            soup,
            crawl["final_url"],
            fetch_external=fetch_external_css,
        )

        entry.update(
            {
                "ok": True,
                "domain": urlparse(crawl["final_url"]).netloc.lower(),
                "palette": extract_palette(css_text),
                "fonts": extract_fonts(css_text),
                "radius": extract_radius(css_text),
                "components": detect_components(soup, css_text),
                "section_types": [
                    section["type"]
                    for section in extract_structure(soup)
                ],
                "css_bytes_scanned": len(css_text.encode("utf-8")),
            }
        )
    except Exception as error:
        entry["error"] = f"gagal membaca gaya: {error}"

    return entry


def build_design_dna(
    urls: list[str],
    fetch_external_css: bool = True,
    on_source=None,
) -> dict:
    """
    Menggabungkan beberapa halaman acuan jadi satu DNA desain.

    Aturan penggabungan berbeda per bidang, dan bedanya disengaja:

    - Palet dan font diambil dari satu sumber saja, yaitu sumber
      pertama yang berhasil. Mencampur warna dari beberapa situs
      menghasilkan kombinasi yang tidak pernah dirancang siapa pun
      dan hampir selalu jelek.
    - Radius diambil median, karena ini satu angka yang aman
      dirata-ratakan.
    - Komponen digabung dengan OR. Kalau pengguna menunjuk tiga
      halaman acuan, ia ingin halamannya punya gabungan komponen
      terbaik dari ketiganya, bukan hanya irisan yang dipakai
      ketiga-tiganya.
    """
    sources: list[dict] = []

    for url in [u.strip() for u in urls if u and u.strip()]:
        entry = read_reference(url, fetch_external_css)
        sources.append(entry)

        if on_source is not None:
            on_source(entry)

    ok_sources = [entry for entry in sources if entry["ok"]]

    components = {name: False for name in COMPONENT_NAMES}

    for entry in ok_sources:
        for name, present in entry["components"].items():
            if present:
                components[name] = True

    if ok_sources:
        lead = ok_sources[0]
        palette = lead["palette"] or default_palette()
        fonts = lead["fonts"]

        radii = [entry["radius"] for entry in ok_sources if entry["radius"]]
        radius = int(median(radii)) if radii else 12
    else:
        # Tanpa satu pun acuan yang terbaca, halaman tetap harus jadi.
        # Palet bawaan sudah punya kontras yang layak, dan seluruh
        # blok tetap terpasang supaya hasilnya tidak mendadak jauh
        # lebih miskin hanya karena acuannya sedang mati.
        palette = default_palette()
        fonts = []
        radius = 12
        components = {name: True for name in COMPONENT_NAMES}

    section_types: list[str] = []

    for entry in ok_sources:
        section_types.extend(entry["section_types"])

    return {
        "sources": sources,
        "ok_count": len(ok_sources),
        "palette": palette,
        "fonts": fonts,
        "radius": radius,
        "components": components,
        "section_types": section_types,
    }
