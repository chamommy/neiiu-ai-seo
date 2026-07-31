import json
import re
from datetime import datetime
from pathlib import Path

import requests

from ai.manager import AIManager
from ai.prompt_builder import PromptBuilder
from ai.response_parser import parse_seo_response
from ai.schemas import SEO_ACTION_PLAN_SCHEMA
from analyzer.content_analyzer import analyze_content
from analyzer.content_recommendation import recommend_content
from analyzer.entity_analyzer import analyze_entities
from analyzer.heading_analyzer import analyze_headings
from analyzer.knowledge_analyzer import analyze_knowledge_gap
from analyzer.seo_score import analyze_seo
from config import (
    ENTITY_FILE,
    KNOWLEDGE_FILE,
    REPORTS_DIR,
    RULES_FILE,
)
from crawler.crawler import fetch_page
from knowledge.knowledge_engine import (
    get_topic,
    load_knowledge,
)
from knowledge.knowledge_loader import load_json
from models.intent_predictor import (
    load_intent_model,
    predict_intent,
)
from parser.html_parser import parse_html


AI_PROVIDER = "ollama"
AI_MODEL = "qwen3:4b-instruct"


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

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

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


def generate_ai_analysis(report: dict) -> dict:
    """
    Mengirim hasil audit ke AI lokal melalui AI Manager.

    Kalau Ollama gagal, audit utama tetap berjalan dan
    informasi error disimpan di report.
    """
    try:
        system_prompt, user_prompt = (
            PromptBuilder.build_seo_prompt(
                report
            )
        )

        ai = AIManager(
            provider=AI_PROVIDER,
            model=AI_MODEL,
        )

        raw_result = ai.ask(
            prompt=user_prompt,
            system_prompt=system_prompt,
            response_schema=SEO_ACTION_PLAN_SCHEMA,
        )

        parsed_result = parse_seo_response(
            raw_result
        )

        return {
            "status": "success",
            **parsed_result,
        }

    except Exception as error:
        return {
            "status": "error",
            "message": str(error),
            "summary": "",
            "action_plan": [],
            "warnings": [],
            "metadata": {
                "provider": AI_PROVIDER,
                "model": AI_MODEL,
                "prompt_tokens": 0,
                "output_tokens": 0,
            },
        }


def print_entity_result(
    entity_result: dict,
) -> None:
    print("\n" + "=" * 60)
    print("ENTITY ANALYSIS")
    print("=" * 60)

    if not entity_result["topic_found"]:
        print(entity_result["message"])
        return

    print(
        f"Topik        : "
        f"{entity_result['topic']}"
    )
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


def print_content_result(
    content: dict,
) -> None:
    print("\n" + "=" * 60)
    print("CONTENT ANALYSIS")
    print("=" * 60)

    print(
        f"Word Count            : "
        f"{content['word_count']}"
    )
    print(
        f"Reading Time          : "
        f"{content['reading_time']} menit"
    )
    print(
        f"Keyword Count         : "
        f"{content['keyword_count']}"
    )
    print(
        f"Keyword Density       : "
        f"{content['keyword_density']}%"
    )
    print(
        f"Keyword in Title      : "
        f"{content['keyword_in_title']}"
    )
    print(
        f"Keyword in Meta       : "
        f"{content['keyword_in_meta']}"
    )
    print(
        f"Keyword in H1         : "
        f"{content['keyword_in_h1']}"
    )
    print(
        f"Paragraph Count       : "
        f"{content['paragraph_count']}"
    )
    print(
        f"Longest Paragraph     : "
        f"{content['longest_paragraph_length']} kata"
    )
    print(
        f"Average Paragraph     : "
        f"{content['average_paragraph_length']} kata"
    )


def print_content_recommendation(
    result: dict,
) -> None:
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


def print_heading_result(
    result: dict,
) -> None:
    print("\n" + "=" * 60)
    print("HEADING ANALYSIS")
    print("=" * 60)

    print(
        f"Heading Score  : "
        f"{result['heading_score']}/100"
    )
    print(
        f"Jumlah H1      : "
        f"{result['h1_count']}"
    )
    print(
        f"Jumlah H2      : "
        f"{result['h2_count']}"
    )
    print(
        f"Jumlah H3      : "
        f"{result['h3_count']}"
    )
    print(
        f"Keyword di H1  : "
        f"{result['keyword_in_h1']}"
    )
    print(
        f"Keyword di H2  : "
        f"{result['keyword_in_h2']}"
    )
    print(
        f"Keyword di H3  : "
        f"{result['keyword_in_h3']}"
    )

    print("\nMasalah heading:")

    if result["problems"]:
        for problem in result["problems"]:
            print(f"- {problem}")
    else:
        print("- Tidak ditemukan masalah utama")

    print("\nRekomendasi heading:")

    if result["recommendations"]:
        for recommendation in result["recommendations"]:
            print(f"- {recommendation}")
    else:
        print("- Struktur heading sudah cukup baik")


def print_knowledge_result(
    result: dict,
) -> None:
    print("\n" + "=" * 60)
    print("KNOWLEDGE GAP ANALYSIS")
    print("=" * 60)

    print("\nCurrent Metrics:")

    for key, value in result[
        "current_metrics"
    ].items():
        print(f"- {key}: {value}")

    print("\nGaps:")

    for key, value in result["gaps"].items():
        print(f"- {key}: {value}")

    print("\nMissing Must-Have:")

    if result["missing_must_have"]:
        for item in result["missing_must_have"]:
            print(f"- {item}")
    else:
        print("- Tidak ada")

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


def print_ai_result(
    result: dict,
) -> None:
    print("\n" + "=" * 60)
    print("NEIIIU AI SEO — AI ACTION PLAN")
    print("=" * 60)

    if result.get("status") != "success":
        print("\nAI Analysis gagal:")
        print(
            result.get(
                "message",
                "Error AI tidak diketahui.",
            )
        )
        print(
            "\nAudit biasa tetap berhasil "
            "dan laporan tetap disimpan."
        )
        return

    print("\nRingkasan:")
    print(
        result.get(
            "summary",
            "Tidak ada ringkasan.",
        )
    )

    print("\nPrioritas Utama:")

    action_plan = result.get(
        "action_plan",
        [],
    )

    if action_plan:
        for item in action_plan:
            print(
                f"{item['priority']}. "
                f"{item['title']}"
            )
            print(
                f"   {item['description']}"
            )
    else:
        print("- Tidak ada action plan")

    print("\nPeringatan:")

    warnings = result.get(
        "warnings",
        [],
    )

    if warnings:
        for warning in warnings:
            print(f"- {warning}")
    else:
        print("- Tidak ada")

    metadata = result.get(
        "metadata",
        {},
    )

    print(
        f"\nProvider : "
        f"{metadata.get('provider', AI_PROVIDER)}"
    )
    print(
        f"Model    : "
        f"{metadata.get('model', AI_MODEL)}"
    )
    print(
        f"Tokens   : "
        f"{metadata.get('prompt_tokens', 0)} prompt, "
        f"{metadata.get('output_tokens', 0)} output"
    )


def print_result(report: dict) -> None:
    page = report["page"]

    print("\n" + "=" * 60)
    print("NEIIIU AI SEO — AUDIT RESULT")
    print("=" * 60)

    print(
        f"URL            : "
        f"{report['final_url']}"
    )
    print(
        f"Status         : "
        f"{report['status_code']}"
    )
    print(
        f"Keyword        : "
        f"{report['keyword']}"
    )
    print(
        f"Intent         : "
        f"{report['intent']['intent']}"
    )
    print(
        f"Confidence     : "
        f"{report['intent']['confidence']}%"
    )
    print(
        f"SEO Score      : "
        f"{report['seo_score']}/100"
    )
    print(
        f"Title          : "
        f"{page['title'] or 'Tidak ada'}"
    )
    print(
        f"Meta           : "
        f"{page['meta_description'] or 'Tidak ada'}"
    )
    print(
        f"Jumlah kata    : "
        f"{page['word_count']}"
    )
    print(
        f"Jumlah H1      : "
        f"{page['headings']['h1_count']}"
    )
    print(
        f"Jumlah H2      : "
        f"{page['headings']['h2_count']}"
    )
    print(
        f"Jumlah H3      : "
        f"{page['headings'].get('h3_count', 0)}"
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
        for recommendation in report[
            "recommendations"
        ]:
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

    print_heading_result(
        report["heading_analysis"]
    )

    print_knowledge_result(
        report["knowledge_analysis"]
    )

    print_ai_result(
        report["ai_analysis"]
    )


def main() -> None:
    url = normalize_url(
        input("Masukkan URL website: ")
    )

    keyword = input(
        "Masukkan keyword utama: "
    ).strip().lower()

    if not keyword:
        print(
            "ERROR: Keyword tidak boleh kosong."
        )
        return

    try:
        print(
            "\nMengambil dan menganalisis halaman..."
        )

        crawl_result = fetch_page(
            url
        )

        page_data = parse_html(
            crawl_result["html"],
            crawl_result["final_url"],
        )

        rules = load_json(
            RULES_FILE
        )

        seo_analysis = analyze_seo(
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

        content_recommendation = (
            recommend_content(
                content_result
            )
        )

        heading_result = analyze_headings(
            page=page_data,
            keyword=keyword,
        )

        knowledge = load_knowledge(
            KNOWLEDGE_FILE
        )

        topic_knowledge = get_topic(
            knowledge,
            "seo",
        )

        knowledge_input = {
            "content": content_result,
            "heading_analysis": heading_result,
            "entity": entity_result,
            "page": page_data,
        }

        knowledge_result = (
            analyze_knowledge_gap(
                report_data=knowledge_input,
                topic_knowledge=topic_knowledge,
            )
        )

        report = {
            "analyzed_at": (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ),
            "requested_url": (
                crawl_result["requested_url"]
            ),
            "final_url": (
                crawl_result["final_url"]
            ),
            "status_code": (
                crawl_result["status_code"]
            ),
            "content_type": (
                crawl_result["content_type"]
            ),
            "keyword": keyword,
            "intent": intent_result,
            "seo_score": (
                seo_analysis["seo_score"]
            ),
            "page": page_data,
            "entity": entity_result,
            "content": content_result,
            "content_recommendation": (
                content_recommendation
            ),
            "heading_analysis": (
                heading_result
            ),
            "knowledge_analysis": (
                knowledge_result
            ),
            "problems": (
                seo_analysis["problems"]
            ),
            "recommendations": (
                seo_analysis[
                    "recommendations"
                ]
            ),
        }

        print(
            "\nAudit selesai. "
            "AI sedang membuat action plan..."
        )

        ai_result = generate_ai_analysis(
            report
        )

        report["ai_analysis"] = (
            ai_result
        )

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
        status_code = (
            error.response.status_code
            if error.response is not None
            else "unknown"
        )

        print(
            f"ERROR HTTP {status_code}: "
            "Server website menolak atau gagal "
            "memproses request."
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