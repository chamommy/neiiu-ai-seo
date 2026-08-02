"""
Kebijakan: slot mana yang boleh diisi, dan diisi sebagai apa.

Pemindai di template_scanner.py sengaja tidak menilai apa pun; ia
melaporkan semua potongan teks yang letaknya bisa dipastikan.
Keputusan mana yang boleh disentuh ada di sini, terpisah, karena
inilah bagian yang paling mungkin salah dan paling perlu dibaca
ulang orang.

Aturan dasarnya satu: kalau tidak jelas sebuah teks adalah isi
artikel, biarkan. Slot yang tidak terisi hanya membuat halaman
memakai teks lama template, sedangkan slot yang salah terisi
menimpa sesuatu yang mungkin penting.
"""

import re


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
)

# Bagian halaman yang isinya bukan artikel. Menu, logo, dan teks
# hukum di footer dipilih sendiri oleh pemilik template, dan
# menimpanya membuat situsnya terlihat rusak.
CHROME_TAGS = {"nav", "header", "footer", "aside", "menu"}

# Teks di dalam tag ini tidak pernah diganti. <a> ada di sini karena
# teks tautan adalah sinyal internal link yang dipilih sengaja, dan
# banyak di antaranya sebenarnya tombol yang lebarnya dipatok CSS.
NEVER_TAGS = {"a", "button", "label", "option", "th", "abbr"}

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

# Paragraf yang sangat pendek biasanya label, harga, atau potongan
# angka, bukan kalimat artikel.
MIN_PARAGRAPH_CHARS = 40

# Teks baru dibatasi sekitar panjang teks lamanya karena CSS
# template dirancang di sekitar ukuran itu. Kartu yang tadinya rapi
# jadi tidak sama tinggi kalau isinya tiba-tiba dua kali lipat.
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

    <a href="/panduan"><h2>Panduan memilih laptop</h2></a> adalah
    bentuk yang lazim di kartu artikel. Induk langsung teksnya h2,
    jadi pemeriksaan yang hanya melihat induk akan menganggapnya
    heading biasa dan menimpanya. Teks tautannya hilang, padahal
    itu justru sinyal internal link yang dipilih sengaja oleh
    pemilik template.
    """
    if slot.get("tag", "") in NEVER_TAGS:
        return True

    return any(tag in NEVER_TAGS for tag in slot.get("path", []))


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

    if in_chrome(slot):
        return ""

    if tag == "time":
        return "review_date" if nearest_hint(slot, REVIEW_HINT) else "date"

    if tag == "summary":
        return "faq_question"

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

        return ""

    if nearest_hint(slot, FAQ_HINT):
        if tag in {"h2", "h3", "h4", "h5", "dt", "strong", "b"}:
            return "faq_question"

        if tag in {"p", "div", "dd", "span"}:
            return "faq_answer"

    if tag in {"h2", "h3", "h4"}:
        return "heading"

    if tag in {"p", "li"} and len(current) >= MIN_PARAGRAPH_CHARS:
        return "paragraph"

    return ""


# Slot yang ada di <head> tidak memengaruhi tata letak sama sekali,
# jadi panjangnya ditentukan aturan hasil pencarian, bukan panjang
# teks lama di template.
HEAD_BUDGET = {
    "title": 60,
    "meta_description": 160,
    "meta_keywords": 200,
}


def length_budget(current: str, role: str = "") -> int:
    """
    Menghitung panjang maksimal teks pengganti untuk satu slot.
    """
    if role in HEAD_BUDGET:
        return HEAD_BUDGET[role]

    room = int(len(current.strip()) * LENGTH_TOLERANCE)

    return max(MIN_LENGTH_BUDGET, min(room, MAX_LENGTH_BUDGET))


def build_slot_map(scanned: dict) -> dict:
    """
    Mengelompokkan slot menurut perannya.

    Mengembalikan {"roles": {peran: [slot,...]}, "skipped": [...]}.
    """
    roles: dict[str, list[dict]] = {}
    skipped: list[dict] = []
    unquoted: list[str] = []

    for slot in scanned["slots"]:
        role = classify(slot)

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
