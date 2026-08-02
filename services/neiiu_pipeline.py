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
    OUTPUT_DIR,
    SERP_PROVIDER,
    SERP_TOP_N,
    SITE_BASE_URL,
    SITE_DISCLAIMER,
    SITE_LOCALE,
    SITE_NAME,
)
from generators.amp_generator import generate_amp_page
from generators.amp_validator import validate_amp
from generators.content_planner import (
    count_plan_words,
    generate_content_plan,
    generate_serp_insight,
)
from generators.landing_generator import generate_landing_page
from generators.seo_validator import validate_page
from generators.template_extractor import (
    extract_template_from_url,
    rank_reference_pages,
)
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


def build_brand(
    brand_name: str = "",
    base_url: str = "",
) -> dict:
    """
    Menyusun identitas situs untuk satu run.

    Keyword dan brand sengaja dipisah: keyword adalah topik yang
    dicari di Google, brand adalah nama situs yang muncul di
    halamannya. Satu keyword yang sama bisa dipakai untuk banyak
    brand, jadi keduanya tidak boleh dipatok bersama di .env.
    """
    clean_name = brand_name.strip() or SITE_NAME
    clean_url = (base_url.strip() or SITE_BASE_URL).rstrip("/")

    if clean_url and not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    return {
        "site_name": clean_name,
        "base_url": clean_url,
        "locale": SITE_LOCALE,
        "disclaimer": SITE_DISCLAIMER,
        "year": str(datetime.now().year),
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


def write_sitemap(
    path: Path,
    page_url: str,
    amp_url: str,
) -> None:
    today = datetime.now().strftime("%Y-%m-%d")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{page_url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{amp_url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
"""

    path.write_text(xml, encoding="utf-8")


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

    lines.append("## Template Acuan\n")
    lines.append(f"Sumber struktur: `{template['source_url']}`\n")
    lines.append(
        f"Section terdeteksi: {template['section_count']} "
        f"({', '.join(template['section_types'][:10])})\n"
    )
    lines.append(
        f"Palet warna: mode {template['design']['palette']['mode']}, "
        f"aksen `{template['design']['palette']['accent']}`\n"
    )
    lines.append(
        "Catatan: yang diambil hanya struktur dan gaya visual. "
        "Seluruh teks halaman baru ditulis ulang dari nol.\n"
    )

    path.write_text("\n".join(lines), encoding="utf-8")


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

    brand = build_brand(brand_name, base_url)

    # 1. SERP
    emit(1, "start")

    serp = search_keyword(
        keyword=clean_keyword,
        limit=limit,
        provider=provider,
        use_cache=use_cache,
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
            if info["tokens"] == 0:
                emit(
                    step,
                    "info",
                    "  memproses prompt, belum ada token keluar...",
                )
                return

            emit(
                step,
                "info",
                f"  menulis... {info['tokens']} token "
                f"({info['elapsed']} detik)",
            )

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

    if reference:
        candidates = [{"url": reference, "domain": reference}]
    else:
        candidates = rank_reference_pages(analysis["pages"])

    if not candidates:
        raise PipelineError(
            "Tidak ada halaman acuan yang bisa dipakai."
        )

    # Kandidat dicoba berurutan. Server kompetitor sering menolak
    # atau kehabisan waktu, dan berhenti di kandidat pertama yang
    # mati akan membuang seluruh pekerjaan langkah 1 sampai 3.
    template = None
    attempts: list[str] = []

    for candidate in candidates[:4]:
        candidate_url = candidate.get("final_url", candidate["url"])

        try:
            template = extract_template_from_url(candidate_url)
            break

        except Exception as error:
            attempts.append(
                f"{candidate.get('domain', candidate_url)}: "
                f"{type(error).__name__}"
            )

            emit(
                4,
                "info",
                f"  {candidate.get('domain', candidate_url)} gagal "
                f"({type(error).__name__}), coba kandidat berikutnya",
            )

    if template is None:
        raise PipelineError(
            "Semua kandidat halaman acuan gagal diambil: "
            + "; ".join(attempts)
            + ". Tentukan halaman acuan sendiri lewat --reference."
        )

    emit(
        4,
        "done",
        f"{template['source_domain']}, "
        f"{template['section_count']} section",
    )

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

    try:
        plan = generate_content_plan(
            analysis=analysis,
            insight=insight,
            template=template,
            brand=brand,
            verbose=False,
            on_progress=ai_progress(5),
        )
    except Exception as error:
        write_analysis_markdown(
            path=output_dir / "ANALISIS.md",
            keyword=clean_keyword,
            serp=serp,
            insight=insight,
            blueprint=blueprint,
            template=template,
        )

        raise PipelineError(
            f"Gagal menyusun konten: {error}. "
            "Pastikan Ollama berjalan dan model sudah ter-pull. "
            "Analisis SERP tetap tersimpan."
        ) from error

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

    landing_html = generate_landing_page(
        plan=plan,
        design=template["design"],
        brand=brand,
        page_url=page_url,
        amp_url=amp_url,
    )

    amp_html = generate_amp_page(
        plan=plan,
        design=template["design"],
        brand=brand,
        page_url=page_url,
        amp_url=amp_url,
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

    write_sitemap(
        output_dir / "sitemap.xml",
        page_url,
        amp_url,
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

    write_analysis_markdown(
        path=output_dir / "ANALISIS.md",
        keyword=clean_keyword,
        serp=serp,
        insight=insight,
        blueprint=blueprint,
        template=template,
    )

    report = {
        "keyword": clean_keyword,
        "brand": brand,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "page_url": page_url,
        "amp_url": amp_url,
        "serp": serp,
        "pages": analysis["pages"],
        "blueprint": blueprint,
        "insight": insight,
        "template": template,
        "plan": plan,
        "validation": {
            "amp": amp_result,
            "seo": seo_result,
        },
    }

    save_json(output_dir / "report.json", report)

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
        "report": report,
    }
