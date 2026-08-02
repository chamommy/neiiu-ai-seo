"""
Kebijakan: slot mana yang boleh diisi, dan diisi sebagai apa.

Pemindai di template_scanner.py sengaja tidak menilai apa pun; ia
melaporkan semua potongan teks yang letaknya bisa dipastikan.
Keputusan mana yang boleh disentuh ada di sini, terpisah, karena
inilah bagian yang paling mungkin salah dan paling perlu dibaca
ulang orang.

Aturan dasarnya: setiap teks yang terbaca pembaca adalah isi, dan
isi diganti. Yang tidak boleh berubah cuma tiga hal, dan ketiganya
bukan teks: susunan tag, alamat tautan, dan blok iklan.

Teks tautan dan teks menu IKUT diganti - tulisannya saja, alamatnya
tidak - karena halaman yang isinya sudah berbahasa Thai tapi
menunya masih berbahasa lama terbaca seperti pekerjaan setengah
jadi. Teks sependek itu diminta ke AI sebagai label pendek supaya
lebarnya tetap muat di tata letak yang sudah ada.
"""

import re

from generators.brand_swap import variants as brand_variants
from utils.region import REGIONS
from utils.text import display_width


# Semua nama kota dari semua zona, untuk mengenali kota mana pun yang
# ada di template - termasuk kota zona lain, yang justru paling perlu
# diganti saat halamannya dipindah ke zona baru.
ALL_CITY_NAMES = {
    nama.casefold()
    for spec in REGIONS.values()
    for nama in spec["city_names"]
}


# Peran yang dikenali. Urutan tidak penting, tapi namanya dipakai
# sebagai kunci saat isi dari AI dipetakan ke slot.
ROLES = (
    "title",
    "meta_description",
    "meta_keywords",
    "h1",
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "review_author",
    "review_date",
    "caption",
    "date",
    "lang",
    # Peran berikut lahir dari permintaan "ubah semua aspek".
    "nav_label",
    "list_item",
    "table_cell",
    "label",
    "city",
    "brand",
)

# Bagian halaman yang isinya menu, bukan artikel. Teksnya tetap
# diganti, tapi lewat peran nav_label supaya yang diminta ke AI
# berupa label sependek aslinya, bukan kalimat.
CHROME_TAGS = {"nav", "header", "footer", "aside", "menu"}

# Tag yang teksnya selalu berupa label pendek, di mana pun letaknya.
LABEL_TAGS = {"a", "button", "label", "option", "th", "abbr", "summary"}

# Teks di dalam tag ini tidak pernah diganti sama sekali. Isinya
# bukan kalimat untuk pembaca melainkan nilai yang dibaca mesin.
NEVER_TAGS = {"script", "style", "code", "pre", "textarea"}

# Teks yang bentuknya memang bukan kalimat: angka, harga, jam,
# persentase, mata uang, satu huruf. Menggantinya dengan tulisan
# tidak membuat halaman lebih baik dan justru merusak tabel harga.
NOT_PROSE = re.compile(
    r"^[\s\d\W]*$"
    r"|^(?:rp|idr|usd|thb|฿|\$)\s*[\d.,]+$"
    r"|^[\d.,]+\s*(?:%|k|jt|m|rb|bath|baht)?$",
    re.IGNORECASE,
)

# Meta yang boleh ditulis ulang, beserta perannya.
META_ROLES = {
    "description": "meta_description",
    "keywords": "meta_keywords",
    "og:description": "meta_description",
    "twitter:description": "meta_description",
    "og:title": "title",
    "twitter:title": "title",
}

FAQ_HINT = re.compile(r"faq|accordion|question|tanya|pertanyaan|คำถาม", re.I)
REVIEW_HINT = re.compile(r"review|testimoni|ulasan|rating|comment|รีวิว", re.I)
AUTHOR_HINT = re.compile(r"author|name|user|nama|reviewer|by\b|ผู้", re.I)
DATE_HINT = re.compile(r"date|time|tanggal|waktu|posted|วันที่", re.I)
CAPTION_HINT = re.compile(r"caption|figcaption|keterangan", re.I)
BRAND_HINT = re.compile(r"\bbrand\b|\blogo\b|site-?name|sitename", re.I)

# Paragraf yang sangat pendek biasanya label, harga, atau potongan
# angka, bukan kalimat artikel.
MIN_PARAGRAPH_CHARS = 40

# Teks baru dibatasi sekitar panjang teks lamanya karena CSS
# template dirancang di sekitar ukuran itu. Kartu yang tadinya rapi
# jadi tidak sama tinggi kalau isinya tiba-tiba dua kali lipat.
#
# Semua angka jatah di berkas ini bersatuan KOLOM TAMPILAN, bukan
# karakter. Dua satuan itu tidak sama untuk aksara yang bertumpuk,
# dan memakai karakter membuat setiap label Thai dinilai hampir dua
# kali lebih panjang dari yang sebenarnya terlihat.
LENGTH_TOLERANCE = 1.35
MIN_LENGTH_BUDGET = 40
MAX_LENGTH_BUDGET = 1200


def has_skip_marker(slot: dict) -> bool:
    """
    Menghormati penanda data-neiiu-skip milik pengguna.

    Ini jalan keluar untuk teks yang tidak boleh berubah tapi tidak
    bisa dikenali otomatis: harga, nomor lisensi, syarat dan
    ketentuan.
    """
    attrs = slot.get("attrs", {})

    return any(
        key.lower() in {"data-neiiu-skip", "data-neiiu"}
        and str(value).lower() in {"skip", "", "no", "false"}
        for key, value in attrs.items()
    )


def explicit_role(slot: dict) -> str:
    """
    Membaca penanda data-neiiu="..." kalau pengguna menuliskannya.

    Penanda selalu menang atas tebakan otomatis, supaya pengguna
    yang mau memastikan sesuatu terisi punya cara yang pasti.
    """
    value = str(slot.get("attrs", {}).get("data-neiiu", "")).strip().lower()

    return value if value in ROLES else ""


def in_chrome(slot: dict) -> bool:
    return any(tag in CHROME_TAGS for tag in slot.get("path", []))


def in_never(slot: dict) -> bool:
    """
    Memeriksa tag terlarang di seluruh leluhur, bukan induk langsung.

    Isi <script> dan <style> bukan teks untuk pembaca, dan
    menggantinya merusak perilaku halaman, bukan mengubah isinya.
    """
    if slot.get("tag", "") in NEVER_TAGS:
        return True

    return any(tag in NEVER_TAGS for tag in slot.get("path", []))


def in_label(slot: dict) -> bool:
    """
    Memeriksa tag berlabel pendek di seluruh leluhur.

    <a href="/panduan"><h2>Panduan memilih laptop</h2></a> adalah
    bentuk yang lazim di kartu artikel. Induk langsung teksnya h2,
    jadi pemeriksaan yang hanya melihat induk akan mengiranya
    heading biasa lalu memberinya kalimat panjang, padahal itu teks
    tautan yang lebarnya dipatok CSS.
    """
    if slot.get("tag", "") in LABEL_TAGS:
        return True

    return any(tag in LABEL_TAGS for tag in slot.get("path", []))


def is_city_name(text: str) -> bool:
    """
    Memeriksa apakah satu potongan teks memang nama kota.

    Yang dicocokkan seluruh teksnya, bukan sebagiannya. Nama kota di
    tengah kalimat sudah ikut tertulis ulang saat kalimatnya diganti;
    yang perlu ditangani di sini hanya kota yang berdiri sendiri,
    seperti di daftar cabang atau di kolom tabel.
    """
    clean = " ".join((text or "").split()).strip(" .,-|").casefold()

    if not clean or len(clean) > 40:
        return False

    return clean in ALL_CITY_NAMES


def hint_text(attrs: dict) -> str:
    return " ".join(
        str(attrs.get(key, ""))
        for key in ("class", "id", "itemprop")
    )


def own_hint(slot: dict, pattern: re.Pattern) -> bool:
    """
    Mencari petunjuk di elemen slot itu sendiri saja.
    """
    return bool(pattern.search(hint_text(slot.get("attrs", {}))))


def nearest_hint(slot: dict, pattern: re.Pattern) -> bool:
    """
    Mencari petunjuk di elemen slot dan seluruh induknya.

    Induk diambil dari tumpukan pengurai, jadi yang diperiksa
    benar-benar elemen yang membungkusnya. Blok ulasan dan blok FAQ
    hampir selalu ditandai di pembungkusnya, bukan di elemen teks.
    """
    if own_hint(slot, pattern):
        return True

    return any(
        pattern.search(hint_text(attrs))
        for attrs in slot.get("ancestors", [])
    )


def classify(slot: dict) -> str:
    """
    Menentukan peran satu slot, atau "" kalau tidak boleh disentuh.
    """
    if slot.get("in_ad"):
        return ""

    if has_skip_marker(slot):
        return ""

    marked = explicit_role(slot)

    if marked:
        return marked

    tag = slot.get("tag", "")
    current = slot.get("current", "").strip()

    if slot["kind"] == "attribute":
        # Atribut lang wajib ikut berubah. Halaman berbahasa Thai
        # yang masih menyatakan lang="id" memberi tahu mesin pencari
        # bahasa yang salah, dan itu justru merugikan halaman yang
        # isinya sudah benar.
        if tag == "html" and slot.get("attr") == "lang":
            return "lang"

        if tag != "meta":
            if slot.get("attr") == "datetime":
                # datetime di dalam blok ulasan harus ikut tanggal
                # ulasannya, bukan tanggal terbit halaman, supaya
                # teks dan atributnya tidak menunjuk hari berbeda.
                return (
                    "review_date"
                    if nearest_hint(slot, REVIEW_HINT)
                    else "date"
                )

            if slot.get("attr") == "alt":
                return "caption"

            return ""

        attrs = slot.get("attrs", {})
        name = str(
            attrs.get("name") or attrs.get("property") or ""
        ).strip().lower()

        return META_ROLES.get(name, "")

    if in_never(slot):
        return ""

    if tag == "title":
        return "title"

    if tag == "h1":
        return "h1"

    # Angka, harga, jam, dan persentase dibiarkan. Bentuknya memang
    # bukan kalimat, dan menimpanya dengan tulisan merusak tabel
    # harga atau daftar jam operasional tanpa menambah apa pun.
    if not current or NOT_PROSE.match(current):
        return ""

    if tag == "time":
        return "review_date" if nearest_hint(slot, REVIEW_HINT) else "date"

    # Nama kota diganti dengan kota di zona tujuan, bukan diminta ke
    # AI. Model kecil sering mengarang nama kota yang tidak ada, dan
    # daftar kota per zona sudah tersedia di registry.
    if is_city_name(current):
        return "city"

    # Menu, tombol, dan teks tautan: tulisannya diganti, alamatnya
    # tidak. Dipisah sebagai peran sendiri supaya yang diminta ke AI
    # berupa label sependek aslinya - kalimat panjang di dalam menu
    # akan memecah header ke dua baris.
    # Teks logo. Ini nama brand, bukan label menu: kalau ikut
    # antrean nav_label ia akan terisi "Promo" dan nama situsnya
    # hilang dari kepala halaman.
    if own_hint(slot, BRAND_HINT):
        return "brand"

    if in_label(slot):
        return "nav_label"

    if in_chrome(slot):
        # Di header dan footer, yang bukan tautan atau tombol
        # biasanya satu baris keterangan: hak cipta, alamat, jam
        # buka. Diberi jatah lebih lega daripada label menu supaya
        # kalimatnya tidak terpotong di tengah.
        return "label"

    if tag == "figcaption" or nearest_hint(slot, CAPTION_HINT):
        return "caption"

    if nearest_hint(slot, REVIEW_HINT):
        # Nama pengulas dan tanggalnya dikenali dari penanda di
        # elemen teks itu sendiri. Kalau petunjuk induk ikut
        # dihitung, seluruh isi kartu ulasan akan terlihat seperti
        # nama pengulas, karena pembungkusnya memang bernama
        # review-card atau sejenisnya.
        if own_hint(slot, AUTHOR_HINT):
            return "review_author"

        if own_hint(slot, DATE_HINT):
            return "review_date"

        if tag == "h2":
            # Judul blok ulasan, sama seperti judul blok FAQ: satu
            # baris yang memperkenalkan blocknya, bukan isi ulasan.
            # Kalau dibiarkan tanpa peran, halaman berbahasa Thai
            # terbit dengan satu baris berbahasa lama di tengahnya.
            # Nama pengulas tidak pernah ditulis sebagai h2, dan yang
            # ditandai review-author sudah tertangkap di atas.
            return "heading"

        if tag in {"p", "blockquote", "q"} or len(current) >= MIN_PARAGRAPH_CHARS:
            return "review_text"

        return "label"

    if nearest_hint(slot, FAQ_HINT):
        if tag in {"h2", "h3", "h4", "h5", "dt", "strong", "b"}:
            return "faq_question"

        if tag in {"p", "div", "dd", "span"}:
            return "faq_answer"

    if tag in {"h2", "h3", "h4", "h5", "h6"}:
        return "heading"

    if tag == "li":
        return "list_item"

    if tag == "td":
        return "table_cell"

    if tag in {"p", "blockquote", "q"}:
        # Paragraf pendek tetap diisi, tapi sebagai label. Yang
        # membedakan bukan penting atau tidaknya, melainkan berapa
        # panjang teks yang pantas menggantikannya.
        return (
            "paragraph"
            if len(current) >= MIN_PARAGRAPH_CHARS
            else "label"
        )

    # Sisanya - span, div, dd, figcaption tanpa penanda, dan
    # sebagainya. Panjang teks lamanya yang menentukan diperlakukan
    # sebagai kalimat atau sebagai label.
    return "paragraph" if len(current) >= MIN_PARAGRAPH_CHARS else "label"


# Slot yang ada di <head> tidak memengaruhi tata letak sama sekali,
# jadi panjangnya ditentukan aturan hasil pencarian, bukan panjang
# teks lama di template.
HEAD_BUDGET = {
    "title": 60,
    "meta_description": 160,
    "meta_keywords": 200,
}


# Peran yang isinya memang pendek. Batas bawah 40 karakter milik
# MIN_LENGTH_BUDGET tidak berlaku di sini: tombol "Daftar" yang
# diganti kalimat 40 karakter akan melebar keluar dari kotaknya.
SHORT_BUDGET = {
    "nav_label": 24,
    "label": 80,
    "table_cell": 40,
    "list_item": 90,
    "review_author": 28,
}

# Lantai jatah untuk label pendek, dalam kolom.
#
# Toleransi 35% cukup untuk teks yang cuma ditulis ulang dalam
# bahasa yang sama, tapi jauh terlalu ketat untuk teks yang
# diterjemahkan: satu kata bisa berlipat panjangnya di bahasa lain.
# "Privasi" lebarnya 7 kolom, jadi toleransinya memberi 9 - padahal
# padanan Thai-nya "ความเป็นส่วนตัว" butuh 12, dan hasilnya terpotong
# jadi "ความเป็น" yang tidak berarti apa-apa.
#
# Angka di bawah kira-kira selebar "Privacy Policy": muat dua kata
# di bahasa mana pun, tapi masih jelas sebuah label dan bukan
# kalimat.
MIN_SHORT_BUDGET = 16


def length_budget(current: str, role: str = "") -> int:
    """
    Menghitung lebar maksimal teks pengganti untuk satu slot.
    """
    if role in HEAD_BUDGET:
        return HEAD_BUDGET[role]

    panjang = display_width(current.strip())
    room = int(panjang * LENGTH_TOLERANCE)

    if role in SHORT_BUDGET:
        # Sedikit lebih longgar dari aslinya, tapi tetap dipatok di
        # atas supaya label pendek tidak berubah jadi kalimat.
        return max(MIN_SHORT_BUDGET, min(room, SHORT_BUDGET[role]))

    return max(MIN_LENGTH_BUDGET, min(room, MAX_LENGTH_BUDGET))


def build_slot_map(scanned: dict, old_brand: str = "") -> dict:
    """
    Mengelompokkan slot menurut perannya.

    Kalau nama brand lama diberitahukan, setiap teks yang isinya
    persis nama itu langsung diperlakukan sebagai brand, apa pun
    tagnya. Ini yang membedakan tulisan logo dari label menu di
    template yang tidak memberi penanda class apa pun.

    Mengembalikan {"roles": {peran: [slot,...]}, "skipped": [...]}.
    """
    roles: dict[str, list[dict]] = {}
    skipped: list[dict] = []
    unquoted: list[str] = []

    nama_lama = {
        " ".join(bentuk.split()).casefold()
        for bentuk in brand_variants(old_brand)
    }

    for slot in scanned["slots"]:
        role = classify(slot)

        if (
            role
            and slot["kind"] == "text"
            and nama_lama
            and " ".join(slot["current"].split()).casefold() in nama_lama
        ):
            role = "brand"

        if not role:
            skipped.append(slot)
            continue

        # Nilai atribut yang ditulis tanpa tanda kutip dilewati di
        # sini, bukan ditolak belakangan saat penggantian diterapkan.
        # Teks baru yang memuat spasi memang tidak boleh masuk ke
        # sana, tapi membatalkan seluruh job karena satu atribut jelas
        # bukan tanggapan yang benar: template yang lewat html-minifier
        # dengan removeAttributeQuotes selalu punya lang=id tanpa
        # kutip, dan seluruh template itu jadi mustahil dikerjakan.
        if slot["kind"] == "attribute" and not slot.get("quote"):
            unquoted.append(f"{slot.get('tag', '')} {slot.get('attr', '')}")
            skipped.append(slot)
            continue

        slot["role"] = role
        slot["budget"] = length_budget(slot["current"], role)

        roles.setdefault(role, []).append(slot)

    demote_block_title(roles)

    return {
        "roles": roles,
        "skipped": skipped,
        "unquoted": unquoted,
        "counts": {role: len(items) for role, items in sorted(roles.items())},
    }


def demote_block_title(roles: dict) -> None:
    """
    Mengembalikan judul blok FAQ dari peran pertanyaan ke heading biasa.

    Hampir setiap blok FAQ diawali satu judul - "Pertanyaan yang
    sering ditanyakan" - yang bentuknya sama dengan pertanyaannya:
    tag heading, di dalam pembungkus yang bertanda faq. Kalau ikut
    dihitung sebagai pertanyaan, dua hal rusak sekaligus. Judul
    blocknya hilang diganti sebuah pertanyaan, dan seluruh pasangan
    tanya-jawab bergeser satu, sehingga kartu terakhir terbit dengan
    pertanyaan lama di atas jawaban baru.

    Yang dipakai membedakan adalah kedalamannya, bukan bahasanya:
    judul blok berdiri langsung di bawah pembungkus FAQ, sedangkan
    pertanyaan selalu satu tingkat lebih dalam di dalam kartunya
    masing-masing. Kalau semua pertanyaan sedalam yang sama, tidak
    ada yang diturunkan - template itu memang tidak punya judul blok.
    """
    slots = roles.get("faq_question")

    if not slots or len(slots) < 3:
        return

    paling_dangkal = min(slot["depth"] for slot in slots)
    dangkal = [slot for slot in slots if slot["depth"] == paling_dangkal]

    if len(dangkal) != 1:
        return

    judul = dangkal[0]

    slots.remove(judul)
    judul["role"] = "heading"
    judul["budget"] = length_budget(judul["current"], "heading")

    heading = roles.setdefault("heading", [])
    heading.append(judul)

    # Urutan dokumen dijaga supaya teks yang ditulis AI turun ke
    # heading dengan urutan yang sama seperti pembacanya melihatnya.
    heading.sort(key=lambda slot: slot["start"])
