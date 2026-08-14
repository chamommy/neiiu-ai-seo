import os
import re
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


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

# Berapa peringkat teratas yang isinya ikut dibaca, bukan cuma
# dihitung.
#
# Membaca berarti kerangka heading, paragraf pembuka, paragraf yang
# menyebut keyword, dan tanya-jawab FAQ ikut dikirim ke model.
# Peringkat di bawah angka ini tetap menyumbang kerangka headingnya
# saja: polanya masih berguna, prosanya tidak sebanding dengan tempat
# yang dimakannya di context.
#
# Lima adalah pilihan sadar. Sepuluh halaman berprosa penuh
# menghabiskan context model 16k sebelum tugasnya sendiri sempat
# ditulis, dan yang paling menentukan peringkat memang lima teratas.
SERP_DIGEST_DEEP_N = int(
    os.getenv(
        "SERP_DIGEST_DEEP_N",
        "5",
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

# Model khusus tahap membaca dan memahami halaman pertama.
#
# Tahap ini beda sifatnya dari tahap menulis. Menulis berarti
# mengikuti aturan panjang dan bentuk yang sudah dipatok, dan model
# 4B sanggup melakukannya. Memahami berarti membaca sepuluh halaman
# sekaligus lalu menyimpulkan apa yang membuat mereka menang, dan di
# situ ukuran model terasa.
#
# Untungnya tahap ini cuma jalan sekali per run, sedangkan tahap
# menulis jalan berkali-kali per batch. Jadi memakai model besar di
# sini menambah waktu jauh lebih sedikit daripada kelihatannya.
#
# Dikosongkan berarti ikut AI_MODEL.
AI_MODEL_INSIGHT = os.getenv(
    "AI_MODEL_INSIGHT",
    "",
).strip() or AI_MODEL

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

# Seberapa bebas model memilih kata berikutnya.
#
# Dulu dipatok nol, dan nol berarti model selalu mengambil kata yang
# paling mungkin. Untuk satu halaman itu terdengar aman; untuk halaman
# KEDUA dari template yang sama, akibatnya terukur - dua run dengan
# keyword dan brand yang sama menghasilkan ulasan yang sama huruf per
# huruf, dan judul yang cuma beda tanda hubung. Membuat ulang halaman
# jadi tidak ada gunanya.
#
# 0,6 diukur di mesin ini dengan prompt yang sama dijalankan dua kali:
# kalimat ulasannya 92% berbeda dan judulnya 62% berbeda, dihitung per
# frasa tiga kata. Menaikkannya ke 0,9 tidak menambah perbedaan yang
# berarti (0,92 dan 0,69) tapi menambah peluang model melantur.
#
# Bentuk JSON-nya tidak ikut terancam berapa pun angkanya: yang
# menjaga strukturnya grammar dari JSON Schema, bukan suhu.
AI_TEMPERATURE = float(
    os.getenv(
        "AI_TEMPERATURE",
        "0.6",
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

# Berapa lapisan model yang dititipkan ke GPU. Nol berarti seluruhnya
# di CPU.
#
# Nolnya bukan menyerah, tapi hasil pengukuran di mesin ini. GT 710
# punya 2 GB dan sekitar 1 GB sudah dipakai desktop, sementara model
# beserta KV cache-nya 4,7 GB - yang muat cuma 573 MB, kira-kira 12%.
# Sisa yang 88% tetap di CPU, dan setiap token harus menunggu bagian
# kecil yang tertinggal di kartu DDR3 berkecepatan ~14 GB/s dengan
# tenaga hitung jauh di bawah i3-12100F.
#
# Diukur dengan prompt 4875 token, sebesar prompt asli saat mengisi
# template:
#
#   dengan GPU  : baca  4,3 tok/s | tulis 2,95 tok/s | 1166 detik
#   tanpa GPU   : baca 50,7 tok/s | tulis 5,13 tok/s |  106 detik
#
# Sebelas kali lebih cepat tanpa kartunya. Yang paling berubah adalah
# membaca prompt, dan itu bagian terbesar: satu giliran pengisian
# template menghabiskan 573 detik hanya untuk membaca, sebelum satu
# kata pun ditulis.
#
# Kalau kartunya diganti dengan yang muat memuat seluruh model, isi
# AI_GPU_LAYERS dengan 999 di .env supaya semua lapisan kembali ke GPU.
AI_GPU_LAYERS = int(
    os.getenv(
        "AI_GPU_LAYERS",
        "0",
    )
)

# Ollama memakai jumlah core fisik kalau tidak diberi tahu. Di mesin
# ini itu 4, dan mengangkatnya ke 8 thread logis terukur menaikkan
# kecepatan baca prompt dari 37,5 ke 50,7 tok/s.
AI_THREADS = int(
    os.getenv(
        "AI_THREADS",
        str(os.cpu_count() or 4),
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

# Lisensi atau badan pengawas yang menaungi brand, ditulis apa
# adanya - misalnya "PAGCOR" atau "Curacao eGaming".
#
# Diisi berarti halaman boleh menyebut lisensinya dengan NAMA itu.
# Dikosongkan berarti halaman tetap boleh berbicara percaya diri
# tentang legalitas dan keamanannya, tapi tanpa menyebut nama badan
# mana pun - karena nama pengawas yang salah lebih buruk daripada
# tidak menyebut nama sama sekali.
#
# NOMOR lisensi sengaja tidak ada di sini. Nomor yang salah satu
# digit adalah nomor milik orang lain, dan tidak ada satu pun tahap
# di pipeline ini yang bisa memeriksanya.
SITE_LICENSE = os.getenv(
    "SITE_LICENSE",
    "",
).strip()

# Tujuan seluruh tombol ajakan di halaman hasil: login, daftar,
# bilah mengambang, dan popup. Kalau dikosongkan, tombolnya
# menunjuk ke beranda situs itu sendiri.
SITE_CTA_URL = os.getenv(
    "SITE_CTA_URL",
    "",
).strip()

# URL halaman yang dipakai sebagai acuan gaya saat NEIIU membuat
# halaman tanpa template. Dipisah koma atau baris baru. Yang
# diambil hanya warna, font, radius, dan komponen yang dipakai —
# teks dan HTML-nya tidak pernah ikut tersalin.
DESIGN_REFERENCES = [
    url.strip()
    for url in re.split(
        r"[,\n]",
        os.getenv("DESIGN_REFERENCES", ""),
    )
    if url.strip()
]
