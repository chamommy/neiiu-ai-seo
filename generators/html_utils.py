"""
Utilitas kecil yang dipakai bersama oleh generator HTML dan AMP.
"""

import html
import re


def escape(value: str) -> str:
    """
    Meng-escape teks supaya aman ditaruh di dalam HTML.
    """
    return html.escape(str(value or ""), quote=True)


def heading_id(value: str) -> str:
    """
    Membuat anchor id dari teks heading.
    """
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(value or "").lower(),
    ).strip("-")

    return slug[:60] or "bagian"


def minify_css(css: str) -> str:
    """
    Memampatkan CSS seperlunya.

    AMP membatasi <style amp-custom> di 75KB, jadi komentar dan
    spasi berlebih dibuang sebelum ditempel ke halaman.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    css = re.sub(r";}", "}", css)

    return css.strip()


def split_sentences(text: str) -> list[str]:
    """
    Memecah paragraf jadi kalimat.
    """
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())

    return [part.strip() for part in parts if part.strip()]
