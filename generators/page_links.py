"""
Alamat yang boleh ditulis ke halaman: canonical, amphtml, dan tujuan
tombol login/daftar.

Berkas ini adalah satu-satunya jalur yang boleh menulis alamat ke
dalam template, dan ia hanya menulis alamat yang DIKETIK PENGGUNA
SENDIRI. Kolom yang dikosongkan tidak menghasilkan satu edit pun,
jadi template yang alamatnya dibiarkan terbit byte demi byte seperti
aslinya.

Aturan itu bukan kehati-hatian umum. Sampai sekarang alamat halaman
diambil dari SITE_BASE_URL di .env, yang bawaannya
"https://example.com" - dan selama pengguna belum mengisinya, setiap
halaman terbit dengan canonical, og:url, dan structured data yang
menunjuk ke situs contoh milik IANA. Itu keluhan yang sudah pernah
disampaikan, dan bentuk yang dipilih di sini membuatnya tidak bisa
terulang: tidak ada nilai bawaan sama sekali di berkas ini. Kosong
berarti tidak ditulis, bukan berarti dipakai nilai cadangan.

Cara menulisnya sama dengan cara gambar ditukar - splice byte di
rentang nilai atributnya, lewat scanned["assets"] - bukan dengan
mengurai lalu menserialisasi ulang dokumen. Serialisasi ulang
merusak template pengguna dengan cara yang tidak kelihatan sampai
halamannya dibuka.
"""

import re


# Peran alamat yang dikenal berkas ini.
LINK_ROLES = ("canonical", "amphtml", "cta")

LINK_LABELS = {
    "canonical": "canonical",
    "amphtml": "amphtml",
    "cta": "tujuan tombol login dan daftar",
}


# Bentuk alamat yang boleh dipasang.
#
# Sengaja sama dengan SAFE_URL di generators/template_assets.py, dan
# sengaja TIDAK diimpor dari sana. Yang diperiksa di sini alamat
# halaman, di sana alamat gambar; keduanya kebetulan berbentuk sama
# hari ini, tapi menautkan keduanya berarti pelonggaran di satu sisi
# diam-diam berlaku di sisi yang lain.
SAFE_URL = re.compile(r"^(?:https?://[^\s\"'<>]+|/[^\s\"'<>]*)$", re.I)


class UnsafeLinkUrl(ValueError):
    """
    Alamat yang tidak boleh dipasang ke halaman.
    """


# Kata yang menandai tombol masuk dan tombol daftar.
#
# Dicocokkan ke teks yang terbaca di tombolnya, lalu ke class, id,
# aria-label, dan title-nya. Urutan itu disengaja: teks tombol adalah
# satu-satunya penanda yang ditulis untuk dibaca manusia, jadi ia yang
# paling jarang salah. Class dan id adalah cadangan untuk tombol yang
# isinya cuma ikon.
#
# Bahasa Thai ikut karena zona Thailand memakai template Thai, dan
# tombolnya bertuliskan Thai. Tanpa barisnya, kolom ini diam-diam
# tidak berlaku untuk separuh zona yang didukung.
CTA_WORDS_LATIN = (
    "login",
    "log in",
    "masuk",
    "sign in",
    "daftar",
    "register",
    "registrasi",
    "sign up",
    "join",
    "gabung",
    "regis",
    # Bentuk Indonesia yang tidak memuat kata "daftar" sama sekali.
    #
    # Ditambahkan sesudah diuji ke template pengguna sungguhan
    # (template 488): tombol utamanya bertuliskan "BUAT AKUN", dan
    # daftar sebelumnya melewatkannya begitu saja - kolom tujuan
    # tombol terisi, tombol pendaftaran paling atas tidak berpindah,
    # dan tidak ada yang melaporkan apa pun.
    "buat akun",
    "buka akun",
    "create account",
    "create an account",
)

CTA_WORDS_THAI = (
    "เข้าสู่ระบบ",
    "เข้าระบบ",
    "ล็อกอิน",
    "สมัครสมาชิก",
    "สมัครเลย",
    "สมัคร",
    "เข้าเล่น",
    "ทางเข้า",
)

# Pemisah di dalam frasa cocok dengan spasi, tanda hubung, atau tanpa
# apa pun sekaligus. Satu tombol yang sama ditulis "Sign Up",
# "Sign-Up", dan "SignUp" di tiga template berbeda, dan ketiganya
# tombol yang sama.
#
# Yang panjang diadu lebih dulu: tanpa itu "create account" tidak
# pernah kebagian giliran karena "create an account" mengandungnya.
CTA_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])("
    + "|".join(
        kata.replace(" ", r"[\s-]*")
        for kata in sorted(CTA_WORDS_LATIN, key=len, reverse=True)
    )
    + r")(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)


# Atribut yang ikut dibaca kalau teks tombolnya tidak menyebut apa pun.
CTA_ATTRS = ("class", "id", "aria-label", "title")

# Penanda yang dipasang pengguna sendiri di templatenya. Menang atas
# tebakan apa pun, dengan alasan yang sama seperti data-neiiu di
# generators/template_assets.py: ini jalan keluar untuk template yang
# tombolnya tidak bisa dikenali cara lain - tombol bergambar, tombol
# berbahasa yang tidak ada di daftar, tombol bertuliskan plesetan.
CTA_MARKS = {"cta", "daftar", "login", "register"}

# Penutup </a>. Dicari sebagai pola dari posisi tertentu, bukan
# dengan menyalin seluruh dokumen jadi huruf kecil untuk tiap anchor -
# template 500 KB dengan 200 tombol berarti 100 MB salinan yang
# dibuang lagi seketika.
ANCHOR_CLOSE = re.compile(r"</a\s*>", re.IGNORECASE)

# Alamat yang tidak pernah dianggap tombol ajakan meski teksnya cocok.
#
# Tautan dalam-halaman dan tautan protokol bukan tombol yang menuju
# situs tujuan, dan menukarnya memutus perilaku yang sudah ada:
# "#daftar" membuka bagian pendaftaran di halaman yang sama, dan
# menggantinya dengan alamat luar menghapus fungsi itu tanpa ada yang
# meminta.
SKIP_HREF = re.compile(
    r"^\s*(?:#|javascript:|mailto:|tel:|whatsapp:|data:)",
    re.IGNORECASE,
)

# Batas teks tombol yang dibaca.
#
# Anchor yang membungkus satu kartu berisi paragraf akan cocok dengan
# kata "daftar" yang kebetulan ada di kalimat ke sekian, dan tombolnya
# bukan tombol. Yang benar-benar tombol memuat satu sampai tiga kata.
CTA_TEXT_LIMIT = 60


def clean_link(value: str, label: str = "") -> str:
    """
    Membersihkan satu alamat yang diketik pengguna.

    Kosong tetap kosong - itu jawaban yang sah dan artinya "jangan
    sentuh". Yang bentuknya tidak sah ditolak dengan menyebut kolom
    mana yang salah, bukan diperbaiki diam-diam.
    """
    bersih = str(value or "").strip()

    if not bersih:
        return ""

    if not SAFE_URL.match(bersih):
        raise UnsafeLinkUrl(
            f"Alamat {label or 'tautan'} tidak bisa dipakai: "
            f"'{bersih[:80]}'. Isi alamat lengkap yang diawali "
            "https:// atau alamat di dalam situs sendiri yang "
            "diawali /."
        )

    return bersih


def clean_links(links: dict | None) -> dict:
    """
    Membersihkan seluruh kolom alamat sekaligus.
    """
    hasil: dict[str, str] = {}

    for peran in LINK_ROLES:
        nilai = clean_link(
            (links or {}).get(peran, ""),
            LINK_LABELS[peran],
        )

        if nilai:
            hasil[peran] = nilai

    return hasil


def rel_of(slot: dict) -> str:
    """
    Nilai rel satu elemen, dinormalkan.
    """
    return " ".join(
        str(slot.get("attrs", {}).get("rel", "")).lower().split()
    )


def anchor_text(html: str, slot: dict) -> str:
    """
    Teks yang terbaca di dalam satu <a>.

    Dibaca dari HTML mentah, bukan dari pohon elemen, karena yang
    dipegang slot cuma rentang byte nilai atributnya. Yang dicari
    dari situ dua hal berurutan: penutup tag pembukanya, lalu </a>
    yang pertama.

    Anchor bersarang tidak ditangani, dan itu memang tidak perlu:
    HTML melarangnya, dan pengurai browser memutus yang di dalam.
    """
    buka = html.find(">", int(slot["end"]))

    if buka == -1:
        return ""

    tutup = ANCHOR_CLOSE.search(html, buka)

    if tutup is None:
        return ""

    isi = html[buka + 1:tutup.start()]

    # Tag di dalam tombol dibuang, bukan isinya. Tombol yang isinya
    # <span>Daftar</span> harus terbaca "Daftar", dan tombol yang
    # isinya cuma <svg> harus terbaca kosong supaya jatuh ke
    # pemeriksaan class dan id.
    isi = re.sub(r"<svg\b.*?</svg\s*>", " ", isi, flags=re.I | re.S)
    isi = re.sub(r"<[^>]*>", " ", isi)

    return " ".join(isi.split())


def looks_like_cta(html: str, slot: dict) -> bool:
    """
    Apakah satu anchor adalah tombol login atau daftar.
    """
    attrs = slot.get("attrs", {})

    # Penanda pengguna dibaca paling dulu, dan menang atas apa pun
    # sesudahnya - termasuk atas href yang biasanya dilewati. Yang
    # menandai sendiri tombolnya sudah menyatakan maksudnya.
    if str(attrs.get("data-neiiu", "")).strip().lower() in CTA_MARKS:
        return True

    if SKIP_HREF.match(str(slot.get("current", ""))):
        return False

    teks = anchor_text(html, slot)

    # Tombol yang punya tulisan dinilai dari tulisannya saja.
    #
    # Panjangnya ikut menentukan supaya anchor yang membungkus satu
    # kartu berisi paragraf tidak ikut tertukar hanya karena kata
    # "daftar" muncul di kalimat ke sekian. Yang benar-benar tombol
    # memuat satu sampai tiga kata.
    if teks:
        return len(teks) <= CTA_TEXT_LIMIT and cocok_cta(teks)

    # Tombol yang isinya cuma ikon tidak punya tulisan sama sekali.
    # Penamaannya yang dibaca kemudian.
    penanda = " ".join(
        str(attrs.get(nama, "")) for nama in CTA_ATTRS
    )

    return bool(penanda.strip()) and cocok_cta(penanda)


def cocok_cta(teks: str) -> bool:
    """
    Apakah satu potong teks menyebut masuk atau daftar.
    """
    if CTA_PATTERN.search(teks):
        return True

    return any(kata in teks for kata in CTA_WORDS_THAI)


def head_insert_point(html: str) -> int:
    """
    Titik penyisipan di dalam <head>, atau -1.

    Disisipkan tepat SEBELUM </head>, bukan sesudah <head>. Yang
    sesudah <head> mendahului <meta charset>, dan charset yang tidak
    berdiri di 1024 byte pertama membuat sebagian pengurai menebak
    encoding-nya sendiri.
    """
    cocok = re.search(r"</head\s*>", html, re.IGNORECASE)

    return cocok.start() if cocok else -1


def existing_slots(scanned: dict, rel: str) -> list[int]:
    """
    Nomor slot <link rel="..."> yang sudah ada di dokumen.
    """
    return [
        nomor
        for nomor, slot in enumerate(scanned.get("assets", []))
        if slot.get("tag") == "link"
        and slot.get("attr") == "href"
        and rel in rel_of(slot).split()
    ]


def link_edits(
    scanned: dict,
    html: str,
    links: dict,
    taken: dict | None = None,
) -> tuple[list[dict], list[dict], dict[str, int], list[str]]:
    """
    Menyusun penukaran alamat untuk satu dokumen.

    Mengembalikan (edits, swaps, tambahan_tag, catatan).

    swaps memberi tahu template_guard.verify penukaran mana yang
    memang diminta pengguna, dengan bentuk yang sama sempitnya dengan
    penukaran gambar: hanya atribut yang namanya disebut, di elemen
    yang nomornya disebut, dan hanya kalau nilainya persis yang
    diminta. Tanpa itu, canonical yang berhasil ditukar akan
    dilaporkan sebagai "atribut elemen berubah" lalu seluruh hasil
    isian ditolak.

    tambahan_tag menyebutkan tag yang disisipkan, supaya pemeriksa
    struktur tahu penambahan itu disengaja. Hanya <link> yang pernah
    disisipkan, dan hanya kalau templatenya memang belum punya.
    """
    sudah = taken or {}

    edits: list[dict] = []
    swaps: list[dict] = []
    tambahan: dict[str, int] = {}
    catatan: list[str] = []

    # Rentang yang sudah ditulis di dalam panggilan ini sendiri.
    #
    # Dipisah dari `taken` supaya berkas ini tidak diam-diam menulisi
    # struktur milik pemanggilnya. Pemanggil yang mendaftarkan hasil
    # ke petanya sendiri melakukannya setelah fungsi ini selesai, dan
    # itu urusan dia.
    dipakai: set[tuple[int, int]] = set()

    def tukar(nomor: int, peran: str, url: str) -> bool:
        slot = scanned["assets"][nomor]
        kunci = (slot["start"], slot["end"])

        if kunci in sudah or kunci in dipakai:
            return False

        if str(slot.get("current", "")).strip() == url:
            return False

        if not slot.get("quote"):
            # Atribut tanpa tanda kutip tidak pernah ditulisi.
            # Alamat yang memuat karakter apa pun di luar kutip akan
            # terbaca sebagai atribut tambahan dan mengubah bentuk
            # tagnya.
            catatan.append(
                f"Alamat {LINK_LABELS[peran]} tidak ditulis: "
                f"atribut {slot['tag']} {slot['attr']} di template "
                "ditulis tanpa tanda kutip."
            )
            return False

        edit = {
            "kind": "attribute",
            "start": slot["start"],
            "end": slot["end"],
            "current": slot["current"],
            "quote": slot["quote"],
            "tag": slot["tag"],
            "attr": slot["attr"],
            "role": f"link_{peran}",
            "text": url,
        }

        edits.append(edit)
        dipakai.add(kunci)

        swaps.append(
            {
                "element": slot["element_index"],
                "attr": slot["attr"],
                "value": url,
            }
        )

        return True

    # 1. canonical dan amphtml.
    for peran in ("canonical", "amphtml"):
        url = str(links.get(peran) or "").strip()

        if not url:
            continue

        nomor_slot = existing_slots(scanned, peran)
        terganti = 0

        for nomor in nomor_slot:
            if tukar(nomor, peran, url):
                terganti += 1

        if terganti:
            catatan.append(
                f"Alamat {LINK_LABELS[peran]} diganti di {terganti} "
                "tempat."
            )
            continue

        if nomor_slot:
            # Sudah ada dan nilainya memang sudah sama, atau
            # rentangnya sudah dipakai lapis lain. Tidak ada yang
            # perlu dilaporkan.
            continue

        # Belum ada sama sekali. Disisipkan, karena kolom yang diisi
        # tapi tidak menghasilkan apa pun adalah kolom yang berbohong.
        titik = head_insert_point(html)

        if titik == -1:
            catatan.append(
                f"Alamat {LINK_LABELS[peran]} tidak bisa dipasang: "
                "template ini tidak punya </head>."
            )
            continue

        edits.append(
            {
                "kind": "raw",
                "start": titik,
                "end": titik,
                "role": f"link_{peran}",
                "text": f'<link rel="{peran}" href="{escape_href(url)}">',
            }
        )

        tambahan["link"] = tambahan.get("link", 0) + 1

        catatan.append(
            f"Template belum punya link rel=\"{peran}\", jadi satu "
            "baris ditambahkan di dalam <head>."
        )

    # 2. Tujuan tombol login dan daftar.
    url_cta = str(links.get("cta") or "").strip()

    if url_cta:
        terganti = 0

        for nomor, slot in enumerate(scanned.get("assets", [])):
            if slot.get("tag") != "a" or slot.get("attr") != "href":
                continue

            # Isi blok iklan tidak pernah disentuh. Janji itu lebih
            # tua daripada kolom ini, dan tombol di dalam iklan
            # memang milik pengiklan, bukan milik halaman.
            if slot.get("in_ad"):
                continue

            if not looks_like_cta(html, slot):
                continue

            if tukar(nomor, "cta", url_cta):
                terganti += 1

        if terganti:
            catatan.append(
                f"{terganti} tombol login/daftar diarahkan ke alamat "
                "yang kamu isi."
            )
        else:
            catatan.append(
                "Tidak ada satu pun tombol login atau daftar yang "
                "dikenali di template ini, jadi alamat tujuannya "
                "tidak dipasang. Tandai tombolnya di template dengan "
                'data-neiiu="daftar" kalau tulisannya bukan kata '
                "yang umum."
            )

    return edits, swaps, tambahan, catatan


def escape_href(url: str) -> str:
    """
    Menyiapkan alamat untuk ditulis di dalam kutip ganda.

    Alamat yang lolos SAFE_URL tidak mungkin memuat kutip ganda,
    tanda kurung sudut, atau spasi - jadi yang tersisa cuma &, yang
    harus jadi &amp; supaya dokumennya tetap sah.
    """
    return url.replace("&", "&amp;")
