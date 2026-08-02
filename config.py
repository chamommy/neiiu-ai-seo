import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


KNOWLEDGE_FILE = (
    BASE_DIR
    / "knowledge"
    / "seo_knowledge.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
)

REQUEST_TIMEOUT = 20

# User-Agent Googlebot resmi.
#
# Sebagian halaman spam melakukan cloaking: pengunjung biasa
# dilayani halaman aslinya, sedangkan Googlebot dilayani halaman
# judi yang kemudian diindeks. Tanpa mengambil kedua versi, crawler
# hanya melihat halaman bersihnya dan menganalisis konten yang sama
# sekali berbeda dari yang benar-benar ngerank.
GOOGLEBOT_USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

RULES_FILE = BASE_DIR / "knowledge" / "seo_rules.json"
REPORTS_DIR = BASE_DIR / "database" / "reports"
CACHE_DIR = BASE_DIR / "database" / "cache"
ENTITY_FILE = BASE_DIR / "knowledge" / "seo_entities.json"


# ==========================================================
# NEIIU PIPELINE — SERP
# ==========================================================

SERP_PROVIDER = os.getenv(
    "SERP_PROVIDER",
    "serper",
).strip().lower()

SERPER_API_KEY = os.getenv(
    "SERPER_API_KEY",
    "",
).strip()

GOOGLE_CSE_KEY = os.getenv(
    "GOOGLE_CSE_KEY",
    "",
).strip()

GOOGLE_CSE_CX = os.getenv(
    "GOOGLE_CSE_CX",
    "",
).strip()

# Zona bawaan kalau job tidak menyebutkan zonanya sendiri.
#
# Satu zona menentukan negara dan bahasa pencarian Google sekaligus
# bahasa halaman yang dibuat. Dulu keduanya diatur terpisah lewat
# SERP_COUNTRY dan SERP_LANGUAGE, dan keduanya bisa saling
# bertentangan: mencari di Google Thailand tapi menulis halamannya
# dalam bahasa Indonesia. Daftar zona ada di utils/region.py.
SERP_REGION = os.getenv(
    "SERP_REGION",
    "id",
).strip().lower()

# Dua nama lama di atas sudah tidak dipakai. Kalau masih ada di .env
# milik pemasangan lama, isinya akan diabaikan tanpa disadari, jadi
# dikatakan sekali di sini.
for _lama in ("SERP_COUNTRY", "SERP_LANGUAGE"):
    if os.getenv(_lama):
        print(
            f"[NEIIU] {_lama} di .env sudah tidak dipakai. "
            "Ganti dengan SERP_REGION (id atau th)."
        )

SERP_TOP_N = int(
    os.getenv(
        "SERP_TOP_N",
        "10",
    )
)

SERP_CACHE_DIR = BASE_DIR / "database" / "serp_cache"

SERP_CACHE_TTL_HOURS = int(
    os.getenv(
        "SERP_CACHE_TTL_HOURS",
        "12",
    )
)

# Dipakai kalau SERP_PROVIDER = "manual".
# Isi file JSON: {"keyword": [...url...]} atau langsung [ ...url... ]
SERP_MANUAL_FILE = BASE_DIR / "database" / "serp_manual.json"


# ==========================================================
# NEIIU PIPELINE — GENERATOR
# ==========================================================

OUTPUT_DIR = BASE_DIR / "output"

# Batas resmi AMP untuk <style amp-custom>
AMP_CSS_MAX_BYTES = 75_000

# Berapa kompetitor teratas yang benar-benar di-crawl.
# Sisanya tetap dicatat dari data SERP tanpa fetch halaman.
CRAWL_TOP_N = int(
    os.getenv(
        "CRAWL_TOP_N",
        "10",
    )
)

# Jeda antar request saat crawl SERP (detik), biar sopan.
CRAWL_DELAY_SECONDS = float(
    os.getenv(
        "CRAWL_DELAY_SECONDS",
        "1.0",
    )
)

# Ambil setiap halaman dua kali (Chrome dan Googlebot) untuk
# mendeteksi cloaking. Menggandakan jumlah request, tapi tanpa ini
# blueprint bisa tersusun dari konten yang bukan konten yang ngerank.
CLOAK_CHECK = os.getenv(
    "CLOAK_CHECK",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}

# Ambang keyakinan sebelum satu halaman dianggap domain bajakan
# dan dikeluarkan dari perhitungan target.
HIJACK_MIN_CONFIDENCE = int(
    os.getenv(
        "HIJACK_MIN_CONFIDENCE",
        "60",
    )
)


# ==========================================================
# NEIIU PIPELINE — AI
# ==========================================================

AI_PROVIDER = os.getenv(
    "AI_PROVIDER",
    "ollama",
).strip().lower()

AI_MODEL = os.getenv(
    "AI_MODEL",
    "qwen3:4b-instruct",
).strip()

# Analisis SERP butuh ruang jawaban jauh lebih besar
# dibanding audit satu halaman.
AI_MAX_TOKENS_INSIGHT = int(
    os.getenv(
        "AI_MAX_TOKENS_INSIGHT",
        "2500",
    )
)

AI_MAX_TOKENS_PLAN = int(
    os.getenv(
        "AI_MAX_TOKENS_PLAN",
        "5000",
    )
)

# Ollama memakai context 4096 kalau tidak diberi tahu, dan diam-diam
# memotong prompt yang lebih panjang. Prompt analisis SERP dengan 10
# kompetitor bisa jauh melewati itu, jadi context harus muat prompt
# sekaligus jawaban.
AI_CONTEXT_LENGTH = int(
    os.getenv(
        "AI_CONTEXT_LENGTH",
        "16384",
    )
)

# Jawaban AI diambil secara streaming, jadi batas waktu ini bukan
# batas total, melainkan jeda maksimal antar token.
#
# Batas total tidak bisa dipakai di sini: menulis 5000 token di CPU
# dengan kecepatan 3 token/detik butuh sekitar 28 menit, dan batas
# total berapa pun akan salah untuk sebagian mesin. Yang benar-benar
# menandakan masalah adalah token yang berhenti mengalir.
AI_STALL_TIMEOUT_SECONDS = int(
    os.getenv(
        "AI_STALL_TIMEOUT_SECONDS",
        "180",
    )
)

# Batas waktu menyambung ke server Ollama.
AI_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv(
        "AI_CONNECT_TIMEOUT_SECONDS",
        "15",
    )
)


# ==========================================================
# NEIIU PIPELINE — SITE IDENTITY
# ==========================================================

SITE_NAME = os.getenv(
    "SITE_NAME",
    "NEIIU",
).strip()

SITE_BASE_URL = os.getenv(
    "SITE_BASE_URL",
    "https://example.com",
).strip().rstrip("/")

SITE_LOCALE = os.getenv(
    "SITE_LOCALE",
    "id_ID",
).strip()

# Disclaimer / catatan kepatuhan yang ditempel di footer.
# Kosongkan kalau tidak dibutuhkan.
SITE_DISCLAIMER = os.getenv(
    "SITE_DISCLAIMER",
    "",
).strip()
