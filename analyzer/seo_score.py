import json
from pathlib import Path


def load_rules(rules_file: Path) -> dict:
    if not rules_file.exists():
        raise FileNotFoundError(
            f"File aturan tidak ditemukan: {rules_file}"
        )

    with rules_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def analyze_seo(
    page: dict,
    rules: dict,
) -> dict:
    score = 100
    problems = []
    recommendations = []

    title = page["title"]
    title_length = page["title_length"]
    title_rules = rules["title"]

    if not title:
        score -= title_rules["penalty_missing"]
        problems.append("Title tidak ditemukan")
        recommendations.append(
            "Tambahkan title yang menjelaskan topik utama halaman."
        )
    elif not (
        title_rules["min"]
        <= title_length
        <= title_rules["max"]
    ):
        score -= title_rules["penalty_length"]
        problems.append(
            f"Panjang title {title_length} karakter"
        )
        recommendations.append(
            f"Gunakan title sekitar "
            f"{title_rules['min']}–{title_rules['max']} karakter."
        )

    meta = page["meta_description"]
    meta_length = page["meta_description_length"]
    meta_rules = rules["meta_description"]

    if not meta:
        score -= meta_rules["penalty_missing"]
        problems.append("Meta description tidak ditemukan")
        recommendations.append(
            "Tambahkan meta description yang relevan."
        )
    elif not (
        meta_rules["min"]
        <= meta_length
        <= meta_rules["max"]
    ):
        score -= meta_rules["penalty_length"]
        problems.append(
            f"Panjang meta description {meta_length} karakter"
        )
        recommendations.append(
            f"Gunakan meta description sekitar "
            f"{meta_rules['min']}–{meta_rules['max']} karakter."
        )

    h1_count = page["headings"]["h1_count"]
    h1_rules = rules["h1"]

    if h1_count == 0:
        score -= h1_rules["penalty_missing"]
        problems.append("H1 tidak ditemukan")
        recommendations.append(
            "Tambahkan satu H1 utama."
        )
    elif h1_count > h1_rules["ideal_count"]:
        score -= h1_rules["penalty_multiple"]
        problems.append(
            f"Ditemukan {h1_count} H1"
        )
        recommendations.append(
            "Pastikan struktur heading memiliki fokus utama yang jelas."
        )

    word_count = page["word_count"]
    content_rules = rules["content"]

    if word_count < content_rules["minimum_words"]:
        score -= content_rules["penalty_thin"]
        problems.append(
            f"Konten hanya sekitar {word_count} kata"
        )
        recommendations.append(
            "Tambahkan informasi yang benar-benar berguna bagi pengguna."
        )

    images_without_alt = page["images"]["without_alt_count"]

    if images_without_alt:
        image_penalty = min(
            images_without_alt,
            rules["images"]["maximum_penalty"],
        )

        score -= image_penalty
        problems.append(
            f"{images_without_alt} gambar tidak memiliki alt text"
        )
        recommendations.append(
            "Tambahkan alt text deskriptif pada gambar penting."
        )

    internal_count = page["links"]["internal_count"]
    internal_rules = rules["internal_links"]

    if internal_count < internal_rules["minimum"]:
        score -= internal_rules["penalty_missing"]
        problems.append("Internal link tidak ditemukan")
        recommendations.append(
            "Tambahkan internal link menuju halaman yang relevan."
        )

    if not page["canonical"]:
        score -= rules["canonical"]["penalty_missing"]
        problems.append("Canonical tidak ditemukan")
        recommendations.append(
            "Tambahkan canonical jika halaman berpotensi memiliki URL duplikat."
        )

    if "noindex" in page["robots_meta"].lower():
        score -= rules["noindex"]["penalty"]
        problems.append("Halaman menggunakan noindex")
        recommendations.append(
            "Periksa apakah noindex memang disengaja."
        )

    return {
        "seo_score": max(score, 0),
        "problems": problems,
        "recommendations": recommendations,
    }