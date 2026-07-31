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