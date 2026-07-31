from abc import ABC, abstractmethod


class BaseAI(ABC):
    """
    Kontrak dasar untuk semua provider AI.
    """

    @abstractmethod
    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> dict:
        """
        Mengirim prompt dan mengembalikan hasil AI.
        """
        raise NotImplementedError