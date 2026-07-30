def analyze_headings(
    page: dict,
    keyword: str,
) -> dict:
    headings = page.get("headings", {})

    h1_list = headings.get("h1", [])
    h2_list = headings.get("h2", [])
    h3_list = headings.get("h3", [])

    h1_count = len(h1_list)
    h2_count = len(h2_list)
    h3_count = len(h3_list)

    keyword = keyword.strip().lower()

    score = 100
    problems = []
    recommendations = []

    keyword_in_h1 = any(
        keyword in heading.lower()
        for heading in h1_list
    )

    keyword_in_h2 = any(
        keyword in heading.lower()
        for heading in h2_list
    )

    keyword_in_h3 = any(
        keyword in heading.lower()
        for heading in h3_list
    )

    empty_headings = []

    for level, heading_list in {
        "H1": h1_list,
        "H2": h2_list,
        "H3": h3_list,
    }.items():
        for index, heading in enumerate(
            heading_list,
            start=1,
        ):
            if not heading.strip():
                empty_headings.append(
                    f"{level} nomor {index}"
                )

    duplicate_headings = []

    all_headings = (
        h1_list
        + h2_list
        + h3_list
    )

    normalized_headings = [
        heading.strip().lower()
        for heading in all_headings
        if heading.strip()
    ]

    seen = set()

    for heading in normalized_headings:
        if heading in seen:
            duplicate_headings.append(heading)
        else:
            seen.add(heading)

    duplicate_headings = sorted(
        set(duplicate_headings)
    )

    if h1_count == 0:
        score -= 25
        problems.append("H1 tidak ditemukan")
        recommendations.append(
            "Tambahkan satu H1 utama yang menjelaskan topik halaman."
        )

    elif h1_count > 1:
        score -= 15
        problems.append(
            f"Ditemukan {h1_count} H1"
        )
        recommendations.append(
            "Gunakan satu H1 utama agar struktur halaman lebih jelas."
        )

    if h2_count == 0:
        score -= 20
        problems.append("H2 tidak ditemukan")
        recommendations.append(
            "Tambahkan H2 untuk membagi topik utama menjadi beberapa bagian."
        )

    elif h2_count < 3:
        score -= 8
        problems.append(
            f"Jumlah H2 hanya {h2_count}"
        )
        recommendations.append(
            "Pertimbangkan menambah H2 jika konten membahas beberapa subtopik."
        )

    if h3_count > 0 and h2_count == 0:
        score -= 10
        problems.append(
            "H3 ditemukan, tetapi tidak ada H2"
        )
        recommendations.append(
            "Pastikan H3 berada di bawah bagian H2 yang relevan."
        )

    if not keyword_in_h1:
        score -= 10
        problems.append(
            "Keyword utama tidak ditemukan di H1"
        )
        recommendations.append(
            "Tambahkan keyword utama ke H1 secara natural jika relevan."
        )

    if h2_count > 0 and not keyword_in_h2:
        score -= 5
        problems.append(
            "Keyword utama tidak ditemukan di H2"
        )
        recommendations.append(
            "Gunakan keyword atau variasinya pada salah satu H2 secara natural."
        )

    if empty_headings:
        score -= min(
            10,
            len(empty_headings) * 2,
        )
        problems.append(
            f"Ditemukan {len(empty_headings)} heading kosong"
        )
        recommendations.append(
            "Hapus heading kosong atau isi dengan teks yang jelas."
        )

    if duplicate_headings:
        score -= min(
            10,
            len(duplicate_headings) * 2,
        )
        problems.append(
            f"Ditemukan {len(duplicate_headings)} heading duplikat"
        )
        recommendations.append(
            "Buat setiap heading lebih unik dan sesuai dengan isi bagiannya."
        )

    return {
        "heading_score": max(score, 0),
        "h1_count": h1_count,
        "h2_count": h2_count,
        "h3_count": h3_count,
        "h1": h1_list,
        "h2": h2_list,
        "h3": h3_list,
        "keyword_in_h1": keyword_in_h1,
        "keyword_in_h2": keyword_in_h2,
        "keyword_in_h3": keyword_in_h3,
        "empty_headings": empty_headings,
        "duplicate_headings": duplicate_headings,
        "problems": problems,
        "recommendations": recommendations,
    }