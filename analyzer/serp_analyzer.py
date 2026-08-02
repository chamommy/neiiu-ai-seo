"""
Analisis halaman pertama Google untuk satu keyword.

Alur:
1. Crawl setiap URL yang muncul di SERP.
2. Jalankan analyzer yang sudah ada (konten, heading, entity, skor).
3. Ambil sinyal teknis tambahan (schema, AMP, FAQ, tabel).
4. Rangkum semuanya jadi blueprint: pola yang dipakai halaman
   yang sedang menang di keyword tersebut.

Blueprint inilah yang jadi target ukuran untuk halaman baru.
"""

import re
import time
from collections import Counter
from statistics import median

from analyzer.cloak_detector import inspect_url, keyword_tokens
from analyzer.content_analyzer import analyze_content
from analyzer.entity_analyzer import analyze_entities
from analyzer.heading_analyzer import analyze_headings
from analyzer.page_signals import extract_signals
from analyzer.seo_score import analyze_seo
from config import (
    CLOAK_CHECK,
    CRAWL_DELAY_SECONDS,
    CRAWL_TOP_N,
    ENTITY_FILE,
    RULES_FILE,
)
from crawler.crawler import fetch_page
from knowledge.knowledge_loader import load_json
from parser.html_parser import parse_html


# Halaman yang lebih pendek dari ini tidak mungkin jadi model untuk
# apa pun, berapa pun peringkatnya.
MIN_USABLE_WORDS = 150


def check_usability(
    page: dict,
    keyword: str,
) -> tuple[bool, str]:
    """
    Menentukan apakah isi halaman layak dijadikan acuan target.

    Cloaking yang canggih tidak cuma memeriksa User-Agent, tapi juga
    memastikan request datang dari rentang IP Google. Terhadap
    halaman seperti itu, crawler ini tetap dilayani halaman aslinya
    atau halaman kosong, bukan konten yang sebenarnya ngerank.

    Hasilnya halaman peringkat satu bisa terbaca dua kata dan tanpa
    satu pun keyword di dalamnya. Membiarkannya ikut menghitung
    median akan menghasilkan target yang tidak masuk akal, jadi
    halaman semacam itu dikeluarkan.
    """
    word_count = page.get("word_count", 0)

    if word_count < MIN_USABLE_WORDS:
        return False, (
            f"Isi halaman hanya terbaca {word_count} kata. "
            "Kemungkinan besar konten aslinya tidak dilayani ke crawler."
        )

    tokens = keyword_tokens(keyword)

    if tokens:
        text = page.get("visible_text", "").lower()

        if not any(token in text for token in tokens):
            return False, (
                "Tidak ada satu pun kata dari keyword di halaman ini, "
                "padahal halaman ini ngerank untuk keyword tersebut. "
                "Isi yang diindeks Google berbeda dari yang kita terima."
            )

    return True, ""


STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada",
    "ini", "itu", "adalah", "atau", "juga", "bisa", "dapat",
    "the", "and", "for", "with", "you", "your", "are", "our",
    "situs", "link", "daftar", "login", "hari", "ini",
}


def crawl_serp_pages(
    serp_results: list[dict],
    keyword: str,
    limit: int = CRAWL_TOP_N,
    delay: float = CRAWL_DELAY_SECONDS,
    verbose: bool = True,
    on_page=None,
    cloak_check: bool = CLOAK_CHECK,
) -> list[dict]:
    """
    Meng-crawl dan menganalisis setiap hasil SERP.

    Halaman yang gagal diambil tetap dicatat dengan status error
    supaya analisis tidak berhenti hanya karena satu situs menolak
    request.
    """
    rules = load_json(RULES_FILE)
    entity_database = load_json(ENTITY_FILE)

    analyzed: list[dict] = []

    for item in serp_results[:limit]:
        position = item["position"]
        url = item["url"]

        if verbose:
            print(f"  [{position:>2}] {item['domain']} ... ", end="", flush=True)

        entry = {
            "position": position,
            "url": url,
            "domain": item["domain"],
            "serp_title": item.get("title", ""),
            "serp_snippet": item.get("snippet", ""),
            "status": "error",
            "error": "",
        }

        try:
            if cloak_check:
                inspection = inspect_url(url, keyword)
                crawl_result = inspection["indexed_crawl"]

                if crawl_result is None:
                    fetched = inspection["fetched"]

                    raise RuntimeError(
                        fetched["googlebot_error"]
                        or fetched["normal_error"]
                        or "Halaman tidak bisa diambil."
                    )

                page = inspection["indexed_page"]
                cloak = inspection["comparison"]
                hijack = inspection["hijack"]
            else:
                crawl_result = fetch_page(url)

                page = parse_html(
                    crawl_result["html"],
                    crawl_result["final_url"],
                )

                cloak = {"checked": False, "cloaking": False}

                hijack = {
                    "is_hijacked": False,
                    "confidence": 0,
                    "reasons": [],
                    "institutional": False,
                }

            html = crawl_result["html"]
            final_url = crawl_result["final_url"]

            signals = extract_signals(html, final_url)

            content = analyze_content(page=page, keyword=keyword)
            headings = analyze_headings(page=page, keyword=keyword)
            seo = analyze_seo(page, rules)

            entity = analyze_entities(
                text=page["visible_text"],
                keyword=keyword,
                entity_database=entity_database,
            )

            entry.update(
                {
                    "status": "ok",
                    "final_url": final_url,
                    "title": page["title"],
                    "title_length": page["title_length"],
                    "meta_description": page["meta_description"],
                    "meta_description_length": page[
                        "meta_description_length"
                    ],
                    "word_count": page["word_count"],
                    "headings": page["headings"],
                    "links": page["links"],
                    "images": page["images"],
                    "signals": signals,
                    "content": content,
                    "heading_analysis": headings,
                    "entity": entity,
                    "seo_score": seo["seo_score"],
                    "cloak": cloak,
                    "hijack": hijack,
                }
            )

            usable, reason = check_usability(page, keyword)

            entry["usable"] = usable
            entry["unusable_reason"] = reason

            if verbose:
                if hijack["is_hijacked"]:
                    print(
                        f"DOMAIN BAJAKAN ({hijack['confidence']}%) "
                        f"— dikeluarkan dari target"
                    )
                elif not usable:
                    print(
                        f"TIDAK TERBACA ({page['word_count']} kata) "
                        f"— dikeluarkan dari target"
                    )
                else:
                    print(
                        f"OK ({page['word_count']} kata, "
                        f"skor {seo['seo_score']})"
                    )

        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"

            if verbose:
                print(f"GAGAL ({type(error).__name__})")

        analyzed.append(entry)

        if on_page is not None:
            on_page(entry, len(analyzed), min(limit, len(serp_results)))

        if delay > 0:
            time.sleep(delay)

    return analyzed


def collect_heading_topics(
    pages: list[dict],
    keyword: str,
    top_n: int = 20,
) -> list[dict]:
    """
    Mencari tema heading yang paling sering dipakai kompetitor.

    Dihitung berdasarkan jumlah domain yang memakai kata itu,
    bukan jumlah kemunculan, supaya satu halaman dengan heading
    berulang tidak mendominasi hasil.
    """
    keyword_parts = set(keyword.lower().split())
    domain_usage: Counter = Counter()

    for page in pages:
        if page["status"] != "ok":
            continue

        headings = page["headings"]
        words: set[str] = set()

        for level in ("h2", "h3"):
            for heading in headings.get(level, []):
                for word in re.findall(r"[a-zA-Z0-9]+", heading.lower()):
                    if len(word) < 4:
                        continue

                    if word in STOPWORDS or word in keyword_parts:
                        continue

                    words.add(word)

        domain_usage.update(words)

    total_ok = sum(1 for page in pages if page["status"] == "ok") or 1

    return [
        {
            "term": term,
            "domain_count": count,
            "coverage_percentage": round(count / total_ok * 100, 1),
        }
        for term, count in domain_usage.most_common(top_n)
    ]


def collect_common_headings(
    pages: list[dict],
    top_n: int = 25,
) -> list[dict]:
    """
    Mengumpulkan H2 mentah dari seluruh kompetitor.

    Dipakai sebagai bahan mentah untuk AI menyusun outline,
    bukan untuk disalin apa adanya.
    """
    counter: Counter = Counter()

    for page in pages:
        if page["status"] != "ok":
            continue

        for heading in page["headings"].get("h2", []):
            clean = re.sub(r"\s+", " ", heading).strip()

            if 8 <= len(clean) <= 120:
                counter[clean] += 1

    return [
        {"heading": heading, "count": count}
        for heading, count in counter.most_common(top_n)
    ]


def safe_median(values: list) -> float:
    return round(median(values), 1) if values else 0.0


def build_blueprint(
    keyword: str,
    serp: dict,
    pages: list[dict],
) -> dict:
    """
    Merangkum karakteristik halaman yang ngerank jadi satu target.
    """
    crawled = [page for page in pages if page["status"] == "ok"]

    hijacked = [
        page
        for page in crawled
        if page.get("hijack", {}).get("is_hijacked")
    ]

    unreadable = [
        page
        for page in crawled
        if not page.get("hijack", {}).get("is_hijacked")
        and not page.get("usable", True)
    ]

    ok_pages = [
        page
        for page in crawled
        if not page.get("hijack", {}).get("is_hijacked")
        and page.get("usable", True)
    ]

    # Kalau tidak ada satu pun halaman yang layak, target tetap
    # dihitung dari apa yang ada. Angka yang meragukan masih lebih
    # berguna daripada tidak ada angka sama sekali, asal statusnya
    # ikut dilaporkan supaya tidak dikira sahih.
    hijack_fallback = not ok_pages and bool(crawled)

    if hijack_fallback:
        ok_pages = crawled

    top5 = [page for page in ok_pages if page["position"] <= 5]

    word_counts = [page["word_count"] for page in ok_pages]
    top5_words = [page["word_count"] for page in top5]

    title_lengths = [
        page["title_length"]
        for page in ok_pages
        if page["title_length"]
    ]

    meta_lengths = [
        page["meta_description_length"]
        for page in ok_pages
        if page["meta_description_length"]
    ]

    h2_counts = [
        page["headings"]["h2_count"] for page in ok_pages
    ]

    h3_counts = [
        page["headings"]["h3_count"] for page in ok_pages
    ]

    internal_links = [
        page["links"]["internal_count"] for page in ok_pages
    ]

    image_counts = [
        page["images"]["total"] for page in ok_pages
    ]

    densities = [
        page["content"]["keyword_density"] for page in ok_pages
    ]

    schema_counter: Counter = Counter()
    entity_counter: Counter = Counter()

    faq_pages = 0
    amp_pages = 0
    table_pages = 0

    for page in ok_pages:
        schema_counter.update(page["signals"]["schema_types"])

        if page["signals"]["faq"]["has_faq"]:
            faq_pages += 1

        if (
            page["signals"]["amp"]["is_amp"]
            or page["signals"]["amp"]["has_amp_version"]
        ):
            amp_pages += 1

        if page["signals"]["table_count"] > 0:
            table_pages += 1

        entity_counter.update(
            page["entity"].get("found_entities", [])
        )

    total_ok = len(ok_pages) or 1

    faq_questions: list[str] = []

    for page in ok_pages:
        faq_questions.extend(page["signals"]["faq"]["questions"])

    return {
        "keyword": keyword,
        "analyzed_pages": len(ok_pages),
        "failed_pages": len(pages) - len(crawled),
        "hijacked_count": len(hijacked),
        "unreadable_count": len(unreadable),
        "unreadable_pages": [
            {
                "position": page["position"],
                "domain": page["domain"],
                "word_count": page["word_count"],
                "reason": page.get("unusable_reason", ""),
            }
            for page in unreadable
        ],
        "hijack_fallback": hijack_fallback,
        "hijacked_pages": [
            {
                "position": page["position"],
                "domain": page["domain"],
                "confidence": page["hijack"]["confidence"],
                "cloaking": page.get("cloak", {}).get("cloaking", False),
                "reasons": page["hijack"]["reasons"],
            }
            for page in hijacked
        ],
        "target": {
            "word_count_median": safe_median(word_counts),
            "word_count_top5_median": safe_median(top5_words),
            "word_count_max": max(word_counts) if word_counts else 0,
            "title_length_median": safe_median(title_lengths),
            "meta_length_median": safe_median(meta_lengths),
            "h2_median": safe_median(h2_counts),
            "h3_median": safe_median(h3_counts),
            "internal_links_median": safe_median(internal_links),
            "images_median": safe_median(image_counts),
            "keyword_density_median": safe_median(densities),
        },
        "adoption": {
            "faq_percentage": round(faq_pages / total_ok * 100, 1),
            "amp_percentage": round(amp_pages / total_ok * 100, 1),
            "table_percentage": round(table_pages / total_ok * 100, 1),
        },
        "common_schema_types": [
            {
                "type": schema_type,
                "domain_count": count,
                "coverage_percentage": round(
                    count / total_ok * 100, 1
                ),
            }
            for schema_type, count in schema_counter.most_common(10)
        ],
        "common_entities": [
            {"entity": entity, "domain_count": count}
            for entity, count in entity_counter.most_common(15)
        ],
        # Tema dan heading diambil dari halaman bersih saja, supaya
        # kosakata halaman institusi yang dibajak tidak ikut jadi
        # acuan konten.
        "heading_topics": collect_heading_topics(ok_pages, keyword),
        "common_headings": collect_common_headings(ok_pages),
        "competitor_questions": faq_questions[:25],
        "people_also_ask": serp.get("people_also_ask", []),
        "related_searches": serp.get("related_searches", []),
    }


def analyze_serp(
    keyword: str,
    serp: dict,
    limit: int = CRAWL_TOP_N,
    verbose: bool = True,
    on_page=None,
) -> dict:
    """
    Pipeline lengkap analisis SERP untuk satu keyword.
    """
    if verbose:
        print(
            f"\nMeng-crawl {min(limit, len(serp['results']))} "
            f"halaman teratas..."
        )

    pages = crawl_serp_pages(
        serp_results=serp["results"],
        keyword=keyword,
        limit=limit,
        verbose=verbose,
        on_page=on_page,
    )

    blueprint = build_blueprint(keyword, serp, pages)

    return {
        "keyword": keyword,
        "serp": serp,
        "pages": pages,
        "blueprint": blueprint,
    }
