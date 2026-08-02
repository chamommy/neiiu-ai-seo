"""
Utilitas kecil yang dipakai bersama oleh generator HTML dan AMP.
"""

import html
import re

from utils.text import anchor_id


def escape(value: str) -> str:
    """
    Meng-escape teks supaya aman ditaruh di dalam HTML.
    """
    return html.escape(str(value or ""), quote=True)


def heading_id(value: str) -> str:
    """
    Membuat anchor id dari teks heading.
    """
    # Aksara non-Latin dipertahankan. Kalau dibuang, setiap heading
    # Thai menghasilkan id yang sama, seluruh tautan daftar isi
    # menunjuk ke satu tempat, dan halamannya punya id kembar.
    return anchor_id(value)


def unique_ids(values: list[str]) -> list[str]:
    """
    Membuat anchor id yang dijamin tidak kembar dalam satu halaman.

    anchor_id sendiri tidak bisa menjamin ini: ia memotong di 60
    karakter dan mengubah semua tanda baca jadi tanda hubung, jadi
    dua heading yang berbeda tetap bisa menghasilkan id yang sama.
    Kalau itu terjadi, dua tautan daftar isi menunjuk ke tempat yang
    sama dan HTML-nya punya id kembar.

    Penomoran dilakukan sekali untuk seluruh daftar, bukan per
    panggilan, supaya daftar isi dan judul section selalu memakai id
    yang sama persis.
    """
    seen: dict[str, int] = {}
    result: list[str] = []

    for value in values:
        base = heading_id(value)

        if base in seen:
            seen[base] += 1
            base = f"{base}-{seen[base]}"
        else:
            seen[base] = 1

        result.append(base)

    return result


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
