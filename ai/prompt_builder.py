import json

from ai.prompts import SEO_SYSTEM_PROMPT


class PromptBuilder:
    """
    Builder untuk seluruh prompt AI.
    """

    @staticmethod
    def build_seo_prompt(report: dict) -> tuple[str, str]:
        """
        Menghasilkan system prompt dan user prompt.
        """

        report_json = json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )

        user_prompt = f"""
TUGAS

Analisis data audit SEO berikut.

Gunakan HANYA data yang diberikan.

Jangan mengarang.

Jika SEO Score = 72
maka gunakan angka 72.

Jika entity coverage = 45
gunakan angka tersebut.

Dilarang menggunakan placeholder seperti:

- Action Plan 1
- Ringkasan
- Deskripsi

Semua isi harus spesifik.

=================================================

DATA AUDIT

{report_json}

=================================================

Output harus mengikuti JSON Schema.
"""

        return (
            SEO_SYSTEM_PROMPT,
            user_prompt,
        )