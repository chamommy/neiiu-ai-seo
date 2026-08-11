"""
Inti pipeline NEIIU, lepas dari cara pemanggilannya.

Modul ini tidak mencetak apa pun. Kemajuan dilaporkan lewat
callback `on_event`, jadi logika yang sama dipakai CLI
(`neiiu.py`) maupun job runner di web app tanpa digandakan.
"""

import json
from datetime import datetime
from pathlib import Path

from analyzer.serp_analyzer import analyze_serp
from config import (
    CRAWL_TOP_N,
    DESIGN_REFERENCES,
    OUTPUT_DIR,
    SERP_PROVIDER,
    SERP_REGION,
    SERP_TOP_N,
    SITE_BASE_URL,
    SITE_CTA_URL,
    SITE_DISCLAIMER,
    SITE_NAME,
)
from utils.region import (
    city_label,
    format_date,
    get_region,
    iso_date,
    resolve_location,
    slug_for_url,
)
from utils.text import author_name
from generators.amp_generator import generate_amp_page
from generators.amp_validator import validate_amp
from generators.article_block import (
    reachable_words,
    stretch_spec,
    template_article_words,
)
from generators.content_planner import (
    check_language,
    count_plan_words,
    generate_content_plan,
    generate_serp_insight,
    generate_template_content,
)
from generators.landing_generator import generate_landing_page
from generators.seo_validator import validate_page
from generators.template_extractor import (
    extract_template_from_url,
    rank_reference_pages,
)
from generators.template_assets import (
    ASSET_LABELS,
    UnsafeAssetUrl,
    clean_assets,
)
from generators.template_filler import (
    derive_spec,
    fill_template,
    merge_specs,
)
from generators.inspiration import build_design_dna
from generators.template_scanner import scan
from generators.template_slots import build_slot_map
from generators.theme import build_theme
from serp.serp_search import search_keyword, slugify


TOTAL_STEPS = 8

STEP_LABELS = {
    1: "Mencari di Google",
    2: "Menganalisis rank 1 sampai 10",
    3: "AI membaca pola ranking",
    4: "Mengambil struktur halaman acuan",
    5: "AI menyusun konten baru",
    6: "Merender landing page dan AMP",
    7: "Validasi AMP dan SEO",
    8: "Menyimpan hasil",
}


class PipelineError(RuntimeError):
    """
    Kegagalan yang sudah punya pesan siap dibaca pengguna.
    """


def content_failure_hint(error: Exception) -> str:
    """
    Memilih saran yang cocok dengan kegagalannya.

    Dulu satu saran dipakai untuk semua sebab: "pastikan Ollama
    berjalan dan model sudah ter-pull". Untuk satu-satunya sebab yang
    memang itu, kalimatnya benar. Untuk sisanya ia menyuruh orang
    memeriksa hal yang sama sekali tidak rusak, sekaligus menutupi
    sebab yang sesungguhnya.

    Contoh nyatanya: job yang dihentikan di tengah jalan membuat
    Ollama menjawab 500 untuk permintaan yang batal, dan pesan lama
    membacanya sebagai "Ollama mati" padahal Ollama sehat dan job itu
    memang sengaja dihentikan.
    """
    teks = str(error).lower()

    # Kesalahan dari lapisan Ollama sudah menjelaskan sebab dan jalan
    # keluarnya sendiri; menambahi saran umum cuma mengaburkannya.
    if "tidak dapat dihubungi" in teks or "tidak mengirim data" in teks:
        return ""

    if "500" in teks and "/api/chat" in teks:
        return (
            "Ollama memutus permintaannya di tengah jalan. Paling "
            "sering ini berarti prosesnya dihentikan - server "
            "dimatikan atau job dibatalkan - bukan Ollama yang mati. "
            "Kalau berulang tanpa dihentikan siapa pun, cek log "
            "Ollama."
        )

    # Ollama menolak permintaannya sebelum satu token pun ditulis
    # karena JSON Schema-nya tidak bisa dijadikan grammar. Ollama
    # sendiri sehat, jadi saran "pastikan Ollama berjalan" di bawah
    # justru menyuruh orang memeriksa satu-satunya hal yang tidak
    # rusak.
    if "parse grammar" in teks or "initialize samplers" in teks:
        return (
            "Batas panjang salah satu teks terlalu besar untuk "
            "dijadikan grammar oleh Ollama. Turunkan kolom Panjang "
            "artikel, atau pakai template yang slot teksnya tidak "
            "sepanjang itu."
        )

    if "bukan json" in teks or "json terstruktur" in teks:
        return (
            "Jawaban model berhenti sebelum JSON-nya selesai. "
            "Templatenya kemungkinan meminta terlalu banyak teks "
            "sekaligus untuk model ini; kurangi jumlah halaman yang "
            "di-crawl atau pakai template yang lebih ringkas."
        )

    return "Pastikan Ollama berjalan dan model sudah ter-pull."


def susun_kabar(info: dict) -> str:
    """
    Menyusun satu baris log dari kabar kemajuan langkah AI.

    Kabarnya datang dalam dua bentuk. Yang berisi "line" adalah catatan
    apa adanya - misalnya peran mana yang dijawab kependekan lalu
    diminta lagi. Sisanya adalah hitungan token yang sedang ditulis
    model.

    Ditulis di tingkat modul supaya bisa diuji tanpa menjalankan
    pipeline: dua kali kesalahan di sini menghanguskan puluhan menit
    kerja model, dan keduanya lolos justru karena fungsinya terkubur di
    dalam run_neiiu dan tidak pernah dipanggil terpisah.
    """
    catatan = str(info.get("line") or "").strip()

    if catatan:
        return f"  {catatan}"

    # Isi template dikerjakan beberapa giliran, karena satu permintaan
    # tidak muat menampung seluruh teks halaman. Nomor gilirannya ikut
    # ditampilkan supaya kemajuannya terbaca sebagai maju, bukan
    # sebagai mengulang.
    giliran = ""

    try:
        jumlah = int(info.get("batches", 1))
    except (TypeError, ValueError):
        jumlah = 1

    if jumlah > 1:
        giliran = f"bagian {info.get('batch', '?')}/{jumlah} — "

    if info.get("batch_retry"):
        giliran += "melengkapi sisa — "

    try:
        token = int(info.get("tokens", 0))
    except (TypeError, ValueError):
        token = 0

    if token == 0:
        return f"  {giliran}memproses prompt, belum ada token keluar..."

    return (
        f"  {giliran}menulis... {token} token "
        f"({info.get('elapsed', '?')} detik)"
    )


def build_brand(
    brand_name: str = "",
    base_url: str = "",
    region: str = SERP_REGION,
    cta_url: str = "",
) -> dict:
    """
    Menyusun identitas situs untuk satu run.

    Keyword dan brand sengaja dipisah: keyword adalah topik yang
    dicari di Google, brand adalah nama situs yang muncul di
    halamannya. Satu keyword yang sama bisa dipakai untuk banyak
    brand, jadi keduanya tidak boleh dipatok bersama di .env.

    Zona ikut dititipkan di sini karena dict ini sudah diterima
    semua generator. Dengan begitu bahasa halaman, locale, arah
    teks, dan bentuk tanggal berasal dari satu sumber yang sama
    dengan negara tempat pencariannya dilakukan, dan keduanya tidak
    bisa lagi berbeda tanpa disadari.
    """
    clean_name = brand_name.strip() or SITE_NAME
    clean_url = (base_url.strip() or SITE_BASE_URL).rstrip("/")

    if clean_url and not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    spec = get_region(region)
    now = datetime.now()

    clean_cta = (cta_url.strip() or SITE_CTA_URL).rstrip()

    if clean_cta and not clean_cta.startswith(("http://", "https://")):
        clean_cta = "https://" + clean_cta

    return {
        "site_name": clean_name,
        "base_url": clean_url,
        "cta_url": clean_cta,
        "region": spec["code"],
        "region_label": spec["label"],
        "language_name": spec["language_name"],
        "html_lang": spec["html_lang"],
        "locale": spec["og_locale"],
        "direction": spec["direction"],
        "disclaimer": SITE_DISCLAIMER,
        # Penanda run, dipakai memilih contoh gaya mana yang dikirim
        # ke model.
        #
        # Ditaruh di sini karena dict ini sudah sampai ke setiap
        # generator tanpa satu pun parameter tambahan, dan karena ia
        # dibuat SEKALI per run. Dua sifat itu yang dibutuhkan: beda
        # antar run supaya halaman kedua tidak menyalin halaman
        # pertama, dan sama sepanjang satu run supaya awalan promptnya
        # tetap identik di semua giliran - kalau berubah di tengah,
        # cache prompt Ollama batal dan tiap giliran membayar prefill
        # dari nol.
        "variation": now.strftime("%Y%m%d%H%M%S%f"),
        # Tahun yang tampil mengikuti kalender setempat, sedangkan
        # tanggal untuk mesin tetap masehi.
        "year": str(now.year + spec["year_offset"]),
        "today": format_date(now, spec["code"]),
        "today_iso": iso_date(now),
    }


def prepare_output_dir(
    keyword: str,
    brand_name: str = "",
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Brand ikut di nama folder supaya beberapa brand yang dibuat
    # dari keyword yang sama tidak tertukar.
    prefix = f"{slugify(brand_name)}-" if brand_name.strip() else ""

    path = OUTPUT_DIR / f"{prefix}{slugify(keyword)}-{timestamp}"

    path.mkdir(parents=True, exist_ok=True)

    return path


def save_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def write_analysis_markdown(
    path: Path,
    keyword: str,
    serp: dict,
    insight: dict,
    blueprint: dict,
    template: dict,
) -> None:
    """
    Menulis ringkasan analisis dalam bentuk yang enak dibaca.
    """
    target = blueprint["target"]
    lines: list[str] = []

    lines.append(f"# Analisis SERP: {keyword}\n")
    lines.append(
        f"Diambil {serp['fetched_at']} lewat provider "
        f"`{serp['provider']}`.\n"
    )

    lines.append("## Intent Pencarian\n")
    lines.append(f"{insight.get('search_intent', '-')}\n")

    lines.append("## Ringkasan Halaman Pertama\n")
    lines.append(f"{insight.get('serp_summary', '-')}\n")

    lines.append("## Kenapa Mereka Bisa Naik\n")

    for item in insight.get("ranking_analysis", []):
        lines.append(
            f"### Peringkat {item['position']} — {item['domain']}\n"
        )
        lines.append(f"{item['why_ranking']}\n")

        if item.get("strengths"):
            lines.append("**Kekuatan:**\n")
            lines.extend(f"- {value}" for value in item["strengths"])
            lines.append("")

        if item.get("weaknesses"):
            lines.append("**Kelemahan:**\n")
            lines.extend(f"- {value}" for value in item["weaknesses"])
            lines.append("")

    hijacked = blueprint.get("hijacked_pages", [])

    if hijacked:
        lines.append("## Domain Bajakan Terdeteksi\n")
        lines.append(
            f"{len(hijacked)} halaman di peringkat atas berdiri di "
            "domain milik pihak lain yang dibobol. Halaman ini "
            "dikeluarkan dari perhitungan target karena ngerank lewat "
            "otoritas domain curian, bukan karena struktur halamannya.\n"
        )

        for item in hijacked:
            flag = " — cloaking terdeteksi" if item["cloaking"] else ""

            lines.append(
                f"- **Peringkat {item['position']}** `{item['domain']}` "
                f"(keyakinan {item['confidence']}%){flag}"
            )

            for reason in item["reasons"]:
                lines.append(f"  - {reason}")

        lines.append("")

    unreadable = blueprint.get("unreadable_pages", [])

    if unreadable:
        lines.append("## Halaman Yang Isinya Tidak Terbaca\n")
        lines.append(
            "Halaman berikut ngerank, tapi isi yang diterima crawler "
            "bukan isi yang diindeks Google. Cloaking yang canggih ikut "
            "memeriksa rentang IP Googlebot, bukan hanya User-Agent, "
            "sehingga yang dilayani ke crawler ini adalah halaman "
            "kosong atau halaman asli pemilik domainnya. Semuanya "
            "dikeluarkan dari perhitungan target.\n"
        )

        for item in unreadable:
            lines.append(
                f"- **Peringkat {item['position']}** `{item['domain']}` "
                f"— hanya {item['word_count']} kata terbaca"
            )

        lines.append("")

    if blueprint.get("hijack_fallback"):
        lines.append(
            "> **Peringatan serius:** tidak ada satu pun halaman "
            "pertama yang layak dijadikan acuan. Target metrik di "
            "bawah dihitung dari data yang tidak sahih dan tidak bisa "
            "dipercaya. Tentukan halaman acuan sendiri lewat "
            "`--reference`, atau isi daftar kompetitor asli lewat "
            "provider manual.\n"
        )

    lines.append("## Target Yang Harus Dikejar\n")
    lines.append("| Metrik | Nilai |")
    lines.append("| --- | --- |")
    lines.append(f"| Median kata | {target['word_count_median']} |")
    lines.append(
        f"| Median kata top 5 | {target['word_count_top5_median']} |"
    )
    lines.append(f"| Median H2 | {target['h2_median']} |")
    lines.append(f"| Median H3 | {target['h3_median']} |")
    lines.append(
        f"| Median internal link | {target['internal_links_median']} |"
    )
    lines.append(
        f"| Median panjang title | {target['title_length_median']} |"
    )
    lines.append(
        f"| Median panjang meta | {target['meta_length_median']} |"
    )
    lines.append("")

    lines.append("## Celah Konten\n")
    lines.extend(
        f"- {value}" for value in insight.get("content_gaps", [])
    )
    lines.append("")

    lines.append("## Strategi Menang\n")
    lines.extend(
        f"- {value}" for value in insight.get("winning_strategy", [])
    )
    lines.append("")

    if template.get("user_template"):
        lines.append("## Template Yang Dipakai\n")
        lines.append(f"Template unggahan: `{template['source_domain']}`\n")

        counts = template.get("slot_counts", {})

        lines.append(
            "Bagian yang diisi ulang: "
            + (
                ", ".join(
                    f"{role} {count}"
                    for role, count in sorted(counts.items())
                )
                or "-"
            )
            + "\n"
        )

        lines.append(
            "Catatan: struktur, tautan, dan blok iklan di dalam "
            "template tidak disentuh sama sekali. Yang diganti hanya "
            "teks di bagian yang disebut di atas.\n"
        )
    else:
        lines.append("## Template Acuan\n")
        lines.append(f"Sumber struktur: `{template['source_url']}`\n")
        lines.append(
            f"Section terdeteksi: {template['section_count']} "
            f"({', '.join(template['section_types'][:10])})\n"
        )

        # Palet hanya ada pada template yang diambil dari halaman
        # kompetitor. Template unggahan tidak melewati pengambilan
        # gaya visual sama sekali, jadi kuncinya memang tidak ada.
        palette = template.get("design", {}).get("palette")

        if palette:
            lines.append(
                f"Palet warna: mode {palette['mode']}, "
                f"aksen `{palette['accent']}`\n"
            )

        lines.append(
            "Catatan: yang diambil hanya struktur dan gaya visual. "
            "Seluruh teks halaman baru ditulis ulang dari nol.\n"
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def sections_from_parts(
    headings: list,
    paragraphs: list,
) -> list[dict]:
    """
    Membagi paragraf ke bawah heading-heading template.

    Bentuk plan ini dipakai kalau pengguna hanya mengunggah template
    landing tanpa berkas AMP: versi AMP-nya dibuat generator biasa
    dari plan ini. Kalau heading disalin tanpa paragrafnya, halaman
    AMP terbit berisi deretan judul kosong sementara seluruh teks
    yang sudah ditulis AI hilang - dan halaman itu yang jadi
    pasangan resmi landing page di mata Google.

    Heading yang tidak kebagian paragraf dibuang, bukan diterbitkan
    kosong.
    """
    bersih = [str(item).strip() for item in headings if str(item).strip()]

    if not bersih or not paragraphs:
        return []

    jatah, sisa = divmod(len(paragraphs), len(bersih))

    sections: list[dict] = []
    cursor = 0

    for index, heading in enumerate(bersih):
        ambil = jatah + (1 if index < sisa else 0)
        bagian = paragraphs[cursor:cursor + ambil]
        cursor += ambil

        if not bagian:
            continue

        sections.append(
            {
                "heading": heading,
                "type": "paragraph",
                "paragraphs": bagian,
                "items": [],
            }
        )

    return sections


def plan_from_template_content(
    content: dict,
    keyword: str,
    brand: dict,
    region: str,
) -> dict:
    """
    Menyusun ringkasan rencana dari isi template yang sudah dicocokkan.

    Bentuk plan dipakai di banyak tempat sesudah ini: penamaan
    berkas, ringkasan job, dan pemeriksaan bahasa. Jadi
    isi template diterjemahkan ke bentuk yang sama supaya bagian
    lain pipeline tidak perlu tahu jalur mana yang dipakai.
    """
    # Pasangan yang salah satu sisinya kosong tidak ikut.
    #
    # Daftar ini bukan cuma laporan: dari sinilah blok FAQPage di
    # structured data disusun, dan dari sini pula halaman AMP dirakit
    # kalau pengguna tidak mengunggah berkas AMP sendiri. Pasangan
    # kosong yang lolos terbit sebagai <Question> bernama string
    # kosong - rich result yang ditolak Google, dan kartu tanya-jawab
    # tanpa pertanyaan di halaman AMP.
    #
    # Slot kosong SENGAJA dibiarkan kosong sampai di sini, bukan
    # dibuang lebih awal, karena nomor urutnya yang memasangkan
    # jawaban ke pertanyaannya. Membuangnya di tengah jalan menggeser
    # seluruh sisa daftar naik satu posisi.
    faq = [
        {"question": question, "answer": answer}
        for question, answer in zip(
            content.get("faq_question", []),
            content.get("faq_answer", []),
        )
        if str(question).strip() and str(answer).strip()
    ]

    keywords = [
        item.strip()
        for item in str(content.get("meta_keywords", "")).split(",")
        if item.strip()
    ]

    if keyword not in keywords:
        keywords.insert(0, keyword)

    paragraphs = [
        item for item in content.get("paragraph", []) if str(item).strip()
    ]

    return {
        "title": content.get("title", ""),
        "meta_description": content.get("meta_description", ""),
        "slug": slug_for_url(content.get("h1") or keyword, region),
        "h1": content.get("h1", ""),
        "intro": paragraphs[:2],
        # Artikelnya ada di dalam paragraphs ini, karena memang di situ
        # tempatnya - slot paragraf milik template. Dua hal di luar
        # halaman template membaca daftar ini: versi AMP yang dibuat
        # generator biasa saat pengguna tidak mengunggah berkas AMP,
        # dan hitungan kata di laporan job.
        "sections": sections_from_parts(
            content.get("heading", []),
            paragraphs[2:],
        ),
        "faq": faq,
        "keywords": keywords[:12],
        "reviews": [
            # Namanya saja, tanpa kota dan bintang yang ikut tertulis
            # di baris pengulas milik template.
            {"text": text, "author": author_name(author)}
            for text, author in zip(
                content.get("review_text", []),
                content.get("review_author", []),
            )
        ],
        "_metadata": content.get("_metadata", {}),
    }


def extract_reference_template(
    candidates: list[dict],
    emit,
) -> dict:
    """
    Mengambil struktur dari halaman kompetitor yang sedang ngerank.

    Kandidat dicoba berurutan. Server kompetitor sering menolak atau
    kehabisan waktu, dan berhenti di kandidat pertama yang mati akan
    membuang seluruh pekerjaan langkah 1 sampai 3.
    """
    attempts: list[str] = []

    for candidate in candidates[:4]:
        candidate_url = candidate.get("final_url", candidate["url"])

        try:
            template = extract_template_from_url(candidate_url)

            emit(
                4,
                "done",
                f"{template['source_domain']}, "
                f"{template['section_count']} section",
            )

            return template

        except Exception as error:
            label = candidate.get("domain", candidate_url)

            attempts.append(f"{label}: {type(error).__name__}")

            emit(
                4,
                "info",
                f"  {label} gagal ({type(error).__name__}), "
                "coba kandidat berikutnya",
            )

    raise PipelineError(
        "Semua kandidat halaman acuan gagal diambil: "
        + "; ".join(attempts)
        + ". Tentukan halaman acuan sendiri lewat --reference, "
        "atau unggah template sendiri."
    )


def run_neiiu(
    keyword: str,
    brand_name: str = "",
    base_url: str = "",
    limit: int = SERP_TOP_N,
    crawl: int = CRAWL_TOP_N,
    provider: str = SERP_PROVIDER,
    reference: str = "",
    use_cache: bool = True,
    analyze_only: bool = False,
    region: str = SERP_REGION,
    city: str = "",
    user_template: dict | None = None,
    template_brand: str = "",
    design_refs: list[str] | None = None,
    cta_url: str = "",
    assets: dict | None = None,
    history: dict | None = None,
    color_variant: int | None = None,
    article_words: int = 0,
    plain: bool = False,
    kit_from_ref: bool = False,
    on_event=None,
) -> dict:
    """
    Menjalankan pipeline penuh dari keyword sampai halaman jadi.

    on_event dipanggil dengan dict:
        {"step": int, "total": int, "label": str,
         "status": "start" | "done" | "info", "message": str}

    Mengembalikan dict hasil. Melempar PipelineError kalau gagal
    di titik yang tidak bisa dilanjutkan.
    """
    def emit(
        step: int,
        status: str,
        message: str = "",
    ) -> None:
        if on_event is None:
            return

        on_event(
            {
                "step": step,
                "total": TOTAL_STEPS,
                "label": STEP_LABELS.get(step, ""),
                "status": status,
                "message": message,
            }
        )

    clean_keyword = keyword.strip()

    if not clean_keyword:
        raise PipelineError("Keyword tidak boleh kosong.")

    brand = build_brand(brand_name, base_url, region, cta_url)

    # Alamat gambar diperiksa SEKARANG, sebelum satu detik pun dipakai
    # untuk crawl dan menulis. Alamat yang salah ketik baru ketahuan di
    # langkah 6 kalau diperiksa belakangan, dan pengguna sudah menunggu
    # belasan menit untuk kegagalan yang bisa disebutkan di awal.
    try:
        clean_assets_map = clean_assets(assets)
    except UnsafeAssetUrl as error:
        raise PipelineError(str(error)) from error

    # 1. SERP
    emit(1, "start")

    emit(
        1,
        "info",
        f"zona {brand['region_label']} "
        f"(gl={get_region(region)['gl']}, "
        f"hl={get_region(region)['hl']}, "
        f"lokasi {resolve_location(region, city)}), "
        f"halaman ditulis dalam bahasa {brand['language_name']}",
    )

    if history:
        emit(
            1,
            "info",
            f"mengingat {sum(len(v) for v in history.values())} teks dari "
            "halaman yang sudah pernah dibuat untuk topik ini - yang "
            "mengulangnya akan ditolak dan diminta ulang",
        )

    if clean_assets_map and user_template:
        emit(
            1,
            "info",
            "gambar yang diganti: "
            + ", ".join(
                f"{ASSET_LABELS[peran]} -> {url}"
                for peran, url in clean_assets_map.items()
            ),
        )
    elif clean_assets_map:
        # Alamat gambar hanya berguna kalau ada template yang punya
        # gambarnya. Halaman yang dirakit NEIIU sendiri tidak memuat
        # satu pun gambar untuk ditukar, jadi didiamkan di sini berarti
        # pengguna menunggu belasan menit lalu mendapati logonya tidak
        # berubah, tanpa satu baris pun yang menyebut sebabnya.
        emit(
            1,
            "info",
            "alamat logo/favicon/poster diisi tapi Template dikosongkan, "
            "jadi tidak ada gambar yang ditukar - halaman yang dirakit "
            "NEIIU sendiri tidak memuat gambar template",
        )

    serp = search_keyword(
        keyword=clean_keyword,
        limit=limit,
        provider=provider,
        use_cache=use_cache,
        region=region,
        city=city,
    )

    emit(
        1,
        "done",
        f"{len(serp['results'])} URL ditemukan"
        + (" (dari cache)" if serp["from_cache"] else ""),
    )

    # 2. Crawl dan analisis
    emit(2, "start")

    def on_page(entry: dict, done: int, total: int) -> None:
        if entry["status"] == "ok":
            detail = f"{entry['word_count']} kata"
        else:
            detail = "gagal di-crawl"

        emit(
            2,
            "info",
            f"[{done}/{total}] {entry['domain']} — {detail}",
        )

    analysis = analyze_serp(
        keyword=clean_keyword,
        serp=serp,
        limit=crawl,
        verbose=False,
        on_page=on_page,
    )

    blueprint = analysis["blueprint"]

    if blueprint["analyzed_pages"] == 0:
        raise PipelineError(
            "Tidak ada satu pun halaman yang berhasil di-crawl. "
            "Kebanyakan situs menolak request."
        )

    hijacked_count = blueprint.get("hijacked_count", 0)

    if hijacked_count:
        emit(
            2,
            "info",
            f"{hijacked_count} halaman berdiri di domain bajakan "
            "dan dikeluarkan dari perhitungan target",
        )

        for item in blueprint.get("hijacked_pages", []):
            emit(
                2,
                "info",
                f"  bajakan: [{item['position']}] {item['domain']} "
                f"({item['confidence']}%"
                + (", cloaking" if item["cloaking"] else "")
                + ")",
            )

    unreadable_count = blueprint.get("unreadable_count", 0)

    for item in blueprint.get("unreadable_pages", []):
        emit(
            2,
            "info",
            f"  tidak terbaca: [{item['position']}] {item['domain']} "
            f"({item['word_count']} kata) — isi aslinya tidak "
            "dilayani ke crawler",
        )

    if blueprint.get("hijack_fallback"):
        emit(
            2,
            "info",
            "PERINGATAN: tidak ada halaman pertama yang layak jadi "
            "acuan, target metrik tidak bisa dipercaya. Pakai "
            "--reference atau daftar kompetitor manual.",
        )

        # Disebut terpisah karena akibatnya terlihat di halaman jadi,
        # bukan cuma di angka. Isi halaman ini disusun tanpa satu pun
        # kata dari kompetitor - kalau tidak dikatakan, FAQ dan
        # headingnya yang lebih tipis terbaca seperti kesalahan lain.
        emit(
            2,
            "info",
            "  kosakata dari kompetitor tidak dipakai sama sekali "
            "untuk keyword ini: yang terbaca crawler adalah isi asli "
            "situs yang dibajak, bukan isi yang ngerank. FAQ dan "
            "heading disusun tanpa bahan dari SERP.",
        )

    emit(
        2,
        "done",
        f"{blueprint['analyzed_pages']} halaman dipakai, "
        f"{hijacked_count} bajakan, "
        f"{unreadable_count} tidak terbaca, "
        f"{blueprint['failed_pages']} gagal",
    )

    # 3. Insight AI
    emit(3, "start")

    def ai_progress(step: int):
        """
        Melaporkan token yang sudah ditulis model.

        Langkah AI bisa berjalan puluhan menit di CPU. Tanpa laporan
        berkala, prosesnya tidak bisa dibedakan dari yang menggantung.
        """
        def report(info: dict) -> None:
            # Seluruh isinya dibungkus karena laporan kemajuan tidak
            # boleh punya kuasa membatalkan pekerjaan yang dilaporkannya.
            # Ini sudah dua kali terjadi di langkah paling mahal: sekali
            # karena "batches" berisi teks lalu dibandingkan dengan
            # angka, sekali lagi karena kabar berbentuk {"line": ...}
            # dibaca sebagai hitungan token. Keduanya menghanguskan
            # puluhan menit kerja model demi satu baris log.
            try:
                emit(step, "info", susun_kabar(info))
            except Exception:
                pass

        return report

    insight = generate_serp_insight(
        analysis,
        verbose=False,
        on_progress=ai_progress(3),
    )

    emit(
        3,
        "done",
        "selesai"
        + (
            " (fallback tanpa AI)"
            if insight.get("status") == "fallback"
            else ""
        ),
    )

    # 4. Template acuan
    emit(4, "start")

    if user_template:
        # Template pengguna menggantikan pencarian halaman acuan.
        # Strukturnya sudah ditentukan sendiri oleh pemiliknya, jadi
        # tidak ada gunanya meniru struktur kompetitor.
        slot_map = build_slot_map(
            scan(user_template["landing"]),
            template_brand,
        )

        # Kebutuhan isi dihitung dari KEDUA berkas, bukan dari landing
        # saja. Versi AMP hampir selalu punya jumlah slot yang berbeda,
        # dan kalau isi hanya dipesan sebanyak slot landing, sisa slot
        # AMP terbit dengan teks lama milik pemilik template - teks
        # tentang keyword yang sama sekali lain.
        specs = [derive_spec(slot_map)]
        counts = dict(slot_map["counts"])

        if user_template.get("amp"):
            amp_map = build_slot_map(
                scan(user_template["amp"]),
                template_brand,
            )

            specs.append(derive_spec(amp_map))

            for role, count in amp_map["counts"].items():
                counts[role] = max(counts.get(role, 0), count)

        template_spec = merge_specs(*specs)

        # Panjang artikel diatur di sini, sebelum satu permintaan pun
        # dikirim ke model: jatah tiap slot paragraf dilebarkan supaya
        # model menulis lebih panjang DI TEMPAT YANG SAMA. Tidak ada
        # paragraf yang ditambahkan, dan tanpa target apa pun tidak
        # ada satu jatah yang berubah.
        muat_di_template = template_article_words(template_spec)
        tercapai = reachable_words(template_spec, article_words)
        dilebarkan = stretch_spec(template_spec, article_words)

        if dilebarkan:
            emit(
                4,
                "run",
                f"panjang artikel: {muat_di_template} kata muat di "
                f"template, jatah {dilebarkan} paragraf dilebarkan "
                "- jumlah paragrafnya tetap.",
            )

        # Target yang di luar jangkauan dikatakan apa adanya.
        #
        # Satu template yang cuma punya tujuh slot paragraf tidak bisa
        # memuat 1.500 kata tanpa menambah paragraf, dan menambah
        # paragraf justru yang tidak boleh dilakukan. Diam-diam
        # berhenti di angka yang tercapai berarti membiarkan pengguna
        # mengira targetnya terpenuhi.
        if article_words and tercapai < article_words:
            emit(
                4,
                "info",
                f"  target {article_words} kata tidak tercapai di "
                f"template ini: paling jauh sekitar {tercapai} kata, "
                "karena satu paragraf paling banyak dilebarkan tiga "
                "kali lipat. Pakai template dengan lebih banyak "
                "paragraf kalau perlu lebih panjang.",
            )

        template = {
            "source_url": f"template: {user_template['name']}",
            "source_domain": user_template["name"],
            "section_count": len(counts),
            "section_types": sorted(counts),
            "structure": [],
            "design": {},
            "user_template": True,
            "slot_counts": counts,
        }

        emit(
            4,
            "done",
            f"template '{user_template['name']}': "
            + ", ".join(
                f"{role} {count}"
                for role, count in sorted(counts.items())
            ),
        )

    else:
        template_spec = None

        if reference:
            candidates = [{"url": reference, "domain": reference}]
        else:
            candidates = rank_reference_pages(analysis["pages"])

        if not candidates:
            raise PipelineError(
                "Tidak ada halaman acuan yang bisa dipakai."
            )

        template = extract_reference_template(candidates, emit)

    output_dir = prepare_output_dir(
        clean_keyword,
        brand["site_name"],
    )

    if analyze_only:
        write_analysis_markdown(
            path=output_dir / "ANALISIS.md",
            keyword=clean_keyword,
            serp=serp,
            insight=insight,
            blueprint=blueprint,
            template=template,
        )

        save_json(
            output_dir / "analysis.json",
            {
                "keyword": clean_keyword,
                "serp": serp,
                "pages": analysis["pages"],
                "blueprint": blueprint,
                "insight": insight,
                "template": template,
            },
        )

        emit(8, "done", "mode analisis saja")

        return {
            "analyze_only": True,
            "keyword": clean_keyword,
            "brand": brand,
            "output_dir": str(output_dir),
            "serp": serp,
            "analysis": analysis,
            "insight": insight,
            "template": template,
        }

    # 5. Rencana konten
    emit(5, "start")

    # Catatan dari langkah pengisian, disimpan supaya ikut ke
    # report.json.
    #
    # Sebelumnya catatan ini hanya dikirim ke log langsung, dan begitu
    # run selesai tidak ada jejaknya sama sekali. Akibatnya terasa
    # persis saat paling dibutuhkan: halaman terbit dengan judul blok
    # milik pemilik template, dan satu-satunya keterangan yang bisa
    # menjelaskan kenapa - "hanya 1 dari 9 heading yang terisi" -
    # sudah hilang bersama prosesnya. Diagnosis jadi menebak-nebak,
    # dan satu run di mesin ini harganya lebih dari sejam.
    content_notes: list[str] = []

    # Isi yang terbit, dipakai lagi di luar untuk diingat sebagai
    # "sudah dipakai". Kosong di jalur tanpa template, karena di situ
    # halamannya dirakit dari plan, bukan dari peta slot.
    content: dict = {}

    try:
        if user_template:
            # Jumlah teks ditentukan template, jadi yang diminta ke
            # AI adalah potongan-potongan terpisah dengan jumlah dan
            # panjang yang persis, bukan rencana halaman bebas.
            content, fit_notes = generate_template_content(
                analysis=analysis,
                insight=insight,
                spec=template_spec,
                brand=brand,
                fallbacks={
                    "faq_question": blueprint["people_also_ask"]
                    + blueprint["competitor_questions"],
                },
                riwayat=history or {},
                on_progress=ai_progress(5),
            )

            for note in fit_notes:
                emit(5, "info", f"  {note}")

            content_notes = list(fit_notes)

            # Keyword ikut dibawa di dalam isi supaya judul blok yang
            # ditulis Python punya bahan kalau brandnya kosong.
            content["_keyword"] = clean_keyword

            plan = plan_from_template_content(
                content,
                clean_keyword,
                brand,
                region,
            )
        else:
            plan = generate_content_plan(
                analysis=analysis,
                insight=insight,
                template=template,
                brand=brand,
                verbose=False,
                on_progress=ai_progress(5),
            )
    except Exception as error:
        saran = content_failure_hint(error)

        raise PipelineError(
            f"Gagal menyusun konten: {error}. "
            + (f"{saran} " if saran else "")
            + "Hasil crawl SERP tetap tersimpan di cache."
        ) from error

    language_warning = check_language(plan, region)

    if language_warning:
        emit(5, "info", f"PERINGATAN: {language_warning}")

    emit(
        5,
        "done",
        f"{len(plan['sections'])} section, "
        f"{len(plan['faq'])} FAQ, "
        f"~{count_plan_words(plan)} kata",
    )

    # 6. Render
    emit(6, "start")

    page_url = f"{brand['base_url']}/{plan['slug']}/"
    amp_url = f"{brand['base_url']}/{plan['slug']}/amp/"

    if user_template:
        landing_result = fill_template(
            html=user_template["landing"],
            content=content,
            brand=brand,
            old_brand=template_brand,
            assets=clean_assets_map,
        )

        landing_html = landing_result["html"]

        emit(
            6,
            "info",
            f"  landing page: {landing_result['edits']} bagian diisi, "
            f"{landing_result['skipped']} dibiarkan apa adanya",
        )

        for note in landing_result["notes"]:
            emit(6, "info", f"  {note}")

        if user_template.get("amp"):
            amp_result = fill_template(
                html=user_template["amp"],
                content=content,
                brand=brand,
                old_brand=template_brand,
                is_amp=True,
                assets=clean_assets_map,
            )

            amp_html = amp_result["html"]

            emit(
                6,
                "info",
                f"  AMP: {amp_result['edits']} bagian diisi, "
                f"{amp_result['skipped']} dibiarkan apa adanya",
            )

            # Catatan berkas AMP ikut ditampilkan. Sebelumnya hanya
            # catatan landing yang muncul, jadi peringatan yang cuma
            # berlaku di berkas AMP - slot yang tidak kebagian isi,
            # atribut tanpa kutip - hilang tanpa jejak.
            for note in amp_result["notes"]:
                emit(6, "info", f"  {note}")
        else:
            # Tanpa template AMP, versi AMP dibuat generator biasa
            # supaya halamannya tetap punya pasangan AMP yang sah.
            amp_html = generate_amp_page(
                plan=plan,
                design={},
                brand=brand,
                page_url=page_url,
                amp_url=amp_url,
            )

            emit(
                6,
                "info",
                "  template AMP tidak diunggah, versi AMP dibuat "
                "NEIIU dari isi yang sama",
            )
    else:
        design = template["design"]
        kit = None

        if not plain:
            # Halaman baru dirakit dari pustaka blok. Gayanya
            # diturunkan dari halaman acuan yang ditunjuk pengguna;
            # kalau tidak ada, dari halaman acuan template; kalau
            # itu pun tidak ada, dari palet bawaan.
            ref_urls = [
                url
                for url in (design_refs or DESIGN_REFERENCES)
                if url.strip()
            ]

            if not ref_urls and reference:
                ref_urls = [reference]

            if not ref_urls and str(
                template.get("source_url", "")
            ).startswith("http"):
                ref_urls = [template["source_url"]]

            def on_source(entry: dict) -> None:
                if entry["ok"]:
                    dipakai = ", ".join(
                        name
                        for name, present in entry["components"].items()
                        if present
                    )

                    emit(
                        6,
                        "info",
                        f"  acuan gaya {entry['domain']}: "
                        f"radius {entry['radius']}px"
                        + (f", komponen {dipakai}" if dipakai else ""),
                    )
                else:
                    emit(
                        6,
                        "info",
                        f"  acuan gaya {entry['domain']} tidak terbaca "
                        f"({entry['error']}), dilewati",
                    )

            dna = build_design_dna(ref_urls, on_source=on_source)

            # Benih warna memuat nama folder hasil, dan nama itu
            # memuat waktu run. Dua halaman brand dan keyword yang
            # sama karena itu tetap keluar dengan warna berbeda,
            # tapi satu run yang diulang persis tetap bisa
            # menghasilkan warna yang sama.
            theme = build_theme(
                dna,
                seed_text=(
                    f"{brand['site_name']}|{clean_keyword}|"
                    f"{output_dir.name}"
                ),
                variant=color_variant,
            )

            design = {
                "palette": theme["palette"],
                "fonts": theme["fonts"],
                "radius": theme["radius"],
            }

            if kit_from_ref:
                kit = dna["components"]
            else:
                # Bawaannya seluruh blok dipasang, dan acuan hanya
                # menentukan warna, font, serta sudut lengkung.
                # Alasannya: halaman acuan yang kebetulan tidak punya
                # popup akan menghasilkan halaman baru tanpa popup,
                # padahal yang diminta dari acuan itu gayanya, bukan
                # daftar komponennya. Yang ingin komponennya ikut
                # menyesuaikan acuan bisa menyalakan kit_from_ref.
                kit = {name: True for name in dna["components"]}

            template["design_dna"] = {
                "sources": [
                    {
                        "url": entry["url"],
                        "domain": entry["domain"],
                        "ok": entry["ok"],
                        "error": entry["error"],
                    }
                    for entry in dna["sources"]
                ],
                "components": kit,
                "components_detected": dna["components"],
                "kit_from_ref": kit_from_ref,
                "theme": {
                    key: value
                    for key, value in theme.items()
                    if key != "palette"
                },
                "palette": theme["palette"],
            }

            emit(
                6,
                "info",
                f"  tema warna {theme['variant'] + 1}"
                f"/{theme['variant_total']} "
                f"(rona {theme['hue']}, {theme['mode']}), "
                f"blok: "
                + ", ".join(
                    name for name, present in kit.items() if present
                ),
            )

        landing_html = generate_landing_page(
            plan=plan,
            design=design,
            brand=brand,
            page_url=page_url,
            amp_url=amp_url,
            kit=kit,
        )

        amp_html = generate_amp_page(
            plan=plan,
            design=design,
            brand=brand,
            page_url=page_url,
            amp_url=amp_url,
            kit=kit,
        )

    amp_dir = output_dir / "amp"
    amp_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(
        landing_html,
        encoding="utf-8",
    )

    (amp_dir / "index.html").write_text(
        amp_html,
        encoding="utf-8",
    )


    emit(6, "done", f"{len(landing_html)} byte")

    # 7. Validasi
    emit(7, "start")

    amp_result = validate_amp(amp_html)

    seo_result = validate_page(
        html=landing_html,
        keyword=clean_keyword,
        blueprint=blueprint,
        page_url=page_url,
    )

    emit(
        7,
        "done",
        f"AMP {'valid' if amp_result['valid'] else 'invalid'}, "
        f"skor SEO {seo_result['score']}/100",
    )

    # 8. Simpan
    emit(8, "start")

    # Folder hasil hanya berisi dua berkas yang memang dipakai:
    # index.html dan amp/index.html.
    #
    # ANALISIS.md dan report.json dulu ikut ditulis di sini. Keduanya
    # menyalin ulang seluruh isi SERP, blueprint, insight, peta slot
    # template, dan rencana konten - berkas beberapa ratus kilobyte
    # yang tidak pernah diunggah ke mana pun. Ringkasan yang dibaca
    # antarmuka tidak diambil dari berkas itu melainkan dari nilai
    # yang dikembalikan fungsi ini, jadi menghapusnya tidak
    # menghilangkan satu angka pun di layar hasil.
    #
    # content_notes tetap dikembalikan lewat nilai balik dan tetap
    # dikirim ke log job, karena itulah satu-satunya keterangan kenapa
    # sebuah halaman bisa terbit setengah berganti.

    emit(8, "done", str(output_dir))

    return {
        "analyze_only": False,
        "keyword": clean_keyword,
        "brand": brand,
        "output_dir": str(output_dir),
        "page_url": page_url,
        "amp_url": amp_url,
        "serp": serp,
        "analysis": analysis,
        "insight": insight,
        "template": template,
        "plan": plan,
        "amp_valid": amp_result["valid"],
        "amp_result": amp_result,
        "seo_result": seo_result,
        "content_notes": content_notes,
        "content": content,
    }
