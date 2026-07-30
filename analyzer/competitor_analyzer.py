def safe_number(value, default=0):
    """
    Mengubah value jadi angka dengan aman.
    """
    if isinstance(value, (int, float)):
        return value

    return default


def get_entity_coverage(report: dict) -> float:
    entity = report.get("entity", {})

    return safe_number(
        entity.get("coverage_percentage", 0)
    )


def get_heading_score(report: dict) -> float:
    heading = report.get("heading_analysis", {})

    return safe_number(
        heading.get("heading_score", 0)
    )


def get_word_count(report: dict) -> int:
    content = report.get("content", {})

    return int(
        safe_number(
            content.get("word_count", 0)
        )
    )


def get_keyword_density(report: dict) -> float:
    content = report.get("content", {})

    return safe_number(
        content.get("keyword_density", 0)
    )


def get_internal_links(report: dict) -> int:
    page = report.get("page", {})
    links = page.get("links", {})

    return int(
        safe_number(
            links.get("internal_count", 0)
        )
    )


def compare_reports(
    your_report: dict,
    competitor_report: dict,
) -> dict:
    """
    Membandingkan dua report audit SEO.
    """

    your_metrics = {
        "seo_score": safe_number(
            your_report.get("seo_score", 0)
        ),
        "word_count": get_word_count(your_report),
        "heading_score": get_heading_score(your_report),
        "entity_coverage": get_entity_coverage(your_report),
        "keyword_density": get_keyword_density(your_report),
        "internal_links": get_internal_links(your_report),
    }

    competitor_metrics = {
        "seo_score": safe_number(
            competitor_report.get("seo_score", 0)
        ),
        "word_count": get_word_count(competitor_report),
        "heading_score": get_heading_score(
            competitor_report
        ),
        "entity_coverage": get_entity_coverage(
            competitor_report
        ),
        "keyword_density": get_keyword_density(
            competitor_report
        ),
        "internal_links": get_internal_links(
            competitor_report
        ),
    }

    differences = {
        key: round(
            competitor_metrics[key] - your_metrics[key],
            2,
        )
        for key in your_metrics
    }

    your_total = (
        your_metrics["seo_score"]
        + your_metrics["heading_score"]
        + your_metrics["entity_coverage"]
    )

    competitor_total = (
        competitor_metrics["seo_score"]
        + competitor_metrics["heading_score"]
        + competitor_metrics["entity_coverage"]
    )

    if your_total > competitor_total:
        winner = "your_website"
    elif competitor_total > your_total:
        winner = "competitor"
    else:
        winner = "tie"

    recommendations = []

    if differences["word_count"] > 0:
        recommendations.append(
            f"Kompetitor memiliki sekitar "
            f"{int(differences['word_count'])} kata lebih banyak."
        )

    if differences["heading_score"] > 0:
        recommendations.append(
            "Struktur heading kompetitor lebih baik."
        )

    if differences["entity_coverage"] > 0:
        recommendations.append(
            f"Entity coverage kompetitor lebih tinggi "
            f"{differences['entity_coverage']}%."
        )

    if differences["internal_links"] > 0:
        recommendations.append(
            f"Kompetitor memiliki "
            f"{int(differences['internal_links'])} "
            f"internal link lebih banyak."
        )

    if differences["seo_score"] > 0:
        recommendations.append(
            f"SEO score kompetitor lebih tinggi "
            f"{differences['seo_score']} poin."
        )

    if not recommendations:
        recommendations.append(
            "Website lu tidak tertinggal pada metrik utama yang dibandingkan."
        )

    return {
        "your_url": your_report.get("final_url"),
        "competitor_url": competitor_report.get("final_url"),
        "your_metrics": your_metrics,
        "competitor_metrics": competitor_metrics,
        "differences": differences,
        "winner": winner,
        "recommendations": recommendations,
    }