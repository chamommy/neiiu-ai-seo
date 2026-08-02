"""
Pemeriksa aturan AMP.

Ini bukan pengganti validator resmi AMP, tapi menangkap seluruh
kesalahan fatal yang bisa muncul dari generator sendiri: tag
wajib yang hilang, tag terlarang, CSS lewat batas, dan JavaScript
di luar runtime AMP.

Setelah lolos di sini, halaman masih layak dicek sekali di
https://validator.ampproject.org sebelum benar-benar diunggah.
"""

import re

from config import AMP_CSS_MAX_BYTES


FORBIDDEN_TAGS = {
    "img": "Ganti <img> dengan <amp-img>.",
    "video": "Ganti <video> dengan <amp-video>.",
    "audio": "Ganti <audio> dengan <amp-audio>.",
    "iframe": "Ganti <iframe> dengan <amp-iframe>.",
    "embed": "Tag <embed> tidak diizinkan di AMP.",
    "object": "Tag <object> tidak diizinkan di AMP.",
    "frame": "Tag <frame> tidak diizinkan di AMP.",
    "frameset": "Tag <frameset> tidak diizinkan di AMP.",
    "applet": "Tag <applet> tidak diizinkan di AMP.",
    "form": "Gunakan <form> hanya bersama komponen amp-form.",
}


def extract_amp_custom_css(html: str) -> str:
    match = re.search(
        r"<style\s+amp-custom[^>]*>(.*?)</style>",
        html,
        re.DOTALL | re.IGNORECASE,
    )

    return match.group(1) if match else ""


def validate_amp(html: str) -> dict:
    """
    Memeriksa satu dokumen AMP.

    Mengembalikan daftar error (bikin invalid) dan warning
    (masih valid tapi sebaiknya diperbaiki).
    """
    errors: list[str] = []
    warnings: list[str] = []

    head_match = re.search(
        r"<head[^>]*>(.*?)</head>",
        html,
        re.DOTALL | re.IGNORECASE,
    )

    head = head_match.group(1) if head_match else ""

    if not head:
        errors.append("Tag <head> tidak ditemukan.")

    if not re.match(r"\s*<!doctype html>", html, re.IGNORECASE):
        errors.append(
            "Dokumen harus diawali <!doctype html>."
        )

    if not re.search(
        r"<html[^>]*\s(amp|⚡)[\s>]",
        html,
        re.IGNORECASE,
    ):
        errors.append(
            "Tag <html> harus punya atribut amp atau ⚡."
        )

    if not re.search(
        r'<html[^>]*\slang\s*=\s*["\'][a-z-]+["\']',
        html,
        re.IGNORECASE,
    ):
        warnings.append(
            "Tag <html> sebaiknya punya atribut lang."
        )

    # charset wajib jadi tag pertama di dalam head.
    first_tag = re.search(r"<\s*([a-zA-Z-]+)", head)

    if first_tag is None or first_tag.group(1).lower() != "meta":
        errors.append(
            "Tag pertama di <head> harus <meta charset=\"utf-8\">."
        )
    elif not re.match(
        r'\s*<meta\s+charset\s*=\s*["\']utf-8["\']',
        head,
        re.IGNORECASE,
    ):
        errors.append(
            "Meta pertama di <head> harus charset utf-8."
        )

    if not re.search(
        r'<script[^>]+src\s*=\s*["\']https://cdn\.ampproject\.org/v0\.js["\']',
        head,
        re.IGNORECASE,
    ):
        errors.append(
            "Runtime AMP (cdn.ampproject.org/v0.js) tidak dipasang."
        )

    if not re.search(
        r'<meta[^>]+name\s*=\s*["\']viewport["\']',
        head,
        re.IGNORECASE,
    ):
        errors.append("Meta viewport wajib ada.")

    elif "width=device-width" not in head:
        errors.append(
            "Meta viewport harus memuat width=device-width."
        )

    if not re.search(
        r'<link[^>]+rel\s*=\s*["\']canonical["\']',
        head,
        re.IGNORECASE,
    ):
        errors.append("Link rel=canonical wajib ada.")

    boilerplate_count = len(
        re.findall(r"<style\s+amp-boilerplate", head, re.IGNORECASE)
    )

    if boilerplate_count < 2:
        errors.append(
            "AMP boilerplate belum lengkap "
            "(butuh <style amp-boilerplate> dan versi <noscript>)."
        )

    custom_styles = re.findall(
        r"<style\s+amp-custom",
        html,
        re.IGNORECASE,
    )

    if len(custom_styles) > 1:
        errors.append(
            "Hanya boleh ada satu <style amp-custom> per halaman."
        )

    css = extract_amp_custom_css(html)
    css_bytes = len(css.encode("utf-8"))

    if css_bytes > AMP_CSS_MAX_BYTES:
        errors.append(
            f"CSS amp-custom {css_bytes} byte, "
            f"melewati batas {AMP_CSS_MAX_BYTES} byte."
        )

    if "!important" in css:
        errors.append(
            "CSS amp-custom tidak boleh memakai !important."
        )

    for pattern, message in (
        (r"@import", "CSS amp-custom tidak boleh memakai @import."),
        (r"-moz-binding", "Properti -moz-binding dilarang di AMP."),
        (r"behavior\s*:", "Properti behavior dilarang di AMP."),
    ):
        if re.search(pattern, css, re.IGNORECASE):
            errors.append(message)

    body_match = re.search(
        r"<body[^>]*>(.*?)</body>",
        html,
        re.DOTALL | re.IGNORECASE,
    )

    body = body_match.group(1) if body_match else ""

    for tag, message in FORBIDDEN_TAGS.items():
        if re.search(rf"<{tag}[\s>]", body, re.IGNORECASE):
            errors.append(message)

    if re.search(r'\sstyle\s*=\s*["\']', body, re.IGNORECASE):
        errors.append(
            "Atribut style inline tidak diizinkan di AMP."
        )

    for match in re.finditer(
        r"<script([^>]*)>",
        html,
        re.IGNORECASE,
    ):
        attrs = match.group(1)

        is_amp_runtime = "cdn.ampproject.org" in attrs
        is_jsonld = re.search(
            r'type\s*=\s*["\']application/ld\+json["\']',
            attrs,
            re.IGNORECASE,
        )

        if not is_amp_runtime and not is_jsonld:
            errors.append(
                "Script kustom tidak diizinkan di AMP: "
                f"<script{attrs[:60]}>"
            )

    if re.search(r"\son[a-z]+\s*=", body, re.IGNORECASE):
        errors.append(
            "Event handler inline (onclick dan sejenisnya) "
            "dilarang di AMP."
        )

    if re.search(
        r'<link[^>]+rel\s*=\s*["\']stylesheet["\']',
        head,
        re.IGNORECASE,
    ):
        errors.append(
            "Stylesheet eksternal tidak diizinkan, kecuali font "
            "dari penyedia yang diizinkan AMP."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "css_bytes": css_bytes,
        "css_limit": AMP_CSS_MAX_BYTES,
    }
