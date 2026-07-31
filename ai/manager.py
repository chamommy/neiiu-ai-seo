from ai.base_ai import BaseAI
from ai.ollama_ai import OllamaAI


class AIManager:
    """
    Memilih provider AI yang digunakan project.
    """

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen3:4b",
    ) -> None:
        self.provider = provider.strip().lower()
        self.model = model
        self.client = self._create_client()

    def _create_client(self) -> BaseAI:
        if self.provider == "ollama":
            return OllamaAI(
                model=self.model,
            )

        if self.provider == "openai":
            raise NotImplementedError(
                "Provider OpenAI belum dipasang."
            )

        raise ValueError(
            f"Provider AI tidak dikenal: {self.provider}"
        )

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        return self.client.ask(
            prompt=prompt,
            system_prompt=system_prompt,
            response_schema=response_schema,
        )