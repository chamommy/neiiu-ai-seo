"""
Penyimpanan job NEIIU.

Satu run pipeline butuh puluhan menit, jauh melewati batas wajar
sebuah request HTTP. Jadi job dicatat di database, dijalankan di
belakang layar, dan halaman web menanyakan kemajuannya berkala.
"""

import json

from database.app_db import db_connection, utc_now


VALID_STATUS = {"queued", "running", "success", "error", "cancelled"}


def init_jobs_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS neiiu_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                provider TEXT NOT NULL,
                crawl_limit INTEGER NOT NULL DEFAULT 10,
                serp_limit INTEGER NOT NULL DEFAULT 10,
                reference_url TEXT NOT NULL DEFAULT '',
                use_cache INTEGER NOT NULL DEFAULT 1,
                analyze_only INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'queued',
                step INTEGER NOT NULL DEFAULT 0,
                total_steps INTEGER NOT NULL DEFAULT 8,
                step_label TEXT NOT NULL DEFAULT '',
                log TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                output_dir TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_neiiu_jobs_user
            ON neiiu_jobs(user_id, id DESC);
            """
        )

        # Kolom brand ditambahkan belakangan. Tabel yang sudah
        # terlanjur dibuat tanpa kolom ini tetap dipakai, cukup
        # ditambahi.
        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(neiiu_jobs)"
            ).fetchall()
        }

        if "brand_name" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN brand_name TEXT NOT NULL DEFAULT ''"
            )

        if "base_url" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN base_url TEXT NOT NULL DEFAULT ''"
            )

        # Zona dan template ditambahkan belakangan. Job lama otomatis
        # bernilai 'id' dan 0, yang memang perilaku waktu mereka
        # dijalankan.
        if "region" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN region TEXT NOT NULL DEFAULT 'id'"
            )

        # Tanpa FOREIGN KEY karena SQLite tidak bisa menambahkannya
        # lewat ALTER TABLE. Kepemilikan tetap diperiksa di lapisan
        # web, dan template yang sudah dihapus ditangani saat job
        # membacanya, bukan dijamin oleh database.
        if "template_id" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN template_id INTEGER NOT NULL DEFAULT 0"
            )

        # Kota pencarian dan nama brand lama di template ditambahkan
        # belakangan. Kosong berarti tingkat negara dan tanpa
        # penggantian brand, sama seperti perilaku job lama.
        if "city" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN city TEXT NOT NULL DEFAULT ''"
            )

        if "template_brand" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN template_brand TEXT NOT NULL DEFAULT ''"
            )

        # Acuan gaya dan tujuan tombol ajakan, dipakai saat halaman
        # dibuat tanpa template unggahan. Disimpan sebagai satu teks
        # dipisah baris baru, bukan tabel sendiri: isinya beberapa
        # URL yang selalu dibaca sekaligus dan tidak pernah dicari
        # satu-satu.
        if "design_refs" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN design_refs TEXT NOT NULL DEFAULT ''"
            )

        if "cta_url" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN cta_url TEXT NOT NULL DEFAULT ''"
            )

        # Target panjang blok artikel, dalam kata. Nol berarti pakai
        # panjang contoh artikel di knowledge/gaya_artikel.txt apa
        # adanya, jadi job lama yang kolomnya baru ditambahkan tetap
        # berperilaku persis seperti sebelum kolom ini ada.
        if "article_words" not in columns:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN article_words INTEGER NOT NULL DEFAULT 0"
            )

        # Alamat gambar pengganti: logo, favicon, dan poster. Kosong
        # berarti gambar template dibiarkan seperti aslinya, yaitu
        # perilaku setiap job sebelum kolom ini ada.
        for kolom in ("logo_url", "favicon_url", "poster_url"):
            if kolom not in columns:
                db.execute(
                    f"ALTER TABLE neiiu_jobs "
                    f"ADD COLUMN {kolom} TEXT NOT NULL DEFAULT ''"
                )

        # Brief kreatif: nada tulisan, jenis halaman, pembaca yang
        # dituju, dan keyword pendukung.
        #
        # Keempatnya kosong secara bawaan, dan kosong berarti tidak
        # menyumbang satu baris pun ke prompt. Job lama karena itu
        # tetap berperilaku persis seperti sebelum kolom ini ada -
        # bukan cuma "mirip", melainkan promptnya sama byte per byte.
        #
        # secondary_keywords disimpan sebagai satu teks dipisah baris
        # baru, bukan tabel sendiri, dengan alasan yang sama dengan
        # design_refs: isinya beberapa potong yang selalu dibaca
        # sekaligus dan tidak pernah dicari satu-satu.
        for kolom in (
            "tone",
            "page_purpose",
            "target_audience",
            "secondary_keywords",
        ):
            if kolom not in columns:
                db.execute(
                    f"ALTER TABLE neiiu_jobs "
                    f"ADD COLUMN {kolom} TEXT NOT NULL DEFAULT ''"
                )

        # Alamat halaman yang diketik pengguna: canonical dan
        # amphtml. Kosong berarti alamat di template dibiarkan apa
        # adanya - yaitu perilaku setiap job sebelum kolom ini ada,
        # dan yang memang diminta pengguna sebagai bawaan.
        for kolom in ("canonical_url", "amphtml_url"):
            if kolom not in columns:
                db.execute(
                    f"ALTER TABLE neiiu_jobs "
                    f"ADD COLUMN {kolom} TEXT NOT NULL DEFAULT ''"
                )

        # Ruang ingatan yang dipakai job ini. Kosong berarti produksi,
        # jadi seluruh job lama tetap berjalan persis seperti dulu.
        #
        # Daftar kolom di atas dibaca sekali di awal, sedangkan fungsi
        # ini bisa dipanggil lebih dari sekali dalam satu proses.
        # Panggilan kedua sempat gagal dengan "duplicate column name"
        # karena daftarnya sudah basi, jadi yang menentukan di sini
        # hasil ALTER-nya sendiri - bukan daftar kolomnya.
        try:
            db.execute(
                "ALTER TABLE neiiu_jobs "
                "ADD COLUMN history_scope TEXT NOT NULL DEFAULT ''"
            )
        except Exception:
            pass


def create_job(
    user_id: int,
    keyword: str,
    provider: str,
    crawl_limit: int,
    serp_limit: int,
    reference_url: str,
    use_cache: bool,
    analyze_only: bool,
    brand_name: str = "",
    base_url: str = "",
    region: str = "id",
    city: str = "",
    template_id: int = 0,
    template_brand: str = "",
    design_refs: str = "",
    cta_url: str = "",
    article_words: int = 0,
    logo_url: str = "",
    favicon_url: str = "",
    poster_url: str = "",
    canonical_url: str = "",
    amphtml_url: str = "",
    tone: str = "",
    page_purpose: str = "",
    target_audience: str = "",
    secondary_keywords: str = "",
    history_scope: str = "",
) -> int:
    now = utc_now()

    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO neiiu_jobs (
                user_id, keyword, brand_name, base_url,
                provider, crawl_limit, serp_limit,
                reference_url, use_cache, analyze_only,
                region, city, template_id, template_brand,
                design_refs, cta_url, article_words,
                logo_url, favicon_url, poster_url,
                canonical_url, amphtml_url,
                tone, page_purpose, target_audience,
                secondary_keywords, history_scope,
                status, created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?, ?,
                'queued', ?, ?
            )
            """,
            (
                user_id,
                keyword,
                brand_name,
                base_url,
                provider,
                crawl_limit,
                serp_limit,
                reference_url,
                int(use_cache),
                int(analyze_only),
                region,
                city,
                int(template_id),
                template_brand,
                design_refs,
                cta_url,
                int(article_words),
                logo_url,
                favicon_url,
                poster_url,
                canonical_url,
                amphtml_url,
                tone,
                page_purpose,
                target_audience,
                secondary_keywords,
                history_scope,
                now,
                now,
            ),
        )

        return int(cursor.lastrowid)


def get_job(job_id: int, user_id: int | None = None):
    query = "SELECT * FROM neiiu_jobs WHERE id = ?"
    params: list = [job_id]

    # user_id sengaja opsional: job runner memakainya tanpa user,
    # sedangkan route web selalu mengirimkannya supaya satu user
    # tidak bisa membuka job milik user lain.
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)

    with db_connection() as db:
        return db.execute(query, params).fetchone()


def list_jobs(user_id: int, limit: int = 50):
    with db_connection() as db:
        return db.execute(
            """
            SELECT id, keyword, brand_name, base_url, provider,
                   region, city, template_id, template_brand,
                   status, step, total_steps,
                   step_label, error, output_dir, summary,
                   analyze_only, created_at, updated_at
            FROM neiiu_jobs
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()


def set_status(
    job_id: int,
    status: str,
    error: str = "",
) -> None:
    if status not in VALID_STATUS:
        raise ValueError(f"Status job tidak dikenal: {status}")

    with db_connection() as db:
        db.execute(
            """
            UPDATE neiiu_jobs
            SET status = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error, utc_now(), job_id),
        )


def update_progress(
    job_id: int,
    step: int,
    step_label: str,
    line: str,
) -> None:
    """
    Menyimpan kemajuan job dan menambahkan satu baris log.
    """
    with db_connection() as db:
        row = db.execute(
            "SELECT log FROM neiiu_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        if row is None:
            return

        try:
            log = json.loads(row["log"])
        except (json.JSONDecodeError, TypeError):
            log = []

        if line:
            log.append(
                {
                    "at": utc_now(),
                    "step": step,
                    "text": line,
                }
            )

        # Log dibatasi supaya baris crawl yang banyak tidak bikin
        # satu baris database membengkak tanpa batas.
        log = log[-200:]

        db.execute(
            """
            UPDATE neiiu_jobs
            SET step = ?, step_label = ?, log = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                step,
                step_label,
                json.dumps(log, ensure_ascii=False),
                utc_now(),
                job_id,
            ),
        )


def finish_job(
    job_id: int,
    output_dir: str,
    summary: dict,
) -> None:
    with db_connection() as db:
        db.execute(
            """
            UPDATE neiiu_jobs
            SET status = 'success',
                output_dir = ?,
                summary = ?,
                step = total_steps,
                updated_at = ?
            WHERE id = ?
            """,
            (
                output_dir,
                json.dumps(summary, ensure_ascii=False),
                utc_now(),
                job_id,
            ),
        )


def delete_job(job_id: int, user_id: int) -> None:
    with db_connection() as db:
        cursor = db.execute(
            "DELETE FROM neiiu_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )

        if cursor.rowcount == 0:
            raise ValueError("Job tidak ditemukan.")


def reset_stuck_jobs() -> int:
    """
    Menandai job yang tertinggal saat server mati.

    Job runner hidup di dalam proses server. Kalau server dimatikan
    di tengah run, statusnya akan selamanya 'running' padahal tidak
    ada yang mengerjakannya.
    """
    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE neiiu_jobs
            SET status = 'error',
                error = 'Server dimatikan saat job berjalan.',
                updated_at = ?
            WHERE status IN ('queued', 'running')
            """,
            (utc_now(),),
        )

        return cursor.rowcount
