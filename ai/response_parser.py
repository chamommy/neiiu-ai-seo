from typing import Any


def parse_seo_response(ai_result: dict) -> dict[str, Any]:
    """
    Memvalidasi hasil structured output dari provider AI.
    """

    structured = ai_result.get("structured_content")

    if not isinstance(structured, dict):
        raise ValueError(
            "Structured content AI tidak tersedia."
        )

    summary = structured.get("summary")
    action_plan = structured.get("action_plan")
    warnings = structured.get("warnings")

    if not isinstance(summary, str):
        raise ValueError(
            "Field summary tidak valid."
        )

    if not isinstance(action_plan, list):
        raise ValueError(
            "Field action_plan tidak valid."
        )

    if not isinstance(warnings, list):
        raise ValueError(
            "Field warnings tidak valid."
        )

    clean_actions = []

    for index, item in enumerate(
        action_plan,
        start=1,
    ):
        if not isinstance(item, dict):
            continue

        clean_actions.append(
            {
                "priority": item.get(
                    "priority",
                    index,
                ),
                "title": str(
                    item.get("title", "")
                ).strip(),
                "description": str(
                    item.get("description", "")
                ).strip(),
            }
        )

    clean_actions.sort(
        key=lambda item: item["priority"]
    )

    return {
        "summary": summary.strip(),
        "action_plan": clean_actions,
        "warnings": [
            str(item).strip()
            for item in warnings
            if str(item).strip()
        ],
        "metadata": {
            "provider": ai_result.get("provider"),
            "model": ai_result.get("model"),
            "prompt_tokens": ai_result.get(
                "prompt_tokens",
                0,
            ),
            "output_tokens": ai_result.get(
                "output_tokens",
                0,
            ),
        },
    }