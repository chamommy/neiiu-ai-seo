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


# Nama orang untuk baris pengulas, satu daftar per zona.
#
# Ditulis di sini, bukan diminta ke model, dengan alasan yang sama
# seperti nama kota: yang diminta ke model tidak pernah benar-benar
# berganti. Terukur pada halaman terbit - baris "Mikaela Hyakuya -
# Malang" milik pemilik template diminta ulang ke model, dan yang
# kembali "Mikaela Hyakuya". Model diberi teks lama sebagai contoh
# bentuk, lalu diperintahkan menulis padanan yang artinya sama; untuk
# sebuah nama, padanan yang artinya sama adalah nama itu juga.
#
# Diambil dari daftar, penggantiannya pasti terjadi dan namanya pasti
# wajar di zona itu - dua hal yang tidak satu pun bisa dijamin waktu
# nama orang dikarang model 4B.
PERSON_NAMES: dict[str, list[str]] = {
    "id": [
        "Andika Pratama", "Rizky Maulana", "Dwi Lestari",
        "Bagus Setiawan", "Nurul Hidayah", "Fajar Nugroho",
        "Siti Rahmawati", "Ahmad Fauzi", "Putri Anggraini",
        "Hendra Wijaya", "Ratna Sari", "Yusuf Ramadhan",
        "Intan Permata", "Bayu Saputra", "Dewi Anjani",
        "Reza Firmansyah", "Lia Kartika", "Agus Salim",
        "Maya Puspita", "Dimas Aditya", "Wulan Safitri",
        "Iqbal Hakim", "Novi Handayani", "Teguh Prasetyo",
    ],
    "th": [
        "สมชาย ทองดี", "ปรีชา แสงทอง", "สุดา วงศ์ไทย",
        "ณัฐพล ศรีสุข", "กัญญา บุญมี", "อนุชา พรมมา",
        "วิไล จันทร์เพ็ญ", "ธนกฤต ยอดแก้ว", "พิมพ์ใจ สุขสันต์",
        "ชัยวัฒน์ เรืองศรี", "อรทัย มณีรัตน์", "ภาณุพงศ์ ใจดี",
        "นภัสสร คำแหง", "ศิริพร ทองใบ", "กิตติศักดิ์ พูลทรัพย์",
        "มาลี ดวงแก้ว", "วรวุฒิ สายทอง", "เบญจมาศ ปิ่นทอง",
        "ธีรศักดิ์ นาคเงิน", "จิราพร แก้วมณี", "สุริยา พันธุ์ดี",
        "อารีย์ ชูเกียรติ", "พงศธร รักษ์ไทย", "ขวัญฤทัย เพชรงาม",
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
        # Berapa karakter yang dipakai bahasa ini untuk mengisi satu
        # kolom lebar. Jatah panjang teks dihitung dalam kolom karena
        # itu yang menentukan tata letak, sedangkan yang dihitung
        # model dan JSON Schema adalah karakter. Tanpa angka
        # penyetaraan ini, batas yang dikirim ke model terlalu ketat
        # untuk aksara yang bertumpuk dan labelnya terpotong.
        "chars_per_column": 1.0,
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
        # Kota yang bisa dipilih sebagai titik pencarian. Nilainya
        # harus persis nama kanonik milik Serper; nama karangan
        # diabaikan diam-diam dan hasilnya balik ke tingkat negara
        # tanpa tanda apa pun.
        "cities": [
            ("Jakarta, Jakarta, Indonesia", "Jakarta"),
            ("Surabaya, East Java, Indonesia", "Surabaya"),
            ("Bandung, West Java, Indonesia", "Bandung"),
            ("Medan, North Sumatra, Indonesia", "Medan"),
            ("Semarang, Central Java, Indonesia", "Semarang"),
            ("Makassar, South Sulawesi, Indonesia", "Makassar"),
            ("Denpasar, Bali, Indonesia", "Denpasar"),
            ("Palembang, South Sumatra, Indonesia", "Palembang"),
        ],
        # Nama kota untuk ditulis DI DALAM halaman, bukan untuk
        # penargetan pencarian.
        # Daftarnya sengaja panjang. Ia dipakai dua arah: memilih kota
        # yang ditulis di halaman, DAN mengenali kota lama yang perlu
        # diganti. Untuk arah kedua, kota yang tidak ada di daftar
        # tidak akan pernah terganti - dan bekasnya terbaca di halaman
        # zona Thailand, yang terbit dengan pengulas dari "Malang" dan
        # "Bogor" karena keduanya tidak tercatat di sini.
        "city_names": [
            "Jakarta", "Surabaya", "Bandung", "Medan", "Semarang",
            "Makassar", "Denpasar", "Palembang", "Yogyakarta",
            "Tangerang", "Bekasi", "Depok", "Batam", "Pekanbaru",
            "Malang", "Bogor", "Solo", "Surakarta", "Padang",
            "Bandar Lampung", "Samarinda", "Balikpapan", "Manado",
            "Pontianak", "Banjarmasin", "Cirebon", "Serang", "Jambi",
            "Bengkulu", "Kediri", "Sidoarjo", "Gresik", "Cimahi",
            "Purwokerto", "Tasikmalaya", "Mataram", "Kupang",
            "Jayapura", "Ambon", "Palu", "Kendari", "Ternate",
            "Sukabumi", "Pekalongan", "Tegal", "Salatiga", "Madiun",
            "Probolinggo", "Pasuruan", "Jember", "Banyuwangi",
        ],
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
        # Sara dan tanda nada Thai menumpuk pada huruf induknya dan
        # tidak menambah lebar sama sekali. "ความเป็นส่วนตัว"
        # panjangnya 15 karakter tapi lebarnya 12 kolom.
        #
        # Angkanya diukur dari halaman Thai yang sudah jadi, bukan
        # ditebak: 2166 karakter untuk 1880 kolom. Tebakan yang
        # terlalu longgar justru merugikan, karena model lalu menulis
        # pas menurut batas karakter yang diberikan tapi kelebihan
        # menurut lebar yang sebenarnya tersedia, dan teksnya kena
        # potong di tahap berikutnya.
        "chars_per_column": 1.15,
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
        "cities": [
            ("Bangkok, Bangkok, Thailand", "Bangkok (กรุงเทพฯ)"),
            ("Chiang Mai, Chiang Mai, Thailand", "Chiang Mai (เชียงใหม่)"),
            ("Nonthaburi, Nonthaburi, Thailand", "Nonthaburi (นนทบุรี)"),
            ("Pattaya, Chon Buri, Thailand", "Pattaya (พัทยา)"),
            ("Phuket, Phuket, Thailand", "Phuket (ภูเก็ต)"),
            ("Khon Kaen, Khon Kaen, Thailand", "Khon Kaen (ขอนแก่น)"),
            ("Hat Yai, Songkhla, Thailand", "Hat Yai (หาดใหญ่)"),
            ("Udon Thani, Udon Thani, Thailand", "Udon Thani (อุดรธานี)"),
        ],
        "city_names": [
            "กรุงเทพฯ", "เชียงใหม่", "นนทบุรี", "พัทยา", "ภูเก็ต",
            "ขอนแก่น", "หาดใหญ่", "อุดรธานี", "นครราชสีมา", "ชลบุรี",
            "สุราษฎร์ธานี", "เชียงราย", "อยุธยา", "ระยอง", "ลำปาง",
            "พิษณุโลก", "นครสวรรค์", "สมุทรปราการ", "ปทุมธานี",
            "นครปฐม", "ราชบุรี", "กาญจนบุรี", "ตรัง", "สงขลา",
            "อุบลราชธานี", "สกลนคร", "มหาสารคาม", "ร้อยเอ็ด",
        ],
    },
}


DEFAULT_REGION = "id"


class UnknownRegionError(ValueError):
    """
    Zona yang diminta tidak ada di daftar.
    """


class UnknownCityError(ValueError):
    """
    Kota yang diminta tidak ada di daftar zona itu.
    """


def region_codes() -> list[str]:
    return list(REGIONS)


def city_codes(region: str = DEFAULT_REGION) -> list[str]:
    """
    Nama kanonik kota yang sah untuk satu zona.
    """
    return [nama for nama, _ in get_region(region)["cities"]]


def resolve_location(region: str, city: str = "") -> str:
    """
    Menentukan nilai "location" yang dikirim ke provider SERP.

    Kota yang tidak ada di daftar zona ini ditolak, bukan diteruskan
    apa adanya. Provider mengabaikan nama lokasi yang tidak dikenal
    tanpa memberi tahu, jadi kesalahan ketik akan berakhir sebagai
    hasil tingkat negara yang disangka hasil tingkat kota.
    """
    spec = get_region(region)

    clean = (city or "").strip()

    if not clean:
        return spec["location"]

    if clean not in city_codes(region):
        raise UnknownCityError(
            f"Kota '{clean}' tidak ada di daftar zona "
            f"{spec['label']}. Pilihan: "
            + ", ".join(city_codes(region))
        )

    return clean


def city_label(region: str, city: str = "") -> str:
    """
    Nama kota yang enak dibaca, untuk ditampilkan di log dan laporan.
    """
    if not city:
        return get_region(region)["label"]

    for nama, label in get_region(region)["cities"]:
        if nama == city:
            return label

    return city


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


def person_names(region: str = DEFAULT_REGION) -> list[str]:
    """
    Nama orang yang pantas ditulis sebagai pengulas di zona itu.

    Zona yang belum punya daftarnya sendiri memakai daftar Indonesia,
    bukan daftar kosong: nama Indonesia di halaman zona lain masih
    jauh lebih baik daripada nama pemilik template yang bertahan
    karena tidak ada penggantinya.
    """
    return PERSON_NAMES.get(
        get_region(region)["code"],
        PERSON_NAMES[DEFAULT_REGION],
    )


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
    #
    # Titik dua ikut dibuang walaupun sah di dalam path. Slug diambil
    # dari h1, dan h1 lazimnya berbentuk "BRAND: Judul Halaman", jadi
    # titik duanya jatuh di segmen PERTAMA - "wayangplay:-slot-gacor".
    # Segmen pertama yang memuat titik dua terbaca sebagai skema URL
    # oleh pengurai yang mengikuti RFC 3986, sehingga tautan relatif
    # ke halaman itu menunjuk ke protokol "wayangplay:" alih-alih ke
    # halamannya.
    clean = re.sub(r"[\s/\\?#\[\]@!$&'()*+,;:=%\"<>{}|^`~]+", "-", clean)
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
