import json
import re
from datetime import datetime
from pathlib import Path

import requests

from analyzer.entity_analyzer import analyze_entities
from analyzer.seo_score import analyze_seo
from analyzer.content_analyzer import analyze_content
from analyzer.content_recommendation import recommend_content
from config import ENTITY_FILE, REPORTS_DIR, RULES_FILE
from crawler.crawler import fetch_page
from knowledge.knowledge_loader import load_json
from models.intent_predictor import (
    load_intent_model,
    predict_intent,
)
from parser.html_parser import parse_html


def normalize_url(url: str) -> str:
    url = url.strip()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def create_report_filename(url: str) -> str:
    safe_name = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        url,
    ).strip("_")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"{safe_name}_{timestamp}.json"


def save_report(report: dict) -> Path:
    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = create_report_filename(
        report["final_url"]
    )

    output_path = REPORTS_DIR / filename

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def print_entity_result(entity_result: dict) -> None:
    print("\n" + "=" * 60)
    print("ENTITY ANALYSIS")
    print("=" * 60)

    if not entity_result["topic_found"]:
        print(entity_result["message"])
        return

    print(f"Topik        : {entity_result['topic']}")
    print(
        f"Coverage     : "
        f"{entity_result['coverage_percentage']}%"
    )
    print(
        f"Found        : "
        f"{entity_result['found_count']}"
    )
    print(
        f"Missing      : "
        f"{entity_result['missing_count']}"
    )
    print(
        f"Total Entity : "
        f"{entity_result['total_entities']}"
    )

    print("\nEntity ditemukan:")

    if entity_result["found_entities"]:
        for item in entity_result["found_entities"]:
            print(f"- {item}")
    else:
        print("- Tidak ada")

    print("\nEntity belum ditemukan:")

    if entity_result["missing_entities"]:
        for item in entity_result["missing_entities"]:
            print(f"- {item}")
    else:
        print("- Semua entity ditemukan")


def print_result(report: dict) -> None:
    page = report["page"]

    print("\n" + "=" * 60)
    print("NEIIIU AI SEO — AUDIT RESULT")
    print("=" * 60)

    print(f"URL            : {report['final_url']}")
    print(f"Status         : {report['status_code']}")
    print(f"Keyword        : {report['keyword']}")
    print(
        f"Intent         : "
        f"{report['intent']['intent']}"
    )

    print(
        f"Confidence     : "
        f"{report['intent']['confidence']}%"
    )
    print(f"SEO Score      : {report['seo_score']}/100")
    print(f"Title          : {page['title'] or 'Tidak ada'}")
    print(
        f"Meta           : "
        f"{page['meta_description'] or 'Tidak ada'}"
    )
    print(f"Jumlah kata    : {page['word_count']}")
    print(
        f"Jumlah H1      : "
        f"{page['headings']['h1_count']}"
    )
    print(
        f"Jumlah H2      : "
        f"{page['headings']['h2_count']}"
    )
    print(
        f"Internal link  : "
        f"{page['links']['internal_count']}"
    )
    print(
        f"External link  : "
        f"{page['links']['external_count']}"
    )

    print("\nMasalah:")

    if report["problems"]:
        for problem in report["problems"]:
            print(f"- {problem}")
    else:
        print("- Tidak ditemukan masalah utama")

    print("\nRekomendasi:")

    if report["recommendations"]:
        for recommendation in report["recommendations"]:
            print(f"- {recommendation}")
    else:
        print("- Tidak ada rekomendasi utama")

    print_entity_result(
        report["entity"]
    )

    print_content_result(
        report["content"]
    )

    print_content_recommendation(
        report["content_recommendation"]
    )

def print_content_recommendation(result: dict) -> None:
    print("\n" + "=" * 60)
    print("CONTENT RECOMMENDATION")
    print("=" * 60)

    print("\nMasalah:")

    if result["problems"]:
        for item in result["problems"]:
            print(f"- {item}")
    else:
        print("- Tidak ditemukan masalah utama")

    print("\nRekomendasi:")

    if result["recommendations"]:
        for item in result["recommendations"]:
            print(f"- {item}")
    else:
        print("- Tidak ada rekomendasi utama")

def print_content_result(content: dict):

    print("\n" + "=" * 60)
    print("CONTENT ANALYSIS")
    print("=" * 60)

    print(f"Word Count            : {content['word_count']}")
    print(f"Reading Time          : {content['reading_time']} menit")
    print(f"Keyword Count         : {content['keyword_count']}")
    print(f"Keyword Density       : {content['keyword_density']}%")
    print(f"Keyword in Title      : {content['keyword_in_title']}")
    print(f"Keyword in Meta       : {content['keyword_in_meta']}")
    print(f"Keyword in H1         : {content['keyword_in_h1']}")
    print(f"Paragraph Count       : {content['paragraph_count']}")
    print(
    f"Longest Paragraph     : "
    f"{content['longest_paragraph_length']} kata"
    )
    print(
        f"Average Paragraph     : "
        f"{content['average_paragraph_length']} kata"
    )

def main() -> None:
    url = normalize_url(
        input("Masukkan URL website: ")
    )

    keyword = input(
        "Masukkan keyword utama: "
    ).strip().lower()

    if not keyword:
        print("ERROR: Keyword tidak boleh kosong.")
        return

    try:
        crawl_result = fetch_page(url)

        page_data = parse_html(
            crawl_result["html"],
            crawl_result["final_url"],
        )

        rules = load_json(
            RULES_FILE
        )

        analysis = analyze_seo(
            page_data,
            rules,
        )

        entity_database = load_json(
            ENTITY_FILE
        )

        entity_result = analyze_entities(
            text=page_data["visible_text"],
            keyword=keyword,
            entity_database=entity_database,
        )

        intent_model = load_intent_model()

        intent_result = predict_intent(
            keyword=keyword,
            model=intent_model,
        )

        content_result = analyze_content(
        page=page_data,
        keyword=keyword,
        )

        content_recommendation = recommend_content(
            content_result
        )

        
        report = {
            "analyzed_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "requested_url": crawl_result["requested_url"],
            "final_url": crawl_result["final_url"],
            "status_code": crawl_result["status_code"],
            "content_type": crawl_result["content_type"],
            "keyword": keyword,
            "intent": intent_result,
            "content": content_result,
            "content_recommendation": content_recommendation,
            "seo_score": analysis["seo_score"],
            "page": page_data,
            "entity": entity_result,
            "problems": analysis["problems"],
            "recommendations": analysis["recommendations"],
        }

        report_path = save_report(
            report
        )

        print_result(
            report
        )

        print(
            f"\nLaporan tersimpan di:\n"
            f"{report_path.resolve()}"
        )

    except requests.exceptions.Timeout:
        print(
            "ERROR: Website terlalu lama merespons."
        )

    except requests.exceptions.HTTPError as error:
        print(
            f"ERROR HTTP: {error}"
        )

    except requests.exceptions.SSLError:
        print(
            "ERROR: Sertifikat SSL website bermasalah."
        )

    except requests.exceptions.RequestException as error:
        print(
            f"ERROR koneksi: {error}"
        )

    except FileNotFoundError as error:
        print(
            f"ERROR file: {error}"
        )

    except json.JSONDecodeError as error:
        print(
            f"ERROR format JSON: {error}"
        )

    except KeyError as error:
        print(
            f"ERROR key data tidak ditemukan: {error}"
        )

    except Exception as error:
        print(
            f"ERROR tidak terduga: {error}"
        )


if __name__ == "__main__":
    main()