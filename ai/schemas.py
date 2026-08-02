SEO_ACTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "maxLength": 400,
        },
        "action_plan": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "title": {
                        "type": "string",
                        "maxLength": 100,
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 300,
                    },
                },
                "required": [
                    "priority",
                    "title",
                    "description",
                ],
            },
        },
        "warnings": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "string",
                "maxLength": 180,
            },
        },
    },
    "required": [
        "summary",
        "action_plan",
        "warnings",
    ],
}


# ==========================================================
# NEIIU PIPELINE
# ==========================================================

SERP_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "serp_summary": {
            "type": "string",
            "maxLength": 700,
        },
        "search_intent": {
            "type": "string",
            "maxLength": 300,
        },
        "ranking_analysis": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "position": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "domain": {
                        "type": "string",
                        "maxLength": 120,
                    },
                    "why_ranking": {
                        "type": "string",
                        "maxLength": 450,
                    },
                    "strengths": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "string",
                            "maxLength": 140,
                        },
                    },
                    "weaknesses": {
                        "type": "array",
                        "maxItems": 3,
                        "items": {
                            "type": "string",
                            "maxLength": 140,
                        },
                    },
                },
                "required": [
                    "position",
                    "domain",
                    "why_ranking",
                    "strengths",
                    "weaknesses",
                ],
            },
        },
        "content_gaps": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "string",
                "maxLength": 200,
            },
        },
        "winning_strategy": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "string",
                "maxLength": 220,
            },
        },
    },
    "required": [
        "serp_summary",
        "search_intent",
        "ranking_analysis",
        "content_gaps",
        "winning_strategy",
    ],
}


CONTENT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "maxLength": 70,
        },
        "meta_description": {
            "type": "string",
            "maxLength": 165,
        },
        "slug": {
            "type": "string",
            "maxLength": 80,
        },
        "h1": {
            "type": "string",
            "maxLength": 90,
        },
        "intro": {
            "type": "string",
            "maxLength": 1200,
        },
        "sections": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "heading": {
                        "type": "string",
                        "maxLength": 110,
                    },
                    "type": {
                        "type": "string",
                        "enum": [
                            "paragraph",
                            "list",
                            "table",
                            "steps",
                            "cta",
                        ],
                    },
                    "paragraphs": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "string",
                            "maxLength": 1000,
                        },
                    },
                    "items": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {
                            "type": "string",
                            "maxLength": 260,
                        },
                    },
                },
                "required": [
                    "heading",
                    "type",
                    "paragraphs",
                    "items",
                ],
            },
        },
        "faq": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "maxLength": 160,
                    },
                    "answer": {
                        "type": "string",
                        "maxLength": 700,
                    },
                },
                "required": [
                    "question",
                    "answer",
                ],
            },
        },
        "keywords": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "string",
                "maxLength": 60,
            },
        },
    },
    "required": [
        "title",
        "meta_description",
        "slug",
        "h1",
        "intro",
        "sections",
        "faq",
        "keywords",
    ],
}