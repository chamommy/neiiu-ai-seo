"""
Perhitungan teks yang sadar aksara.

Seluruh analisis NEIIU bersandar pada tiga angka: berapa kata satu
halaman, berapa kali keywordnya muncul, dan seberapa mirip dua
versi halaman. Ketiganya ditulis dengan anggapan teksnya memakai
spasi antar kata dan hurufnya Latin.

Bahasa Thai melanggar keduanya. Kalimatnya ditulis tanpa spasi, dan
hurufnya di luar rentang a-z. Akibatnya bukan hasil yang meleset
sedikit, melainkan angka yang salah arah: jumlah kata jadi
seperlima, density jadi berlipat, dan kemiripan dua halaman selalu
1.0 sehingga cloaking tidak pernah terdeteksi.

Aksara ditentukan dari teksnya sendiri, bukan dari zona yang
dipilih pengguna. Halaman berbahasa Thai yang muncul di pencarian
Indonesia tetap harus dihitung sebagai teks Thai.
"""

import re
import unicodedata


THAI_RANGE = re.compile(r"[฀-๿]")

# Rata-rata panjang satu kata Thai setelah tanda vokal dan nada
# dibuang. Angka ini perkiraan, bukan pemenggalan kata sungguhan,
# dan hanya dipakai untuk membandingkan panjang antar halaman.
THAI_CHARS_PER_WORD = 3.5

# Kalau sebagian kecil saja teksnya beraksara Thai, biasanya itu
# cuma nama atau kutipan di halaman berbahasa lain, jadi cara
# hitung berspasi masih yang benar.
THAI_SHARE_THRESHOLD = 0.15

# Panjang potongan untuk membandingkan dua teks tanpa spasi.
# Empat karakter kira-kira sepanjang satu kata Thai, jadi irisannya
# bermakna seperti irisan kata pada teks berspasi.
THAI_GRAM = 4

LATIN_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def thai_share(text: str) -> float:
    """
    Porsi karakter beraksara Thai dalam satu teks.
    """
    clean = [char for char in text if not char.isspace()]

    if not clean:
        return 0.0

    thai = sum(1 for char in clean if THAI_RANGE.match(char))

    return thai / len(clean)


def is_unspaced(text: str) -> bool:
    """
    Menentukan apakah teks ini ditulis tanpa spasi antar kata.
    """
    return thai_share(text) >= THAI_SHARE_THRESHOLD


def strip_marks(text: str) -> str:
    """
    Membuang tanda vokal dan nada yang menempel pada huruf.

    Di aksara Thai tanda ini ditulis di atas atau di bawah huruf
    induknya dan tidak menambah panjang kata, jadi menghitungnya
    akan melebih-lebihkan jumlah kata.
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def count_words(text: str) -> int:
    """
    Menghitung jumlah kata dengan cara yang sesuai aksaranya.

    Untuk teks tanpa spasi, bagian beraksara Thai diperkirakan dari
    jumlah hurufnya sedangkan bagian Latin (nama brand, angka)
    tetap dihitung biasa, karena halaman Thai hampir selalu
    bercampur keduanya.
    """
    clean = (text or "").strip()

    if not clean:
        return 0

    if not is_unspaced(clean):
        return len(clean.split())

    thai_chars: list[str] = []
    other_parts: list[str] = []
    buffer: list[str] = []

    for char in clean:
        if THAI_RANGE.match(char):
            if buffer:
                other_parts.append("".join(buffer))
                buffer = []

            thai_chars.append(char)
        else:
            buffer.append(char)

    if buffer:
        other_parts.append("".join(buffer))

    thai_words = round(
        len(strip_marks("".join(thai_chars))) / THAI_CHARS_PER_WORD
    )

    other_words = sum(len(part.split()) for part in other_parts)

    return max(thai_words + other_words, 1)


def count_keyword(text: str, keyword: str) -> int:
    """
    Menghitung kemunculan keyword di dalam teks.

    Batas kata (\\b) hanya dipasang kalau keywordnya memang punya
    batas kata. Di teks Thai tidak ada peralihan huruf-ke-bukan-huruf
    di antara kata, jadi \\b tidak pernah cocok dan hasilnya selalu
    nol, seolah keywordnya tidak ada di halaman mana pun.
    """
    clean = (keyword or "").strip().lower()
    body = (text or "").lower()

    if not clean or not body:
        return 0

    if is_unspaced(clean):
        return body.count(clean)

    # Batasnya diperiksa terhadap huruf Latin saja, bukan lewat \b.
    # \b menandai peralihan antara \w dan bukan \w, dan aksara Thai
    # termasuk \w, sehingga keyword Latin yang menempel pada teks
    # Thai seperti "เว็บslot gacorที่ดี" tidak pernah dianggap punya
    # batas kata dan hasilnya nol. Padahal keyword Latin di halaman
    # Thai justru lazim: nama brand dan istilah teknis.
    return len(
        re.findall(
            rf"(?<![0-9A-Za-z_]){re.escape(clean)}(?![0-9A-Za-z_])",
            body,
        )
    )


def keyword_tokens(keyword: str) -> list[str]:
    """
    Memecah keyword jadi potongan yang bisa dicari di dalam teks.

    Untuk keyword Thai tidak ada yang bisa dipecah, jadi keywordnya
    dipakai utuh. Memaksakan pemecahan lewat regex Latin
    menghasilkan daftar kosong, dan setiap pemeriksaan yang memakai
    daftar itu jadi dilewati diam-diam.
    """
    clean = (keyword or "").strip().lower()

    if not clean:
        return []

    if is_unspaced(clean):
        return [clean]

    return [
        token
        for token in re.findall(r"[^\W_]+", clean, re.UNICODE)
        if len(token) >= 3
    ]


def token_set(text: str, limit: int = 4000) -> set[str]:
    """
    Kumpulan potongan teks untuk membandingkan dua halaman.

    Teks berspasi dipecah per kata. Teks tanpa spasi dipecah jadi
    potongan empat karakter, karena tanpa itu himpunannya kosong
    dan dua halaman yang sama sekali berbeda akan dinilai identik.
    """
    body = (text or "").lower()

    if not body:
        return set()

    if is_unspaced(body):
        thai_only = "".join(
            char for char in body if THAI_RANGE.match(char)
        )

        grams = {
            thai_only[index:index + THAI_GRAM]
            for index in range(max(len(thai_only) - THAI_GRAM + 1, 0))
        }

        latin = set(LATIN_WORD.findall(body))

        # Diurutkan dulu sebelum dipotong. Urutan iterasi himpunan
        # Python ikut acak hash string yang berbeda tiap proses, jadi
        # tanpa ini potongan 4000 pertama berubah tiap kali server
        # dijalankan ulang dan vonis cloaking untuk halaman yang sama
        # bisa berbeda antar run.
        return set(sorted(grams | latin)[:limit])

    return set(sorted(set(LATIN_WORD.findall(body)))[:limit])


def anchor_id(value: str, fallback: str = "bagian") -> str:
    """
    Membuat id anchor dari teks heading.

    Aksara non-Latin dipertahankan. Kalau dibuang, semua heading
    Thai menghasilkan id yang sama, seluruh tautan daftar isi
    menunjuk ke satu tempat, dan HTML-nya punya id kembar.
    """
    # Tanda vokal dan nada Thai termasuk kategori Mn dan tidak
    # dianggap \w oleh Python, padahal tanda itu bagian dari
    # hurufnya. Kalau ikut dibuang, anchornya penuh tanda hubung
    # dan sulit dikenali saat muncul di bilah alamat.
    kept = "".join(
        char
        if (char.isalnum() or unicodedata.category(char) == "Mn")
        else "-"
        for char in str(value or "").lower()
    )

    slug = re.sub(r"-{2,}", "-", kept).strip("-")

    return slug[:60] or fallback
