"""
Ekstraksi template dari halaman kompetitor yang sedang ngerank.

Yang diambil adalah kerangka dan gaya visualnya:
  - urutan section dan tipe kontennya
  - palet warna, font, dan radius
  - tipe schema yang dipakai
  - pola panjang title dan meta

Teks isi kompetitor tidak ikut diambil. Konten halaman baru
ditulis ulang dari nol oleh content planner, jadi hasil akhirnya
mengikuti struktur yang terbukti ngerank tanpa menyalin materi
milik orang lain, sekaligus menghindari CSS bundle mereka yang
hampir selalu melewati batas 75KB milik AMP.
"""

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from analyzer.page_signals import collect_schema_types, detect_faq
from config import REQUEST_TIMEOUT, USER_AGENT


HEX_PATTERN = re.compile(
    r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b"
)

RGB_PATTERN = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})",
)

FONT_PATTERN = re.compile(
    r"font-family\s*:\s*([^;{}]+)",
    re.IGNORECASE,
)

RADIUS_PATTERN = re.compile(
    r"border-radius\s*:\s*([0-9]+)px",
    re.IGNORECASE,
)

GENERIC_FONTS = {
    "inherit", "initial", "unset", "serif", "sans-serif",
    "monospace", "cursive", "fantasy", "system-ui",
}


def expand_hex(value: str) -> str:
    """
    Mengubah #abc jadi #aabbcc.
    """
    if len(value) == 3:
        return "".join(char * 2 for char in value).lower()

    return value.lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.lstrip("#")

    return (
        int(clean[0:2], 16),
        int(clean[2:4], 16),
        int(clean[4:6], 16),
    )


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def luminance(rgb: tuple[int, int, int]) -> float:
    """
    Perkiraan kecerahan warna, skala 0 sampai 1.
    """
    red, green, blue = rgb

    return (
        0.2126 * red + 0.7152 * green + 0.0722 * blue
    ) / 255


def saturation(rgb: tuple[int, int, int]) -> float:
    """
    Seberapa berwarna sebuah warna, skala 0 sampai 1.
    """
    highest = max(rgb)
    lowest = min(rgb)

    return (highest - lowest) / 255


def collect_css(
    soup: BeautifulSoup,
    base_url: str,
    fetch_external: bool = True,
    max_files: int = 3,
    max_bytes: int = 400_000,
) -> str:
    """
    Mengumpulkan CSS halaman: blok <style> ditambah beberapa
    stylesheet eksternal dari domain yang sama.

    CSS ini hanya dibaca untuk mengambil warna dan font, tidak
    ikut dipakai di halaman hasil.
    """
    chunks = [
        (tag.string or tag.get_text() or "")
        for tag in soup.find_all("style")
    ]

    if fetch_external:
        base_domain = urlparse(base_url).netloc.lower()
        fetched = 0

        for tag in soup.find_all(
            "link",
            rel=lambda value: value and "stylesheet" in value,
        ):
            if fetched >= max_files:
                break

            href = str(tag.get("href", "")).strip()

            if not href:
                continue

            css_url = urljoin(base_url, href)

            if urlparse(css_url).netloc.lower() != base_domain:
                continue

            try:
                response = requests.get(
                    css_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                )

                response.raise_for_status()

                chunks.append(response.text[:max_bytes])
                fetched += 1

            except requests.exceptions.RequestException:
                continue

    # Warna yang ditulis langsung di atribut style juga dihitung.
    chunks.extend(
        str(tag.get("style", ""))
        for tag in soup.find_all(attrs={"style": True})
    )

    return "\n".join(chunks)


def extract_palette(css_text: str) -> dict:
    """
    Menyusun palet warna dari CSS kompetitor.

    Warna dipilih berdasarkan frekuensi pakai, lalu dipetakan ke
    peran: background, surface, teks, dan aksen.
    """
    counter: dict[str, int] = {}

    for match in HEX_PATTERN.finditer(css_text):
        color = "#" + expand_hex(match.group(1))
        counter[color] = counter.get(color, 0) + 1

    for match in RGB_PATTERN.finditer(css_text):
        try:
            rgb = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            continue

        if any(channel > 255 for channel in rgb):
            continue

        color = rgb_to_hex(rgb)
        counter[color] = counter.get(color, 0) + 1

    if not counter:
        return default_palette()

    ranked = sorted(
        counter.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    top_colors = [color for color, _ in ranked[:40]]

    darks = [
        color
        for color in top_colors
        if luminance(hex_to_rgb(color)) < 0.25
    ]

    lights = [
        color
        for color in top_colors
        if luminance(hex_to_rgb(color)) > 0.85
    ]

    accents = [
        color
        for color in top_colors
        if saturation(hex_to_rgb(color)) > 0.35
        and 0.2 < luminance(hex_to_rgb(color)) < 0.85
    ]

    is_dark = len(darks) >= len(lights)

    palette = default_palette()

    if is_dark:
        palette["mode"] = "dark"
        palette["background"] = darks[0] if darks else "#0b0f19"
        palette["surface"] = (
            darks[1] if len(darks) > 1 else "#151b2b"
        )
        palette["text"] = "#e8ecf5"
        palette["muted"] = "#9aa4bd"
        palette["border"] = "#252d42"
    else:
        palette["mode"] = "light"
        palette["background"] = lights[0] if lights else "#ffffff"
        palette["surface"] = (
            lights[1] if len(lights) > 1 else "#f5f7fb"
        )
        palette["text"] = darks[0] if darks else "#14181f"
        palette["muted"] = "#5b6478"
        palette["border"] = "#e2e6ef"

    if accents:
        palette["accent"] = accents[0]
        palette["accent_2"] = (
            accents[1] if len(accents) > 1 else accents[0]
        )

    accent_rgb = hex_to_rgb(palette["accent"])

    palette["accent_text"] = (
        "#0b0f19" if luminance(accent_rgb) > 0.6 else "#ffffff"
    )

    palette["source_colors"] = top_colors[:12]

    return palette


def default_palette() -> dict:
    return {
        "mode": "dark",
        "background": "#0b0f19",
        "surface": "#151b2b",
        "text": "#e8ecf5",
        "muted": "#9aa4bd",
        "border": "#252d42",
        "accent": "#f5b301",
        "accent_2": "#e8531f",
        "accent_text": "#0b0f19",
        "source_colors": [],
    }


SAFE_FONT_NAME = re.compile(r"^[A-Za-z0-9 _-]+$")


def extract_fonts(css_text: str) -> list[str]:
    """
    Mengambil font utama yang dipakai kompetitor.

    Nama font ini nantinya ditempel apa adanya ke dalam blok CSS
    halaman hasil. Karena sumbernya CSS milik orang lain, isinya
    tidak boleh dipercaya: nama seperti
    `Arial</style><script>...` akan keluar dari blok style dan
    berubah jadi kode yang ikut jalan di halaman hasil. Karena itu
    hanya nama dengan huruf, angka, spasi, dan tanda hubung yang
    diterima.
    """
    seen: list[str] = []

    for match in FONT_PATTERN.finditer(css_text):
        stack = match.group(1)

        for raw_font in stack.split(","):
            font = raw_font.strip().strip("'\"").strip()

            if not font or font.lower() in GENERIC_FONTS:
                continue

            if len(font) > 40 or font.startswith("var("):
                continue

            if not SAFE_FONT_NAME.match(font):
                continue

            if font not in seen:
                seen.append(font)

            break

        if len(seen) >= 3:
            break

    return seen


def extract_radius(css_text: str) -> int:
    """
    Menebak sudut membulat yang dominan.
    """
    values = [
        int(match.group(1))
        for match in RADIUS_PATTERN.finditer(css_text)
    ]

    values = [value for value in values if 0 < value <= 40]

    if not values:
        return 12

    return max(set(values), key=values.count)


def classify_section(
    heading_tag,
    following,
) -> str:
    """
    Menentukan tipe section berdasarkan isi setelah headingnya.
    """
    heading_text = heading_tag.get_text(" ", strip=True).lower()

    if "?" in heading_text:
        return "faq"

    if any(
        word in heading_text
        for word in ("faq", "pertanyaan", "tanya jawab")
    ):
        return "faq"

    if any(
        word in heading_text
        for word in ("cara", "langkah", "panduan", "tutorial", "step")
    ):
        return "steps"

    tags = [
        node
        for node in following
        if getattr(node, "name", None) is not None
    ]

    if any(node.name == "table" for node in tags):
        return "table"

    # next_elements ikut menghasilkan induk dan anaknya sekaligus,
    # jadi <li> harus dihitung lewat identitas node. Kalau dihitung
    # dengan find_all per node, satu daftar yang bersarang dalam
    # beberapa div akan terhitung berkali-kali.
    list_items = len({id(node) for node in tags if node.name == "li"})

    if list_items >= 4:
        return "list"

    return "paragraph"


def extract_structure(soup: BeautifulSoup) -> list[dict]:
    """
    Membaca urutan section halaman berdasarkan alur headingnya.
    """
    body = soup.body or soup

    headings = body.find_all(["h1", "h2", "h3"])
    sections: list[dict] = []

    for index, heading in enumerate(headings):
        level = heading.name

        if level == "h3" and sections:
            # H3 dianggap bagian dari section di atasnya.
            sections[-1]["subheading_count"] += 1
            continue

        following = []

        for sibling in heading.next_elements:
            if sibling is None:
                break

            name = getattr(sibling, "name", None)

            if name in ("h1", "h2"):
                if sibling is not heading:
                    break

            following.append(sibling)

            if len(following) > 400:
                break

        section_type = (
            "hero"
            if level == "h1" and not sections
            else classify_section(heading, following)
        )

        sections.append(
            {
                "order": len(sections) + 1,
                "level": level,
                "type": section_type,
                "heading_length": len(
                    heading.get_text(" ", strip=True)
                ),
                "subheading_count": 0,
            }
        )

        if len(sections) >= 20:
            break

    return sections


def extract_template(
    html: str,
    final_url: str,
    fetch_external_css: bool = True,
) -> dict:
    """
    Menghasilkan blueprint template dari satu halaman kompetitor.
    """
    soup = BeautifulSoup(html, "html.parser")

    css_text = collect_css(
        soup,
        final_url,
        fetch_external=fetch_external_css,
    )

    structure = extract_structure(soup)

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else ""
    )

    meta_tag = soup.find(
        "meta",
        attrs={"name": re.compile(r"^description$", re.I)},
    )

    meta_description = (
        str(meta_tag.get("content", "")).strip()
        if meta_tag
        else ""
    )

    faq = detect_faq(soup)

    section_types = [section["type"] for section in structure]

    return {
        "source_url": final_url,
        "source_domain": urlparse(final_url).netloc.lower(),
        "design": {
            "palette": extract_palette(css_text),
            "fonts": extract_fonts(css_text),
            "radius": extract_radius(css_text),
        },
        "structure": structure,
        "section_types": section_types,
        "section_count": len(structure),
        "has_faq": faq["has_faq"],
        "schema_types": collect_schema_types(soup),
        "meta_pattern": {
            "title_length": len(title),
            "meta_length": len(meta_description),
        },
        "css_bytes_scanned": len(css_text.encode("utf-8")),
    }


def extract_template_from_url(
    url: str,
    fetch_external_css: bool = True,
) -> dict:
    """
    Mengambil halaman kompetitor lalu mengekstrak templatenya.
    """
    from crawler.crawler import fetch_page

    crawl_result = fetch_page(url)

    return extract_template(
        html=crawl_result["html"],
        final_url=crawl_result["final_url"],
        fetch_external_css=fetch_external_css,
    )


def rank_reference_pages(pages: list[dict]) -> list[dict]:
    """
    Mengurutkan kandidat halaman acuan dari yang paling layak.

    Dikembalikan sebagai daftar, bukan satu halaman, karena server
    kompetitor sering menolak atau kehabisan waktu saat diambil.
    Kalau hanya ada satu kandidat dan kandidat itu mati, seluruh
    pipeline ikut berhenti padahal masih ada kandidat lain yang
    sama-sama layak.
    """
    usable = [
        page
        for page in pages
        if page["status"] == "ok"
        and not page.get("hijack", {}).get("is_hijacked")
        and page.get("usable", True)
    ]

    if not usable:
        # Semua terindikasi bajakan atau tidak terbaca. Lebih baik
        # mundur ke apa pun yang berhasil di-crawl daripada berhenti.
        usable = [page for page in pages if page["status"] == "ok"]

    def score(page: dict) -> float:
        signals = page["signals"]

        value = 0.0
        value += max(0, 11 - page["position"]) * 3
        value += page["headings"]["h2_count"] * 1.5
        value += 12 if signals["faq"]["has_faq"] else 0
        value += 8 if signals["schema_types"] else 0
        value += min(page["word_count"] / 200, 15)

        return value

    return sorted(usable, key=score, reverse=True)


def pick_reference_page(pages: list[dict]) -> dict | None:
    """
    Memilih halaman kompetitor terbaik untuk dijadikan acuan template.

    Diprioritaskan yang posisinya tinggi, strukturnya lengkap,
    dan sudah punya FAQ serta schema.

    Halaman di domain bajakan tidak pernah dipilih. Strukturnya
    adalah struktur situs institusi yang dibobol, bukan struktur
    landing page, jadi menirunya tidak ada gunanya.
    """
    ranked = rank_reference_pages(pages)

    return ranked[0] if ranked else None
