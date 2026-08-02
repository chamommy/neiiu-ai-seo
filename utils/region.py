"""
Zona pencarian dan bahasa keluaran.

Satu pilihan zona menentukan tiga hal sekaligus: ke Google negara
mana pencarian dikirim, bahasa apa yang dipakai menulis halaman,
dan bagaimana teksnya diperlakukan. Ketiganya digabung di sini
supaya tidak bisa saling bertentangan, misalnya mencari di Google
Thailand tapi menulis halamannya dalam bahasa Indonesia.

Menambah negara berikutnya cukup menambah satu entri di REGIONS.
"""

import hashlib
import re
import unicodedata


# Bahasa Thai ditulis tanpa spasi antar kata, jadi teks Thai tidak
# bisa dihitung dengan .split() seperti bahasa Indonesia. Angka ini
# adalah rata-rata panjang satu kata Thai setelah tanda vokal dan
# nada dibuang. Hasilnya perkiraan, bukan pemenggalan kata sungguhan,
# dan hanya dipakai untuk membandingkan panjang halaman.
THAI_CHARS_PER_WORD = 3.5

THAI_BLOCK = re.compile(r"[฀-๿]")

# Karakter yang tidak tampak tapi ikut terbawa saat keyword ditempel
# dari halaman lain. Karakter kontrol tidak sah di dalam XML sama
# sekali: satu saja yang lolos ke <loc> membuat seluruh sitemap.xml
# gagal diurai, bukan cuma barisnya. Yang zero-width tidak merusak
# XML tapi membuat dua URL terlihat sama persis padahal berbeda.
INVISIBLE = re.compile(
    "[\x00-\x1f\x7f-\x9f"
    "­​-‏  ‪-‮"
    "⁠-⁤﻿]+"
)

# Nama yang tidak boleh dipakai sebagai nama file di Windows, apa pun
# ekstensinya. Folder hasil dinamai dari keyword, jadi keyword seperti
# "con" akan gagal dibuat kalau tidak ditangani.
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
}


# Nama bulan dipakai untuk menulis tanggal di halaman hasil. Bahasa
# Thai tidak punya bentuk bulan yang bisa diturunkan dari locale
# Python di Windows, jadi ditulis di sini supaya hasilnya sama di
# mesin mana pun.
MONTH_NAMES: dict[str, list[str]] = {
    "id": [
        "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ],
    "th": [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน",
        "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม",
        "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    ],
}


REGIONS: dict[str, dict] = {
    "id": {
        "code": "id",
        "label": "Indonesia",
        # Parameter penargetan Google.
        #
        # google_domain sengaja tidak ada di sini: Serper menerima
        # parameter itu lalu membuangnya diam-diam, dan googlehost
        # milik Google CSE sudah tidak berlaku lagi. Mencantumkannya
        # cuma memberi kesan penargetannya bekerja padahal tidak.
        "gl": "id",
        "hl": "id",
        "location": "Indonesia",
        # Bahasa keluaran halaman.
        "language_name": "Indonesia",
        "language_native": "Bahasa Indonesia",
        "html_lang": "id",
        "og_locale": "id_ID",
        "direction": "ltr",
        # Bahasa Indonesia memakai spasi antar kata.
        "word_mode": "spaced",
        # Font yang pasti punya huruf Latin di Windows dan Android.
        "font_fallback": [
            "system-ui",
            "-apple-system",
            "Segoe UI",
            "Roboto",
            "Arial",
            "sans-serif",
        ],
        # Selisih tahun yang ditulis di halaman terhadap tahun masehi.
        "year_offset": 0,
    },
    "th": {
        "code": "th",
        "label": "Thailand",
        "gl": "th",
        "hl": "th",
        "location": "Thailand",
        "language_name": "Thai",
        "language_native": "ภาษาไทย",
        "html_lang": "th",
        "og_locale": "th_TH",
        "direction": "ltr",
        "word_mode": "unspaced",
        # Font Latin biasa tidak punya aksara Thai sama sekali. Tanpa
        # font berikut, halaman Thai tampil sebagai kotak kosong di
        # sebagian perangkat.
        "font_fallback": [
            "Sarabun",
            "Noto Sans Thai",
            "Leelawadee UI",
            "Tahoma",
            "system-ui",
            "sans-serif",
        ],
        # Situs Thailand lazim menulis tahun Buddha, yaitu tahun
        # masehi ditambah 543. Yang bergeser hanya tanggal yang
        # dibaca manusia; atribut datetime pada <time> tetap masehi
        # ISO supaya mesin pencari membacanya benar.
        "year_offset": 543,
    },
}


DEFAULT_REGION = "id"


class UnknownRegionError(ValueError):
    """
    Zona yang diminta tidak ada di daftar.
    """


def region_codes() -> list[str]:
    return list(REGIONS)


def get_region(code: str = "") -> dict:
    """
    Mengambil satu entri zona.

    Zona yang tidak dikenal ditolak, bukan diam-diam diganti default.
    Salah zona berarti seluruh halaman ditulis dalam bahasa yang salah,
    dan itu terlalu mahal untuk ditebak.
    """
    clean = (code or "").strip().lower()

    if not clean:
        return REGIONS[DEFAULT_REGION]

    if clean not in REGIONS:
        available = ", ".join(sorted(REGIONS))

        raise UnknownRegionError(
            f"Zona '{code}' tidak dikenal. Pilihan: {available}"
        )

    return REGIONS[clean]


def strip_marks(text: str) -> str:
    """
    Membuang tanda vokal dan nada yang menempel pada huruf.

    Di aksara Thai tanda-tanda ini ditulis di atas atau di bawah
    huruf induknya dan tidak menambah panjang kata, jadi ikut
    menghitungnya akan melebih-lebihkan jumlah kata.
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def count_words(text: str, region: str = DEFAULT_REGION) -> int:
    """
    Menghitung jumlah kata dengan cara yang sesuai bahasanya.

    Untuk bahasa berspasi, dihitung apa adanya. Untuk bahasa tanpa
    spasi, bagian beraksara Thai diperkirakan dari jumlah hurufnya
    sedangkan bagian Latin (nama brand, angka) tetap dihitung biasa,
    karena halaman Thai hampir selalu bercampur keduanya.
    """
    clean = (text or "").strip()

    if not clean:
        return 0

    spec = get_region(region)

    if spec["word_mode"] == "spaced":
        return len(clean.split())

    thai_chars = 0
    latin_parts: list[str] = []
    buffer: list[str] = []

    for char in clean:
        if THAI_BLOCK.match(char):
            if buffer:
                latin_parts.append("".join(buffer))
                buffer = []

            thai_chars += 1
        else:
            buffer.append(char)

    if buffer:
        latin_parts.append("".join(buffer))

    thai_visible = len(strip_marks("".join(
        char for char in clean if THAI_BLOCK.match(char)
    )))

    thai_words = round(thai_visible / THAI_CHARS_PER_WORD)
    latin_words = sum(len(part.split()) for part in latin_parts)

    # Dibulatkan ke atas ke 1 supaya teks pendek tidak jadi nol kata
    # dan lolos dari pemeriksaan "halaman kosong".
    return max(thai_words + latin_words, 1 if thai_chars else 0)


def slug_for_url(text: str, region: str = DEFAULT_REGION) -> str:
    """
    Membuat slug URL yang boleh memuat aksara non-Latin.

    Slug URL beraksara Thai sah dan dipahami Google; browser yang
    mengubahnya jadi persen-encoding tetap menunjuk halaman yang sama.
    Membuang aksara Thai justru menghasilkan slug kosong dan
    menghilangkan keyword dari URL.
    """
    clean = (text or "").strip().lower()

    # Karakter kontrol dibuang lebih dulu, bukan diubah jadi tanda
    # hubung. Karakter ini tidak sah di dalam XML sama sekali, dan
    # satu saja yang lolos ke <loc> membuat sitemap.xml gagal diurai
    # seluruhnya, bukan cuma barisnya.
    clean = re.sub(INVISIBLE, '', clean)

    # Yang dibuang hanya karakter yang benar-benar bermasalah di URL,
    # bukan semua yang bukan ASCII.
    clean = re.sub(r"[\s/\\?#\[\]@!$&'()*+,;=%\"<>{}|^`~]+", "-", clean)
    clean = re.sub(r"[.]+", "-", clean)
    clean = re.sub(r"-{2,}", "-", clean).strip("-")

    return clean or "halaman"


def slug_for_filename(text: str, region: str = DEFAULT_REGION) -> str:
    """
    Membuat nama file dan folder yang aman di Windows.

    Nama file berbeda urusannya dari slug URL: aksara Thai di nama
    folder menyulitkan saat file dibuka lewat terminal atau dikirim
    lewat ZIP ke mesin lain. Jadi di sini aksara non-ASCII dibuang,
    dan kalau tidak ada yang tersisa dipakai sidik ringkas dari teks
    aslinya supaya dua keyword berbeda tidak berakhir di nama yang sama.
    """
    clean = (text or "").strip().lower()

    ascii_only = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    ascii_only = re.sub(r"-{2,}", "-", ascii_only)

    if not ascii_only:
        # Tidak ada satu pun huruf Latin yang tersisa, misalnya
        # keyword yang seluruhnya beraksara Thai. Sidik ringkas dari
        # teks aslinya dipakai supaya dua keyword yang berbeda tidak
        # berakhir di nama folder yang sama.
        ascii_only = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:10]

    if ascii_only in WINDOWS_RESERVED:
        ascii_only = f"{ascii_only}-halaman"

    return ascii_only[:80].rstrip("-") or "halaman"


def format_date(
    moment,
    region: str = DEFAULT_REGION,
) -> str:
    """
    Menulis tanggal dalam bentuk yang lazim di zona itu.

    Untuk Thailand tahunnya digeser ke tahun Buddha, karena situs
    lokal di sana menulis 2569 bukan 2026, dan tanggal masehi
    membuat halamannya terbaca seperti hasil terjemahan.
    """
    spec = get_region(region)
    months = MONTH_NAMES.get(spec["code"], MONTH_NAMES["id"])

    year = moment.year + spec["year_offset"]

    return f"{moment.day} {months[moment.month - 1]} {year}"


def iso_date(moment) -> str:
    """
    Tanggal untuk atribut mesin, selalu masehi.

    Dipisah dari format_date karena schema.org dan atribut datetime
    hanya mengenal kalender masehi. Menuliskan tahun Buddha di sana
    akan membuat tanggalnya terbaca 543 tahun di masa depan.
    """
    return moment.strftime("%Y-%m-%d")


def font_stack(extra: list[str] | None = None, region: str = DEFAULT_REGION) -> str:
    """
    Menyusun daftar font CSS yang pasti bisa menampilkan bahasanya.

    Font pilihan dari halaman acuan ditaruh di depan, tapi cadangan
    milik zona selalu ikut di belakang. Tanpa itu, halaman Thai yang
    memakai font Latin hasil tiruan kompetitor akan tampil sebagai
    deretan kotak kosong.
    """
    spec = get_region(region)

    names: list[str] = []

    for name in list(extra or []) + spec["font_fallback"]:
        clean = name.strip()

        if clean and clean not in names:
            names.append(clean)

    return ", ".join(
        name if re.match(r"^[A-Za-z0-9-]+$", name) else f'"{name}"'
        for name in names
    )
