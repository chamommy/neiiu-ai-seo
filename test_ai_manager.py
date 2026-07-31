from ai.manager import AIManager


def main() -> None:
    ai = AIManager(
        provider="ollama",
        model="qwen3:4b",
    )

    print("Menghubungkan Python ke Ollama...\n")

    result = ai.ask(
        prompt=(
            "Jelaskan fungsi title tag SEO "
            "dalam maksimal 3 kalimat."
        ),
        system_prompt=(
            "Jawab singkat dalam bahasa Indonesia. "
            "Jangan lebih dari 80 kata."
        ),
    )

    print("=" * 60)
    print("AI MANAGER TEST")
    print("=" * 60)
    print(f"Provider : {result['provider']}")
    print(f"Model    : {result['model']}")
    print("\nJawaban:")
    print(result["content"])
    print(
        f"\nTokens   : "
        f"{result['prompt_tokens']} prompt, "
        f"{result['output_tokens']} output"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}")