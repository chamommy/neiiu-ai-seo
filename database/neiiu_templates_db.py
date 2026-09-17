"""
Penyimpanan template landing page dan AMP milik pengguna.

Berkasnya disimpan di disk, barisnya di database. Nama berkas di
disk tidak pernah berasal dari nama berkas yang diunggah: nama dari
klien bisa memuat "..", garis miring terbalik, huruf drive, atau
nama cadangan Windows, dan semuanya bisa membuat berkas mendarat di
luar folder yang dimaksud. Yang dipakai adalah nomor template
ditambah nama tetap.
"""

import shutil
from pathlib import Path

from config import BASE_DIR
from database.app_db import db_connection, utc_now


TEMPLATE_DIR = BASE_DIR / "uploads" / "templates"

# Nama berkas di disk ditetapkan program, bukan pengguna.
LANDING_FILE = "landing.html"
AMP_FILE = "amp.html"

# Batas ukuran satu berkas. Angka ini bukan soal kuota melainkan
# soal memori: pengurai HTML memakai memori berkali lipat ukuran
# berkasnya, dan job runner berjalan di dalam proses server yang
# sama, jadi satu unggahan raksasa bisa menjatuhkan server untuk
# semua pengguna.
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024

MAX_TEMPLATES_PER_USER = 20


class TemplateError(RuntimeError):
    """
    Kegagalan yang pesannya sudah siap dibaca pengguna.
    """


def init_templates_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS neiiu_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                landing_bytes INTEGER NOT NULL DEFAULT 0,
                amp_bytes INTEGER NOT NULL DEFAULT 0,
                slot_summary TEXT NOT NULL DEFAULT '{}',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_neiiu_templates_user
            ON neiiu_templates(user_id, id DESC);
            """
        )

        # Tabel yang sudah ada sejak sebelum kolom ini lahir
        # ditambahi di tempat, bukan dibuat ulang. Template yang
        # sudah tersimpan berisi berkas di disk yang terikat ke
        # nomor barisnya; membuat ulang tabelnya memutus ikatan itu.
        kolom = {
            baris["name"]
            for baris in db.execute(
                "PRAGMA table_info(neiiu_templates)"
            ).fetchall()
        }

        if "updated_at" not in kolom:
            db.execute(
                "ALTER TABLE neiiu_templates "
                "ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
            )

            # Yang belum pernah diubah dianggap terakhir diubah saat
            # dibuat. Dikosongkan, antarmuka harus menebak-nebak
            # antara "belum pernah diubah" dan "kolomnya baru".
            db.execute(
                "UPDATE neiiu_templates SET updated_at = created_at "
                "WHERE updated_at = ''"
            )


def template_dir(user_id: int, template_id: int) -> Path:
    return TEMPLATE_DIR / str(int(user_id)) / str(int(template_id))


def count_for_user(user_id: int) -> int:
    with db_connection() as db:
        row = db.execute(
            "SELECT COUNT(*) AS jumlah FROM neiiu_templates "
            "WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    return int(row["jumlah"])


def create_template(
    user_id: int,
    name: str,
    landing_html: str,
    amp_html: str = "",
    slot_summary: str = "{}",
    notes: str = "",
) -> int:
    """
    Menyimpan satu template beserta berkasnya.
    """
    if count_for_user(user_id) >= MAX_TEMPLATES_PER_USER:
        raise TemplateError(
            f"Sudah ada {MAX_TEMPLATES_PER_USER} template tersimpan. "
            "Hapus salah satu dulu sebelum menambah yang baru."
        )

    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO neiiu_templates (
                user_id, name, landing_bytes, amp_bytes,
                slot_summary, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name.strip()[:120] or "Template",
                len(landing_html.encode("utf-8")),
                len(amp_html.encode("utf-8")),
                slot_summary,
                notes,
                waktu := utc_now(),
                waktu,
            ),
        )

        template_id = int(cursor.lastrowid)

    folder = template_dir(user_id, template_id)
    folder.mkdir(parents=True, exist_ok=True)

    (folder / LANDING_FILE).write_text(landing_html, encoding="utf-8")

    if amp_html:
        (folder / AMP_FILE).write_text(amp_html, encoding="utf-8")

    return template_id


def get_template(template_id: int, user_id: int):
    """
    Mengambil satu template milik pengguna tertentu.

    user_id selalu wajib. Menjadikannya opsional membuka jalan bagi
    satu pengguna memakai template pengguna lain hanya dengan
    menebak nomornya.
    """
    with db_connection() as db:
        return db.execute(
            "SELECT * FROM neiiu_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id),
        ).fetchone()


def list_templates(user_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT id, name, landing_bytes, amp_bytes,
                   slot_summary, notes, created_at, updated_at
            FROM neiiu_templates
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()


def read_template_files(template_id: int, user_id: int) -> dict:
    """
    Membaca isi berkas template dari disk.
    """
    row = get_template(template_id, user_id)

    if row is None:
        raise TemplateError("Template tidak ditemukan.")

    folder = template_dir(user_id, template_id)

    landing_path = folder / LANDING_FILE
    amp_path = folder / AMP_FILE

    if not landing_path.exists():
        raise TemplateError(
            "Berkas template landing page hilang dari disk."
        )

    # utf-8-sig, bukan utf-8: template yang sudah tersimpan sebelum
    # BOM disaring di lapisan unggah masih membawanya di disk, dan BOM
    # di depan <!doctype> membuat berkas AMP hasil ditolak validator.
    # Menyaringnya di sini membereskan template lama tanpa perlu
    # diunggah ulang.
    return {
        "name": row["name"],
        "landing": landing_path.read_text(encoding="utf-8-sig"),
        "amp": (
            amp_path.read_text(encoding="utf-8-sig")
            if amp_path.exists()
            else ""
        ),
    }


def update_template(
    template_id: int,
    user_id: int,
    name: str | None = None,
    landing_html: str | None = None,
    amp_html: str | None = None,
    slot_summary: str | None = None,
    notes: str | None = None,
) -> None:
    """
    Mengubah template yang sudah tersimpan, di tempatnya sendiri.

    Nomornya TIDAK berganti, dan itu yang membedakannya dari "simpan
    baru lalu hapus yang lama": nomor template adalah yang mengikat
    landing page dan AMP jadi satu pasangan, dan halaman yang sudah
    menunjuk template itu akan menunjuk yang salah begitu nomornya
    bergeser.

    Yang bernilai None tidak disentuh sama sekali - berkasnya tidak
    ditulis ulang, kolomnya tidak ikut di-UPDATE. Jadi mengganti nama
    saja tidak menyentuh satu byte pun di disk.

    Berkasnya mendarat di folder yang sama seperti waktu dibuat, dan
    namanya tetap ditetapkan program - lihat keterangan di kepala
    berkas soal nama berkas yang datang dari klien.
    """
    if get_template(template_id, user_id) is None:
        raise TemplateError("Template tidak ditemukan.")

    kolom: list[str] = []
    nilai: list = []

    if name is not None:
        kolom.append("name = ?")
        nilai.append(name.strip()[:120] or "Template")

    if landing_html is not None:
        kolom.append("landing_bytes = ?")
        nilai.append(len(landing_html.encode("utf-8")))

    if amp_html is not None:
        kolom.append("amp_bytes = ?")
        nilai.append(len(amp_html.encode("utf-8")))

    if slot_summary is not None:
        kolom.append("slot_summary = ?")
        nilai.append(slot_summary)

    if notes is not None:
        kolom.append("notes = ?")
        nilai.append(notes)

    # Waktu ubah selalu ikut, dan selalu jadi kolom terakhir yang
    # ditulis. Berkas di disk boleh berubah tanpa satu kolom pun
    # berubah - mengganti isi landing saja tidak menyentuh nama
    # maupun catatan - jadi tanpa baris ini "terakhir diubah" akan
    # berbohong justru untuk perubahan yang paling besar.
    kolom.append("updated_at = ?")
    nilai.append(utc_now())

    if kolom:
        with db_connection() as db:
            # Nama kolomnya seluruhnya tulisan tetap di atas; yang
            # datang dari pengguna cuma nilainya, dan itu tetap lewat
            # tanda tanya.
            db.execute(
                f"UPDATE neiiu_templates SET {', '.join(kolom)} "
                "WHERE id = ? AND user_id = ?",
                (*nilai, template_id, user_id),
            )

    folder = template_dir(user_id, template_id)
    folder.mkdir(parents=True, exist_ok=True)

    if landing_html is not None:
        (folder / LANDING_FILE).write_text(landing_html, encoding="utf-8")

    if amp_html is not None:
        (folder / AMP_FILE).write_text(amp_html, encoding="utf-8")


def delete_template(template_id: int, user_id: int) -> None:
    row = get_template(template_id, user_id)

    if row is None:
        raise TemplateError("Template tidak ditemukan.")

    with db_connection() as db:
        db.execute(
            "DELETE FROM neiiu_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id),
        )

    shutil.rmtree(
        template_dir(user_id, template_id),
        ignore_errors=True,
    )
