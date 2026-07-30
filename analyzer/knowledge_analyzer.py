def safe_number(value, default=0):
    if isinstance(value, (int, float)):
        return value

    return default


def analyze_knowledge_gap(
    report_data: dict,
    topic_knowledge: dict,
) -> dict:
    ideal = topic_knowledge.get("ideal", {})
    must_have = topic_knowledge.get("must_have", [])

    content = report_data.get("content", {})
    heading = report_data.get("heading_analysis", {})
    entity = report_data.get("entity", {})
    page = report_data.get("page", {})

    links = page.get("links", {})

    current = {
        "word_count": safe_number(
            content.get("word_count", 0)
        ),
        "h1": safe_number(
            heading.get("h1_count", 0)
        ),
        "h2": safe_number(
            heading.get("h2_count", 0)
        ),
        "h3": safe_number(
            heading.get("h3_count", 0)
        ),
        "keyword_density": safe_number(
            content.get("keyword_density", 0)
        ),
        "entity_coverage": safe_number(
            entity.get("coverage_percentage", 0)
        ),
        "internal_links": safe_number(
            links.get("internal_count", 0)
        ),
    }

    gaps = {}
    problems = []
    recommendations = []

    ideal_word_count = safe_number(
        ideal.get("word_count", 0)
    )

    if ideal_word_count:
        word_gap = ideal_word_count - current["word_count"]
        gaps["word_count"] = max(word_gap, 0)

        if word_gap > 0:
            problems.append(
                f"Konten kurang sekitar {word_gap} kata "
                "dibanding standar ideal."
            )
            recommendations.append(
                f"Tambahkan sekitar {word_gap} kata yang relevan, "
                "bukan sekadar memperpanjang konten."
            )

    ideal_h1 = safe_number(
        ideal.get("h1", 1)
    )

    gaps["h1"] = ideal_h1 - current["h1"]

    if current["h1"] != ideal_h1:
        problems.append(
            f"Jumlah H1 saat ini {current['h1']}, "
            f"idealnya {ideal_h1}."
        )
        recommendations.append(
            "Gunakan satu H1 utama yang jelas."
        )

    ideal_h2 = safe_number(
        ideal.get("h2", 0)
    )

    if ideal_h2:
        h2_gap = ideal_h2 - current["h2"]
        gaps["h2"] = max(h2_gap, 0)

        if h2_gap > 0:
            problems.append(
                f"Masih kurang sekitar {h2_gap} H2."
            )
            recommendations.append(
                f"Tambahkan sekitar {h2_gap} H2 untuk "
                "membagi subtopik penting."
            )

    ideal_h3 = safe_number(
        ideal.get("h3", 0)
    )

    if ideal_h3:
        h3_gap = ideal_h3 - current["h3"]
        gaps["h3"] = max(h3_gap, 0)

        if h3_gap > 0:
            problems.append(
                f"Masih kurang sekitar {h3_gap} H3."
            )
            recommendations.append(
                "Gunakan H3 untuk menjelaskan rincian "
                "di bawah bagian H2 yang relevan."
            )

    density_min = safe_number(
        ideal.get("keyword_density_min", 0)
    )

    density_max = safe_number(
        ideal.get("keyword_density_max", 100)
    )

    keyword_density = current["keyword_density"]

    gaps["keyword_density"] = {
        "current": keyword_density,
        "minimum": density_min,
        "maximum": density_max,
    }

    if keyword_density < density_min:
        problems.append(
            "Keyword density berada di bawah rentang knowledge."
        )
        recommendations.append(
            "Tambahkan keyword atau variasinya secara natural."
        )

    elif keyword_density > density_max:
        problems.append(
            "Keyword density berada di atas rentang knowledge."
        )
        recommendations.append(
            "Kurangi pengulangan keyword agar konten tetap natural."
        )

    ideal_entity = safe_number(
        ideal.get("entity_coverage", 0)
    )

    if ideal_entity:
        entity_gap = (
            ideal_entity
            - current["entity_coverage"]
        )

        gaps["entity_coverage"] = max(
            entity_gap,
            0,
        )

        if entity_gap > 0:
            problems.append(
                f"Entity coverage masih kurang "
                f"{round(entity_gap, 2)}%."
            )
            recommendations.append(
                "Tambahkan entity yang benar-benar relevan "
                "dengan pembahasan."
            )

    ideal_internal_links = safe_number(
        ideal.get("internal_links", 0)
    )

    if ideal_internal_links:
        internal_gap = (
            ideal_internal_links
            - current["internal_links"]
        )

        gaps["internal_links"] = max(
            internal_gap,
            0,
        )

        if internal_gap > 0:
            problems.append(
                f"Masih kurang sekitar "
                f"{internal_gap} internal link."
            )
            recommendations.append(
                "Tambahkan internal link ke halaman relevan."
            )

    detected_features = {
        "canonical": bool(
            page.get("canonical")
        ),
        "internal link": (
            current["internal_links"] > 0
        ),
        "faq": False,
        "schema": False,
        "robots": bool(
            page.get("robots_meta")
        ),
    }

    missing_must_have = []

    for feature in must_have:
        normalized_feature = feature.lower()

        if not detected_features.get(
            normalized_feature,
            False,
        ):
            missing_must_have.append(feature)

    if missing_must_have:
        problems.append(
            "Beberapa elemen penting belum terdeteksi: "
            + ", ".join(missing_must_have)
        )
        recommendations.append(
            "Periksa dan tambahkan elemen penting "
            "yang memang relevan dengan halaman."
        )

    return {
        "current_metrics": current,
        "ideal_metrics": ideal,
        "gaps": gaps,
        "must_have": must_have,
        "missing_must_have": missing_must_have,
        "problems": problems,
        "recommendations": recommendations,
    }