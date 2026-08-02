"""
Cek konfigurasi sumber SERP.

Menjalankan satu pencarian percobaan lalu melaporkan apa yang
salah kalau gagal. Dipakai sebelum menjalankan pipeline penuh,
supaya masalah API key ketahuan dalam hitungan detik, bukan
setelah menunggu puluhan menit.

Contoh pakai:
    python check_serp.py
    python check_serp.py "slot gacor"
    python check_serp.py "slot gacor" --provider serper
"""

import argparse
import sys

from config import (
    GOOGLE_CSE_CX,
    GOOGLE_CSE_KEY,
    SERP_COUNTRY,
    SERP_LANGUAGE,
    SERP_MANUAL_FILE,
    SERP_PROVIDER,
    SERPER_API_KEY,
)
from serp.providers import SerpProviderError, run_provider


LINE = "=" * 62


def mask(value: str) -> str:
    """
    Menampilkan API key tanpa membocorkan isinya.
    """
    if not value:
        return "(kosong)"

    if len(value) <= 8:
        return "*" * len(value)

    return f"{value[:4]}...{value[-4:]} ({len(value)} karakter)"


def print_config(provider: str) -> None:
    print(LINE)
    print("KONFIGURASI SERP")
    print(LINE)

    print(f"Provider aktif   : {provider}")
    print(f"Negara (gl)      : {SERP_COUNTRY}")
    print(f"Bahasa (hl)      : {SERP_LANGUAGE}")
    print(f"SERPER_API_KEY   : {mask(SERPER_API_KEY)}")
    print(f"GOOGLE_CSE_KEY   : {mask(GOOGLE_CSE_KEY)}")
    print(f"GOOGLE_CSE_CX    : {mask(GOOGLE_CSE_CX)}")
    print(f"File manual      : {SERP_MANUAL_FILE}")
    print(
        f"                   "
        f"{'ada' if SERP_MANUAL_FILE.exists() else 'belum dibuat'}"
    )


def print_guidance(provider: str) -> None:
    print()
    print(LINE)
    print("CARA MEMPERBAIKI")
    print(LINE)

    if provider == "serper":
        print(
            "1. Daftar di https://serper.dev (login Google, gratis).\n"
            "2. Buka Dashboard, salin API key.\n"
            "3. Buka file .env, isi:\n"
            "     SERP_PROVIDER=serper\n"
            "     SERPER_API_KEY=kunci_yang_disalin\n"
            "4. Jalankan lagi: python check_serp.py"
        )

    elif provider == "google_cse":
        print(
            "Butuh DUA nilai berbeda: API key dan Search engine ID.\n"
            "\n"
            "A. API key\n"
            "   1. Buka https://console.cloud.google.com\n"
            "   2. Buat project baru.\n"
            "   3. APIs & Services > Library, cari\n"
            "      'Custom Search API', klik Enable.\n"
            "   4. APIs & Services > Credentials >\n"
            "      Create credentials > API key. Salin.\n"
            "\n"
            "B. Search engine ID (cx)\n"
            "   1. Buka https://programmablesearchengine.google.com\n"
            "   2. Add, beri nama bebas.\n"
            "   3. PENTING: aktifkan 'Search the entire web'.\n"
            "      Tanpa ini, hasilnya cuma dari situs yang\n"
            "      kamu daftarkan sendiri.\n"
            "   4. Salin 'Search engine ID'.\n"
            "\n"
            "C. Isi .env:\n"
            "     SERP_PROVIDER=google_cse\n"
            "     GOOGLE_CSE_KEY=api_key_dari_langkah_A\n"
            "     GOOGLE_CSE_CX=search_engine_id_dari_langkah_B\n"
            "\n"
            "Kuota gratis 100 query per hari.\n"
            "\n"
            "Catatan penting: hasil Custom Search API TIDAK sama\n"
            "persis dengan halaman google.com yang dilihat orang.\n"
            "Urutannya bisa berbeda. Untuk analisis peringkat,\n"
            "Serper.dev lebih mendekati kenyataan."
        )

    else:
        print(
            "Mode manual tidak butuh API key.\n"
            "\n"
            f"1. Buat file: {SERP_MANUAL_FILE}\n"
            "2. Buka Google, cari keywordmu.\n"
            "3. Salin URL hasil rank 1 sampai 10.\n"
            "4. Isi filenya seperti ini:\n"
            "\n"
            '     {\n'
            '       "slot gacor": [\n'
            '         "https://situs-rank1.com/halaman",\n'
            '         "https://situs-rank2.com/halaman"\n'
            '       ]\n'
            '     }\n'
            "\n"
            "Urutan di dalam list dianggap sebagai urutan peringkat."
        )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="check_serp",
        description="Menguji konfigurasi sumber SERP.",
    )

    parser.add_argument(
        "keyword",
        nargs="?",
        default="belajar python",
        help="Keyword percobaan (default: \"belajar python\")",
    )

    parser.add_argument(
        "--provider",
        default=SERP_PROVIDER,
        choices=["serper", "google_cse", "manual"],
        help="Provider yang mau diuji",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Jumlah hasil yang diminta (default 5)",
    )

    args = parser.parse_args()

    print_config(args.provider)

    print()
    print(LINE)
    print(f"UJI PENCARIAN: \"{args.keyword}\"")
    print(LINE)

    try:
        # Cache sengaja dilewati supaya yang diuji benar-benar
        # koneksi ke provider, bukan hasil simpanan lama.
        results = run_provider(
            provider=args.provider,
            keyword=args.keyword,
            limit=args.limit,
        )

    except SerpProviderError as error:
        print(f"\nGAGAL: {error}")
        print_guidance(args.provider)
        return 1

    except Exception as error:
        print(f"\nGAGAL: {type(error).__name__}: {error}")
        print_guidance(args.provider)
        return 1

    if not results:
        print("\nGAGAL: provider tidak mengembalikan hasil apa pun.")
        print_guidance(args.provider)
        return 1

    extras = results[0].pop("_extras", {})

    print(f"\nBERHASIL. {len(results)} hasil diterima.\n")

    for item in results:
        print(f"  {item['position']:>2}. {item['domain']}")
        print(f"      {item['url']}")

        if item["title"]:
            print(f"      {item['title'][:70]}")

    if extras.get("people_also_ask"):
        print("\n  People Also Ask:")

        for question in extras["people_also_ask"][:5]:
            print(f"    - {question}")

    if extras.get("related_searches"):
        print("\n  Pencarian terkait:")

        for query in extras["related_searches"][:5]:
            print(f"    - {query}")

    print(
        f"\nProvider '{args.provider}' siap dipakai.\n"
        f"Jalankan: python neiiu.py \"{args.keyword}\" "
        f"--provider {args.provider}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
