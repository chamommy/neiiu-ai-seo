def recommend_content(
    content: dict,
) -> dict:
    problems = []
    recommendations = []

    keyword_density = content["keyword_density"]
    paragraph_count = content["paragraph_count"]
    average_paragraph = content["average_paragraph_length"]
    longest_paragraph = content["longest_paragraph_length"]

    if not content["keyword_in_title"]:
        problems.append("Keyword belum ditemukan di title")
        recommendations.append(
            "Tambahkan keyword utama ke title secara natural."
        )

    if not content["keyword_in_meta"]:
        problems.append("Keyword belum ditemukan di meta description")
        recommendations.append(
            "Tambahkan keyword utama ke meta description."
        )

    if not content["keyword_in_h1"]:
        problems.append("Keyword belum ditemukan di H1")
        recommendations.append(
            "Tambahkan keyword utama ke H1 secara natural."
        )

    if keyword_density == 0:
        problems.append("Keyword tidak ditemukan di konten")
        recommendations.append(
            "Gunakan keyword utama di beberapa bagian penting."
        )
    elif keyword_density < 0.3:
        problems.append("Keyword density cukup rendah")
        recommendations.append(
            "Tambahkan keyword secara natural tanpa memaksakan."
        )
    elif keyword_density > 3:
        problems.append("Keyword density cukup tinggi")
        recommendations.append(
            "Kurangi pengulangan keyword agar konten tetap natural."
        )

    if paragraph_count == 0:
        problems.append("Paragraf tidak ditemukan")
        recommendations.append(
            "Pisahkan konten menjadi paragraf yang jelas."
        )

    if average_paragraph > 80:
        problems.append("Rata-rata paragraf terlalu panjang")
        recommendations.append(
            "Pecah paragraf panjang agar lebih mudah dibaca."
        )

    if longest_paragraph > 150:
        problems.append("Ada paragraf yang sangat panjang")
        recommendations.append(
            "Pecah paragraf terpanjang menjadi beberapa bagian."
        )

    return {
        "problems": problems,
        "recommendations": recommendations,
    }