"""
Pembuat palet warna per halaman.

Layout halaman sengaja dibuat tetap — yang berganti tiap kali
halaman dibuat adalah warna dan teksnya. Modul ini yang mengurus
bagian warnanya.

Warnanya tidak diacak begitu saja. Titik berangkatnya adalah warna
aksen dari halaman acuan yang ditunjuk pengguna, lalu rona-nya
diputar sejauh jarak yang sudah ditentukan. Memutar rona menjaga
kekontrasan tetap utuh: gelap tetap gelap, terang tetap terang,
dan teks tetap terbaca. Mengacak ketiga kanal RGB secara bebas
tidak punya jaminan itu dan cepat menghasilkan halaman yang tidak
bisa dibaca.

Ronanya diputar dengan jarak yang lebar, bukan digeser sedikit,
supaya dua halaman berurutan terlihat jelas berbeda. Halaman
bertema merah dan halaman bertema merah yang lebih tua akan
terbaca sebagai halaman yang sama oleh manusia maupun mesin.
"""

import colorsys
import hashlib

from generators.template_extractor import (
    default_palette,
    hex_to_rgb,
    luminance,
    rgb_to_hex,
)


# Jarak putaran rona, dalam derajat. Nilainya tersebar cukup jauh
# satu sama lain supaya urutan mana pun tetap menghasilkan warna
# yang jelas berbeda dari tetangganya.
HUE_STEPS = (0, 40, 82, 125, 168, 205, 248, 292, 330)


def seed_number(text: str) -> int:
    """
    Mengubah teks jadi angka acak yang tetap.

    `hash()` bawaan Python diacak ulang tiap proses, jadi memakainya
    membuat halaman yang sama menghasilkan warna berbeda tiap kali
    server dinyalakan ulang. Nilai yang tetap membuat satu run bisa
    diulang persis kalau hasilnya perlu diperiksa.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()

    return int.from_bytes(digest[:8], "big")


def hex_to_hsl(value: str) -> tuple[float, float, float]:
    red, green, blue = hex_to_rgb(value)

    hue, lightness, saturation = colorsys.rgb_to_hls(
        red / 255,
        green / 255,
        blue / 255,
    )

    return hue * 360, saturation, lightness


def hsl_to_hex(hue: float, saturation: float, lightness: float) -> str:
    red, green, blue = colorsys.hls_to_rgb(
        (hue % 360) / 360,
        max(0.0, min(1.0, lightness)),
        max(0.0, min(1.0, saturation)),
    )

    return rgb_to_hex(
        (
            round(red * 255),
            round(green * 255),
            round(blue * 255),
        )
    )


def readable_on(background: str) -> str:
    """
    Memilih hitam atau putih untuk teks di atas satu warna.

    Ambangnya 0.45, bukan 0.5. Warna jenuh seperti kuning dan hijau
    terang punya luminance sedikit di bawah setengah tapi sudah
    terlalu terang untuk teks putih.
    """
    return "#10121a" if luminance(hex_to_rgb(background)) > 0.45 else "#ffffff"


def build_theme(
    dna: dict,
    seed_text: str = "",
    variant: int | None = None,
) -> dict:
    """
    Menurunkan satu palet lengkap dari DNA desain.

    `variant` bisa diisi kalau pemakainya ingin memilih sendiri
    nomor variasi warnanya. Kalau dikosongkan, nomornya diambil dari
    `seed_text` — biasanya gabungan brand, keyword, dan waktu run.
    """
    base = dict(default_palette())
    base.update(dna.get("palette") or {})

    seed = seed_number(seed_text or "neiiu")

    if variant is None:
        variant = seed % len(HUE_STEPS)

    step = HUE_STEPS[variant % len(HUE_STEPS)]

    accent_hue, accent_sat, accent_light = hex_to_hsl(
        base.get("accent", "#f5b301")
    )

    # Kejenuhan dan kecerahan aksen ikut dijaga di rentang yang
    # pantas untuk tombol. Halaman acuan kadang memakai abu-abu
    # sebagai aksen, dan menurunkannya apa adanya membuat seluruh
    # tombol halaman baru ikut kelabu.
    hue = (accent_hue + step) % 360
    sat = min(0.92, max(0.55, accent_sat or 0.7))
    light = min(0.62, max(0.42, accent_light or 0.52))

    # Rona kedua dipakai untuk gradasi tombol dan header. Jaraknya
    # dibuat sempit supaya gradasinya terbaca sebagai satu warna
    # yang berubah, bukan sebagai dua warna yang bertabrakan.
    hue_2 = (hue + (28 if variant % 2 == 0 else -28)) % 360

    brand = hsl_to_hex(hue, sat, light)
    brand_mid = hsl_to_hex(hue_2, sat, max(0.3, light - 0.1))
    brand_dark = hsl_to_hex(hue, min(0.95, sat + 0.05), max(0.18, light - 0.26))

    dark = str(base.get("mode", "dark")).lower() != "light"

    if dark:
        background = hsl_to_hex(hue, 0.28, 0.06)
        surface = hsl_to_hex(hue, 0.24, 0.11)
        border = hsl_to_hex(hue, 0.20, 0.21)
        text = hsl_to_hex(hue, 0.16, 0.95)
        muted = hsl_to_hex(hue, 0.12, 0.68)
    else:
        background = "#ffffff"
        surface = hsl_to_hex(hue, 0.34, 0.966)
        border = hsl_to_hex(hue, 0.22, 0.87)
        text = hsl_to_hex(hue, 0.22, 0.11)
        muted = hsl_to_hex(hue, 0.10, 0.42)

    palette = {
        "mode": "dark" if dark else "light",
        "background": background,
        "surface": surface,
        "text": text,
        "muted": muted,
        "border": border,
        "accent": brand,
        "accent_2": brand_mid,
        "accent_text": readable_on(brand),
        # Dipakai blok baru: gradasi tombol, bilah mengambang, dan
        # popup semuanya memakai tiga perhentian warna yang sama.
        "brand": brand,
        "brand_mid": brand_mid,
        "brand_dark": brand_dark,
        "on_brand": readable_on(brand),
        "star": hsl_to_hex((hue + 45) % 360, 0.9, 0.55),
    }

    return {
        "palette": palette,
        "fonts": dna.get("fonts") or [],
        "radius": int(dna.get("radius") or 12),
        "variant": variant % len(HUE_STEPS),
        "hue": round(hue),
        "mode": palette["mode"],
        "variant_total": len(HUE_STEPS),
    }
