"""
Menemukan wilayah iklan dan konten pihak ketiga di dalam template.

Template yang diunggah dipakai sebagai kerangka: isi halamannya
ditulis ulang mengikuti brief baru. Tapi sebagian template memuat
titipan orang lain - banner sponsor, kartu mitra, kreatif kampanye
merek lain - dan titipan itu bukan milik kita. Menerjemahkannya,
mengganti mereknya dengan merek pengguna, atau menulis ulang harga
penawarannya sama saja merusak iklan yang sudah dibayar.

Yang membedakan keduanya BUKAN bahasanya. Iklan Samsung berbahasa
Inggris di halaman Thai tetap iklan Samsung; ia bukan kebocoran
bahasa. Yang membedakan letaknya di dokumen dan hubungannya keluar:
ke domain siapa tautannya pergi, dari mana gambarnya diambil,
label apa yang dipasang pemilik template di wadahnya.

    Tidak ada satu pun nama merek di berkas ini, dan memang tidak
    boleh ada. Daftar nama tidak akan pernah mengenali pengiklan
    berikutnya, dan template berikutnya selalu memuat pengiklan yang
    belum pernah kita lihat.

Bukti dikumpulkan, bukan ditebak dari satu tanda. Satu kata
"banner" di nama kelas tidak cukup - template memakai kata itu untuk
gambar sampulnya sendiri - sedangkan <ins class="adsbygoogle"> sudah
cukup sendirian karena tidak ada yang memakai nama itu selain
jaringan iklan.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

# Tag yang keberadaannya sendiri sudah berarti iklan.
AD_TAGS = {"ins", "amp-ad", "amp-embed", "amp-sticky-ad"}

# Nama jaringan iklan dan atribut yang hanya dipakai jaringan iklan.
NETWORK_MARK = re.compile(
    r"adsbygoogle|googlesyndication|googletag|doubleclick|adservice|"
    r"data-ad-client|data-ad-slot|data-ad-format|amp-ad|taboola|outbrain|"
    r"adsterra|propeller|media\.net|adnxs",
    re.IGNORECASE,
)

# Kata yang menamai wilayah titipan. Cukup kuat untuk jadi satu
# bukti, tapi tidak cukup untuk memutuskan sendirian.
SPONSOR_WORD = re.compile(
    r"sponsor|sponsored|partner|advertis|advertorial|affiliate|"
    r"endorse|iklan|pariwara|โฆษณา|ผู้สนับสนุน",
    re.IGNORECASE,
)

# Kata yang SERING dipakai template untuk isinya sendiri. Hanya
# dihitung sebagai bukti tambahan, tidak pernah sebagai bukti utama.
WEAK_WORD = re.compile(r"promo|banner|campaign|deal|offer", re.IGNORECASE)

# Jejak pelacakan kampanye di alamat tautan.
TRACKING = re.compile(
    r"[?&](?:utm_[a-z]+|aff(?:iliate)?_?id|clickid|cmpid|campaign|"
    r"partner|ref|irclickid|gclid|fbclid)=",
    re.IGNORECASE,
)

# Atribut data- yang menandai kreatif, bukan isi halaman.
TRACK_ATTR = re.compile(
    r"^data-(?:ad|ads|advert|sponsor|partner|campaign|promo|creative|"
    r"placement|slot)[\w-]*$",
    re.IGNORECASE,
)

# Wadah yang boleh dianggap satu kreatif utuh.
BOX_TAGS = {
    "div", "section", "aside", "article", "figure", "a", "li",
    "ins", "iframe", "amp-ad", "amp-embed", "amp-iframe", "amp-sticky-ad",
}

# Iklan tidak pernah sebesar halamannya sendiri.
#
# Tanpa batas ini satu bukti yang kebetulan menempel di <body> akan
# membekukan seluruh halaman, dan yang terbit adalah template
# aslinya utuh - kegagalan yang jauh lebih buruk daripada satu iklan
# yang ikut tertulis ulang.
MAX_SHARE = 0.45

# Sedikitnya berapa bukti sebelum satu wadah dinyatakan titipan.
NEED_SCORE = 2


def registrable(host: str) -> str:
    """
    Nama domain yang bisa didaftarkan, tanpa subdomainnya.

    "shop.realmadrid.com" dan "www.realmadrid.com" satu pemilik, dan
    kalau subdomainnya ikut dihitung keduanya terbaca sebagai dua
    pihak yang berbeda.
    """
    bagian = [x for x in str(host or "").lower().split(".") if x]

    if len(bagian) < 2:
        return ".".join(bagian)

    # Akhiran dua tingkat seperti .co.uk dan .co.id perlu tiga bagian.
    DUA = {"co", "com", "net", "org", "gov", "ac", "or", "sch", "web"}

    if len(bagian) >= 3 and bagian[-2] in DUA and len(bagian[-1]) <= 3:
        return ".".join(bagian[-3:])

    return ".".join(bagian[-2:])


class Pohon(HTMLParser):
    """
    Membangun ulang susunan elemen beserta rentang bytenya.

    Pemindai utama tidak menyimpan rentang - ia bekerja mengalir dan
    memang tidak perlu tahu di mana satu elemen berakhir. Di sini
    justru itu yang dibutuhkan: bukti sebuah kreatif hampir selalu
    ada di ANAK-anaknya, jadi tiap wadah harus tahu apa saja yang
    ada di dalamnya sebelum bisa dinilai.
    """

    VOID = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.html = html
        self.nodes: list[dict] = []
        self.stack: list[int] = []

    def titik(self) -> int:
        # Namanya bukan offset: HTMLParser sudah memakai nama itu
        # untuk bilangan miliknya sendiri, dan menimpanya membuat
        # pemanggilan biasa gagal dengan 'int object is not callable'.
        baris, kolom = self.getpos()
        return self.line_start(baris) + kolom

    def line_start(self, baris: int) -> int:
        if not hasattr(self, "_baris"):
            self._baris = [0]
            for m in re.finditer(r"\n", self.html):
                self._baris.append(m.end())

        return self._baris[baris - 1] if baris - 1 < len(self._baris) else 0

    def handle_starttag(self, tag, attrs):
        simpul = {
            "tag": tag,
            "attrs": {k: (v or "") for k, v in attrs},
            "start": self.titik(),
            "end": len(self.html),
            "parent": self.stack[-1] if self.stack else -1,
            "depth": len(self.stack),
        }
        self.nodes.append(simpul)

        if tag not in self.VOID:
            self.stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

        if self.stack and self.nodes[self.stack[-1]]["tag"] == tag:
            self.nodes[self.stack.pop()]["end"] = self.titik()

    def handle_endtag(self, tag):
        for posisi in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[posisi]]["tag"] == tag:
                akhir = self.titik() + len(tag) + 3

                for mati in self.stack[posisi:]:
                    self.nodes[mati]["end"] = akhir

                del self.stack[posisi:]
                return


def house_domains(html: str, base_url: str = "") -> set:
    """
    Domain milik situsnya sendiri, ditebak dari mayoritas.

    Tautan dan gambar milik pemilik situs selalu jauh lebih banyak
    daripada milik pengiklan - itu yang membedakan tuan rumah dari
    tamu, dan itu berlaku di template mana pun tanpa perlu tahu nama
    siapa pun. Yang dominan dihitung terpisah untuk tautan dan untuk
    gambar, karena banyak situs menaruh gambarnya di CDN yang
    domainnya memang lain.
    """
    rumah = set()

    if base_url:
        rumah.add(registrable(urlparse(base_url).hostname or ""))

    for pola in (r'href="(https?://[^"]+)"', r'src="(https?://[^"]+)"'):
        hitung: dict[str, int] = {}

        for m in re.finditer(pola, html, re.IGNORECASE):
            nama = registrable(urlparse(m.group(1)).hostname or "")

            if nama:
                hitung[nama] = hitung.get(nama, 0) + 1

        if not hitung:
            continue

        tertinggi = max(hitung.values())

        # Yang jumlahnya sekelas dengan yang terbanyak ikut dihitung
        # tuan rumah. Situs yang memakai dua domain sendiri - satu
        # untuk halaman, satu untuk gambar - tidak boleh membuat
        # salah satunya terbaca sebagai tamu.
        rumah.update(
            nama for nama, n in hitung.items() if n >= max(2, tertinggi * 0.25)
        )

    return {x for x in rumah if x}


def evidence(simpul: dict, dalam: str, rumah: set) -> list:
    """
    Mengumpulkan alasan kenapa satu wadah terlihat seperti titipan.
    """
    alasan = []
    attrs = simpul["attrs"]
    tag = simpul["tag"]

    tanda = " ".join(
        [tag]
        + list(attrs.keys())
        + [
            str(v)
            for k, v in attrs.items()
            if k.lower()
            in {"class", "id", "role", "aria-label", "type", "rel", "name"}
        ]
    )

    if tag in AD_TAGS or NETWORK_MARK.search(tanda):
        alasan.append(("jaringan iklan", 3))

    if SPONSOR_WORD.search(tanda):
        alasan.append(("label sponsor/mitra", 2))
    elif WEAK_WORD.search(tanda):
        alasan.append(("kata promosi", 1))

    if any(TRACK_ATTR.match(k) for k in attrs):
        alasan.append(("atribut pelacak", 2))

    # rel="sponsored" adalah cara resmi menandai tautan berbayar.
    if re.search(r'rel="[^"]*\bsponsored\b', dalam, re.IGNORECASE):
        alasan.append(("rel=sponsored", 3))

    if TRACKING.search(dalam):
        alasan.append(("parameter kampanye", 2))

    if NETWORK_MARK.search(dalam):
        alasan.append(("skrip jaringan iklan", 3))

    # Tautan dan gambar yang pergi ke pihak lain.
    tamu = set()

    for m in re.finditer(r'(?:href|src)="(https?://[^"]+)"', dalam, re.I):
        nama = registrable(urlparse(m.group(1)).hostname or "")

        if nama and nama not in rumah:
            tamu.add(nama)

    if tamu:
        alasan.append((f"domain pihak lain: {', '.join(sorted(tamu)[:2])}", 2))

    return alasan


def protected_regions(html: str, base_url: str = "") -> list:
    """
    Wilayah yang isinya milik pihak ketiga dan tidak boleh disentuh.

    Yang dikembalikan wadah TERLUAR yang memenuhi syarat, supaya
    perlindungannya berlaku untuk seluruh isinya sekaligus. Kalau
    yang dilindungi cuma simpul yang kebetulan kena bukti, hasilnya
    iklan yang setengah tertulis ulang: logonya selamat, judulnya
    berganti bahasa, tombolnya memakai merek pengguna.
    """
    teks = str(html or "")

    if not teks.strip():
        return []

    pohon = Pohon(teks)

    try:
        pohon.feed(teks)
        pohon.close()
    except Exception:
        return []

    rumah = house_domains(teks, base_url)
    batas = len(teks) * MAX_SHARE
    hasil: list[dict] = []

    for simpul in pohon.nodes:
        if simpul["tag"] not in BOX_TAGS:
            continue

        lebar = simpul["end"] - simpul["start"]

        if lebar <= 0 or lebar > batas:
            continue

        dalam = teks[simpul["start"] : simpul["end"]]
        alasan = evidence(simpul, dalam, rumah)
        nilai = sum(bobot for _, bobot in alasan)

        if nilai < NEED_SCORE or len(alasan) < 2 and nilai < 3:
            continue

        hasil.append(
            {
                "start": simpul["start"],
                "end": simpul["end"],
                "tag": simpul["tag"],
                "score": nilai,
                "reasons": [nama for nama, _ in alasan],
            }
        )

    # Hanya wadah terluar yang disimpan.
    hasil.sort(key=lambda x: (x["start"], -(x["end"])))
    terluar: list[dict] = []

    for wilayah in hasil:
        if terluar and wilayah["end"] <= terluar[-1]["end"]:
            continue

        terluar.append(wilayah)

    return terluar


def protected_ranges(html: str, base_url: str = "") -> list:
    """Rentang byte saja, untuk yang tidak perlu tahu alasannya."""
    return [(x["start"], x["end"]) for x in protected_regions(html, base_url)]


def inside(posisi: int, ranges: list) -> bool:
    """Apakah satu titik berada di dalam salah satu rentang."""
    return any(awal <= posisi < akhir for awal, akhir in ranges)
