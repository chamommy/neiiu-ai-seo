"""
Menjalankan NEIIU AI supaya bisa dibuka dari perangkat lain.

Secara bawaan uvicorn hanya mendengarkan di 127.0.0.1, sehingga
hanya bisa dibuka dari komputer yang menjalankannya. Skrip ini
membukanya ke seluruh jaringan lokal, sekaligus mengurus dua hal
yang wajib beres sebelum itu aman dilakukan:

1. Kunci sesi. Nilai bawaannya dulu berupa teks tetap di dalam
   kode. Begitu server dibuka ke jaringan, siapa pun yang bisa
   membaca kode ini dapat menandatangani cookie sesi sendiri dan
   masuk sebagai admin tanpa password. Skrip ini membuatkan kunci
   acak dan menyimpannya di .env.

2. Alamat yang harus dibuka dari perangkat lain, karena
   127.0.0.1 di laptop lain menunjuk ke laptop itu sendiri.

Contoh pakai:
    python serve.py
    python serve.py --port 9000
    python serve.py --local-only
"""

import argparse
import os
import re
import secrets
import socket
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
SECRET_KEY_NAME = "NEIIU_SESSION_SECRET"

LINE = "=" * 62


def read_env_file() -> str:
    if not ENV_FILE.exists():
        return ""

    return ENV_FILE.read_text(encoding="utf-8")


def ensure_session_secret() -> str:
    """
    Memastikan ada kunci sesi tetap di .env.

    Kalau belum ada, dibuatkan dan ditulis. Kalau .env belum ada
    sama sekali, file barunya dibuat berisi kunci itu saja.
    """
    content = read_env_file()

    match = re.search(
        rf"^{SECRET_KEY_NAME}=(.*)$",
        content,
        re.MULTILINE,
    )

    if match and match.group(1).strip():
        return match.group(1).strip()

    secret = secrets.token_urlsafe(48)
    line = f"{SECRET_KEY_NAME}={secret}"

    if match:
        content = re.sub(
            rf"^{SECRET_KEY_NAME}=.*$",
            line,
            content,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        block = (
            "\n\n# Kunci penanda tangan cookie sesi. Dibuat otomatis.\n"
            "# Jangan dibagikan dan jangan di-commit.\n"
            f"{line}\n"
        )

        content = content.rstrip("\n") + block if content else block.lstrip()

    ENV_FILE.write_text(content, encoding="utf-8")

    print(f"  Kunci sesi baru dibuat dan disimpan di {ENV_FILE.name}")

    return secret


def local_ip_addresses() -> list[str]:
    """
    Mencari alamat IP komputer ini di jaringan lokal.
    """
    found: list[str] = []

    # Cara paling andal: buka socket UDP ke alamat luar dan lihat
    # alamat lokal mana yang dipilih sistem. Tidak ada data yang
    # benar-benar dikirim.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        probe.connect(("8.8.8.8", 80))
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    try:
        for info in socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
        ):
            address = info[4][0]

            if address not in found and not address.startswith("127."):
                found.append(address)
    except socket.gaierror:
        pass

    return found


def print_banner(
    host: str,
    port: int,
) -> None:
    print(LINE)
    print("NEIIU AI")
    print(LINE)

    if host == "127.0.0.1":
        print("\nMode lokal. Hanya bisa dibuka dari komputer ini.\n")
        print(f"  http://127.0.0.1:{port}/neiiu")
        return

    print("\nBuka dari komputer ini:")
    print(f"  http://127.0.0.1:{port}/neiiu")

    addresses = local_ip_addresses()

    if addresses:
        print("\nBuka dari PC atau HP lain di jaringan yang sama:")

        for address in addresses:
            print(f"  http://{address}:{port}/neiiu")
    else:
        print(
            "\nAlamat jaringan tidak terdeteksi. "
            "Cek dengan perintah: ipconfig"
        )

    print(
        "\nCatatan:\n"
        "  - Perangkat lain harus tersambung ke Wi-Fi atau jaringan\n"
        "    yang sama dengan komputer ini.\n"
        "  - Windows Firewall biasanya menanyakan izin saat pertama\n"
        "    kali dijalankan. Pilih Allow untuk jaringan Private.\n"
        "  - Sambungannya HTTP biasa, jadi password yang diketik di\n"
        "    perangkat lain lewat dalam bentuk terbaca di jaringan\n"
        "    lokal. Pakai hanya di jaringan yang kamu percaya, jangan\n"
        "    di Wi-Fi publik.\n"
        "  - Hasil generate diunduh ke folder Download milik\n"
        "    perangkat yang membukanya, bukan ke komputer ini."
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="serve",
        description=(
            "Menjalankan NEIIU AI dan membukanya ke jaringan lokal."
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port yang dipakai (default 8000)",
    )

    parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "Hanya bisa dibuka dari komputer ini, "
            "seperti perilaku uvicorn biasa"
        ),
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Muat ulang otomatis saat kode diubah (untuk ngoding)",
    )

    args = parser.parse_args()

    host = "127.0.0.1" if args.local_only else "0.0.0.0"

    print(LINE)
    print("PERSIAPAN")
    print(LINE)

    secret = ensure_session_secret()

    # Kunci dipasang ke environment proses ini supaya web_app
    # memakainya, tanpa perlu menyentuh file .env lagi.
    os.environ[SECRET_KEY_NAME] = secret

    print(f"  Kunci sesi siap ({len(secret)} karakter)")

    if not args.local_only:
        print("  Server dibuka ke jaringan lokal")

    print()
    print_banner(host, args.port)
    print(f"\n{LINE}")
    print("Tekan Ctrl+C untuk menghentikan server.")
    print(LINE + "\n")

    import uvicorn

    uvicorn.run(
        "web_app:app",
        host=host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
