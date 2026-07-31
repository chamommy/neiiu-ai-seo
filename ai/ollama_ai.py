from typing import Any

import json
import requests

from ai.base_ai import BaseAI


class OllamaAI(BaseAI):
    """
    Provider AI lokal menggunakan Ollama.
    """

    def __init__(
        self,
        model: str = "qwen3:4b",
        base_url: str = "http://localhost:11434",
        timeout: int = 900,
        max_tokens: int = 700,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens

    def check_connection(self) -> bool:
        """
        Mengecek apakah server Ollama sedang aktif.
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )

            return response.status_code == 200

        except requests.exceptions.RequestException:
            return False

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        """
        Mengirim prompt ke Ollama melalui API lokal.
        """
        clean_prompt = prompt.strip()

        if not clean_prompt:
            raise ValueError("Prompt tidak boleh kosong.")

        if not self.check_connection():
            raise ConnectionError(
                "Ollama tidak dapat dihubungi. "
                "Pastikan aplikasi Ollama sedang berjalan."
            )

        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt.strip()}\n\n"
                        "Berikan hanya jawaban final. "
                        "Jangan tampilkan proses berpikir, draft, "
                        "catatan internal, atau analisis tersembunyi."
                    ),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": clean_prompt,
            }
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": self.max_tokens,
            },
        }
        if response_schema is not None:
            payload["format"] = response_schema

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )

        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})

        content = str(
            message.get("content", "")
        ).strip()

        thinking = str(
            message.get("thinking", "")
        ).strip()

        if not content:
            raise RuntimeError(
                "Ollama tidak mengembalikan jawaban final."
            )

        structured_content = None

        if response_schema is not None:
            try:
                structured_content = json.loads(content)
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"Jawaban AI bukan JSON yang valid: {error}"
                ) from error

        return {
            "provider": "ollama",
            "model": self.model,
            "content": content,
            "structured_content": structured_content,
            "thinking_hidden": bool(thinking),
            "prompt_tokens": data.get(
                "prompt_eval_count",
                0,
            ),
            "output_tokens": data.get(
                "eval_count",
                0,
            ),
        }