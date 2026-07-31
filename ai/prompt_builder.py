from ai.prompts import SEO_SYSTEM_PROMPT


class PromptBuilder:
    """
    Membuat prompt ringkas dari report SEO.
    """

    @staticmethod
    def build_seo_prompt(
        report: dict,
    ) -> tuple[str, str]:
        content = report.get(
            "content",
            {},
        )

        heading = report.get(
            "heading_analysis",
            {},
        )

        entity = report.get(
            "entity",
            {},
        )

        knowledge = report.get(
            "knowledge_analysis",
            {},
        )

        problems = report.get(
            "problems",
            [],
        )

        recommendations = report.get(
            "recommendations",
            [],
        )

        heading_problems = heading.get(
            "problems",
            [],
        )

        missing_entities = entity.get(
            "missing_entities",
            [],
        )

        missing_must_have = knowledge.get(
            "missing_must_have",
            [],
        )

        all_problems = (
            problems
            + heading_problems
        )

        problem_text = PromptBuilder._format_list(
            all_problems,
            limit=8,
        )

        recommendation_text = (
            PromptBuilder._format_list(
                recommendations,
                limit=6,
            )
        )

        missing_entity_text = (
            PromptBuilder._format_list(
                missing_entities,
                limit=8,
            )
        )

        missing_feature_text = (
            PromptBuilder._format_list(
                missing_must_have,
                limit=6,
            )
        )

        user_prompt = f"""
# DATA AUDIT SEO

URL: {report.get("final_url", "-")}
Keyword: {report.get("keyword", "-")}
Intent: {PromptBuilder._get_intent(report)}
SEO Score: {report.get("seo_score", 0)}/100

## Konten
Word Count: {content.get("word_count", 0)}
Keyword Density: {content.get("keyword_density", 0)}%
Keyword di Title: {content.get("keyword_in_title", False)}
Keyword di Meta: {content.get("keyword_in_meta", False)}
Keyword di H1: {content.get("keyword_in_h1", False)}

## Heading
Heading Score: {heading.get("heading_score", 0)}/100
H1: {heading.get("h1_count", 0)}
H2: {heading.get("h2_count", 0)}
H3: {heading.get("h3_count", 0)}

## Entity
Coverage: {entity.get("coverage_percentage", 0)}%
Entity Belum Ada:
{missing_entity_text}

## Elemen Penting Belum Ada
{missing_feature_text}

## Masalah Utama
{problem_text}

## Rekomendasi Engine
{recommendation_text}

# TUGAS

Buat:
- Ringkasan maksimal 2 kalimat.
- Maksimal 5 action plan konkret.
- Maksimal 5 peringatan penting.

Aturan:
- Gunakan hanya data di atas.
- Prioritaskan dampak SEO terbesar.
- Jangan mengarang angka.
- Jangan menjanjikan ranking.
- Jangan memakai placeholder.
- Jawab dalam bahasa Indonesia.
- Ikuti JSON Schema.
""".strip()

        return (
            SEO_SYSTEM_PROMPT,
            user_prompt,
        )

    @staticmethod
    def _format_list(
        items: list,
        limit: int,
    ) -> str:
        clean_items = [
            str(item).strip()
            for item in items
            if str(item).strip()
        ]

        if not clean_items:
            return "- Tidak ada"

        return "\n".join(
            f"- {item}"
            for item in clean_items[:limit]
        )

    @staticmethod
    def _get_intent(
        report: dict,
    ) -> str:
        intent = report.get(
            "intent",
            {},
        )

        if isinstance(intent, dict):
            return str(
                intent.get(
                    "intent",
                    "unknown",
                )
            )

        return str(intent)