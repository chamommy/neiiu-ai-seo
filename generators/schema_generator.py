"""
Pembuat structured data JSON-LD.

Schema yang dipasang mengikuti apa yang dipakai halaman yang
sedang ngerank, ditambah FAQPage kalau halaman punya blok FAQ.
JSON-LD diizinkan di halaman AMP, jadi blok yang sama dipakai di
kedua versi.
"""

import json
from datetime import datetime


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
                "name": "Beranda",
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
        "inLanguage": "id-ID",
        "datePublished": published_at,
        "dateModified": published_at,
        "keywords": ", ".join(plan.get("keywords", [])),
        "isPartOf": {
            "@type": "WebSite",
            "@id": brand["base_url"] + "#website",
            "url": brand["base_url"] + "/",
            "name": brand["site_name"],
            "inLanguage": "id-ID",
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
        "inLanguage": "id-ID",
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

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
