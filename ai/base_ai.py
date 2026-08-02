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
        on_progress=None,
    ) -> dict:
        """
        Mengirim prompt dan mengembalikan hasil AI.

        on_progress boleh diabaikan provider yang tidak mendukung
        streaming. Kalau didukung, fungsi ini dipanggil berkala
        dengan {"tokens": int, "elapsed": int} supaya proses panjang
        tidak terlihat menggantung.
        """
        raise NotImplementedError