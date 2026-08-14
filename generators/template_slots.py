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
from generators.page_prices import looks_like_price
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
    "review_tag",
    "review_date",
    "card_title",
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
    # Remah navigasi. Dipisah dari nav_label meski bentuknya mirip -
    # sama-sama tautan pendek di dalam <nav> - karena isinya beda
    # jenis. Menu menyebut bagian-bagian SITUS, dan itu milik
    # template. Breadcrumb menyebut letak HALAMAN INI di dalam
    # topiknya, jadi ia harus ikut berganti setiap kali topiknya
    # berganti.
    #
    # Selama ikut nav_label, dua kebijakan sekaligus membekukannya:
    # nav_label ada di KEPT_ROLES, dan <nav> ada di FROZEN_TAGS.
    # Akibatnya remah "Slot Online > Deposit QRIS 1 Detik" terbit
    # apa adanya di halaman yang topiknya sudah lain, lengkap di
    # hasil pencarian tepat di bawah judul.
    "breadcrumb",
)

# Bagian halaman yang isinya menu, bukan artikel. Teksnya tetap
# diganti, tapi lewat peran nav_label supaya yang diminta ke AI
# berupa label sependek aslinya, bukan kalimat.
CHROME_TAGS = {"nav", "header", "footer", "aside", "menu"}

# Tag yang teksnya selalu berupa label pendek, di mana pun letaknya.
LABEL_TAGS = {"a", "button", "label", "option", "th", "abbr", "summary"}

# Atribut yang isinya dibaca orang, bukan mesin.
LABEL_ATTRS = {"placeholder", "aria-label", "title"}

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

# "accordion" sengaja TIDAK ikut di sini. Akordeon jauh lebih sering
# dipakai untuk keterangan produk, tabel ukuran, dan syarat pengiriman
# daripada untuk FAQ - di template yang dipakai menguji, class
# "accordion-item" membuat deskripsi jersey dan daftar ongkos kirim
# ikut terbaca sebagai tanya-jawab, lalu terbit di JSON-LD sebagai
# FAQPage berisi "EU:", "Spain:", dan "Rest of the world:".
#
# Akordeon FAQ yang tidak memberi penanda apa pun tetap tertangkap,
# lewat bentuk <details><summary> di bawah - itu tanda struktural dan
# tidak bergantung pada penamaan class siapa pun.
FAQ_HINT = re.compile(r"faq|question|tanya|pertanyaan|คำถาม", re.I)
REVIEW_HINT = re.compile(r"review|testimoni|ulasan|rating|comment|รีวิว", re.I)
AUTHOR_HINT = re.compile(r"author|name|user|nama|reviewer|by\b|ผู้", re.I)
DATE_HINT = re.compile(r"date|time|tanggal|waktu|posted|วันที่", re.I)
CAPTION_HINT = re.compile(r"caption|figcaption|keterangan", re.I)
BRAND_HINT = re.compile(r"\bbrand\b|\blogo\b|site-?name|sitename", re.I)

# Paragraf yang sangat pendek biasanya label, harga, atau potongan
# angka, bukan kalimat artikel.
MIN_PARAGRAPH_CHARS = 40

# Kata pembuka pertanyaan. Dipakai untuk memisahkan judul akordeon
# yang benar-benar pertanyaan dari judul akordeon yang cuma nama
# bagian - "Shipping and Returns" bukan pertanyaan, "Apakah deposit
# aman?" iya.
QUESTION_WORDS = re.compile(
    r"^(?:apa|apakah|bagaimana|gimana|berapa|kapan|di\s?mana|ke\s?mana|"
    r"mengapa|kenapa|siapa|bolehkah|adakah|amankah|benarkah|"
    r"what|how|why|when|where|who|which|is|are|do|does|did|can|"
    r"could|should|will|would)\b",
    re.IGNORECASE,
)

# Penanda tanya bahasa Thai. Ditulis terpisah karena \b tidak pernah
# cocok di antara dua aksara Thai - seluruhnya masuk kategori \w bagi
# Python - dan penanda tanyanya lazim jatuh di akhir kalimat, bukan
# di awal.
THAI_QUESTION = re.compile(
    r"ไหม|หรือไม่|อะไร|อย่างไร|ทำไม|เมื่อไหร่|เมื่อไร|ที่ไหน|ใคร|ยังไง"
)


def looks_like_question(text: str) -> bool:
    """
    Menilai apakah satu teks memang berbunyi seperti pertanyaan.
    """
    clean = " ".join((text or "").split()).strip()

    if not clean:
        return False

    if clean.rstrip(" .:•-")[-1:] in {"?", "？"}:
        return True

    if QUESTION_WORDS.match(clean):
        return True

    return bool(THAI_QUESTION.search(clean))


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


# Bagian yang isinya kerangka situs, bukan tulisan tentang topik
# halaman. Teksnya tidak pernah ditulis ulang.
#
# <aside> sengaja TIDAK ikut meski ada di CHROME_TAGS. Sidebar
# memang sering berisi menu, tapi sama seringnya berisi tulisan
# sungguhan - ringkasan artikel, kotak promo, keterangan penulis -
# dan membekukannya berarti membiarkan kalimat milik pemilik
# template terbit di halaman yang selebihnya sudah berganti.
FROZEN_TAGS = {"footer", "header", "nav", "menu"}


def frozen_tags(slot: dict) -> set:
    """
    Bagian beku mana saja yang menaungi slot ini.
    """
    return {tag for tag in slot.get("path", []) if tag in FROZEN_TAGS}


def in_frozen(slot: dict) -> bool:
    """
    Apakah slot ini berada di bagian yang dibekukan.

    Yang dipakai tag-nya, bukan nama class. Nama class bebas
    dipilih pembuat template dan "footer-cta" di tengah halaman
    bukan footer, sedangkan tag <footer> dan <nav> sudah
    menyatakan maksudnya sendiri.
    """
    return any(tag in FROZEN_TAGS for tag in slot.get("path", []))


def in_never(slot: dict) -> bool:
    """
    Memeriksa tag terlarang di seluruh leluhur, bukan induk langsung.

    Isi <script> dan <style> bukan teks untuk pembaca, dan
    menggantinya merusak perilaku halaman, bukan mengubah isinya.
    """
    if slot.get("tag", "") in NEVER_TAGS:
        return True

    return any(tag in NEVER_TAGS for tag in slot.get("path", []))


# Penanda yang dipakai template untuk remah navigasi. Dicari di
# class, id, aria-label, dan itemtype, karena tidak ada satu bentuk
# baku - sebagian template menandainya lewat CSS, sebagian lewat
# aksesibilitas, sebagian lewat microdata schema.org.
BREADCRUMB_MARKS = ("breadcrumb", "bread-crumb", "bread_crumb", "crumb")

BREADCRUMB_ATTRS = ("class", "id", "aria-label", "itemtype", "typeof")


# Pemisah yang lazim dipakai memisahkan nama pengulas dari kotanya.
AUTHOR_SEPARATORS = ("—", "–", "-", "•", "|", ",", "·", "@")

# Bintang penilaian, dalam bentuk yang bisa ditulis sebagai teks.
RATING_MARKS = "★☆⭐"

# Akhir kalimat. Dipakai memisahkan tulisan dari keterangan.
SENTENCE_END = re.compile(r"[.!?。！？]")


def looks_like_sentence(text: str) -> bool:
    """
    Apakah teks ini berbentuk kalimat, bukan keterangan.

    Keterangan menamai sesuatu - "Ulasan Pengguna Terbaru", "Kolom
    Seksi Review" - dan berhenti tanpa titik. Tulisan yang dibaca
    orang hampir selalu punya penutup kalimat di dalamnya.

    Yang sangat panjang tetap dianggap tulisan meski tanpa titik,
    karena keterangan sepanjang itu praktis tidak ada.
    """
    bersih = str(text or "").strip()

    if len(bersih) >= 120:
        return True

    return bool(SENTENCE_END.search(bersih))


# Isi yang seluruhnya berupa penilaian: bintang, angka, pemisahnya.
# "★★★★★", "4.8", "4.8/5", "5,0 dari 5" semuanya masuk sini.
RATING_ONLY = re.compile(
    rf"^[\s{RATING_MARKS}0-9.,/|·•\-]*$"
)


def is_rating_text(text: str) -> bool:
    """
    Apakah teks ini cuma penilaian, bukan nama orang.

    Dipakai saat menelusuri mundur mencari baris nama pengulas.
    Banyak template menaruh bintang di antara nama dan isi
    ulasannya, dan tanpa pemeriksaan ini barisan bintang itulah yang
    terangkat jadi nama - lalu ditimpa nama orang, sehingga
    bintangnya hilang dan nama aslinya tetap tertinggal.
    """
    bersih = " ".join(str(text or "").split())

    if not bersih:
        return True

    if RATING_ONLY.match(bersih):
        return True

    # "Rating 4.8 dari 5" dan sejenisnya: ada kata, tapi tidak ada
    # satu pun huruf di luar kosakata penilaian.
    tanpa_angka = re.sub(r"[\d.,/|·•\-\s]", "", bersih).lower()

    return tanpa_angka in {
        "rating", "dari", "of", "ratingdari", "ratingof", "nilai",
        "skor", "score", "bintang", "stars", "star",
    }


def looks_like_author_line(text: str) -> bool:
    """
    Apakah teks ini baris identitas pengulas.

    Bentuknya khas dan berulang di hampir semua template ulasan:
    nama orang, satu pemisah, lalu kotanya - kadang ditutup bintang.
    Contoh yang terbaca di template pengguna:

        Mikaela Hyakuya — Malang • ★★★★★

    Dikenali dari bentuk, bukan dari nama class, supaya template yang
    tidak menamai elemennya tetap kebagian. Tanpa ini barisnya jatuh
    ke aturan panjang teks dan terbit sebagai komentar - dan nama
    beserta kota pengulasnya tidak pernah berganti.
    """
    bersih = " ".join(str(text or "").split())

    if not bersih or len(bersih) > 80:
        return False

    # Kalimat penuh bukan baris identitas.
    if SENTENCE_END.search(bersih):
        return False

    if any(tanda in bersih for tanda in RATING_MARKS):
        return True

    if not any(tanda in bersih for tanda in AUTHOR_SEPARATORS):
        return False

    # Harus ada nama kota yang dikenali di salah satu sisi
    # pemisahnya. Tanpa syarat ini, "Deposit - Cepat dan Aman" ikut
    # tertangkap.
    for tanda in AUTHOR_SEPARATORS:
        if tanda not in bersih:
            continue

        for bagian in bersih.split(tanda):
            if is_city_name(bagian.strip(" •|,·")):
                return True

    return False


def in_breadcrumb(slot: dict) -> bool:
    """
    Apakah slot ini bagian dari remah navigasi.

    Diperiksa sampai ke seluruh leluhur, karena penandanya berdiri
    di wadahnya - <nav class="breadcrumb"> atau <ol
    itemtype="https://schema.org/BreadcrumbList"> - sedangkan
    teksnya beberapa tingkat di dalam, di <a> atau <span> yang
    tidak bertanda apa-apa.
    """
    daftar = list(slot.get("ancestors") or [])
    daftar.append(slot.get("attrs") or {})

    for attrs in daftar:
        if not isinstance(attrs, dict):
            continue

        for kunci in BREADCRUMB_ATTRS:
            nilai = str(attrs.get(kunci) or "").lower()

            if any(tanda in nilai for tanda in BREADCRUMB_MARKS):
                return True

    return False


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

            # Atribut yang isinya tetap dibaca orang meski tidak
            # tampil sebagai teks biasa: tulisan abu-abu di kolom
            # pencarian, keterangan yang dibacakan pembaca layar,
            # tooltip yang muncul saat kursor berhenti. Selama ini
            # dilewati, sehingga nama brand lama masih tertinggal di
            # placeholder "Cari Di Google OSB99" dan aria-label
            # "Keunggulan OSB99" di halaman yang seluruh teksnya
            # sudah berganti.
            if slot.get("attr") in LABEL_ATTRS:
                return "nav_label"

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

    # Harga diperiksa SEBELUM bail-out di bawah.
    #
    # Ia memang bukan kalimat, jadi tanpa baris ini ia ikut dilewati
    # bersama jam operasional dan nomor urut. Bedanya, harga menyatakan
    # zona - dan halaman berbahasa Indonesia yang harganya masih euro
    # terbaca sebagai halaman orang lain yang tulisannya ditimpa.
    # Terukur pada halaman terbit: dua belas harga euro milik toko
    # jersey asal template bertahan utuh di halaman slot.
    #
    # Pengguna sudah menyatakannya boleh diubah, dan ini satu-satunya
    # angka yang boleh: "currency dan harga barang itu tidak apa-apa
    # di ubah". Yang menulis penggantinya Python, bukan AI - lihat
    # generators/page_prices.py.
    if current and looks_like_price(current):
        return "price"

    # Angka, jam, dan persentase dibiarkan. Bentuknya memang bukan
    # kalimat, dan menimpanya dengan tulisan merusak tabel ukuran atau
    # daftar jam operasional tanpa menambah apa pun.
    if not current or NOT_PROSE.match(current):
        return ""

    if tag == "time":
        return "review_date" if nearest_hint(slot, REVIEW_HINT) else "date"

    # Diperiksa sebelum in_label dan sebelum kebijakan beku, karena
    # kalau tidak, remah navigasi jatuh ke nav_label dan berhenti di
    # situ: tautannya pendek dan berdiri di <nav>, persis seperti
    # menu. Bedanya bukan pada bentuk, melainkan pada apa yang
    # dinyatakannya - dan itu cuma terbaca dari penanda wadahnya.
    if in_breadcrumb(slot):
        return "breadcrumb"

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

    # Akordeon FAQ, diperiksa SEBELUM tag berlabel pendek.
    #
    # <summary> ada di LABEL_TAGS, jadi selama pemeriksaan label
    # jalan lebih dulu setiap pertanyaan FAQ berakhir sebagai label
    # menu dengan jatah 24 kolom. Terbukti di halaman jadi: tujuh
    # pertanyaan berganti jadi "Slot Terbaik", "Slot Terkini",
    # "Slot Terlaris", dan seterusnya - berjejer di atas jawaban
    # yang masih kalimat penuh, dan tidak ada satu pun yang
    # bertanya apa pun.
    #
    # Bentuknya yang dipakai sebagai tanda, bukan nama classnya:
    # <details> memang elemen akordeon, dan <summary> memang
    # judulnya. Syarat berbunyi pertanyaan tetap dipasang supaya
    # akordeon non-FAQ - tabel ukuran, syarat pengiriman - tidak
    # ikut terbit sebagai FAQPage di structured data.
    if (
        tag == "summary"
        and "details" in slot.get("path", [])
        and looks_like_question(current)
    ):
        return "faq_question"

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

        # Judul blok ulasan, sama seperti judul blok FAQ: satu baris
        # yang memperkenalkan blocknya, bukan isi ulasan.
        #
        # SELURUH tingkat heading diperiksa, bukan h2 saja. Dulu cuma
        # h2, dan akibatnya terbaca di halaman jadi: template yang
        # menulis judul bloknya sebagai <h3> atau <h4> jatuh ke aturan
        # di bawah, panjangnya melewati 40 karakter, lalu terbit
        # sebagai review_text - keterangan "ini blok apa" diganti
        # sebuah komentar pengguna. Keterangan dan isi memang beda
        # jenis, dan tingkat headingnya tidak pernah jadi pembeda.
        if tag in HEADING_TAGS:
            return "heading"

        # Baris pengulas yang tidak bertanda class apa pun.
        #
        # own_hint di atas cuma menangkap template yang menamai
        # elemennya - class="reviewer-name" dan sejenisnya. Banyak
        # template tidak menamainya sama sekali, dan barisnya jatuh ke
        # aturan di bawah: kalau panjangnya lewat 40 karakter ia
        # terbit sebagai komentar, kalau tidak sebagai label. Dua-duanya
        # membuat nama dan kota pengulas tidak pernah berganti.
        #
        # Yang dipakai bentuknya: nama, pemisah, kota, kadang bintang.
        if looks_like_author_line(current):
            return "review_author"

        # Isi ulasan harus BERBENTUK kalimat, bukan sekadar panjang.
        #
        # Ambang 40 karakter sendirian terlalu longgar untuk elemen
        # yang bukan <p>: keterangan blok seperti "Apa kata pengguna
        # kami selama ini" ikut melewatinya, lalu terbit sebagai
        # komentar orang. Untuk <p> ambang lama tetap dipakai, karena
        # di situ penulisnya sendiri sudah menyatakan itu paragraf.
        # Panjang minimum tetap ditegakkan, termasuk untuk <p>.
        #
        # Kelonggaran <p> sempat tanpa syarat panjang sama sekali,
        # dengan alasan penulisnya sendiri sudah menyatakan itu
        # paragraf. Yang terlewat: blok ulasan juga memakai <p> untuk
        # LABEL. Terukur di template 298, "TRUST MEMBER" - dua belas
        # huruf di dalam <p> - terbit sebagai isi ulasan, lalu diisi
        # kalimat 180 karakter. Kotaknya selebar satu kata, jadi yang
        # tampil di halaman satu kata per baris dari atas ke bawah.
        if tag in {"p", "blockquote", "q"}:
            if len(current) >= MIN_PARAGRAPH_CHARS:
                return "review_text"

            return "label"

        if len(current) >= MIN_PARAGRAPH_CHARS and looks_like_sentence(current):
            return "review_text"

        return "label"

    if nearest_hint(slot, FAQ_HINT):
        # h6 ikut, sama seperti tingkat lainnya. Ia sempat tertinggal
        # dari daftar tanpa alasan, dan template yang menulis
        # pertanyaannya sebagai <h6> menerbitkannya sebagai heading
        # artikel - satu pertanyaan hilang, dan pasangan tanya-jawab
        # sesudahnya bergeser.
        if tag in {"h2", "h3", "h4", "h5", "h6", "dt"}:
            return "faq_question"

        # <strong> dan <b> dipakai untuk dua hal yang sama sekali
        # berbeda di dalam blok yang sama: pertanyaannya, dan kata
        # yang ditebalkan di tengah jawabannya. Bunyi teksnya yang
        # memisahkan - yang tidak bertanya apa-apa diteruskan ke
        # aturan di bawah dan berakhir sebagai label biasa.
        if tag in {"strong", "b"}:
            if looks_like_question(current):
                return "faq_question"

        elif tag in {"p", "div", "dd", "span"}:
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
    "title": 70,
    "meta_description": 180,
    "meta_keywords": 200,
}


# Lantai panjang untuk dua slot yang dibaca orang di hasil pencarian.
#
# Yang penting di sini bukan angkanya melainkan bahwa ADA lantainya.
# Sebelumnya title cuma dipatok di atas - "maksimal 60 karakter" -
# tanpa lantai sama sekali, dan model lokal selalu memilih yang aman:
# terukur pada halaman jadi, titlenya 41 karakter, jauh di bawah ruang
# yang sebenarnya ada. Judul sependek itu memakai kurang dari separuh
# baris yang diberikan Google, dan separuh sisanya adalah kata kunci
# yang tidak pernah ditulis.
#
# Angka title sempat 65-80 atas permintaan pengguna, lalu diturunkan
# lagi ke 50-70 supaya judulnya tidak kepanjangan. Rentang yang
# sekarang duduk di sekitar titik potong tampilan Google - sekitar 580
# piksel, kira-kira 60 karakter - jadi sebagian besar judul terbaca
# utuh di layar, dan yang melewatinya cuma kehilangan ekornya.
#
# Deskripsi sempat 160-200, lalu diturunkan ke 140-180 atas permintaan
# pengguna. Rentang yang sekarang duduk di sekitar titik potong
# tampilan Google - sekitar 155-160 karakter di layar ponsel - jadi
# sebagian besar deskripsi terbaca utuh, sementara yang di bawah 140
# masih membuang ruang yang sudah diberikan. Yang lewat batas tetap
# terbaca mesin pencari, jadi bagian terpenting tetap ditulis di depan.
# Aturannya ada di brief.
HEAD_FLOOR = {
    "title": 50,
    "meta_description": 140,
}


# Lantai untuk teks yang dibaca orang di badan halaman.
#
# Berbeda dari HEAD_FLOOR yang berlaku mutlak, yang ini dipatok ke
# jatah slotnya sendiri lewat FLOOR_SHARE di bawah. Alasannya, slot di
# badan halaman punya lebar yang berbeda-beda dan sebagiannya memang
# sempit; memaksa 200 karakter ke kartu yang jatahnya 120 cuma
# memindahkan masalahnya ke tata letak.
#
# Ulasan ikut karena inilah keluhannya: "ulasannya terlalu pendek".
# Terukur pada template pengguna, lima slot ulasannya berjatah 162,
# 176, 172, 148, dan 164 karakter - cukup untuk dua kalimat - dan yang
# terbit rutin cuma satu kalimat pujian.
BODY_FLOOR = {
    "review_text": 120,
    "paragraph": 150,
    "faq_answer": 110,
}

# Berapa bagian dari jatah slotnya yang wajib terisi.
#
# Lantai tetap saja tidak cukup. Slot paragraf di template pengguna
# berjatah 542 karakter, dan lantai 150 membiarkan model menulis 160
# lalu berhenti - secara teknis lolos, tapi meninggalkan tujuh
# persepuluh ruangnya kosong. Yang mengikat karena itu yang lebih
# besar di antara lantai tetap dan sebagian jatahnya sendiri.
#
# 0,55 dipilih supaya paragraf yang jatahnya besar tetap terisi tebal
# tanpa memaksa model menulis persis sampai batas - ruang sisanya
# yang membuat kalimat terakhirnya bisa ditutup dengan wajar.
FLOOR_SHARE = 0.55


def length_floor(role: str = "", budget: int = 0) -> int:
    """
    Panjang terpendek yang masih diterima untuk satu slot.

    Nol berarti tidak ada lantai. Itu jawaban untuk sebagian besar
    peran: menu, tombol, label formulir, dan sel tabel panjangnya
    ditentukan teks lama yang digantikannya, dan memaksa lantai di
    sana akan melebarkan tombol keluar dari kotaknya.
    """
    if role in HEAD_FLOOR:
        return HEAD_FLOOR[role]

    dasar = BODY_FLOOR.get(role, 0)

    if not dasar or budget <= 0:
        return 0

    # Slot yang jatahnya sendiri di bawah lantai tidak diberi lantai
    # sama sekali. Yang seperti itu bukan paragraf artikel melainkan
    # keterangan pendek yang kebetulan berperan sama - di template
    # pengguna ada slot "paragraph" berjatah 79 karakter - dan memaksa
    # lantai di sana berarti memaksa teksnya menempel persis di batas
    # kotaknya.
    if budget < dasar:
        return 0

    return max(dasar, int(budget * FLOOR_SHARE))


# Peran yang isinya memang pendek. Batas bawah 40 karakter milik
# MIN_LENGTH_BUDGET tidak berlaku di sini: tombol "Daftar" yang
# diganti kalimat 40 karakter akan melebar keluar dari kotaknya.
# Remah navigasi terbit di satu baris bersama pemisahnya, dan baris
# itu tidak boleh membungkus. Diberi sedikit lebih lega daripada menu
# karena remah menyebut topik - "Panduan Belajar Python" - sedangkan
# menu cuma menyebut bagian situs.
#
# Diberi nama supaya pipeline bisa memakai angka yang sama saat
# memesan remah ke AI untuk template yang menyimpannya di JSON-LD
# saja, yaitu template yang tidak punya slot remah sama sekali.
BREADCRUMB_WIDTH = 34


SHORT_BUDGET = {
    "nav_label": 24,
    "breadcrumb": BREADCRUMB_WIDTH,
    "label": 80,
    "table_cell": 40,
    "list_item": 90,
    "review_author": 28,
    # Judul kartu keunggulan. Nomor urutnya ikut dihitung di sini
    # karena ikut tertulis di slotnya: "1. Deposit QRIS 1 Detik"
    # lebarnya 23 kolom, dan tiga kata Indonesia yang menggantikannya
    # jarang lebih dari itu.
    "card_title": 60,
    "review_tag": 40,
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


# Jatah paling sempit yang masih masuk akal untuk peran tertentu.
#
# Jatah biasanya diturunkan dari lebar teks lama, dan untuk hampir
# semua peran itu benar - yang menentukan muat atau tidak adalah kotak
# tempat teks itu berdiri. Tiga peran di bawah ini berbeda: isinya
# mengalir dan membungkus sendiri ke baris berikutnya, jadi yang
# dijaga bukan lebar kotaknya melainkan apakah kalimatnya sanggup
# mengatakan sesuatu.
#
# Ini penyebab pertanyaan FAQ yang terbit KOSONG, dan sebabnya tidak
# kelihatan dari gejalanya. Satu slot di template pengguna berisi
# "Apakah proses deposit QRIS aman?" - 32 kolom - sehingga jatahnya
# 43 karakter. Pertanyaan tidak pernah dipotong (memotong pertanyaan
# menghasilkan pertanyaan yang rusak, bukan yang lebih pendek), jadi
# jawaban model yang 58 karakter dibuang bulat-bulat, diminta ulang
# dua kali, dan tetap dibuang. Slotnya lalu terbit dengan pertanyaan
# LAMA milik brand lama, sementara jawaban barunya sudah terpasang di
# bawahnya - dan itulah "ditanya A dijawab B" yang tersisa.
#
# Nama brand baru saja sudah bisa memakan selisihnya: "OSB99" lima
# huruf, "BAMTOTO" tujuh.
MIN_ROLE_BUDGET = {
    "faq_question": 90,
    "faq_answer": 160,
    "review_text": 140,
}


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

    return max(
        MIN_ROLE_BUDGET.get(role, MIN_LENGTH_BUDGET),
        min(room, MAX_LENGTH_BUDGET),
    )


# Peran yang teksnya TIDAK pernah ditulis ulang oleh AI.
#
# Isinya bukan tulisan tentang topik halaman melainkan perkakas
# situsnya: menu, tombol, label formulir, keterangan gambar, sel
# tabel. Menuliskannya ulang tidak pernah membuat halaman lebih
# menjelaskan apa pun, dan yang terjadi justru sebaliknya - terukur
# di template pengguna: 72 nav_label berisi "Skip to content",
# "Size Guide", "XS", "S", "M", dan 36 label berisi "Roster", "Name
# and Number is required", "Details:". Semuanya milik toko yang
# templatenya dipinjam, dan semuanya ikut ditulis ulang jadi kalimat
# tentang slot online.
#
# Dilewati di sini, BUKAN dibekukan. Bedanya menentukan: slot yang
# dilewati tetap kebagian dua lapis berikutnya - nama brand lama di
# dalamnya diganti, dan teks yang bunyinya sama dengan judul lama
# ikut memakai judul baru. Itu yang membuat 34 atribut alt gambar
# yang isinya "OSB99 - Solusi Deposit QRIS 1 Detik yang Cepat dan
# Praktis" terbit sebagai judul baru, bukan sebagai kalimat karangan
# yang berbeda-beda di tiap gambar.
KEPT_ROLES = {"nav_label", "label", "caption", "table_cell"}


# Peran yang ditulis ulang HANYA kalau berdiri di dalam bagian milik
# brand lama. Di luar itu isinya milik pemilik template.
#
# Template pengguna memuat keduanya sekaligus: 12 paragraf salinan
# produk adidas ("Exude confidence on the pitch with the Real Madrid
# 26/27 home jersey...") dan 15 paragraf blok SEO brand lama. Keduanya
# berperan "paragraph" dan tidak ada bedanya kalau dilihat satu per
# satu - yang membedakan cuma di bawah judul mana masing-masing
# berdiri.
BLOCK_SCOPED_ROLES = {"paragraph", "list_item"}


HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Judul yang boleh membatasi bagian. h1 sengaja tidak ikut.
#
# h1 menamai seluruh halaman, bukan satu bagian di dalamnya, jadi ia
# tidak pernah menandai di mana sebuah bagian berakhir. Terukur di
# template pengguna: h1 berisi judul SEO brand lama berdiri di byte
# 411.936, sementara paragraf milik toko berdiri di 451.706 - jauh
# sesudahnya tapi masih sebelum judul berikutnya. Memakai h1 sebagai
# pembatas membuat dua paragraf toko itu terhitung milik brand lama.
SECTION_TAGS = ("h2", "h3", "h4", "h5", "h6")


def heading_sections(scanned: dict) -> list[tuple[int, str]]:
    """
    Letak dan bunyi tiap judul bagian, urut dokumen.

    Dibaca dari SELURUH judul di dokumen, bukan dari slot heading yang
    dikenali. Bedanya menentukan: template pengguna punya 19 judul
    tapi hanya 5 di antaranya jadi slot, dan judul yang tidak jadi
    slot - "Become a Madridista Platinum" - justru yang membatasi
    paragraf milik tokonya.

    Bunyi judul diambil dari teks pertama sesudah tagnya. Itu benar
    untuk judul yang isinya teks biasa, dan judul yang isinya bukan
    teks biasa - ikon, gambar - tidak akan cocok dengan nama brand
    mana pun, jadi bagiannya jatuh ke sisi yang aman.
    """
    teks = sorted(
        (slot["start"], " ".join(str(slot["current"]).split()))
        for slot in scanned["slots"]
        if slot["kind"] == "text" and str(slot["current"]).strip()
    )

    hasil: list[tuple[int, str]] = []

    for element in scanned["elements"]:
        if element["tag"] not in SECTION_TAGS:
            continue

        mulai = element["start"]

        isi = next(
            (nilai for posisi, nilai in teks if posisi > mulai),
            "",
        )

        hasil.append((mulai, isi))

    hasil.sort()

    return hasil


# Tanda pisah yang lazim memisahkan nama situs dari sisa judulnya.
TITLE_SPLIT = re.compile(r"\s*[|–—:\-·]\s+")


def guess_old_brand(roles: dict) -> str:
    """
    Menebak nama brand lama dari judul template, kalau tidak diberi.

    Judul halaman hampir selalu dibuka nama situsnya sendiri -
    "OSB99 - Solusi Deposit QRIS 1 Detik yang Cepat dan Praktis" -
    jadi potongan sebelum tanda pisah pertama adalah tebakan yang
    murah dan biasanya benar.

    Dipakai hanya untuk mengenali bagian mana milik brand lama.
    Penggantian nama sendiri TIDAK memakai tebakan ini: mengganti
    kata yang cuma ditebak berarti menulis ulang teks pemilik
    template atas dasar dugaan, dan itu jauh lebih merugikan
    daripada satu bagian yang tidak dikenali.
    """
    for peran in ("title", "h1"):
        for slot in roles.get(peran, []):
            judul = " ".join(str(slot["current"]).split())

            if not judul:
                continue

            depan = TITLE_SPLIT.split(judul, maxsplit=1)[0].strip()

            # Satu sampai dua kata. Lebih dari itu bukan nama situs
            # melainkan kalimat yang kebetulan tidak punya tanda pisah.
            if depan and len(depan.split()) <= 2 and len(depan) <= 30:
                return depan

    return ""


# Sepanjang apa satu baris masih masuk akal sebagai nama pengulas.
#
# "Mikaela Hyakuya — Malang • ★★★★★" panjangnya 32 kolom. Batas di
# bawah memberi ruang untuk nama panjang dan kota bernama dua kata,
# tapi tetap menolak kalimat - baris yang lebih panjang dari ini
# hampir pasti kalimat pembuka blok, bukan nama orang.
MAX_AUTHOR_WIDTH = 80


def promote_review_authors(scanned: dict, roles: dict, skipped: list) -> int:
    """
    Menaikkan baris nama pengulas jadi peran review_author.

    Nama pengulas dikenali dari LETAKNYA, bukan dari penandanya.
    Penanda memang cara yang lebih pasti, tapi tidak selalu ada:
    template pengguna menulis barisnya sebagai <strong> polos tanpa
    class apa pun -

        <strong>Mikaela Hyakuya — Malang • ★★★★★</strong>
        <span>Deposit pakai QRIS benar-benar cepat...</span>

    - sehingga terbaca sebagai label biasa, dan berakhir dibekukan
    bersama label formulir. Akibatnya halaman zona Thailand terbit
    dengan lima pengulas bernama Indonesia dari kota Indonesia.

    Yang dipakai di sini satu-satunya hal yang selalu benar tentang
    baris itu: ia berdiri tepat sebelum isi ulasannya. Judul blok
    tidak ikut terangkat karena tagnya heading, dan slot yang sudah
    punya peran lain dibiarkan.
    """
    isi_ulasan = roles.get("review_text")

    if not isi_ulasan:
        return 0

    teks = sorted(
        (slot["start"], slot)
        for slot in scanned["slots"]
        if slot["kind"] == "text" and str(slot["current"]).strip()
    )

    sudah_berperan = {
        (slot["start"], slot["end"])
        for slots in roles.values()
        for slot in slots
    }

    diangkat: list[dict] = []

    for ulasan in isi_ulasan:
        # Slot sebelum isi ulasan, dari yang terdekat ke yang terjauh.
        #
        # Dulu yang diambil cuma SATU yang terdekat, dan itu salah
        # untuk kartu yang menaruh bintang di antara nama dan
        # ulasannya:
        #
        #     <strong>Jeongmin Choi</strong>
        #     <span>★★★★★</span>          <- yang terdekat
        #     <p>isi ulasannya...</p>
        #
        # Yang terangkat jadi nama pengulas adalah barisan bintangnya,
        # lalu ditimpa nama orang - sehingga bintangnya lenyap - dan
        # nama aslinya di <strong> tidak pernah tersentuh. Terbaca di
        # halaman jadi: "Jeongmin Choi | Intan Permata", nama lama
        # berdampingan dengan nama baru.
        #
        # Sekarang penelusurannya mundur melewati apa pun yang jelas
        # bukan nama. Dibatasi beberapa langkah supaya tidak menyeret
        # teks milik kartu sebelumnya.
        kandidat = []

        for posisi, slot in teks:
            if posisi >= ulasan["start"]:
                break

            kandidat.append(slot)

        sebelum = None

        for slot in reversed(kandidat[-4:]):
            teks_slot = str(slot["current"]).strip()

            # HANYA penilaian yang dilewati. Sisanya menghentikan
            # penelusuran, bukan dilompati.
            #
            # Bedanya penting, dan sempat salah: begitu apa pun boleh
            # dilompati, kartu yang slot terdekatnya sudah dipakai
            # membuat penelusuran jalan terus sampai menabrak baris
            # "Tag: Cepat & Praktis" milik kartu di atasnya, lalu
            # baris tag itu terbit sebagai nama orang. Yang dicari
            # berdiri TEPAT sebelum ulasannya - paling jauh dipisahkan
            # bintang.
            if is_rating_text(teks_slot):
                continue

            if (slot["start"], slot["end"]) in sudah_berperan:
                break

            if slot.get("frozen") or slot.get("in_ad"):
                break

            if slot.get("tag") in HEADING_TAGS:
                break

            if TAG_HINT.match(teks_slot):
                break

            if display_width(teks_slot) > MAX_AUTHOR_WIDTH:
                break

            sebelum = slot
            break

        if sebelum is None:
            continue

        diangkat.append(sebelum)
        sudah_berperan.add((sebelum["start"], sebelum["end"]))

    if not diangkat:
        return 0

    dibuang = {(slot["start"], slot["end"]) for slot in diangkat}

    skipped[:] = [
        slot
        for slot in skipped
        if (slot["start"], slot["end"]) not in dibuang
    ]

    for slot in diangkat:
        slot.pop("kept", None)
        slot["role"] = "review_author"
        slot["budget"] = length_budget(slot["current"], "review_author")

    roles.setdefault("review_author", []).extend(diangkat)
    roles["review_author"].sort(key=lambda slot: slot["start"])

    return len(diangkat)


# Sepanjang apa satu baris masih masuk akal sebagai judul kartu.
#
# "5. Mendukung Berbagai Pembayaran" lebarnya 32 kolom. Batas di
# bawah memberi ruang untuk judul empat kata bernomor, tapi menolak
# kalimat - yang lebih panjang dari ini adalah keterangan kartunya,
# bukan judulnya, dan keterangan itu sudah punya perannya sendiri.
MAX_CARD_TITLE_WIDTH = 64

# Sedalam apa selisih kedalaman dua slot masih terhitung sekartu.
#
# Judul kartu dan keterangannya hampir selalu bersaudara langsung -
# <strong> lalu <span> di dalam satu <div> - jadi kedalamannya sama.
# Selisih satu diberikan untuk template yang membungkus salah
# satunya sekali lagi. Lebih dari itu bukan satu kartu melainkan dua
# bagian halaman yang kebetulan bertetangga.
SAME_CARD_DEPTH = 1

# Penanda baris tag di kartu ulasan, kalau template menuliskannya.
TAG_HINT = re.compile(r"^\s*(?:tag|label|kategori|topik|#)\b", re.I)


def previous_text_slot(teks: list[tuple[int, dict]], batas: int) -> dict | None:
    """
    Slot teks terakhir yang berdiri sebelum satu posisi.
    """
    sebelum = None

    for posisi, slot in teks:
        if posisi >= batas:
            break

        sebelum = slot

    return sebelum


def next_text_slot(teks: list[tuple[int, dict]], batas: int) -> dict | None:
    """
    Slot teks pertama yang berdiri sesudah satu posisi.
    """
    for posisi, slot in teks:
        if posisi > batas:
            return slot

    return None


def sorted_text_slots(scanned: dict) -> list[tuple[int, dict]]:
    """
    Semua slot teks berisi, urut dokumen.
    """
    return sorted(
        (slot["start"], slot)
        for slot in scanned["slots"]
        if slot["kind"] == "text" and str(slot["current"]).strip()
    )


def can_promote(slot: dict | None, sudah_berperan: set) -> bool:
    """
    Apakah satu slot yang dilewati kebijakan boleh diangkat perannya.

    Yang diangkat hanya slot yang DILEWATI karena dianggap perkakas
    situs - ditandai "kept". Slot yang dilewati karena alasan lain
    tidak ikut: yang berada di iklan, yang diberi penanda skip
    pengguna, yang isinya angka, dan yang berdiri di dalam <script>
    semuanya dilewati dengan alasan yang tetap berlaku.
    """
    if slot is None:
        return False

    if (slot["start"], slot["end"]) in sudah_berperan:
        return False

    if not slot.get("kept"):
        return False

    if slot.get("frozen") or slot.get("in_ad"):
        return False

    if slot.get("tag") in HEADING_TAGS:
        return False

    # Teks tautan dan tombol tidak pernah diangkat.
    #
    # Bentuknya memang cocok - pendek, tebal, berdiri tepat di atas
    # sebuah paragraf - tapi teks itu menunjuk ke sebuah alamat.
    # Menuliskannya ulang sebagai judul kartu membuat "Lihat Semua"
    # yang menuju /koleksi terbit sebagai "Spin Tanpa Jeda":
    # alamatnya benar, tulisannya berbohong.
    return slot.get("tag") not in LABEL_TAGS


def take_from_skipped(skipped: list, diangkat: list[dict], role: str) -> None:
    """
    Memindahkan slot dari daftar yang dilewati ke sebuah peran.
    """
    dibuang = {(slot["start"], slot["end"]) for slot in diangkat}

    skipped[:] = [
        slot
        for slot in skipped
        if (slot["start"], slot["end"]) not in dibuang
    ]

    for slot in diangkat:
        slot.pop("kept", None)
        slot["role"] = role
        slot["budget"] = length_budget(slot["current"], role)


def promote_card_titles(scanned: dict, roles: dict, skipped: list) -> int:
    """
    Menaikkan judul kartu keunggulan jadi peran card_title.

    Kartu fitur ditulis sebagai judul pendek yang ditebalkan lalu
    keterangannya di sebelahnya -

        <strong>1. Deposit QRIS 1 Detik</strong>
        <span>Proses deposit berlangsung cepat...</span>

    - dan judul sependek itu tidak punya penanda apa pun yang
    membedakannya dari label formulir, jadi classify() memberinya
    peran label dan label dibekukan bersama "Size Guide" dan "XS".

    Akibatnya terbaca di halaman terbit dan dilaporkan pengguna:
    enam keterangan kartu berganti jadi tulisan tentang brand baru,
    sementara keenam judulnya masih "1. Deposit QRIS 1 Detik" milik
    brand lama - halaman yang isinya sudah berganti tapi daftar
    keunggulannya menjanjikan hal yang tidak dibahas di bawahnya.

    Yang dipakai membedakan letaknya: judul kartu berdiri tepat
    sebelum keterangan kartunya, sekedalaman dengannya, dan lebih
    pendek daripadanya. Label formulir tidak pernah memenuhi
    ketiganya sekaligus.

    Dijalankan SESUDAH scope_to_brand_block, dan itu mengikat:
    sesudah penyisihan itu, peran paragraph tinggal berisi teks yang
    memang milik bagian brand lama. Dijalankan sebelumnya, setiap
    keterangan produk milik toko yang templatenya dipinjam ikut
    menyeret label di atasnya.
    """
    keterangan = roles.get("paragraph")

    if not keterangan:
        return 0

    teks = sorted_text_slots(scanned)

    sudah_berperan = {
        (slot["start"], slot["end"])
        for slots in roles.values()
        for slot in slots
    }

    diangkat: list[dict] = []

    for kartu in keterangan:
        judul = previous_text_slot(teks, kartu["start"])

        if not can_promote(judul, sudah_berperan):
            continue

        if abs(judul["depth"] - kartu["depth"]) > SAME_CARD_DEPTH:
            continue

        lebar = display_width(str(judul["current"]).strip())

        if lebar > MAX_CARD_TITLE_WIDTH:
            continue

        # Judul selalu lebih pendek daripada yang dikepalainya. Dua
        # teks yang panjangnya sebanding adalah dua paragraf, dan yang
        # di atas sudah punya jalannya sendiri lewat peran paragraph.
        if lebar >= display_width(str(kartu["current"]).strip()):
            continue

        # Keterangan yang dikepalainya dicatat, supaya giliran yang
        # menulis judul kartu bisa membacanya lebih dulu. Judul kartu
        # yang ditulis tanpa melihat keterangannya menghasilkan
        # halaman yang strukturnya utuh tapi judul kartunya
        # menjanjikan hal lain daripada kalimat di bawahnya.
        judul["partner"] = kartu["start"]

        diangkat.append(judul)
        sudah_berperan.add((judul["start"], judul["end"]))

    if not diangkat:
        return 0

    take_from_skipped(skipped, diangkat, "card_title")

    roles.setdefault("card_title", []).extend(diangkat)
    roles["card_title"].sort(key=lambda slot: slot["start"])

    return len(diangkat)


def promote_review_tags(scanned: dict, roles: dict, skipped: list) -> int:
    """
    Menaikkan baris tag di kartu ulasan jadi peran review_tag.

    Sama sebabnya dengan judul kartu, dan sama kelihatannya di
    halaman terbit: <em>Tag: Cepat &amp; Praktis</em> lebarnya 20
    kolom, jadi ia label, jadi ia dibekukan - dan lima kartu ulasan
    terbit dengan lima ulasan baru yang seluruhnya ditandai dengan
    tag milik brand lama.

    Letaknya lagi yang dipakai: baris tag berdiri tepat SESUDAH isi
    ulasannya, di dalam kartu yang sama. Nama pengulas berikutnya
    juga berdiri sesudahnya, tapi sudah punya peran sendiri dari
    promote_review_authors - jadi urutan kedua fungsi ini mengikat.
    """
    isi_ulasan = roles.get("review_text")

    if not isi_ulasan:
        return 0

    teks = sorted_text_slots(scanned)

    sudah_berperan = {
        (slot["start"], slot["end"])
        for slots in roles.values()
        for slot in slots
    }

    batas_kartu = sorted(slot["start"] for slot in isi_ulasan)

    diangkat: list[dict] = []

    for ulasan in isi_ulasan:
        tag = next_text_slot(teks, ulasan["start"])

        if not can_promote(tag, sudah_berperan):
            continue

        # Masih di kartu yang sama, bukan sudah masuk kartu ulasan
        # berikutnya.
        if any(
            ulasan["start"] < mulai <= tag["start"] for mulai in batas_kartu
        ):
            continue

        if display_width(str(tag["current"]).strip()) > MAX_AUTHOR_WIDTH:
            continue

        # Dua bentuk yang sama-sama sah. Template pengguna memakai
        # yang pertama; template yang menulis tagnya tanpa awalan
        # apa pun tertangkap lewat yang kedua, karena baris itu
        # selalu berdiri lebih dalam daripada isi ulasannya.
        if not (
            TAG_HINT.match(str(tag["current"]))
            or tag["depth"] > ulasan["depth"]
        ):
            continue

        # Ulasan yang ditandainya dicatat. Permintaan pengguna
        # persisnya: tagnya harus sesuai komentarnya.
        tag["partner"] = ulasan["start"]

        diangkat.append(tag)
        sudah_berperan.add((tag["start"], tag["end"]))

    if not diangkat:
        return 0

    take_from_skipped(skipped, diangkat, "review_tag")

    roles.setdefault("review_tag", []).extend(diangkat)
    roles["review_tag"].sort(key=lambda slot: slot["start"])

    return len(diangkat)


def scope_to_brand_block(
    scanned: dict,
    roles: dict,
    skipped: list,
    old_brand: str,
) -> int:
    """
    Menyisihkan paragraf dan butir daftar yang bukan milik brand lama.

    Satu bagian dianggap milik brand lama kalau judulnya menyebut
    namanya. Isi di bawah judul itulah yang ditulis ulang; sisanya
    tetap memakai kalimat pemilik template.

    Mengembalikan berapa slot yang disisihkan.
    """
    nama = (old_brand or "").strip() or guess_old_brand(roles)

    if not nama:
        return 0

    pola = re.compile(re.escape(nama), re.IGNORECASE)

    bagian = heading_sections(scanned)

    if not bagian:
        return 0

    # Rentang tiap bagian milik brand lama.
    milik: list[tuple[int, float]] = []

    for urutan, (mulai, judul) in enumerate(bagian):
        if not pola.search(judul):
            continue

        batas = (
            bagian[urutan + 1][0]
            if urutan + 1 < len(bagian)
            else float("inf")
        )

        milik.append((mulai, batas))

    disisihkan = 0

    for peran in BLOCK_SCOPED_ROLES:
        tersisa: list[dict] = []

        for slot in roles.get(peran, []):
            posisi = slot["start"]

            di_dalam = any(
                mulai < posisi < batas for mulai, batas in milik
            )

            # Teks yang menyebut namanya sendiri ikut, di mana pun ia
            # berdiri. Bagian yang judulnya berupa gambar tidak akan
            # pernah cocok dengan nama apa pun, dan tanpa syarat ini
            # isinya hilang bersama judulnya.
            if di_dalam or pola.search(str(slot["current"])):
                tersisa.append(slot)
                continue

            slot["kept"] = True
            skipped.append(slot)
            disisihkan += 1

        if tersisa:
            roles[peran] = tersisa
        else:
            roles.pop(peran, None)

    return disisihkan


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

        # Menu dan footer mengikuti template apa adanya.
        #
        # Isinya bukan tulisan tentang topik halaman melainkan
        # kerangka situs - menu layanan, daftar bahasa, cara bayar,
        # hak cipta - dan menuliskannya ulang tidak pernah membuat
        # halaman lebih menjelaskan apa pun. Yang terjadi justru
        # sebaliknya, terukur di halaman jadi: 69 teks footer milik
        # toko jersey terbit sebagai "Bahasa global", "38. Inggris",
        # "Dapatkan diskon 15% lebih untuk semua pesanan" di footer
        # halaman slot.
        #
        # Dilewati di sini, bukan dihapus: nama brand lama di
        # dalamnya tetap diganti belakangan lewat brand_edits, yang
        # memang menyapu slot yang dilewati kebijakan. Jadi menu dan
        # footer terbit dengan kata-kata template dan nama brand
        # yang baru.
        # Dua pengecualian dari kebijakan beku, keduanya karena yang
        # dibekukan ternyata bukan perkakas situs.
        #
        # Remah navigasi tinggal di dalam <nav> sambil menyatakan hal
        # yang sepenuhnya berbeda dari menu: bukan bagian-bagian
        # situs, melainkan letak halaman INI.
        #
        # Judul yang berdiri di dalam <header> juga bukan menu. Di
        # situlah banyak template menaruh h1 dan tagline halamannya,
        # dan membekukannya berarti menerbitkan judul milik pemilik
        # template di halaman yang seluruh isinya sudah berganti -
        # inilah sebab "H1 kadang tidak berubah". Judul di dalam
        # <footer>, <nav>, dan <menu> tetap beku, karena di sana ia
        # memang menamai kolom menu.
        beku = frozen_tags(slot)

        boleh_lewat = role == "breadcrumb" or (
            role in {"h1", "heading"} and beku == {"header"}
        )

        if beku and not boleh_lewat:
            slot["frozen"] = True
            skipped.append(slot)
            continue

        # Perkakas situs - menu, tombol, label formulir, keterangan
        # gambar - tetap memakai kata-kata template. Penjelasannya
        # panjang di KEPT_ROLES.
        if role in KEPT_ROLES:
            slot["kept"] = True
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
    demote_faq_lead(roles)
    label_block_headings(roles)
    demote_split_prose(scanned, roles, skipped)

    # Keduanya dijalankan sesudah seluruh slot dikelompokkan, karena
    # yang menentukan bukan slotnya sendiri melainkan apa yang berdiri
    # di sekitarnya - dan itu baru diketahui setelah semuanya terbaca.
    promote_review_authors(scanned, roles, skipped)

    # Baris tag menyusul nama pengulas, bukan mendahuluinya. Kartu
    # ulasan berikutnya dibuka nama pengulas, dan selama nama itu
    # belum berperan ia terlihat persis seperti baris tag yang berdiri
    # sesudah ulasan sebelumnya.
    promote_review_tags(scanned, roles, skipped)

    di_luar_blok = scope_to_brand_block(scanned, roles, skipped, old_brand)

    # Judul kartu diangkat PALING AKHIR, sesudah paragraf yang bukan
    # milik brand lama disisihkan. Diangkat sebelumnya, setiap
    # keterangan produk milik toko yang templatenya dipinjam ikut
    # menyeret label di atasnya jadi judul kartu.
    promote_card_titles(scanned, roles, skipped)

    return {
        "roles": roles,
        "skipped": skipped,
        "unquoted": unquoted,
        "outside_block": di_luar_blok,
        "counts": {role: len(items) for role, items in sorted(roles.items())},
    }


# Peran yang kehadirannya menandai jenis sebuah blok, beserta nama
# blok itu. Urutan menentukan siapa yang menang kalau satu blok memuat
# keduanya - tanya-jawab lebih spesifik daripada ulasan.
BLOCK_MARKERS = (
    ("faq_question", "faq"),
    ("review_text", "review"),
)


# Peran yang isinya tulisan utuh, jadi tidak boleh jatuh ke potongan
# kalimat.
PROSE_ROLES = ("paragraph", "faq_answer", "review_text")


def demote_split_prose(scanned: dict, roles: dict, skipped: list) -> int:
    """
    Melepas peran tulisan dari potongan kalimat.

    Satu <p> yang memuat penanda di tengahnya terbaca sebagai
    beberapa slot terpisah, karena yang dipotong scanner adalah
    simpul teks, bukan kalimat. Terukur di template pengguna:

        <p>Rating Keseluruhan: <strong>4.7 / 5.0</strong>
           dari 1.800+ ulasan. Kelengkapan pasaran...</p>

    Tiga slot lahir dari satu kalimat. Yang pertama dapat peran
    label, angkanya dilewati karena bukan prosa, dan yang KETIGA
    dapat peran paragraph - lalu ikut dilebarkan jatah panjangnya
    oleh pengatur panjang artikel. Yang terbit: kotak pemberitahuan
    peringkat yang isinya paragraf artikel, menyambung dari
    "4.7 / 5.0" ke kalimat yang tidak ada hubungannya.

    Potongan seperti ini dikembalikan jadi label - teksnya
    dipertahankan, nama brand lama di dalamnya tetap diganti
    belakangan. Menuliskannya ulang sebagai tulisan bebas tidak
    mungkin benar: yang dipegang cuma ekor kalimat, sedangkan
    kepalanya berdiri di slot lain yang diisi terpisah.

    Yang tidak terpecah tidak tersentuh sama sekali.
    """
    per_elemen: dict[int, list] = {}

    for slot in scanned.get("slots", []):
        if slot.get("kind") != "text" or not slot.get("current", "").strip():
            continue

        per_elemen.setdefault(slot.get("element_index", -1), []).append(slot)

    diturunkan = 0

    for peran in PROSE_ROLES:
        daftar = roles.get(peran)

        if not daftar:
            continue

        tetap = []

        for slot in daftar:
            rekan = per_elemen.get(slot.get("element_index", -1), [])

            if len(rekan) < 2:
                tetap.append(slot)
                continue

            slot["role"] = "label"
            slot["kept"] = True
            slot["split"] = True

            skipped.append(slot)
            diturunkan += 1

        if tetap:
            roles[peran] = tetap
        else:
            roles.pop(peran, None)

    return diturunkan


def demote_faq_lead(roles: dict) -> None:
    """
    Melepas peran jawaban dari paragraf pembuka blok FAQ.

    Jawaban selalu berdiri SESUDAH pertanyaannya. Paragraf yang
    berdiri sebelum pertanyaan pertama - "Berikut pertanyaan umum
    seputar OSB99" - bukan jawaban apa pun; ia keterangan blok.

    Selama ia terhitung jawaban, jumlah jawaban melebihi jumlah
    pertanyaan dan SELURUH pasangan bergeser satu langkah: jawaban
    pertama masuk ke keterangan blok, jawaban kedua masuk ke slot
    jawaban pertama, dan seterusnya sampai ujung. Yang terbaca
    pengguna adalah pertanyaan yang dijawab hal lain - terukur di
    halaman jadi, "What Sets ASG Apart?" dijawab keterangan cara
    login lewat HP.

    Diturunkan jadi paragraf, bukan dibuang: teksnya memang tampil
    di halaman dan tetap perlu diganti supaya tidak menyebut brand
    lama. Yang dilepas cuma pasangannya dengan pertanyaan.
    """
    tanya = roles.get("faq_question") or []
    jawab = roles.get("faq_answer") or []

    if not tanya or not jawab:
        return

    tanya_pertama = min(slot["start"] for slot in tanya)

    sebelum = [slot for slot in jawab if slot["start"] < tanya_pertama]

    if not sebelum:
        return

    for slot in sebelum:
        slot["role"] = "paragraph"
        slot["budget"] = length_budget(slot["current"], "paragraph")
        roles.setdefault("paragraph", []).append(slot)

    roles["faq_answer"] = [
        slot for slot in jawab if slot["start"] >= tanya_pertama
    ]

    roles["paragraph"].sort(key=lambda slot: slot["start"])


def label_block_headings(roles: dict) -> None:
    """
    Menandai judul menurut blok yang berdiri di bawahnya.

    Judul blok tidak bisa dikenali dari bunyinya sendiri - "FAQ OSB99"
    dan "Keunggulan OSB99" sama-sama cuma sebaris teks - tapi bisa
    dikenali dari apa yang dikepalainya. Yang dibaca di sini letaknya
    di dokumen: slot mana saja yang berdiri antara judul ini dan judul
    berikutnya.

    Gunanya, judul semacam itu tidak perlu diminta ke AI sama sekali.
    Dua run berturut-turut membuktikan kenapa itu penting: sekali
    model menamai blok FAQ "Fitur Utama Aplikasi", sekali lagi model
    tidak menjawab sama sekali sehingga blocknya terbit masih
    bertuliskan "FAQ OSB99" - nama brand pemilik template, di halaman
    yang seluruh isinya sudah berganti.
    """
    judul = sorted(roles.get("heading", []), key=lambda slot: slot["start"])

    if not judul:
        return

    penanda = sorted(
        (slot["start"], nama)
        for peran, nama in BLOCK_MARKERS
        for slot in roles.get(peran, [])
    )

    for urutan, slot in enumerate(judul):
        batas = (
            judul[urutan + 1]["start"]
            if urutan + 1 < len(judul)
            else None
        )

        ditemukan = {
            nama
            for mulai, nama in penanda
            if slot["start"] < mulai and (batas is None or mulai < batas)
        }

        for _, nama in BLOCK_MARKERS:
            if nama in ditemukan:
                slot["block"] = nama
                break


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
