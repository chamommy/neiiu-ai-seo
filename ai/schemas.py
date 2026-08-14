from generators.template_slots import HEAD_BUDGET, HEAD_FLOOR


# Rentang panjang title dan meta description, satu sumber untuk dua
# jalur yang berbeda.
#
# Halaman yang dirakit dari nol dan halaman yang mengisi template
# pengguna dulu memakai angka sendiri-sendiri, dan angkanya tidak sama:
# title dipatok 70 di satu tempat dan 60 di tempat lain, lalu dipotong
# lagi jadi 62 waktu nama brand ditambal. Yang terbit karena itu bukan
# halaman yang salah, melainkan dua halaman dengan aturan berbeda dari
# satu perintah yang sama.
TITLE_MIN = HEAD_FLOOR["title"]
TITLE_MAX = HEAD_BUDGET["title"]
META_MIN = HEAD_FLOOR["meta_description"]
META_MAX = HEAD_BUDGET["meta_description"]

# Kelonggaran plafon schema terhadap batas yang diminta di prompt.
SCHEMA_HEADROOM = 1.3

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
                    # Sudut pembahasan halaman itu: menjual apa,
                    # menjawab kebutuhan apa. Dipisah dari
                    # why_ranking supaya tidak tenggelam - selama
                    # ini why_ranking selalu terisi angka, karena
                    # angka memang satu-satunya yang dikirim.
                    "angle": {
                        "type": "string",
                        "maxLength": 300,
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
                    "angle",
                    "strengths",
                    "weaknesses",
                ],
            },
        },
        # Bukti tekstual yang membuat intent disimpulkan begitu.
        # Tanpa ini search_intent bisa diisi tebakan yang terdengar
        # masuk akal, dan tidak ada cara membedakannya dari
        # kesimpulan yang benar-benar dibaca dari halaman.
        "intent_evidence": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "string",
                "maxLength": 200,
            },
        },
        # Topik yang wajib dibahas halaman baru. Inilah yang
        # menyeberang ke tahap penulisan: hasil membaca berubah jadi
        # perintah, bukan berhenti sebagai laporan.
        "must_cover": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "maxLength": 120,
                    },
                    "reason": {
                        "type": "string",
                        "maxLength": 200,
                    },
                },
                "required": ["topic", "reason"],
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
        "intent_evidence",
        "ranking_analysis",
        "must_cover",
        "content_gaps",
        "winning_strategy",
    ],
}


CONTENT_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        # Plafonnya dilonggarkan 30% dari batas yang diminta di
        # prompt, sama seperti di generators/template_filler.py.
        # Grammar memotong string tepat di batasnya tanpa tahu apa-apa
        # soal kata; yang memotong sungguhan bekerja belakangan, di
        # tempat yang tahu di mana kata berakhir. Lantai tidak
        # dilonggarkan - teks yang kependekan tidak bisa diperbaiki
        # tahap mana pun.
        "title": {
            "type": "string",
            "minLength": TITLE_MIN,
            "maxLength": int(TITLE_MAX * SCHEMA_HEADROOM),
        },
        "meta_description": {
            "type": "string",
            "minLength": META_MIN,
            "maxLength": int(META_MAX * SCHEMA_HEADROOM),
        },
        "slug": {
            "type": "string",
            "maxLength": 80,
        },
        "h1": {
            "type": "string",
            "maxLength": 90,
        },
        # Jalur breadcrumb, dari yang paling umum ke halaman ini.
        #
        # Dipesan ke model, bukan disusun dari template, karena
        # breadcrumb menyatakan halaman ini berdiri di mana dalam
        # topiknya. Milik template menyatakan letak halaman LAIN:
        # remah "Slot Online > Deposit QRIS 1 Detik" ikut terbit di
        # hasil pencarian halaman yang topiknya sudah lain sama
        # sekali, karena perannya nav_label dan nav_label sengaja
        # dipertahankan sebagai perkakas situs.
        "breadcrumb": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "string",
                "maxLength": 60,
            },
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
        # Tanggal ulasan sengaja tidak diminta ke model. NEIIU yang
        # memasangnya, supaya selalu berupa tanggal yang benar-benar
        # ada dan tidak pernah jatuh di masa depan.
        "reviews": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 40,
                    },
                    "rating": {
                        "type": "number",
                        "minimum": 4,
                        "maximum": 5,
                    },
                    "text": {
                        "type": "string",
                        "maxLength": 600,
                    },
                },
                "required": [
                    "name",
                    "rating",
                    "text",
                ],
            },
        },
        "ratings": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "maxLength": 40,
                    },
                    "value": {
                        "type": "number",
                        "minimum": 4,
                        "maximum": 5,
                    },
                },
                "required": [
                    "label",
                    "value",
                ],
            },
        },
    },
    "required": [
        "title",
        "meta_description",
        "slug",
        "h1",
        "breadcrumb",
        "intro",
        "sections",
        "faq",
        "keywords",
        "reviews",
        "ratings",
    ],
}