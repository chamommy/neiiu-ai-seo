"""
Daftar IP yang boleh mengakses NEIIU AI.

Dipakai setelah server dibuka ke jaringan lokal, supaya bukan
sembarang perangkat di jaringan yang sama bisa membuka halaman
login dan mencoba menebak password.

Satu hal yang dijaga ketat di seluruh modul ini: admin tidak boleh
sampai mengunci dirinya sendiri. Alamat loopback selalu diizinkan
dan tidak bisa dihapus, jadi komputer yang menjalankan server ini
selalu punya jalan masuk untuk membetulkan daftarnya.
"""

import ipaddress

from database.app_db import db_connection, utc_now


SETTING_ENABLED = "ip_allowlist_enabled"


def init_ip_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS allowed_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def normalize_entry(value: str) -> str:
    """
    Memeriksa dan merapikan satu isian IP.

    Menerima alamat tunggal (192.168.1.20) maupun rentang CIDR
    (192.168.1.0/24). Rentang penting supaya admin bisa mengizinkan
    seluruh jaringan rumahnya sekaligus tanpa mendaftar satu per
    satu, karena IP dari DHCP bisa berubah.
    """
    clean = value.strip()

    if not clean:
        raise ValueError("Alamat IP tidak boleh kosong.")

    try:
        if "/" in clean:
            network = ipaddress.ip_network(clean, strict=False)

            return str(network)

        return str(ipaddress.ip_address(clean))

    except ValueError as error:
        raise ValueError(
            f"'{clean}' bukan alamat IP atau rentang CIDR yang sah. "
            "Contoh yang benar: 192.168.1.20 atau 192.168.1.0/24"
        ) from error


def is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def list_ips() -> list[dict]:
    with db_connection() as db:
        rows = db.execute(
            "SELECT * FROM allowed_ips ORDER BY id"
        ).fetchall()

    return [dict(row) for row in rows]


def add_ip(
    value: str,
    label: str,
    created_by: str,
) -> str:
    entry = normalize_entry(value)

    with db_connection() as db:
        existing = db.execute(
            "SELECT id FROM allowed_ips WHERE value = ?",
            (entry,),
        ).fetchone()

        if existing:
            raise ValueError(f"{entry} sudah ada di daftar.")

        db.execute(
            """
            INSERT INTO allowed_ips (value, label, created_by, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (entry, label.strip()[:60], created_by, utc_now()),
        )

    return entry


def delete_ip(ip_id: int) -> None:
    with db_connection() as db:
        cursor = db.execute(
            "DELETE FROM allowed_ips WHERE id = ?",
            (ip_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError("Alamat tidak ditemukan.")


def is_enabled() -> bool:
    with db_connection() as db:
        row = db.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (SETTING_ENABLED,),
        ).fetchone()

    return bool(row) and row["value"] == "1"


def set_enabled(enabled: bool) -> None:
    """
    Menyalakan atau mematikan penyaringan IP.

    Penyaringan tidak boleh dinyalakan saat daftarnya masih kosong.
    Kalau itu terjadi, semua perangkat selain komputer server akan
    langsung tertolak, termasuk laptop admin yang sedang mengaturnya.
    """
    if enabled and not list_ips():
        raise ValueError(
            "Daftar IP masih kosong. Tambahkan minimal satu alamat "
            "dulu, biasanya IP perangkat yang sedang kamu pakai, "
            "sebelum penyaringan dinyalakan."
        )

    with db_connection() as db:
        db.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SETTING_ENABLED, "1" if enabled else "0"),
        )


def is_allowed(ip: str) -> bool:
    """
    Mengecek apakah satu alamat boleh masuk.
    """
    if not ip:
        return False

    # Komputer yang menjalankan server selalu boleh masuk. Ini yang
    # menjamin admin punya jalan membetulkan daftar kalau salah atur.
    if is_loopback(ip):
        return True

    if not is_enabled():
        return True

    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for item in list_ips():
        entry = item["value"]

        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue

    return False
