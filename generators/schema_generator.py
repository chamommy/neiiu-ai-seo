"""
Pembuat structured data JSON-LD.

Schema yang dipasang mengikuti apa yang dipakai halaman yang
sedang ngerank, ditambah FAQPage kalau halaman punya blok FAQ.
JSON-LD diizinkan di halaman AMP, jadi blok yang sama dipakai di
kedua versi.
"""

import json
from datetime import datetime

from generators.page_text import text_of


def language_tag(brand: dict) -> str:
    """
    Kode bahasa untuk schema.org, misalnya id-ID atau th-TH.

    Diambil dari locale yang sudah ditentukan zona, dengan garis
    bawah diganti tanda hubung sesuai bentuk BCP 47.
    """
    return str(brand.get("locale", "id_ID")).replace("_", "-")


def build_faq_schema(faq: list[dict]) -> dict | None:
    """
    Schema FAQPage dari daftar tanya jawab.
    """
    if not faq:
        return None

    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"],
                },
            }
            for item in faq
        ],
    }


def build_breadcrumb_schema(
    brand: dict,
    plan: dict,
    page_url: str,
) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": text_of(brand)["home"],
                "item": brand["base_url"] + "/",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": plan["h1"],
                "item": page_url,
            },
        ],
    }


def build_webpage_schema(
    brand: dict,
    plan: dict,
    page_url: str,
    published_at: str,
) -> dict:
    return {
        "@type": "WebPage",
        "@id": page_url + "#webpage",
        "url": page_url,
        "name": plan["title"],
        "description": plan["meta_description"],
        "inLanguage": language_tag(brand),
        "datePublished": published_at,
        "dateModified": published_at,
        "keywords": ", ".join(plan.get("keywords", [])),
        "isPartOf": {
            "@type": "WebSite",
            "@id": brand["base_url"] + "#website",
            "url": brand["base_url"] + "/",
            "name": brand["site_name"],
            "inLanguage": language_tag(brand),
        },
        "publisher": {
            "@type": "Organization",
            "@id": brand["base_url"] + "#organization",
            "name": brand["site_name"],
            "url": brand["base_url"] + "/",
        },
    }


def build_article_schema(
    brand: dict,
    plan: dict,
    page_url: str,
    published_at: str,
) -> dict:
    return {
        "@type": "Article",
        "headline": plan["h1"][:110],
        "description": plan["meta_description"],
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": page_url + "#webpage",
        },
        "inLanguage": language_tag(brand),
        "datePublished": published_at,
        "dateModified": published_at,
        "author": {
            "@type": "Organization",
            "name": brand["site_name"],
        },
        "publisher": {
            "@type": "Organization",
            "@id": brand["base_url"] + "#organization",
            "name": brand["site_name"],
        },
    }


def build_schema_graph(
    plan: dict,
    brand: dict,
    page_url: str,
    include_article: bool = True,
) -> str:
    """
    Menyusun seluruh JSON-LD jadi satu blok @graph.
    """
    published_at = datetime.now().isoformat(timespec="seconds")

    graph = [
        build_webpage_schema(brand, plan, page_url, published_at),
        build_breadcrumb_schema(brand, plan, page_url),
    ]

    if include_article:
        graph.append(
            build_article_schema(
                brand,
                plan,
                page_url,
                published_at,
            )
        )

    faq_schema = build_faq_schema(plan.get("faq", []))

    if faq_schema is not None:
        graph.append(faq_schema)

    payload = {
        "@context": "https://schema.org",
        "@graph": graph,
    }

    return json_for_html(payload)


def json_for_html(payload: dict) -> str:
    """
    Menyerialisasi JSON untuk ditempel ke dalam <script> di HTML.

    json.dumps saja tidak aman di sini. Blok <script> diakhiri oleh
    pengurai HTML begitu menemukan teks "</script>", di mana pun
    letaknya, termasuk di tengah string JSON. Judul atau nama brand
    yang memuat teks itu akan menutup blok lebih awal dan sisanya
    diperlakukan sebagai HTML biasa, sehingga tag apa pun yang
    menyusul ikut hidup di halaman hasil.

    Menuliskan kurung siku dan ampersand sebagai escape \\u kembali
    menghasilkan karakter yang sama saat JSON diurai, jadi arti
    datanya tidak berubah sedikit pun, tapi tidak ada lagi urutan
    huruf yang bisa dibaca sebagai tag oleh pengurai HTML.
    """
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        # Pemisah baris Unicode ini sah di JSON tapi memutus string
        # di JavaScript, jadi ikut dinetralkan.
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
