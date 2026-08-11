"""
Penggantian gambar milik template: logo, favicon, dan poster.

Bedanya dengan seluruh modul pengisi yang lain: yang ditulis di sini
BUKAN karangan AI. Isinya alamat yang diketik pengguna sendiri di
formulir, dan satu-satunya tugas modul ini adalah menemukan di mana
alamat lama berdiri lalu menukarnya.

Pemisahan itu disengaja. Nilai src dan href adalah struktur, bukan
isi - template_guard menolak hasil isian yang mengubahnya, dan
penolakan itu yang selama ini menjaga gambar template tidak hilang
gara-gara satu pemetaan slot yang keliru. Jadi penukaran di sini
harus lewat pintu yang menyebutkan dirinya: setiap penukaran
didaftarkan sebagai izin bernama ke pemeriksa, satu per satu, lengkap
dengan elemen dan atribut yang boleh berubah. Yang tidak didaftarkan
tetap dihitung pelanggaran.

Yang dikenali:

  favicon : <link rel="icon">, "shortcut icon", "apple-touch-icon",
            "mask-icon", dan <meta name="msapplication-TileImage">
  logo    : gambar yang class, id, alt, atau alamatnya menyebut logo,
            dan - kalau tidak ada satu pun yang menyebutnya - gambar
            pertama di dalam <header> atau <nav>
  poster  : og:image, twitter:image, atribut poster milik <video>,
            lalu SELURUH gambar isi yang tersisa - semuanya, kecuali
            yang berukuran ikon, berkas SVG, bertanda
            data-neiiu-skip, atau ada di dalam blok iklan sungguhan.
            Alasan bentuk "semua kecuali" ada di tahap_sisa().
"""

import re

from generators.template_slots import has_skip_marker


# Peran gambar yang bisa diganti, urut dari yang paling spesifik.
# Urutan ini yang menentukan siapa yang menang saat satu elemen cocok
# untuk dua peran - "apple-touch-icon" yang alamatnya memuat kata
# logo adalah favicon, bukan logo.
ASSET_ROLES = ("favicon", "logo", "poster")

ASSET_LABELS = {
    "favicon": "favicon",
    "logo": "logo",
    "poster": "gambar poster",
}

FAVICON_REL = re.compile(
    r"(?:^|\s)(?:shortcut\s+)?icon(?:\s|$)|apple-touch-icon|mask-icon|"
    r"fluid-icon",
    re.I,
)

LOGO_HINT = re.compile(r"logo|brand-?mark|site-?mark", re.I)

# Penanda yang menyebut dirinya gambar utama. Ini cuma jalan cepat -
# gambar isi yang tidak menyebut apa pun tetap kebagian peran poster
# lewat aturan sisa di asset_roles(). Lihat catatan di situ.
#
# "cover" sengaja TIDAK ada di sini. Itu pernah dipakai, dan akibatnya
# terukur di job 39: class Tailwind "object-cover" menempel di hampir
# semua gambar, jadi yang tertukar justru 74 thumbnail menu ukuran 250
# piksel - sementara foto utama selebar 2000 piksel, yang tidak punya
# class sama sekali, lolos seluruhnya. Persis kebalikan dari yang
# diminta.
POSTER_HINT = re.compile(
    r"poster|banner|hero|jumbotron|billboard|thumbnail|featured|slide",
    re.I,
)

# Gambar sekecil ini bukan poster: ikon media sosial, panah, bendera
# bahasa, avatar. Angkanya dari atribut width/height kalau ditulis.
ICON_MAX = 64

# Ukuran yang ditulis sebagai class Tailwind - w-6, h-12, size-5, dan
# bentuk pentingnya !w-6. Skala Tailwind dihitung dalam 4 piksel, jadi
# angka 16 sama dengan 64 piksel.
TAILWIND_SIZE = re.compile(r"(?:^|\s|!)(?:w|h|size)-(\d{1,2})(?:\s|$)")
TAILWIND_MAX = 16

# Nama berkas yang menyebut dirinya ikon.
ICON_HINT = re.compile(
    r"\bicon|ikon|sprite|arrow|chevron|caret|avatar|badge|flag-|"
    r"bendera|payment|pay-|method",
    re.I,
)

# Berkas SVG di template semacam ini hampir selalu ikon atau logo,
# bukan foto. Menukarnya dengan poster JPG membuat ikon panah terbit
# sebagai gambar sampul selebar layar.
SVG_FILE = re.compile(r"\.svg(?:[?#]|$)", re.I)

# Nama meta yang isinya alamat gambar untuk dibagikan ke media sosial
# dan ke kartu pratinjau. Dicocokkan persis, bukan dicari sebagian:
# "og:image:width" isinya angka, bukan alamat.
POSTER_META = {
    "og:image",
    "og:image:url",
    "og:image:secure_url",
    "twitter:image",
    "twitter:image:src",
}

FAVICON_META = {"msapplication-tileimage"}

# Tag yang membungkus kepala halaman. Dipakai untuk menebak logo di
# template yang tidak menamai apa pun.
HEADER_TAGS = {"header", "nav"}

HEADER_HINT = re.compile(r"header|navbar|topbar|masthead|brand", re.I)

# Tag yang benar-benar menampilkan gambar. <source> ikut karena
# <picture> menaruh alamat aslinya di situ, dan mengganti <img> saja
# meninggalkan gambar lama tetap tampil di layar lebar.
IMAGE_TAGS = {"img", "amp-img", "amp-anim", "source", "video", "amp-video"}

# Tag yang isinya pasti foto, jadi boleh ditukar tanpa penamaan apa
# pun. <video> tidak ikut: satu-satunya atribut gambarnya, poster,
# sudah dikenali dari namanya sendiri.
PHOTO_TAGS = {"img", "amp-img", "amp-anim"}

# Penanda iklan yang TIDAK cukup kuat untuk menghalangi penggantian
# gambar.
#
# "banner" masuk daftar iklan di template_scanner karena blok iklan
# sungguhan memang sering menamai dirinya begitu. Tapi kata itu sama
# seringnya dipakai template untuk gambar sampulnya sendiri, dan
# akibatnya terukur di job 39: <amp-img class="banner-amp"> - satu
# satunya gambar besar di berkas AMP - tidak pernah ikut berganti.
#
# Kelonggaran ini cuma berlaku untuk ALAMAT GAMBAR. Teks di dalam
# blok yang sama tetap tidak disentuh sama sekali, dan penanda yang
# cuma dipakai jaringan iklan sungguhan - adsbygoogle,
# googlesyndication, data-ad-, adslot, sponsor, propeller, adsterra,
# dan tag <ins>/<amp-ad> - tetap menghalangi seperti sebelumnya.
SOFT_AD_MARKERS = {"banner"}

# Alamat yang boleh ditulis. Selain http(s) dan alamat relatif, tidak
# ada bentuk lain yang berguna untuk gambar - sedangkan "javascript:"
# di dalam href adalah jalan masuk skrip ke halaman orang.
SAFE_URL = re.compile(r"^(?:https?://[^\s\"'<>]+|/[^\s\"'<>]*)$", re.I)


class UnsafeAssetUrl(ValueError):
    """Alamat gambar yang tidak boleh dipasang ke halaman."""


def clean_url(value: str, label: str = "") -> str:
    """
    Memeriksa satu alamat gambar dari formulir.

    Melempar UnsafeAssetUrl kalau bentuknya bukan alamat. Dilempar,
    bukan didiamkan: pengguna yang salah menempel alamat lebih baik
    tahu sekarang daripada menemukan halamannya terbit tanpa logo.
    """
    url = " ".join(str(value or "").split())

    if not url:
        return ""

    if not SAFE_URL.match(url):
        raise UnsafeAssetUrl(
            f"Alamat {label or 'gambar'} tidak dikenali: {url[:80]!r}. "
            "Tulis alamat lengkap yang diawali https:// atau alamat "
            "di dalam situs sendiri yang diawali /."
        )

    return url


def clean_assets(assets: dict | None) -> dict:
    """
    Menyaring seluruh alamat gambar sekaligus.
    """
    hasil: dict[str, str] = {}

    for peran in ASSET_ROLES:
        url = clean_url(
            (assets or {}).get(peran, ""),
            ASSET_LABELS[peran],
        )

        if url:
            hasil[peran] = url

    return hasil


def hint_of(slot: dict) -> str:
    """
    Menggabungkan penanda milik elemennya sendiri.

    Alamat lamanya ikut dibaca karena template sungguhan jauh lebih
    sering menamai berkasnya - "assets/img/logo-putih.png" - daripada
    menamai elemennya.
    """
    attrs = slot.get("attrs", {})

    return " ".join(
        str(attrs.get(key, ""))
        for key in ("class", "id", "alt", "rel", "itemprop")
    ) + " " + str(slot.get("current", ""))


def ancestor_hint(slot: dict) -> str:
    return " ".join(
        " ".join(str(attrs.get(key, "")) for key in ("class", "id"))
        for attrs in slot.get("ancestors", [])
    )


def skipped(slot: dict) -> bool:
    """
    Menghormati data-neiiu-skip di elemennya sendiri maupun induknya.

    Induk ikut diperiksa karena penanda itu hampir selalu ditulis di
    pembungkusnya, bukan di gambarnya. Bentuk yang lazim:

      <div class="mitra" data-neiiu-skip>
        <img src="/img/logo-bank.png" alt="Logo bank">
      </div>

    Logo bank di situ bukan logo situsnya, dan menukarnya berarti
    halaman terbit dengan logo brand di tempat daftar mitra.
    """
    if has_skip_marker(slot):
        return True

    return any(
        has_skip_marker({"attrs": attrs})
        for attrs in slot.get("ancestors", [])
    )


def in_header(slot: dict) -> bool:
    if any(tag in HEADER_TAGS for tag in slot.get("path", [])):
        return True

    return bool(HEADER_HINT.search(ancestor_hint(slot)))


def sized_icon(slot: dict) -> bool:
    """
    Apakah gambar ini terlalu kecil untuk jadi poster.

    Diperiksa dari tiga arah karena tidak ada satu pun yang selalu
    ada: atribut width/height, class ukuran Tailwind, dan nama
    berkasnya. Template yang dipakai menguji tidak menulis satu pun
    width - ukurannya semua di class.
    """
    attrs = slot.get("attrs", {})

    for kunci in ("width", "height"):
        nilai = str(attrs.get(kunci, "")).strip()

        if nilai.isdigit() and int(nilai) <= ICON_MAX:
            return True

    for angka in TAILWIND_SIZE.findall(str(attrs.get("class", ""))):
        if int(angka) <= TAILWIND_MAX:
            return True

    isi = str(slot.get("current", ""))

    if SVG_FILE.search(isi):
        return True

    return bool(ICON_HINT.search(hint_of(slot)))


def in_real_ad(slot: dict) -> bool:
    """
    Apakah gambar ini benar-benar berada di dalam blok iklan.

    Blok yang satu-satunya penandanya kata "banner" tidak dihitung -
    lihat SOFT_AD_MARKERS. Kalau pemindainya tidak mencatat alasan
    sama sekali, in_ad dipakai apa adanya: menebak longgar di sini
    berarti menukar gambar iklan orang.
    """
    if not slot.get("in_ad"):
        return False

    alasan = slot.get("ad_reasons")

    if not alasan:
        return True

    return any(
        str(item).strip().lower() not in SOFT_AD_MARKERS for item in alasan
    )


def is_photo(slot: dict) -> bool:
    """
    Apakah slot ini benar-benar memuat alamat foto.

    <source> dipisahkan dari yang lain karena tag itu dipakai dua
    keperluan yang sangat berbeda: di dalam <picture> isinya gambar,
    sedangkan di dalam <video> isinya berkas video. Menukar yang
    kedua dengan alamat JPG mematikan videonya.
    """
    tag = slot.get("tag", "")

    if tag in PHOTO_TAGS:
        return True

    return tag == "source" and "picture" in slot.get("path", [])


def named_role(slot: dict) -> str:
    """
    Peran satu slot gambar dari penamaannya sendiri, atau "".

    Cuma penamaan yang jelas yang dijawab di sini. Dua tebakan lain -
    gambar pertama di dalam header sebagai logo, dan sisa gambar isi
    sebagai poster - ditangani terpisah di asset_roles(), karena
    urutannya menentukan dan tidak bisa diputuskan per slot.
    """
    if skipped(slot):
        return ""

    tag = slot.get("tag", "")
    attr = slot.get("attr", "")
    attrs = slot.get("attrs", {})

    # Penanda pengguna menang atas tebakan apa pun. Ini jalan keluar
    # untuk template yang menamai gambarnya dengan cara yang tidak
    # bisa ditebak siapa pun.
    tanda = str(attrs.get("data-neiiu", "")).strip().lower()

    if tanda in ASSET_ROLES:
        return tanda

    if tag == "link":
        return "favicon" if FAVICON_REL.search(str(attrs.get("rel", ""))) else ""

    if tag == "meta":
        nama = str(
            attrs.get("name") or attrs.get("property") or ""
        ).strip().lower()

        if nama in FAVICON_META:
            return "favicon"

        return "poster" if nama in POSTER_META else ""

    if tag not in IMAGE_TAGS:
        return ""

    # poster="..." milik <video> memang namanya poster, dan itu
    # memang gambar pratinjaunya.
    if attr == "poster":
        return "poster"

    petunjuk = hint_of(slot)

    if LOGO_HINT.search(petunjuk):
        return "logo"

    if sized_icon(slot) or not is_photo(slot):
        return ""

    if POSTER_HINT.search(petunjuk) or POSTER_HINT.search(ancestor_hint(slot)):
        return "poster"

    return ""


def asset_roles(scanned: dict) -> tuple[dict[int, str], dict[str, int]]:
    """
    Menentukan peran setiap slot gambar di satu dokumen.

    Menghasilkan ({nomor slot di scanned["assets"]: peran}, terhalang),
    dengan terhalang berisi jumlah gambar yang cocok tapi berada di
    dalam blok yang terbaca sebagai iklan.

    Tiga tahap, dan urutannya menentukan:

      1. yang menamai dirinya sendiri - rel="icon", og:image, class
         yang menyebut logo atau hero
      2. logo, kalau tahap 1 tidak menemukan satu pun
      3. SISA gambar isi jadi poster
    """
    daftar = scanned.get("assets", [])
    hasil: dict[int, str] = {}
    terhalang: dict[str, int] = {}

    # Nomor slot yang sudah dihitung terhalang. Tanpa ini, gambar yang
    # ditolak di tahap penamaan diperiksa lagi di tahap sisa lalu
    # dihitung dua kali dengan peran yang berbeda - satu gambar iklan
    # dilaporkan sebagai "1 logo dan 1 poster terhalang".
    ditolak: set[int] = set()

    def catat(nomor: int, slot: dict, peran: str) -> None:
        if in_real_ad(slot):
            # Isi blok iklan tidak pernah disentuh, dan itu janji yang
            # lebih tua daripada fitur ini. Yang bisa dilakukan cuma
            # menghitungnya supaya bisa disebutkan.
            terhalang[peran] = terhalang.get(peran, 0) + 1
            ditolak.add(nomor)
            return

        hasil[nomor] = peran

    for nomor, slot in enumerate(daftar):
        peran = named_role(slot)

        if peran:
            catat(nomor, slot, peran)

    if "logo" in hasil.values():
        return tahap_sisa(daftar, hasil, terhalang, catat, ditolak)

    # Tidak ada satu pun gambar yang menyebut dirinya logo. Yang
    # dipakai kemudian gambar pertama di dalam header atau nav -
    # tebakan, tapi tebakan yang benar di hampir semua template,
    # karena di situlah logo berdiri.
    #
    # Hanya SATU elemen yang diambil, bukan semua yang di header.
    # Header sungguhan juga memuat ikon menu, bendera bahasa, dan
    # gambar tombol, dan menukar semuanya dengan logo yang sama
    # meninggalkan halaman dengan enam logo berjajar.
    elemen_logo = None

    for nomor, slot in enumerate(daftar):
        if nomor in hasil:
            continue

        if slot.get("tag") not in {"img", "amp-img", "amp-anim"}:
            continue

        if in_real_ad(slot) or skipped(slot) or not in_header(slot):
            continue

        if elemen_logo is None:
            elemen_logo = slot.get("element_index")

        if slot.get("element_index") != elemen_logo:
            break

        # src dan srcset milik elemen yang sama ikut semuanya, kalau
        # tidak yang tertinggal justru yang dipakai browser.
        hasil[nomor] = "logo"

    return tahap_sisa(daftar, hasil, terhalang, catat, ditolak)


def tahap_sisa(
    daftar: list[dict],
    hasil: dict[int, str],
    terhalang: dict[str, int],
    catat,
    ditolak: set[int],
) -> tuple[dict[int, str], dict[str, int]]:
    """
    Menjadikan SISA gambar isi sebagai poster.

    Ini tahap yang paling menentukan hasilnya, dan bentuknya begini
    karena tebakan berdasarkan penamaan sudah dicoba dan gagal.
    Terukur di job 39, pada template sungguhan milik pengguna:

      terganti : 74 thumbnail menu 250 piksel, karena class Tailwind
                 "object-cover" menempel di semuanya
      lolos    : seluruh foto utama selebar 2000 piksel, yang tidak
                 punya satu class pun

    Sebabnya template modern menamai gambarnya dengan ukuran, bukan
    dengan fungsi: "absolute inset-0 object-cover", "w-full h-12".
    Tidak ada kata "poster", "hero", atau "banner" di mana pun, dan
    tidak akan pernah ada. Jadi yang dipakai bukan daftar kata
    melainkan kebalikannya: semua gambar isi diganti, KECUALI yang
    punya alasan untuk tidak.

    Alasan untuk tidak, semuanya sudah diputuskan sebelum tahap ini:
    sudah kebagian peran lain (logo, favicon), berukuran ikon,
    berkas SVG, bertanda data-neiiu-skip, atau ada di dalam blok
    iklan.
    """
    for nomor, slot in enumerate(daftar):
        if nomor in hasil or nomor in ditolak:
            continue

        if not is_photo(slot) or skipped(slot) or sized_icon(slot):
            continue

        if not str(slot.get("current", "")).strip():
            continue

        catat(nomor, slot, "poster")

    return hasil, terhalang


def asset_edits(
    scanned: dict,
    assets: dict,
    taken: dict | None = None,
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Menyusun penggantian alamat gambar beserta izin untuk pemeriksa.

    Mengembalikan (edits, swaps, notes). swaps adalah daftar izin yang
    diteruskan ke template_guard.verify(): tanpa itu, setiap
    penggantian src akan dilaporkan sebagai gambar template yang
    hilang dan seluruh hasil isian ditolak.
    """
    urls = {
        peran: url
        for peran, url in (assets or {}).items()
        if str(url or "").strip()
    }

    if not urls:
        return [], [], []

    peta, terhalang = asset_roles(scanned)
    sudah = taken or {}

    edits: list[dict] = []
    swaps: list[dict] = []
    jumlah: dict[str, int] = {}
    tanpa_kutip: list[str] = []

    for nomor, peran in peta.items():
        url = urls.get(peran)

        if not url:
            continue

        slot = scanned["assets"][nomor]
        kunci = (slot["start"], slot["end"])

        if kunci in sudah:
            continue

        if str(slot.get("current", "")).strip() == url:
            continue

        if not slot.get("quote"):
            # Atribut tanpa tanda kutip tidak boleh ditulisi sama
            # sekali - alamat yang memuat spasi akan terbaca sebagai
            # atribut tambahan dan mengubah struktur tagnya.
            tanpa_kutip.append(f"{slot['tag']} {slot['attr']}")
            continue

        edits.append(
            {
                "kind": "attribute",
                "start": slot["start"],
                "end": slot["end"],
                "current": slot["current"],
                "quote": slot["quote"],
                "tag": slot["tag"],
                "attr": slot["attr"],
                "role": f"asset_{peran}",
                "text": url,
            }
        )

        swaps.append(
            {
                "element": slot["element_index"],
                "attr": slot["attr"],
                "value": url,
            }
        )

        jumlah[peran] = jumlah.get(peran, 0) + 1

    notes: list[str] = []

    for peran in ASSET_ROLES:
        if peran not in urls:
            continue

        if jumlah.get(peran):
            notes.append(
                f"{ASSET_LABELS[peran].capitalize()} diganti di "
                f"{jumlah[peran]} tempat."
            )
        elif not terhalang.get(peran):
            notes.append(
                f"Alamat {ASSET_LABELS[peran]} diisi, tapi template ini "
                "tidak punya satu pun tempat yang bisa dikenali sebagai "
                f"{ASSET_LABELS[peran]}, jadi tidak ada yang diganti. "
                "Tandai gambarnya di template dengan class atau id yang "
                f"memuat kata \"{peran}\"."
            )

        if terhalang.get(peran):
            notes.append(
                f"{terhalang[peran]} gambar yang cocok sebagai "
                f"{ASSET_LABELS[peran]} berada di dalam blok iklan - "
                "ditandai adsbygoogle, data-ad-, adslot, sponsor, atau "
                "tag <ins>/<amp-ad>. Isi blok iklan tidak pernah "
                "disentuh, jadi gambar itu dibiarkan. Kalau itu bukan "
                "iklan pihak lain, gantilah sendiri di templatenya."
            )

    if tanpa_kutip:
        notes.append(
            f"{len(tanpa_kutip)} alamat gambar ditulis tanpa tanda kutip "
            "di template, jadi dibiarkan apa adanya: "
            + ", ".join(sorted(set(tanpa_kutip))[:5])
        )

    return edits, swaps, notes
