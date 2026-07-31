from typing import Any

from ai.manager import AIManager


NORMAL_SYSTEM_PROMPT = """
Kamu adalah Neiiu AI, asisten AI yang ramah, akurat, dan praktis.

Aturan:
- Jawab dalam bahasa yang digunakan pengguna.
- Berikan jawaban final tanpa menunjukkan proses berpikir internal.
- Jangan mengarang fakta.
- Jika tidak yakin, katakan dengan jelas.
- Utamakan jawaban yang mudah dipahami dan langsung berguna.
- Jangan membuat jawaban terlalu panjang kecuali diminta.
""".strip()


SEO_SYSTEM_PROMPT = """
Kamu adalah Neiiu AI SEO, konsultan SEO profesional.

Keahlian utama:
- Technical SEO
- On-page SEO
- Content SEO
- Search intent
- Keyword mapping
- Internal linking
- Schema markup
- Title dan meta description
- Content brief
- Landing page SEO
- Competitor analysis
- Indexing dan crawling

Aturan:
- Fokuskan jawaban pada SEO.
- Gunakan bahasa yang digunakan pengguna.
- Berikan rekomendasi konkret dan berurutan.
- Jangan menjanjikan ranking pertama.
- Jangan mengarang data, traffic, ranking, atau metrik.
- Jika audit membutuhkan data URL yang belum dianalisis, jelaskan data apa yang dibutuhkan.
- Berikan hanya jawaban final tanpa proses berpikir internal.
- Jangan membuat jawaban terlalu panjang kecuali diminta.
""".strip()


def format_history(
    history: list[dict[str, Any]],
    limit: int = 8,
) -> str:
    """
    Mengubah riwayat chat menjadi konteks singkat.
    """
    clean_messages = []

    for item in history[-limit:]:
        role = str(
            item.get("role", "")
        ).strip().lower()

        content = str(
            item.get("content", "")
        ).strip()

        if not content:
            continue

        if role == "user":
            label = "Pengguna"
        elif role == "assistant":
            label = "Neiiu AI"
        else:
            continue

        clean_messages.append(
            f"{label}: {content}"
        )

    if not clean_messages:
        return "Belum ada percakapan sebelumnya."

    return "\n\n".join(clean_messages)


def generate_chat_response(
    message: str,
    mode: str,
    history: list[dict[str, Any]] | None = None,
) -> dict:
    """
    Menghasilkan jawaban chat memakai provider AI aktif.
    """
    clean_message = message.strip()

    if not clean_message:
        raise ValueError(
            "Pesan tidak boleh kosong."
        )

    normalized_mode = mode.strip().lower()

    if normalized_mode not in {
        "normal",
        "seo",
    }:
        raise ValueError(
            f"Mode tidak dikenal: {mode}"
        )

    system_prompt = (
        SEO_SYSTEM_PROMPT
        if normalized_mode == "seo"
        else NORMAL_SYSTEM_PROMPT
    )

    conversation_context = format_history(
        history or []
    )

    prompt = f"""
RIWAYAT PERCAKAPAN:
{conversation_context}

PESAN TERBARU PENGGUNA:
{clean_message}

Jawab pesan terbaru dengan mempertimbangkan konteks percakapan.
""".strip()

    selected_model = (
    "qwen3:4b-instruct"
    if normalized_mode == "seo"
    else "qwen3:1.7b"
)

    selected_model = "qwen3:4b-instruct"

    max_tokens = (
        450
        if normalized_mode == "seo"
        else 180
    )

    ai = AIManager(
        provider="ollama",
        model=selected_model,
        max_tokens=max_tokens,
    )

    result = ai.ask(
        prompt=prompt,
        system_prompt=system_prompt,
    )

    return {
        "status": "success",
        "mode": normalized_mode,
        "answer": result["content"],
        "provider": result["provider"],
        "model": result["model"],
        "prompt_tokens": result.get(
            "prompt_tokens",
            0,
        ),
        "output_tokens": result.get(
            "output_tokens",
            0,
        ),
    }