"""
Pemeriksa kualitas SEO halaman hasil generate.

Halaman baru diukur terhadap blueprint SERP, bukan terhadap
patokan umum. Standar "cukup panjang" untuk satu keyword bisa
jauh berbeda dari keyword lain, jadi acuannya diambil dari
halaman yang sedang menang di keyword itu sendiri.
"""

import re

from parser.html_parser import parse_html


def check_length(
    label: str,
    value: int,
    minimum: int,
    maximum: int,
    problems: list[str],
) -> None:
    if value < minimum:
        problems.append(
            f"{label} terlalu pendek ({value}, minimal {minimum})."
        )
    elif value > maximum:
        problems.append(
            f"{label} terlalu panjang ({value}, maksimal {maximum})."
        )


def validate_page(
    html: str,
    keyword: str,
    blueprint: dict,
    page_url: str,
) -> dict:
    """
    Membandingkan halaman hasil generate dengan target SERP.
    """
    page = parse_html(html, page_url)
    target = blueprint["target"]

    problems: list[str] = []
    passed: list[str] = []

    keyword_lower = keyword.lower()

    check_length(
        "Title",
        page["title_length"],
        30,
        62,
        problems,
    )

    check_length(
        "Meta description",
        page["meta_description_length"],
        120,
        165,
        problems,
    )

    if keyword_lower in page["title"].lower():
        passed.append("Keyword ada di title.")
    else:
        problems.append("Keyword tidak ada di title.")

    if keyword_lower in page["meta_description"].lower():
        passed.append("Keyword ada di meta description.")
    else:
        problems.append("Keyword tidak ada di meta description.")

    h1_count = page["headings"]["h1_count"]

    if h1_count == 1:
        passed.append("Jumlah H1 tepat satu.")
    else:
        problems.append(
            f"Jumlah H1 harus satu, saat ini {h1_count}."
        )

    h1_text = " ".join(page["headings"]["h1"]).lower()

    if keyword_lower in h1_text:
        passed.append("Keyword ada di H1.")
    else:
        problems.append("Keyword tidak ada di H1.")

    word_target = int(
        max(
            target["word_count_top5_median"],
            target["word_count_median"],
        )
    )

    word_count = page["word_count"]

    if word_target and word_count < word_target * 0.8:
        problems.append(
            f"Konten {word_count} kata, target halaman pertama "
            f"sekitar {word_target} kata."
        )
    else:
        passed.append(
            f"Panjang konten {word_count} kata, "
            f"sesuai target {word_target} kata."
        )

    h2_target = int(target["h2_median"])
    h2_count = page["headings"]["h2_count"]

    if h2_target and h2_count < h2_target:
        problems.append(
            f"Jumlah H2 {h2_count}, kompetitor rata-rata {h2_target}."
        )
    else:
        passed.append(f"Jumlah H2 {h2_count}, sudah memadai.")

    text_lower = page["visible_text"].lower()
    keyword_count = text_lower.count(keyword_lower)

    density = (
        round(
            keyword_count
            * len(keyword_lower.split())
            / max(word_count, 1)
            * 100,
            2,
        )
    )

    if density > 3:
        problems.append(
            f"Keyword density {density}%, terlalu padat."
        )
    elif density < 0.5:
        problems.append(
            f"Keyword density {density}%, terlalu tipis."
        )
    else:
        passed.append(f"Keyword density {density}%, wajar.")

    if page["canonical"]:
        passed.append("Canonical terpasang.")
    else:
        problems.append("Canonical belum terpasang.")

    if re.search(
        r'<link[^>]+rel=["\']amphtml["\']',
        html,
        re.IGNORECASE,
    ):
        passed.append("Link ke versi AMP terpasang.")
    else:
        problems.append("Link rel=amphtml belum terpasang.")

    if "application/ld+json" in html:
        passed.append("Structured data JSON-LD terpasang.")
    else:
        problems.append("Structured data belum terpasang.")

    if '"FAQPage"' in html:
        passed.append("Schema FAQPage terpasang.")
    else:
        problems.append("Schema FAQPage belum terpasang.")

    score = round(
        len(passed) / max(len(passed) + len(problems), 1) * 100
    )

    return {
        "score": score,
        "word_count": word_count,
        "word_target": word_target,
        "keyword_density": density,
        "title_length": page["title_length"],
        "meta_length": page["meta_description_length"],
        "h2_count": h2_count,
        "passed": passed,
        "problems": problems,
    }
