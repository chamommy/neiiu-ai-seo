"""
Sinyal SEO teknis yang tidak tercakup parser HTML dasar.

Modul ini membaca HTML mentah dan mengambil hal-hal yang
dipakai untuk membandingkan kompetitor di SERP: tipe schema,
keberadaan versi AMP, blok FAQ, tabel, dan berat halaman.
"""

import json
import re

from bs4 import BeautifulSoup


FAQ_QUESTION_PATTERN = re.compile(
    r"\b(apa|apakah|bagaimana|kenapa|mengapa|kapan|dimana|di mana|"
    r"berapa|siapa|cara|bisakah|amankah)\b",
    re.IGNORECASE,
)


def collect_schema_types(soup: BeautifulSoup) -> list[str]:
    """
    Mengambil seluruh @type dari blok JSON-LD.
    """
    types: set[str] = set()

    for tag in soup.find_all(
        "script",
        attrs={"type": re.compile(r"application/ld\+json", re.I)},
    ):
        raw = tag.string or tag.get_text() or ""

        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, AttributeError):
            continue

        for entry in flatten_jsonld(data):
            schema_type = entry.get("@type")

            if isinstance(schema_type, str):
                types.add(schema_type)
            elif isinstance(schema_type, list):
                types.update(
                    str(item) for item in schema_type
                )

    # Microdata masih dipakai sebagian template lama.
    for tag in soup.find_all(attrs={"itemtype": True}):
        itemtype = str(tag.get("itemtype", ""))

        if "schema.org/" in itemtype:
            types.add(itemtype.rsplit("/", 1)[-1])

    return sorted(types)


def flatten_jsonld(data) -> list[dict]:
    """
    Meratakan struktur JSON-LD yang bisa berupa list, @graph,
    atau objek bersarang.
    """
    found: list[dict] = []

    if isinstance(data, list):
        for item in data:
            found.extend(flatten_jsonld(item))

        return found

    if not isinstance(data, dict):
        return found

    found.append(data)

    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in data:
            found.extend(flatten_jsonld(data[key]))

    return found


def detect_faq(soup: BeautifulSoup) -> dict:
    """
    Mendeteksi blok FAQ, baik lewat schema maupun pola heading.
    """
    schema_types = collect_schema_types(soup)
    has_faq_schema = any(
        "FAQ" in item or "Question" in item
        for item in schema_types
    )

    question_headings = []

    for tag in soup.find_all(["h2", "h3", "h4", "summary", "dt"]):
        text = tag.get_text(" ", strip=True)

        if not text or len(text) > 160:
            continue

        if "?" in text or FAQ_QUESTION_PATTERN.search(text):
            question_headings.append(re.sub(r"\s+", " ", text))

    return {
        "has_faq_schema": has_faq_schema,
        "question_count": len(question_headings),
        "questions": question_headings[:15],
        "has_faq": has_faq_schema or len(question_headings) >= 3,
    }


def detect_amp(
    soup: BeautifulSoup,
    html: str,
) -> dict:
    """
    Mengecek apakah halaman ini AMP, atau punya versi AMP terpisah.
    """
    amp_link = soup.find(
        "link",
        rel=lambda value: value and "amphtml" in value,
    )

    html_tag = soup.find("html")
    is_amp = False

    if html_tag is not None:
        attrs = {key.lower() for key in html_tag.attrs}
        is_amp = bool(attrs & {"amp", "⚡"})

    if not is_amp:
        is_amp = bool(
            re.search(
                r"<html[^>]*\s(amp|⚡)[\s>]",
                html[:2000],
                re.IGNORECASE,
            )
        )

    return {
        "is_amp": is_amp,
        "has_amp_version": amp_link is not None,
        "amp_url": (
            amp_link.get("href", "") if amp_link else ""
        ),
    }


def extract_signals(
    html: str,
    final_url: str,
) -> dict:
    """
    Mengumpulkan seluruh sinyal teknis dari satu halaman.
    """
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    lists = soup.find_all(["ul", "ol"])

    list_items = sum(
        len(tag.find_all("li", recursive=False))
        for tag in lists
    )

    faq = detect_faq(soup)
    amp = detect_amp(soup, html)

    viewport = soup.find(
        "meta",
        attrs={"name": re.compile(r"^viewport$", re.I)},
    )

    open_graph = [
        str(tag.get("property", ""))
        for tag in soup.find_all(
            "meta",
            attrs={"property": re.compile(r"^og:", re.I)},
        )
    ]

    return {
        "schema_types": collect_schema_types(soup),
        "faq": faq,
        "amp": amp,
        "table_count": len(tables),
        "list_count": len(lists),
        "list_item_count": list_items,
        "has_viewport": viewport is not None,
        "open_graph_count": len(open_graph),
        "html_bytes": len(html.encode("utf-8")),
        "script_count": len(soup.find_all("script")),
        "inline_style_bytes": sum(
            len((tag.string or "").encode("utf-8"))
            for tag in soup.find_all("style")
        ),
        "final_url": final_url,
    }
