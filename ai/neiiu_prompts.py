"""
Prompt untuk pipeline NEIIU: analisis SERP dan rencana konten.

Prompt di sini sengaja memadatkan data hasil crawl jadi angka dan
daftar pendek. Model lokal punya jendela konteks terbatas, jadi
memberi ringkasan terstruktur jauh lebih akurat daripada
menempelkan seluruh isi halaman kompetitor.
"""


SERP_ANALYST_SYSTEM_PROMPT = """
Kamu adalah analis SEO yang membaca data halaman pertama Google.

Aturan:
- Gunakan hanya data crawl yang diberikan.
- Jangan mengarang metrik, backlink, atau otoritas domain.
- Jelaskan alasan ranking dari bukti yang terlihat di data.
- Kalau data tidak cukup untuk satu posisi, katakan apa adanya.
- Jangan menjanjikan ranking.
- Gunakan bahasa Indonesia yang jelas dan padat.
- Berikan hanya hasil akhir, tanpa proses berpikir.
- Ikuti JSON Schema yang diberikan sistem.
""".strip()


# Instruksi bahasa ditulis dua kali: sekali dalam bahasa Indonesia
# supaya konsisten dengan aturan lain, sekali dalam bahasa
# sasarannya sendiri. Model kecil cenderung menjawab dalam bahasa
# yang dipakai promptnya, dan satu baris perintah di tengah prompt
# berbahasa Indonesia sering kalah oleh kecenderungan itu.
LANGUAGE_ORDERS = {
    "id": "Tulis seluruh isi halaman dalam bahasa Indonesia.",
    "th": (
        "Tulis SELURUH isi halaman dalam bahasa Thai, memakai aksara "
        "Thai. Jangan memakai bahasa Indonesia atau Inggris untuk "
        "judul, paragraf, FAQ, maupun bagian lain.\n"
        "เขียนเนื้อหาทั้งหมดเป็นภาษาไทยโดยใช้อักษรไทยเท่านั้น "
        "ห้ามใช้ภาษาอินโดนีเซียหรือภาษาอังกฤษ"
    ),
}


def content_planner_system_prompt(language_code: str = "id") -> str:
    """
    System prompt penyusun konten, dengan bahasa sasaran ditegaskan.
    """
    order = LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])

    return f"""
Kamu adalah content strategist SEO yang menyusun landing page baru.

Aturan:
- Tulis konten orisinal. Jangan menyalin kalimat kompetitor.
- Ikuti target struktur dan panjang yang diberikan.
- Masukkan keyword utama secara wajar, jangan menumpuk.
- Setiap paragraf harus berisi informasi konkret, bukan basa-basi.
- Heading harus deskriptif dan menjawab kebutuhan pencari.
- Jangan memakai placeholder seperti "lorem ipsum" atau "xxx".
- Jangan menjanjikan hasil, keuntungan, atau kemenangan.
- Berikan hanya hasil akhir, tanpa proses berpikir.
- Ikuti JSON Schema yang diberikan sistem.

BAHASA (paling penting):
{order}
""".strip()


def format_list(
    items: list,
    limit: int = 10,
    empty: str = "- Tidak ada",
) -> str:
    clean = [
        str(item).strip()
        for item in items
        if str(item).strip()
    ]

    if not clean:
        return empty

    return "\n".join(f"- {item}" for item in clean[:limit])


def format_competitor_table(pages: list[dict]) -> str:
    """
    Membuat ringkasan satu baris per kompetitor.
    """
    lines: list[str] = []

    for page in pages:
        if page["status"] != "ok":
            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— gagal di-crawl ({page['error']})"
            )
            continue

        hijack = page.get("hijack", {})

        if not page.get("usable", True) and not hijack.get("is_hijacked"):
            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— ISI TIDAK TERBACA (hanya {page['word_count']} kata "
                "sampai ke crawler, konten yang diindeks Google tidak "
                "dilayani ke kita)"
            )
            continue

        if hijack.get("is_hijacked"):
            cloaking = page.get("cloak", {}).get("cloaking")

            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— DOMAIN BAJAKAN (keyakinan {hijack['confidence']}%)"
                + (", terbukti cloaking" if cloaking else "")
                + "\n    "
                + "; ".join(hijack.get("reasons", [])[:2])
            )
            continue

        signals = page["signals"]
        headings = page["headings"]

        lines.append(
            f"[{page['position']}] {page['domain']}\n"
            f"    title ({page['title_length']} char): "
            f"{page['title'][:90]}\n"
            f"    kata: {page['word_count']} | "
            f"H2: {headings['h2_count']} | "
            f"H3: {headings['h3_count']} | "
            f"internal link: {page['links']['internal_count']} | "
            f"gambar: {page['images']['total']}\n"
            f"    density keyword: "
            f"{page['content']['keyword_density']}% | "
            f"keyword di title: "
            f"{page['content']['keyword_in_title']} | "
            f"di H1: {page['content']['keyword_in_h1']}\n"
            f"    FAQ: {signals['faq']['has_faq']} | "
            f"AMP: {signals['amp']['is_amp'] or signals['amp']['has_amp_version']} | "
            f"tabel: {signals['table_count']} | "
            f"schema: {', '.join(signals['schema_types'][:5]) or 'tidak ada'}\n"
            f"    entity coverage: "
            f"{page['entity'].get('coverage_percentage', 0)}% | "
            f"skor SEO: {page['seo_score']}/100"
        )

    return "\n".join(lines) if lines else "- Tidak ada data"


def build_serp_insight_prompt(
    analysis: dict,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk menjelaskan kenapa rank 1–10 bisa naik.
    """
    keyword = analysis["keyword"]
    pages = analysis["pages"]
    blueprint = analysis["blueprint"]
    target = blueprint["target"]
    adoption = blueprint["adoption"]

    schema_text = format_list(
        [
            f"{item['type']} (dipakai {item['domain_count']} domain)"
            for item in blueprint["common_schema_types"]
        ],
        limit=8,
    )

    topic_text = format_list(
        [
            f"{item['term']} ({item['coverage_percentage']}% domain)"
            for item in blueprint["heading_topics"]
        ],
        limit=15,
    )

    user_prompt = f"""
# DATA HALAMAN PERTAMA GOOGLE

Keyword: {keyword}
Halaman bersih yang dianalisis: {blueprint["analyzed_pages"]}
Halaman gagal di-crawl: {blueprint["failed_pages"]}
Halaman di domain bajakan: {blueprint.get("hijacked_count", 0)}
Halaman yang isinya tidak terbaca: {blueprint.get("unreadable_count", 0)}

## Detail Per Peringkat
{format_competitor_table(pages)}

## Catatan Domain Bajakan
{format_list(
    [
        f"Peringkat {item['position']} — {item['domain']} "
        f"(keyakinan {item['confidence']}%"
        + (", cloaking terdeteksi" if item["cloaking"] else "")
        + ")"
        for item in blueprint.get("hijacked_pages", [])
    ],
    limit=10,
    empty="- Tidak ada",
)}

## Median Halaman Pertama
Jumlah kata (semua): {target["word_count_median"]}
Jumlah kata (top 5): {target["word_count_top5_median"]}
Jumlah kata tertinggi: {target["word_count_max"]}
Panjang title: {target["title_length_median"]} karakter
Panjang meta: {target["meta_length_median"]} karakter
Jumlah H2: {target["h2_median"]}
Jumlah H3: {target["h3_median"]}
Internal link: {target["internal_links_median"]}
Keyword density: {target["keyword_density_median"]}%

## Tingkat Pemakaian Fitur
Punya FAQ: {adoption["faq_percentage"]}% halaman
Punya AMP: {adoption["amp_percentage"]}% halaman
Punya tabel: {adoption["table_percentage"]}% halaman

## Schema Yang Dipakai
{schema_text}

## Tema Heading Yang Sering Muncul
{topic_text}

## Pertanyaan Yang Diangkat Kompetitor
{format_list(blueprint["competitor_questions"], limit=12)}

## People Also Ask
{format_list(blueprint["people_also_ask"], limit=10)}

## Pencarian Terkait
{format_list(blueprint["related_searches"], limit=10)}

# TUGAS

1. Ringkas karakter halaman pertama untuk keyword ini.
2. Tentukan search intent yang dilayani halaman-halaman itu.
3. Untuk setiap peringkat, jelaskan kenapa halaman itu bisa naik
   berdasarkan bukti di data. Sebutkan kekuatan dan kelemahannya.
4. Sebutkan celah konten yang belum digarap kompetitor.
5. Susun strategi konkret untuk mengalahkan mereka.

Aturan tambahan:
- Halaman yang gagal di-crawl tetap dibahas, tapi katakan bahwa
  datanya tidak tersedia.
- Jangan menyebut backlink atau domain authority karena tidak
  ada di data.
- Halaman yang ditandai DOMAIN BAJAKAN ngerank karena menumpang
  otoritas domain milik institusi lain, bukan karena kualitas
  halamannya. Katakan apa adanya dan jangan menyarankan menirunya.
- Kalau sebagian besar halaman pertama adalah domain bajakan,
  sebutkan bahwa keyword ini dikuasai spam dan halaman yang
  dibangun secara wajar bersaing dengan lapangan yang tidak setara.
- Halaman berlabel ISI TIDAK TERBACA jangan dinilai kualitas
  kontennya, karena datanya memang tidak ada. Sebut saja bahwa
  isinya disembunyikan dari crawler.
- Jangan menyimpulkan target jumlah kata dari halaman yang tidak
  terbaca atau dari domain bajakan.
""".strip()

    return (
        SERP_ANALYST_SYSTEM_PROMPT,
        user_prompt,
    )


ROLE_LABELS = {
    "title": "judul halaman (tag title)",
    "meta_description": "meta description",
    "meta_keywords": "daftar keyword dipisah koma",
    "h1": "heading utama H1",
    "heading": "heading bagian",
    "paragraph": "paragraf isi artikel",
    "faq_question": "pertanyaan FAQ",
    "faq_answer": "jawaban FAQ",
    "review_text": "isi ulasan pengguna",
    "review_author": "nama orang yang menulis ulasan",
    "caption": "keterangan gambar",
}


def build_template_content_prompt(
    analysis: dict,
    insight: dict,
    spec: dict,
    brand: dict,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk mengisi template milik pengguna.

    Bedanya dengan brief biasa: di sini bentuk halamannya sudah
    ditentukan template, jadi yang diminta adalah sejumlah potongan
    teks dengan jumlah dan panjang yang persis, bukan rencana
    halaman yang bebas bentuk.
    """
    keyword = analysis["keyword"]
    blueprint = analysis["blueprint"]

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")

    kebutuhan: list[str] = []

    for role, rule in sorted(spec.items()):
        label = ROLE_LABELS.get(role, role)
        count = rule["count"]
        limit = rule["max_length"]

        if role in {"title", "meta_description", "meta_keywords", "h1"}:
            kebutuhan.append(
                f"- {role}: 1 teks, maksimal {limit} karakter ({label})"
            )
        else:
            kebutuhan.append(
                f"- {role}: tepat {count} teks, "
                f"masing-masing maksimal {limit} karakter ({label})"
            )

    user_prompt = f"""
# MENGISI TEMPLATE HALAMAN

Keyword utama: {keyword}
Nama brand: {brand_name or "-"}
Bahasa isi halaman: {language_name}
Negara sasaran: {brand.get("region_label", "Indonesia")}

{LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])}

## Yang Perlu Diketahui Dari Halaman Pertama Google
Intent pencarian: {insight.get("search_intent", "-")}
Ringkasan SERP: {insight.get("serp_summary", "-")}

Celah konten yang bisa diambil:
{format_list(insight.get("content_gaps", []), limit=6)}

Tema yang sering muncul di heading kompetitor:
{format_list(
    [item["term"] for item in blueprint["heading_topics"]],
    limit=10,
)}

Pertanyaan yang dicari orang:
{format_list(
    blueprint["people_also_ask"] + blueprint["competitor_questions"],
    limit=10,
)}

# YANG HARUS KAMU TULIS

Halamannya memakai template yang sudah jadi, jadi jumlah teksnya
tidak boleh dikira-kira. Tulis persis sebanyak ini:

{chr(10).join(kebutuhan)}

Aturan:
- Batas karakter itu keras. Teks yang lebih panjang akan merusak
  tata letak halaman, karena kolom dan kartunya sudah dipatok.
- Jangan menomori atau memberi awalan seperti "1." di setiap teks.
- Setiap teks berdiri sendiri dan langsung berisi, tanpa pembuka.
- Sebut "{brand_name}" secukupnya saja, tidak di setiap teks.
- Jangan mengarang data tentang "{brand_name}" seperti jumlah
  member, lisensi, penghargaan, atau tahun berdiri.
- Nama penulis ulasan tulis sebagai nama orang yang wajar di
  {brand.get("region_label", "Indonesia")}.
- Jangan menjanjikan hasil, keuntungan, atau kemenangan.
""".strip()

    return (
        content_planner_system_prompt(language_code),
        user_prompt,
    )


def build_content_plan_prompt(
    analysis: dict,
    insight: dict,
    template: dict,
    brand: dict,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk membuat isi landing page baru.
    """
    keyword = analysis["keyword"]
    blueprint = analysis["blueprint"]
    target = blueprint["target"]

    # Target panjang diambil dari top 5, bukan rata-rata semua,
    # supaya halaman baru mengejar yang benar-benar menang.
    word_target = int(
        max(
            target["word_count_top5_median"],
            target["word_count_median"],
            900,
        )
    )

    section_target = max(int(target["h2_median"]), 5)
    section_target = min(section_target, 9)

    structure_text = format_list(
        [
            f"{section['order']}. {section['type']} "
            f"({section['level']}, {section['subheading_count']} subheading)"
            for section in template["structure"]
        ],
        limit=12,
    )

    disclaimer_rule = (
        "- Sisipkan nada informatif dan netral, bukan ajakan berlebihan."
        if brand.get("disclaimer")
        else "- Fokus ke informasi yang berguna untuk pembaca."
    )

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")

    user_prompt = f"""
# BRIEF LANDING PAGE BARU

Keyword utama: {keyword}
Nama brand: {brand_name or "-"}
Bahasa isi halaman: {language_name}
Negara sasaran: {brand.get("region_label", "Indonesia")}

{LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])}

## Bedanya Keyword dan Brand
Keyword "{keyword}" adalah topik yang dicari orang di Google.
Brand "{brand_name}" adalah nama situs yang menyajikan halaman ini.
Keduanya berbeda dan tidak boleh dipertukarkan.

## Hasil Analisis SERP
Intent pencarian: {insight.get("search_intent", "-")}
Ringkasan SERP: {insight.get("serp_summary", "-")}

Celah konten yang bisa diambil:
{format_list(insight.get("content_gaps", []), limit=8)}

Strategi menang:
{format_list(insight.get("winning_strategy", []), limit=8)}

## Target Yang Harus Dikejar
Total kata halaman: sekitar {word_target} kata
Jumlah section (H2): {section_target} section
Panjang title: maksimal 60 karakter
Panjang meta description: 140 sampai 160 karakter
Keyword density wajar: 0.8% sampai 2%

## Struktur Halaman Acuan Yang Ngerank
Sumber acuan: {template["source_domain"]}
{structure_text}

## Tema Yang Wajib Disinggung
{format_list(
    [item["term"] for item in blueprint["heading_topics"]],
    limit=12,
)}

## Entity Yang Sering Muncul Di Kompetitor
{format_list(
    [item["entity"] for item in blueprint["common_entities"]],
    limit=12,
)}

## Pertanyaan Yang Harus Dijawab Di FAQ
{format_list(
    blueprint["people_also_ask"] + blueprint["competitor_questions"],
    limit=10,
)}

# TUGAS

Susun isi landing page lengkap:

1. title — memuat brand "{brand_name}" DAN keyword "{keyword}",
   maksimal 60 karakter. Pola yang dianjurkan:
   "{brand_name}: {keyword.title()} ..." atau
   "{keyword.title()} di {brand_name} ..."
2. meta_description — 140 sampai 160 karakter, memuat keyword dan
   sebutkan brand "{brand_name}" sekali.
3. slug — huruf kecil, dipisah tanda hubung, memuat keyword.
4. h1 — berbeda susunan kata dari title, tetap memuat keyword dan
   brand "{brand_name}".
5. intro — 2 sampai 3 paragraf pembuka yang langsung menjawab intent.
6. sections — {section_target} section. Setiap section punya:
   - heading deskriptif
   - type: paragraph, list, table, steps, atau cta
   - paragraphs: isi penjelasan
   - items: poin-poin kalau tipenya list, table, atau steps
   Kalau tipenya paragraph, biarkan items kosong.
   Kalau tipenya list atau steps, isi minimal 4 item.
7. faq — 6 sampai 8 pertanyaan beserta jawabannya.
8. keywords — variasi keyword turunan yang dipakai di halaman.

Aturan tambahan:
- Total seluruh teks harus mendekati {word_target} kata.
- Jangan mengulang kalimat yang sama di section berbeda.
- Setiap section membahas sudut yang berbeda.
{disclaimer_rule}
- Jangan memakai kata "kami menjamin" atau klaim pasti menang.

Aturan brand:
- Sebut "{brand_name}" di paragraf pembuka, sekali saja.
- Sebut "{brand_name}" di section penutup atau CTA.
- Di seluruh halaman, brand cukup muncul 3 sampai 5 kali.
  Menyebutnya di setiap paragraf membuat halaman terbaca seperti
  iklan dan menurunkan kualitasnya di mata pembaca.
- Jangan menulis brand sebagai bagian dari keyword, misalnya
  "{brand_name} gacor". Keduanya berdiri sendiri.
- Jangan mengarang klaim tentang "{brand_name}" seperti jumlah
  member, lisensi, penghargaan, atau tahun berdiri. Tidak ada
  datanya, dan mengarang hal itu bisa menyesatkan pembaca.
""".strip()

    return (
        content_planner_system_prompt(language_code),
        user_prompt,
    )
