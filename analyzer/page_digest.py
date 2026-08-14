"""
Menyiapkan bahan bacaan kompetitor untuk dikirim ke AI.

Crawler sudah mengunduh seluruh halaman yang ngerank, tapi yang
selama ini tersimpan cuma angkanya: jumlah kata, jumlah H2, density
keyword. Teks halamannya dipakai sebentar untuk menghitung entity,
lalu hilang bersama variabel lokalnya. Akibatnya prompt insight
meminta model menjelaskan "kenapa halaman ini bisa naik" sambil
hanya menyodorkan tabel angka, dan model menjawab satu-satunya cara
yang mungkin: dengan membacakan ulang angka itu.

Modul ini yang menyimpan bacaannya. Bukan seluruh halaman - itu
tidak akan muat di context - melainkan bagian yang benar-benar
menjelaskan sebuah halaman: kerangka headingnya, paragraf pembuka
yang menyatakan sudut pandangnya, paragraf yang menyebut keyword,
dan pasangan tanya-jawab FAQ.

Urutan dokumen sengaja dijaga di sini. parse_html mengumpulkan
semua <p> jadi satu daftar datar dan semua <h2> jadi daftar lain,
sehingga tidak ada lagi cara mengetahui paragraf mana ada di bawah
heading mana. Padahal justru pasangan heading-dan-isinya itu yang
memperlihatkan bagaimana halaman disusun.
"""

import re

from bs4 import BeautifulSoup


BLOCK_TAGS = ("h1", "h2", "h3", "h4", "p", "li")

HEADING_TAGS = ("h1", "h2", "h3", "h4")

# Tag yang isinya bukan bacaan manusia.
NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "template",
    "nav",
    "footer",
    "form",
)

QUESTION_PATTERN = re.compile(
    r"^(apa|apakah|bagaimana|kenapa|mengapa|kapan|siapa|di\s?mana|"
    r"berapa|what|how|why|when|who|where|which|is|are|do|does|can)\b",
    re.IGNORECASE,
)

# Penanda tautan permalink yang menempel di ujung heading. Banyak
# generator dokumentasi memasangnya sebagai karakter biasa, jadi
# ikut terbaca sebagai bagian judulnya.
ANCHOR_MARKS = "¶#§🔗"

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_heading(value: str) -> str:
    return clean_text(value).rstrip(ANCHOR_MARKS + " ").strip()


def is_prose(text: str) -> bool:
    """
    Menyaring paragraf yang bentuknya kalimat, bukan daftar tautan.

    Halaman dokumentasi dan footer situs penuh baris seperti
    "Documentation : https://contoh.com" yang panjangnya lolos
    ambang karakter tapi tidak menjelaskan apa pun. Kalau ikut
    terkirim, model menyimpulkan halaman itu membahas alamat URL.
    """
    tanpa_url = URL_PATTERN.sub("", text).strip()

    # Kalau yang tersisa sesudah URL dibuang tinggal sedikit,
    # isinya memang tautan.
    if len(tanpa_url) < len(text) * 0.6:
        return False

    if len(tanpa_url) < 40:
        return False

    # Bahasa berspasi diminta punya cukup kata supaya potongan
    # seperti "Beranda Kontak Promo Daftar" tidak lolos. Bahasa
    # tanpa spasi seperti Thai dilewati dari aturan ini, karena di
    # sana jumlah spasi tidak ada hubungannya dengan jumlah kata.
    if " " in tanpa_url and len(tanpa_url.split()) < 8:
        return False

    return True


def clip(value: str, limit: int) -> str:
    """
    Memotong teks di batas kata terdekat, bukan di tengah kata.

    Teks Thai ditulis tanpa spasi antar kata, jadi kalau tidak ada
    spasi sama sekali di jangkauan potong, teksnya dipotong apa
    adanya. Itu tetap lebih baik daripada membuang seluruh kalimat.
    """
    value = clean_text(value)

    if len(value) <= limit:
        return value

    potong = value[:limit]
    spasi = potong.rfind(" ")

    # Hanya mundur ke spasi kalau spasinya tidak terlalu jauh ke
    # belakang. Kalau jauh, berarti bahasanya memang tidak berspasi.
    if spasi > limit * 0.6:
        potong = potong[:spasi]

    return potong.rstrip(" ,;:-") + "..."


def is_question(text: str) -> bool:
    if "?" in text:
        return True

    return bool(QUESTION_PATTERN.match(text))


def strip_noise(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Membuang bagian yang bukan isi artikel.

    Menu dan footer muncul di setiap halaman sebuah situs dan
    isinya nama-nama kategori, bukan pembahasan. Kalau ikut terbaca,
    model menyimpulkan halaman membahas "beranda, kontak, promo".
    """
    salinan = BeautifulSoup(str(soup), "html.parser")

    for tag in salinan(list(NOISE_TAGS)):
        tag.decompose()

    return salinan


def extract_sections(soup: BeautifulSoup, min_chars: int = 40) -> list[dict]:
    """
    Menyusun halaman jadi urutan bagian: heading beserta isinya.

    Ditelusuri sesuai urutan dokumen supaya paragraf jatuh ke
    heading yang benar-benar menaunginya.
    """
    bagian: list[dict] = []
    sekarang: dict | None = None

    for tag in soup.find_all(BLOCK_TAGS):
        teks = clean_text(tag.get_text(" ", strip=True))

        if not teks:
            continue

        if tag.name in HEADING_TAGS:
            # Heading raksasa hampir selalu hasil markup berantakan,
            # bukan judul bagian.
            if len(teks) > 200:
                continue

            judul = clean_heading(teks)

            if not judul:
                continue

            sekarang = {
                "level": int(tag.name[1]),
                "heading": judul,
                "paragraphs": [],
            }

            bagian.append(sekarang)
            continue

        if len(teks) < min_chars or not is_prose(teks):
            continue

        if sekarang is None:
            # Paragraf sebelum heading pertama: itu pembuka halaman.
            sekarang = {
                "level": 0,
                "heading": "",
                "paragraphs": [],
            }

            bagian.append(sekarang)

        sekarang["paragraphs"].append(teks)

    return bagian


def extract_faq_pairs(
    bagian: list[dict],
    limit: int = 4,
    answer_chars: int = 220,
) -> list[dict]:
    """
    Mengambil tanya-jawab, bukan cuma tanyanya.

    Selama ini yang dipanen hanya pertanyaannya. Pertanyaan
    memberitahu topik apa yang dianggap perlu dijawab; jawabannya
    yang memberitahu sedalam apa kompetitor menjawabnya.
    """
    pasangan: list[dict] = []

    for item in bagian:
        heading = item["heading"]

        if not heading or not is_question(heading):
            continue

        if not item["paragraphs"]:
            continue

        pasangan.append(
            {
                "question": clip(heading, 160),
                "answer": clip(item["paragraphs"][0], answer_chars),
            }
        )

        if len(pasangan) >= limit:
            break

    return pasangan


def pick_key_paragraphs(
    bagian: list[dict],
    keyword: str,
    limit: int,
    chars: int,
) -> list[str]:
    """
    Memilih paragraf yang paling menjelaskan isi halaman.

    Yang menyebut keyword didahulukan, karena di situlah halaman
    menyatakan hubungannya dengan pencarian. Sisanya diisi paragraf
    terpanjang, yang biasanya bagian pembahasan, bukan basa-basi.
    """
    semua: list[str] = []

    for item in bagian:
        semua.extend(item["paragraphs"])

    if not semua:
        return []

    kunci = keyword.lower().strip()

    menyebut = [teks for teks in semua if kunci and kunci in teks.lower()]
    sisanya = [teks for teks in semua if teks not in menyebut]

    sisanya.sort(key=len, reverse=True)

    terpilih = (menyebut + sisanya)[:limit]

    return [clip(teks, chars) for teks in terpilih]


def build_digest(
    html: str,
    keyword: str,
    deep: bool = True,
    outline_limit: int = 14,
    lead_chars: int = 260,
    body_limit: int = 3,
    body_chars: int = 260,
) -> dict:
    """
    Menghasilkan bahan bacaan satu halaman kompetitor.

    deep=False hanya mengambil kerangka headingnya. Dipakai untuk
    peringkat bawah: kerangkanya tetap berguna untuk melihat pola
    yang berulang, sedangkan prosanya tidak sebanding dengan tempat
    yang dimakannya di context.
    """
    soup = strip_noise(BeautifulSoup(html, "html.parser"))

    bagian = extract_sections(soup)

    outline = [
        {"level": item["level"], "heading": item["heading"]}
        for item in bagian
        if item["heading"]
    ][:outline_limit]

    if not deep:
        return {
            "outline": outline,
            "lead": "",
            "key_paragraphs": [],
            "faq": [],
            "deep": False,
        }

    pembuka = ""

    for item in bagian:
        if item["paragraphs"]:
            pembuka = clip(item["paragraphs"][0], lead_chars)
            break

    faq = extract_faq_pairs(bagian)

    # Paragraf yang sudah terpakai sebagai pembuka atau jawaban FAQ
    # tidak diambil lagi, supaya jatah yang sedikit ini tidak habis
    # untuk mengulang kalimat yang sama.
    terpakai = {pembuka} | {item["answer"] for item in faq}

    kunci = [
        teks
        for teks in pick_key_paragraphs(
            bagian,
            keyword,
            limit=body_limit + len(terpakai),
            chars=body_chars,
        )
        if teks not in terpakai
    ][:body_limit]

    return {
        "outline": outline,
        "lead": pembuka,
        "key_paragraphs": kunci,
        "faq": faq,
        "deep": True,
    }
