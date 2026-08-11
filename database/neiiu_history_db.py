"""
Ingatan teks yang sudah pernah terbit, lintas run.

NEIIU sudah punya penolak kalimat kembar, tapi seluruhnya hidup di
dalam SATU run: begitu prosesnya selesai, semua yang pernah ditulis
hilang. Akibatnya halaman kedua untuk topik yang sama berangkat dari
titik yang persis sama dengan halaman pertama - contoh gaya yang
mirip, kompetitor yang sama, template yang sama - dan model yang
diberi masukan yang sama cenderung menjawab hal yang sama.

Yang disimpan di sini cuma teks yang sudah TERBIT, dipakai untuk dua
hal:

  1. dikirim ke model sebagai daftar yang tidak boleh dipakai lagi
  2. dipakai Python menolak jawaban yang mengulangnya, lalu memintanya
     ulang

Yang kedua yang menentukan. Aturan di prompt saja diikuti model
kadang-kadang, dan pengalaman di fitur-fitur sebelumnya di proyek ini
selalu sama: yang tidak ditegakkan di Python tidak benar-benar
berlaku.
"""

from database.app_db import db_connection, utc_now


# Peran yang diingat. Bukan semuanya: nav_label dan label isinya kata
# tunggal seperti "Beranda" yang memang harus sama di setiap halaman,
# dan melarangnya berulang berarti memaksa halaman kedua menamai
# menunya dengan kata yang aneh.
HISTORY_ROLES = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "review_tag",
    "card_title",
    "list_item",
)

# Berapa halaman terakhir yang diingat.
#
# Dibatasi karena isinya masuk ke prompt, dan prompt yang membengkak
# memakan context yang seharusnya dipakai menulis. Lima halaman sudah
# jauh lebih banyak daripada yang biasa dibuat berturut-turut untuk
# satu topik.
MAX_HISTORY_PAGES = 5

# Batas jumlah baris yang dibaca sekali muat, penjaga terakhir kalau
# satu halaman ternyata punya ratusan slot.
MAX_HISTORY_ROWS = 600

# Job yang lebih tua dari ini dibuang saat menyimpan yang baru,
# supaya tabelnya tidak tumbuh tanpa batas.
KEEP_JOBS_PER_USER = 30

# Batas panjang tiap teks yang disimpan. Yang dipakai membandingkan
# cuma pembukanya, dan paragraf 2.000 karakter utuh di dalam prompt
# memakan ruang yang tidak sebanding gunanya.
MAX_TEXT_CHARS = 400


def init_history_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS neiiu_used_text (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                keyword TEXT NOT NULL DEFAULT '',
                brand_name TEXT NOT NULL DEFAULT '',
                template_id INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_neiiu_used_lookup
            ON neiiu_used_text(user_id, job_id DESC);
            """
        )


def key_of(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def flatten(content: dict) -> list[tuple[str, str]]:
    """
    Meratakan isi satu halaman jadi pasangan (peran, teks).
    """
    hasil: list[tuple[str, str]] = []

    for role in HISTORY_ROLES:
        nilai = (content or {}).get(role)

        if nilai is None:
            continue

        daftar = nilai if isinstance(nilai, (list, tuple)) else [nilai]

        for item in daftar:
            teks = " ".join(str(item or "").split())

            if teks:
                hasil.append((role, teks[:MAX_TEXT_CHARS]))

    return hasil


def save_used_text(
    user_id: int,
    job_id: int,
    keyword: str,
    brand_name: str,
    template_id: int,
    content: dict,
) -> int:
    """
    Menyimpan teks yang terbit di satu job.

    Mengembalikan jumlah baris yang tersimpan.
    """
    baris = flatten(content)

    if not baris:
        return 0

    sekarang = utc_now()

    with db_connection() as db:
        db.executemany(
            """
            INSERT INTO neiiu_used_text (
                user_id, job_id, keyword, brand_name, template_id,
                role, text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(user_id),
                    int(job_id),
                    key_of(keyword),
                    key_of(brand_name),
                    int(template_id or 0),
                    role,
                    teks,
                    sekarang,
                )
                for role, teks in baris
            ],
        )

        # Job lama dibuang di sini, bukan lewat tugas terjadwal. Satu
        # tempat yang pasti dijalankan lebih bisa diandalkan daripada
        # tempat kedua yang harus diingat menjalankannya.
        db.execute(
            """
            DELETE FROM neiiu_used_text
            WHERE user_id = ?
              AND job_id NOT IN (
                  SELECT job_id FROM (
                      SELECT DISTINCT job_id
                      FROM neiiu_used_text
                      WHERE user_id = ?
                      ORDER BY job_id DESC
                      LIMIT ?
                  )
              )
            """,
            (int(user_id), int(user_id), KEEP_JOBS_PER_USER),
        )

    return len(baris)


def forget_job(job_id: int) -> None:
    """
    Melupakan teks satu job.

    Dipanggil saat jobnya dihapus. Tanpa ini, halaman yang sudah
    dibuang pengguna tetap membatasi halaman berikutnya - dan itu
    membingungkan justru karena tidak kelihatan di mana pun.
    """
    with db_connection() as db:
        db.execute(
            "DELETE FROM neiiu_used_text WHERE job_id = ?",
            (int(job_id),),
        )


def load_used_text(
    user_id: int,
    keyword: str,
    template_id: int,
    exclude_job: int = 0,
) -> dict[str, list[str]]:
    """
    Membaca teks yang sudah terbit di halaman-halaman sebelumnya.

    Yang diambil halaman dengan keyword yang sama ATAU template yang
    sama. Dua-duanya perlu: orang membuat halaman kedua untuk keyword
    yang sama dengan brand berbeda, dan juga memakai satu template
    untuk beberapa keyword. Kalau cuma salah satu yang dicocokkan,
    separuh kasusnya lolos tanpa ingatan sama sekali.

    Menghasilkan {peran: [teks, ...]}, terbaru lebih dulu.
    """
    syarat = ["user_id = ?"]
    params: list = [int(user_id)]

    cocok = ["keyword = ?"]
    params.append(key_of(keyword))

    if int(template_id or 0):
        cocok.append("template_id = ?")
        params.append(int(template_id))

    syarat.append("(" + " OR ".join(cocok) + ")")

    if exclude_job:
        syarat.append("job_id != ?")
        params.append(int(exclude_job))

    with db_connection() as db:
        job_rows = db.execute(
            f"""
            SELECT DISTINCT job_id
            FROM neiiu_used_text
            WHERE {" AND ".join(syarat)}
            ORDER BY job_id DESC
            LIMIT ?
            """,
            params + [MAX_HISTORY_PAGES],
        ).fetchall()

        jobs = [int(row["job_id"]) for row in job_rows]

        if not jobs:
            return {}

        tanda = ",".join("?" for _ in jobs)

        rows = db.execute(
            f"""
            SELECT role, text
            FROM neiiu_used_text
            WHERE user_id = ? AND job_id IN ({tanda})
            ORDER BY job_id DESC, id ASC
            LIMIT ?
            """,
            [int(user_id)] + jobs + [MAX_HISTORY_ROWS],
        ).fetchall()

    hasil: dict[str, list[str]] = {}

    for row in rows:
        daftar = hasil.setdefault(row["role"], [])

        if row["text"] not in daftar:
            daftar.append(row["text"])

    return hasil
