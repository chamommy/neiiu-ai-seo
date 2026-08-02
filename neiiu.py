"""
NEIIU — pipeline keyword ke landing page + AMP (antarmuka terminal).

Logika pipelinenya ada di services/neiiu_pipeline.py supaya bisa
dipakai bersama oleh web app. File ini hanya mengurus argumen
baris perintah dan menampilkan hasilnya.

Contoh pakai:
    python neiiu.py "slot gacor"
    python neiiu.py "slot online" --limit 10 --no-cache
    python neiiu.py "slot gacor" --reference https://contoh.com/halaman
    python neiiu.py "slot gacor" --analyze-only
"""

import argparse
import sys

from config import CRAWL_TOP_N, SERP_PROVIDER, SERP_TOP_N
from serp.providers import SerpProviderError
from services.neiiu_pipeline import PipelineError, run_neiiu


LINE = "=" * 64


def heading(text: str) -> None:
    # flush dipaksa supaya progres tetap terlihat saat output
    # di-pipe ke file atau terminal lain.
    print(f"\n{LINE}\n{text}\n{LINE}", flush=True)


def on_event(event: dict) -> None:
    """
    Menampilkan kemajuan pipeline saat sedang berjalan.
    """
    step = event["step"]
    status = event["status"]
    message = event["message"]

    if status == "start":
        heading(
            f"LANGKAH {step}/{event['total']} — "
            f"{event['label'].upper()}"
        )

    elif status == "info":
        print(f"  {message}", flush=True)

    elif status == "done" and message:
        print(f"  selesai: {message}", flush=True)


def print_serp(serp: dict) -> None:
    heading("HASIL PENCARIAN GOOGLE")

    source = "cache" if serp["from_cache"] else serp["provider"]

    print(f"Keyword  : {serp['keyword']}")
    print(f"Sumber   : {source}")
    print(f"Diambil  : {serp['fetched_at']}")
    print(f"Hasil    : {len(serp['results'])} URL\n")

    for item in serp["results"]:
        print(f"  {item['position']:>2}. {item['domain']}")
        print(f"      {item['url']}")


def print_blueprint(blueprint: dict) -> None:
    heading("TARGET DARI HALAMAN PERTAMA")

    target = blueprint["target"]
    adoption = blueprint["adoption"]

    print(f"Halaman dipakai      : {blueprint['analyzed_pages']}")
    print(f"Halaman gagal        : {blueprint['failed_pages']}")
    print(f"Domain bajakan       : {blueprint.get('hijacked_count', 0)}")
    print(f"Isi tidak terbaca    : {blueprint.get('unreadable_count', 0)}")
    print(f"Median kata          : {target['word_count_median']}")
    print(f"Median kata (top 5)  : {target['word_count_top5_median']}")
    print(f"Median H2            : {target['h2_median']}")
    print(f"Median internal link : {target['internal_links_median']}")
    print(f"Median panjang title : {target['title_length_median']}")
    print(f"Pakai FAQ            : {adoption['faq_percentage']}%")
    print(f"Pakai AMP            : {adoption['amp_percentage']}%")
    print(f"Pakai tabel          : {adoption['table_percentage']}%")

    if blueprint["common_schema_types"]:
        print("\nSchema yang umum dipakai:")

        for item in blueprint["common_schema_types"][:6]:
            print(
                f"  - {item['type']} "
                f"({item['coverage_percentage']}% halaman)"
            )

    print_hijacked(blueprint)


def print_hijacked(blueprint: dict) -> None:
    unreadable = blueprint.get("unreadable_pages", [])

    if unreadable:
        heading("HALAMAN YANG ISINYA TIDAK BISA DIBACA")

        print(
            "Halaman berikut ngerank, tapi isi yang kita terima bukan\n"
            "isi yang diindeks Google. Cloaking canggih memeriksa juga\n"
            "IP Googlebot, bukan cuma User-Agent, jadi crawler ini\n"
            "tetap dilayani halaman kosong atau halaman aslinya.\n"
            "Semuanya dikeluarkan dari perhitungan target.\n"
        )

        for item in unreadable:
            print(
                f"[{item['position']}] {item['domain']} "
                f"— {item['word_count']} kata"
            )
            print(f"    {item['reason']}")
            print()

    hijacked = blueprint.get("hijacked_pages", [])

    if not hijacked:
        print_fallback_warning(blueprint)
        return

    heading("DOMAIN BAJAKAN TERDETEKSI")

    print(
        f"{len(hijacked)} dari halaman pertama berdiri di domain "
        "milik pihak lain yang dibobol.\n"
        "Halaman-halaman ini tidak dipakai untuk menghitung target,\n"
        "karena mereka ngerank lewat otoritas domain curian, bukan\n"
        "karena struktur halamannya.\n"
    )

    for item in hijacked:
        flag = " [cloaking]" if item["cloaking"] else ""

        print(
            f"[{item['position']}] {item['domain']} "
            f"— keyakinan {item['confidence']}%{flag}"
        )

        for reason in item["reasons"]:
            print(f"    - {reason}")

        print()

    print_fallback_warning(blueprint)


def print_fallback_warning(blueprint: dict) -> None:
    if not blueprint.get("hijack_fallback"):
        return

    heading("PERINGATAN SERIUS")

    print(
        "Tidak ada satu pun halaman pertama yang layak dijadikan\n"
        "acuan. Semuanya berupa domain bajakan, halaman yang isinya\n"
        "tidak terbaca, atau keduanya.\n\n"
        "Target metrik di atas terpaksa dihitung dari data itu, jadi\n"
        "angkanya TIDAK bisa dipercaya. Halaman yang dibuat dari\n"
        "target ini kemungkinan besar tidak masuk akal.\n\n"
        "Yang sebaiknya dilakukan:\n"
        "  - Tentukan halaman acuan sendiri: --reference <url>\n"
        "  - Atau pakai --provider manual dan isi sendiri daftar\n"
        "    kompetitor asli yang kamu tahu di serp_manual.json"
    )


def print_insight(insight: dict) -> None:
    heading("ANALISIS RANKING HALAMAN PERTAMA")

    if insight.get("status") == "fallback":
        print(
            "Catatan: AI tidak tersedia, analisis disusun "
            "langsung dari data crawl.\n"
        )

    print(f"Intent  : {insight.get('search_intent', '-')}\n")
    print(f"{insight.get('serp_summary', '-')}\n")

    for item in insight.get("ranking_analysis", []):
        print(f"[{item['position']}] {item['domain']}")
        print(f"    {item['why_ranking']}")

        for strength in item.get("strengths", []):
            print(f"    + {strength}")

        for weakness in item.get("weaknesses", []):
            print(f"    - {weakness}")

        print()

    print("Celah konten yang bisa diambil:")

    for gap in insight.get("content_gaps", []):
        print(f"  - {gap}")

    print("\nStrategi menang:")

    for step in insight.get("winning_strategy", []):
        print(f"  - {step}")


def print_validation(
    amp_result: dict,
    seo_result: dict,
) -> None:
    heading("VALIDASI HALAMAN")

    status = "VALID" if amp_result["valid"] else "INVALID"

    print(f"AMP        : {status}")
    print(
        f"CSS AMP    : {amp_result['css_bytes']} / "
        f"{amp_result['css_limit']} byte"
    )

    for error in amp_result["errors"]:
        print(f"  ERROR   : {error}")

    for warning in amp_result["warnings"]:
        print(f"  WARNING : {warning}")

    print(f"\nSkor SEO   : {seo_result['score']}/100")
    print(
        f"Jumlah kata: {seo_result['word_count']} "
        f"(target {seo_result['word_target']})"
    )
    print(f"Density    : {seo_result['keyword_density']}%")

    if seo_result["problems"]:
        print("\nMasih perlu diperbaiki:")

        for problem in seo_result["problems"]:
            print(f"  - {problem}")

    print("\nSudah sesuai:")

    for item in seo_result["passed"]:
        print(f"  + {item}")


def print_result(result: dict) -> None:
    """
    Menampilkan laporan lengkap setelah pipeline selesai.
    """
    print_serp(result["serp"])
    print_blueprint(result["analysis"]["blueprint"])
    print_insight(result["insight"])

    if result["analyze_only"]:
        heading("SELESAI (MODE ANALISIS SAJA)")
        print(f"Hasil tersimpan di:\n{result['output_dir']}")
        return

    plan = result["plan"]
    brand = result["brand"]

    heading("KONTEN YANG DIBUAT")
    print(f"Brand   : {brand['site_name']}")
    print(f"Domain  : {brand['base_url']}")
    print(f"Keyword : {result['keyword']}")
    print(f"Title   : {plan['title']}")
    print(f"Meta    : {plan['meta_description']}")
    print(f"Slug    : {plan['slug']}")
    print(f"URL     : {result['page_url']}")
    print(f"Section : {len(plan['sections'])}")
    print(f"FAQ     : {len(plan['faq'])}")

    print_validation(
        result["amp_result"],
        result["seo_result"],
    )

    heading("SELESAI")
    print(f"Folder hasil:\n{result['output_dir']}\n")
    print("Isi folder:")
    print("  index.html      — landing page kanonik")
    print("  amp/index.html  — versi AMP")
    print("  sitemap.xml     — sitemap dua URL di atas")
    print("  ANALISIS.md     — kenapa rank 1-10 bisa naik")
    print("  report.json     — seluruh data mentah")
    print(
        "\nSebelum diunggah, ganti SITE_BASE_URL di .env supaya "
        "canonical dan sitemap memakai domain asli."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neiiu",
        description=(
            "Menganalisis halaman pertama Google untuk satu keyword, "
            "lalu membuat landing page dan AMP baru dari pola yang "
            "dipakai halaman yang sedang ngerank."
        ),
    )

    parser.add_argument(
        "keyword",
        help="Keyword yang mau dianalisis, contoh: \"slot gacor\"",
    )

    parser.add_argument(
        "--brand",
        default="",
        help=(
            "Nama brand yang muncul di halaman, contoh: ABECE. "
            "Berbeda dari keyword, yang merupakan topik pencarian. "
            "Kalau kosong, dipakai SITE_NAME dari .env"
        ),
    )

    parser.add_argument(
        "--base-url",
        default="",
        help=(
            "Domain brand ini, contoh: https://abece.com. "
            "Dipakai untuk canonical, sitemap, dan structured data. "
            "Kalau kosong, dipakai SITE_BASE_URL dari .env"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=SERP_TOP_N,
        help=f"Jumlah hasil SERP yang diambil (default {SERP_TOP_N})",
    )

    parser.add_argument(
        "--crawl",
        type=int,
        default=CRAWL_TOP_N,
        help=f"Jumlah halaman yang di-crawl (default {CRAWL_TOP_N})",
    )

    parser.add_argument(
        "--provider",
        default=SERP_PROVIDER,
        choices=["serper", "google_cse", "manual"],
        help=f"Sumber data SERP (default {SERP_PROVIDER})",
    )

    parser.add_argument(
        "--reference",
        default="",
        help="URL halaman acuan template, kalau mau memilih sendiri",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Paksa ambil SERP baru, abaikan cache",
    )

    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Berhenti setelah analisis, tanpa membuat halaman",
    )

    return parser


def main() -> int:
    # Terminal Windows default memakai cp1252 dan mengacak karakter
    # seperti em dash saat output dialihkan ke file.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = build_parser()
    args = parser.parse_args()

    try:
        result = run_neiiu(
            keyword=args.keyword,
            brand_name=args.brand,
            base_url=args.base_url,
            limit=args.limit,
            crawl=args.crawl,
            provider=args.provider,
            reference=args.reference,
            use_cache=not args.no_cache,
            analyze_only=args.analyze_only,
            on_event=on_event,
        )

    except SerpProviderError as error:
        print(f"\nERROR SERP: {error}")
        print(
            "\nTanpa API key, jalankan dengan provider manual:\n"
            "  1. Salin URL hasil pencarian Google ke "
            "database/serp_manual.json\n"
            f'  2. Format: {{"{args.keyword}": ["https://...", ...]}}\n'
            f'  3. Jalankan: python neiiu.py "{args.keyword}" '
            "--provider manual"
        )
        return 1

    except PipelineError as error:
        print(f"\nERROR: {error}")
        return 1

    except KeyboardInterrupt:
        print("\nDibatalkan.")
        return 130

    except Exception as error:
        print(
            f"\nERROR tidak terduga: {type(error).__name__}: {error}"
        )
        return 1

    print_result(result)

    if result["analyze_only"]:
        return 0

    return 0 if result["amp_valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
