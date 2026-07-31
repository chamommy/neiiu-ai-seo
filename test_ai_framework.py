from ai.manager import AIManager
from ai.prompt_builder import PromptBuilder
from ai.prompts import SEO_SYSTEM_PROMPT
from ai.response_parser import parse_seo_response
from ai.schemas import SEO_ACTION_PLAN_SCHEMA


TEST_REPORT = {
    "final_url": "https://example.com",
    "keyword": "belajar seo",
    "intent": {
        "intent": "informational",
        "confidence": 81.5,
    },
    "seo_score": 72,
    "content": {
        "word_count": 950,
        "keyword_density": 3.4,
        "keyword_in_title": True,
        "keyword_in_meta": False,
        "keyword_in_h1": False,
        "paragraph_count": 10,
    },
    "heading_analysis": {
        "heading_score": 65,
        "h1_count": 2,
        "h2_count": 3,
        "h3_count": 0,
        "problems": [
            "Ditemukan 2 H1",
            "Keyword tidak ditemukan di H1",
        ],
    },
    "entity": {
        "topic_found": True,
        "coverage_percentage": 45,
        "missing_entities": [
            "canonical",
            "schema markup",
            "internal link",
        ],
    },
    "page": {
        "links": {
            "internal_count": 4,
            "external_count": 2,
        },
    },
    "knowledge_analysis": {
        "gaps": {
            "word_count": 1250,
            "entity_coverage": 35,
            "internal_links": 11,
        },
        "missing_must_have": [
            "faq",
            "schema",
            "canonical",
        ],
    },
    "problems": [
        "Meta description terlalu pendek",
        "Canonical tidak ditemukan",
    ],
    "recommendations": [
        "Tambahkan canonical",
        "Perbaiki meta description",
    ],
}

def main() -> None:
    system_prompt, prompt = (
        PromptBuilder.build_seo_prompt(
            TEST_REPORT
        )
    )

    ai = AIManager(
        provider="ollama",
        model="qwen3:4b",
    )

    print("AI sedang menganalisis report...\n")

    print("=" * 60)
    print("PROMPT YANG DIKIRIM KE AI")
    print("=" * 60)
    print(prompt)
    print("=" * 60)

    raw_result = ai.ask(
        prompt=prompt,
        system_prompt=system_prompt,
        response_schema=SEO_ACTION_PLAN_SCHEMA,
    )

    print("\nRAW RESPONSE")
    print("=" * 60)
    print(raw_result["content"])
    print("=" * 60)

    result = parse_seo_response(
        raw_result
    )

    print("=" * 60)
    print("NEIIIU AI SEO — FRAMEWORK TEST")
    print("=" * 60)

    print("\nRingkasan:")
    print(result["summary"])

    print("\nAction Plan:")

    for item in result["action_plan"]:
        print(
            f"{item['priority']}. "
            f"{item['title']}"
        )
        print(
            f"   {item['description']}"
        )

    print("\nPeringatan:")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"- {warning}")
    else:
        print("- Tidak ada")

    metadata = result["metadata"]

    print(
        f"\nProvider : {metadata['provider']}"
    )
    print(
        f"Model    : {metadata['model']}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")