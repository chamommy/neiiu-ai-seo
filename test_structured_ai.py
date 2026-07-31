from ai.manager import AIManager


SEO_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "maxLength": 300,
        },
        "action_plan": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "priority": {
                        "type": "integer",
                    },
                    "title": {
                        "type": "string",
                        "maxLength": 80,
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 250,
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
                "maxLength": 160,
            },
        },
    },
    "required": [
        "summary",
        "action_plan",
        "warnings",
    ],
}


def main() -> None:
    ai = AIManager(
        provider="ollama",
        model="qwen3:4b",
    )

    result = ai.ask(
        prompt="""
Data audit SEO:

SEO Score: 80
Word Count: 1200
Keyword Density: 2.5%
Entity Coverage: 65%
Jumlah H1: 2
Jumlah H2: 7

Masalah:
- Keyword density tinggi
- Entity coverage rendah

Buat ringkasan maksimal 2 kalimat,
maksimal 5 action plan dengan deskripsi singkat,
dan maksimal 5 peringatan.

Isi seluruh field secara ringkas.
Pastikan JSON selesai dan valid.
Jangan menambahkan teks di luar JSON.
""".strip(),
        system_prompt=(
            "Kamu adalah analis SEO. "
            "Gunakan hanya data yang diberikan. "
            "Jangan mengarang angka atau menjanjikan ranking."
        ),
        response_schema=SEO_RESPONSE_SCHEMA,
    )

    data = result["structured_content"]

    print("\n" + "=" * 60)
    print("NEIIIU AI SEO — ACTION PLAN")
    print("=" * 60)

    print("\nRingkasan:")
    print(data["summary"])

    print("\nPrioritas Utama:")

    for item in data["action_plan"]:
        print(
            f"{item['priority']}. "
            f"{item['title']}"
        )
        print(
            f"   {item['description']}"
        )

    print("\nPeringatan:")

    if data["warnings"]:
        for warning in data["warnings"]:
            print(f"- {warning}")
    else:
        print("- Tidak ada")

    print(
        f"\nProvider : {result['provider']}"
    )
    print(
        f"Model    : {result['model']}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")