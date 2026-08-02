from typing import Any

import json
import time

import requests

from ai.base_ai import BaseAI
from config import (
    AI_CONNECT_TIMEOUT_SECONDS,
    AI_STALL_TIMEOUT_SECONDS,
)
from utils.text import THAI_RANGE


# Berapa karakter yang muat dalam satu token, per jenis aksara.
# Tokenizer byte-level memecah aksara Thai hampir satu token per
# karakter, sementara teks Latin sekitar tiga.
LATIN_CHARS_PER_TOKEN = 3.0
THAI_CHARS_PER_TOKEN = 1.0

# Kecepatan pemrosesan prompt yang dipakai menghitung jatah waktu.
# Diukur di mesin ini: 1389 token dalam 242 detik, yaitu 5,7 token
# per detik saat Ollama sepi. Angka di bawah sengaja separuhnya,
# karena begitu ada job lain yang ikut memakai Ollama kecepatannya
# turun dan batas yang pas-pasan akan lewat tepat sebelum token
# pertama keluar - membunuh job yang sebenarnya sehat.
PREFILL_TOKENS_PER_SECOND = 2.5


def estimate_tokens(text: str) -> int:
    """
    Memperkirakan jumlah token satu potongan teks.

    Dihitung per jenis aksara, bukan dengan satu angka pembagi.
    Prompt berbahasa Thai yang diperkirakan memakai angka Latin
    keluar tiga kali lebih kecil dari sebenarnya.
    """
    body = text or ""

    thai = sum(1 for char in body if THAI_RANGE.match(char))
    lain = len(body) - thai

    return int(
        thai / THAI_CHARS_PER_TOKEN + lain / LATIN_CHARS_PER_TOKEN
    ) + 1


class OllamaAI(BaseAI):
    """
    Provider AI lokal menggunakan Ollama.

    Jawaban diambil secara streaming. Ini bukan soal menampilkan
    teks yang mengalir, tapi soal batas waktu: menulis 5000 token
    di CPU dengan kecepatan 3 token/detik butuh sekitar 28 menit,
    sehingga batas waktu total berapa pun akan salah untuk sebagian
    mesin. Dengan streaming, yang dibatasi adalah jeda antar token,
    jadi generasi lambat tetap diizinkan selesai sementara server
    yang benar-benar macet tetap ketahuan cepat.
    """

    def __init__(
        self,
        model: str = "qwen3:4b",
        base_url: str = "http://localhost:11434",
        timeout: int = AI_STALL_TIMEOUT_SECONDS,
        max_tokens: int = 700,
        context_length: int = 4096,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.context_length = context_length

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
        on_progress=None,
    ) -> dict:
        """
        Mengirim prompt ke Ollama melalui API lokal.

        on_progress dipanggil berkala dengan jumlah token yang sudah
        diterima, supaya proses yang berjalan puluhan menit tidak
        terlihat seperti menggantung.
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
            "stream": True,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": self.max_tokens,
                # Tanpa num_ctx, Ollama memakai context 4096 dan
                # memotong prompt panjang tanpa peringatan. Prompt
                # analisis SERP jauh lebih besar dari itu, jadi
                # context harus muat prompt sekaligus jawabannya.
                "num_ctx": self.context_length,
            },
        }

        if response_schema is not None:
            payload["format"] = response_schema

        return self._stream_request(
            payload=payload,
            on_progress=on_progress,
            expect_json=response_schema is not None,
            read_timeout=self._read_timeout(messages),
        )

    def _read_timeout(self, messages: list[dict]) -> int:
        """
        Menghitung jeda maksimal menunggu data dari Ollama.

        Sebelum token pertama keluar, Ollama memproses seluruh
        prompt lebih dulu, dan selama itu tidak ada satu byte pun
        yang dikirim. Kalau batasnya dipatok pada jeda antar token
        saja, prompt panjang akan divonis macet padahal sedang
        bekerja normal.

        Dua hal yang dulu salah di sini, dan keduanya membunuh job
        yang sebenarnya sehat:

        1. Jumlah token diperkirakan dari panjang teks dibagi tiga.
           Angka tiga itu berlaku untuk huruf Latin. Aksara Thai
           dipecah tokenizer hampir satu token per karakter, jadi
           prompt berbahasa Thai diperkirakan tiga kali lebih kecil
           dari sebenarnya dan jatah waktunya ikut tiga kali kurang.

        2. Kecepatan pemrosesan dipatok 5 token per detik tanpa
           kelonggaran. Diukur di mesin ini hasilnya 5,7 token per
           detik saat sepi - tapi begitu ada job lain yang juga
           memakai Ollama, angkanya turun jauh di bawah 5 dan
           batasnya lewat tepat sebelum token pertama keluar.
        """
        prompt_tokens = sum(
            estimate_tokens(message["content"]) for message in messages
        )

        prefill_seconds = prompt_tokens / PREFILL_TOKENS_PER_SECOND

        return int(
            max(
                self.timeout,
                prefill_seconds + self.timeout,
            )
        )

    def _stream_request(
        self,
        payload: dict,
        on_progress=None,
        expect_json: bool = False,
        read_timeout: int | None = None,
    ) -> dict:
        started_at = time.monotonic()
        wait_limit = read_timeout or self.timeout

        # Tahap pemrosesan prompt tidak mengirim apa pun. Tanpa
        # kabar ini, proses yang sehat terlihat menggantung.
        if on_progress:
            on_progress({"tokens": 0, "elapsed": 0})

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                # Nilai kedua berlaku sebagai jeda maksimal antar
                # potongan data, bukan batas waktu keseluruhan.
                timeout=(
                    AI_CONNECT_TIMEOUT_SECONDS,
                    wait_limit,
                ),
            )

            response.raise_for_status()

            return self._consume_stream(
                response=response,
                started_at=started_at,
                on_progress=on_progress,
                expect_json=expect_json,
            )

        except (
            requests.exceptions.ReadTimeout,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ConnectionError,
        ) as error:
            # Ketiganya harus ditangkap bersama, bukan ReadTimeout
            # saja. Begitu potongan pertama diterima, pembacaan
            # berikutnya lewat iter_content, dan di sana requests
            # membungkus timeout urllib3 jadi ConnectionError, bukan
            # ReadTimeout. Kalau hanya ReadTimeout yang ditangkap,
            # justru kasus yang paling ingin dikenali, yaitu model
            # yang macet di tengah jalan, lolos tanpa diterjemahkan.
            raise self._describe_stream_failure(
                error,
                started_at,
                wait_limit,
            ) from error

    def _describe_stream_failure(
        self,
        error: Exception,
        started_at: float,
        wait_limit: int,
    ) -> Exception:
        """
        Menerjemahkan kegagalan streaming jadi pesan yang berguna.
        """
        elapsed = int(time.monotonic() - started_at)
        text = str(error).lower()

        stalled = isinstance(
            error,
            requests.exceptions.ReadTimeout,
        ) or "timed out" in text or "timeout" in text

        if stalled:
            return TimeoutError(
                f"Ollama tidak mengirim data selama {wait_limit} detik "
                f"(total berjalan {elapsed} detik). "
                "Dua sebab yang paling sering: ada job lain yang juga "
                "memakai Ollama sehingga giliran job ini menunggu di "
                "antrean, atau promptnya terlalu panjang untuk mesin "
                "ini. Coba jalankan satu job saja dalam satu waktu, "
                "kurangi jumlah halaman yang di-crawl, atau pakai "
                "model yang lebih kecil."
            )

        return ConnectionError(
            f"Sambungan ke Ollama terputus setelah {elapsed} detik "
            f"({type(error).__name__}). "
            "Biasanya berarti prosesnya dihentikan paksa karena "
            "kehabisan memori. Coba kecilkan AI_CONTEXT_LENGTH atau "
            "pakai model yang lebih kecil, lalu cek log Ollama."
        )

    def _consume_stream(
        self,
        response,
        started_at: float,
        on_progress=None,
        expect_json: bool = False,
    ) -> dict:
        """
        Merakit ulang jawaban dari potongan-potongan streaming.
        """
        chunks: list[str] = []
        thinking_seen = False
        token_count = 0
        last_reported = 0
        last_report_at = started_at

        prompt_tokens = 0
        output_tokens = 0

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("error"):
                raise RuntimeError(
                    f"Ollama mengembalikan error: {data['error']}"
                )

            message = data.get("message", {})
            piece = message.get("content", "")

            if piece:
                chunks.append(piece)
                token_count += 1

            if message.get("thinking"):
                thinking_seen = True

            # Laporan tidak dikirim tiap token supaya tidak
            # membanjiri log job di database. Syarat waktu tetap
            # dipasang karena pada model yang sangat lambat, 100
            # token bisa makan lebih dari satu menit dan prosesnya
            # terlihat mati.
            if on_progress:
                now = time.monotonic()

                if (
                    token_count - last_reported >= 100
                    or now - last_report_at >= 20
                ):
                    last_reported = token_count
                    last_report_at = now

                    on_progress(
                        {
                            "tokens": token_count,
                            "elapsed": int(now - started_at),
                        }
                    )

            if data.get("done"):
                prompt_tokens = data.get("prompt_eval_count", 0)
                output_tokens = data.get("eval_count", 0)

        content = "".join(chunks).strip()

        if not content:
            raise RuntimeError(
                "Ollama tidak mengembalikan jawaban final."
            )

        return {
            "provider": "ollama",
            "model": self.model,
            "content": content,
            "structured_content": (
                self._parse_structured(content)
                if expect_json
                else None
            ),
            "thinking_hidden": thinking_seen,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens or token_count,
            "elapsed_seconds": int(time.monotonic() - started_at),
        }

    @staticmethod
    def _parse_structured(content: str) -> dict | None:
        """
        Mengurai jawaban jadi objek JSON.

        Hanya dipanggil kalau pemanggilnya memang meminta schema.
        Jawaban chat biasa tidak pernah lewat sini, supaya balasan
        yang kebetulan diawali kurung kurawal tidak diperlakukan
        sebagai JSON yang rusak.
        """
        try:
            parsed = json.loads(content.strip())
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Jawaban AI bukan JSON yang valid: {error}"
            ) from error

        return parsed if isinstance(parsed, dict) else None
