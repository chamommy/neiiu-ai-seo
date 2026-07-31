from ai.manager import AIManager


def generate_ai_recommendation(
    report: dict,
) -> dict:
    """
    Menghasilkan rekomendasi SEO menggunakan AI.
    """

    prompt = f"""
SEO SCORE:
{report["seo_score"]}

WORD COUNT:
{report["content"]["word_count"]}

KEYWORD DENSITY:
{report["content"]["keyword_density"]}

ENTITY COVERAGE:
{report["entity"]["coverage_percentage"]}

H1:
{report["page"]["headings"]["h1_count"]}

H2:
{report["page"]["headings"]["h2_count"]}

MASALAH:
{chr(10).join(report["problems"])}

REKOMENDASI:
{chr(10).join(report["recommendations"])}

Berikan:

1. Ringkasan singkat

2. 5 Prioritas utama

3. Action Plan

Gunakan bahasa Indonesia.
"""

    ai = AIManager()

    result = ai.ask(
        prompt=prompt,
        system_prompt=(
            "Kamu adalah SEO Expert."
            "Jawab singkat."
            "Fokus pada action plan."
        ),
    )

    return result