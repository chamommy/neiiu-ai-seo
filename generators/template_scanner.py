"""
Pemindai slot isi di template HTML milik pengguna.

Template yang diunggah pengguna tidak boleh berubah strukturnya.
Itu menutup jalan yang biasa dipakai, yaitu mengurai HTML dengan
BeautifulSoup lalu menyerialisasi ulang: penyerialisasi menulis
ulang seluruh dokumen, mengurutkan atribut menurut abjad, mengubah
atribut boolean jadi bentuk bernilai, dan menambahkan tanda kutip.
Template AMP yang tadinya sah bisa rusak sebelum satu huruf pun
diganti.

Modul ini memakai pengurai bawaan Python hanya untuk MENEMUKAN
LETAK setiap potongan yang boleh diganti, lalu penggantian
dilakukan langsung pada teks aslinya. Semua yang tidak diganti
tetap sama byte demi byte, termasuk iklan, skrip pihak ketiga,
komentar, dan atribut yang ditulis tanpa tanda kutip.
"""

import re
from html.parser import HTMLParser


# Isi tag ini bukan teks yang tampil ke pembaca. Menggantinya akan
# merusak perilaku halaman, bukan mengubah kontennya.
OPAQUE_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "code",
    "pre",
    "textarea",
}

# Tag yang tidak punya penutup, jadi tidak boleh masuk tumpukan
# induk. Kalau ikut ditumpuk, seluruh sisa dokumen akan dikira
# berada di dalamnya.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
    # Elemen AMP yang lazim ditulis tanpa penutup.
    "amp-img", "amp-pixel",
}

# Penanda blok iklan. Apa pun di dalamnya tidak disentuh sama
# sekali, sesuai permintaan bahwa iklan yang sudah ada tidak boleh
# hilang atau berubah.
AD_MARKERS = re.compile(
    r"adsbygoogle|googlesyndication|googletag|data-ad-|"
    r"\bads?\b|\badslot\b|banner|sponsor|propeller|adsterra",
    re.IGNORECASE,
)

AD_TAGS = {"ins", "amp-ad", "amp-embed", "amp-analytics", "amp-pixel"}

# Batas kedalaman sarang. Halaman sungguhan jarang lewat 30 tingkat;
# 200 sudah sangat longgar. Batas ini ada karena tiap simpul teks
# perlu tahu atribut seluruh induknya, dan tanpa batas sebuah berkas
# kecil berisi <div><div><div>... bisa memaksa server bekerja
# kuadratik sampai berpuluh detik hanya untuk satu unggahan.
MAX_DEPTH = 200


class TemplateTooDeep(ValueError):
    """Template bersarang jauh lebih dalam daripada halaman wajar."""


# Atribut yang isinya teks untuk dibaca manusia atau mesin pencari,
# jadi termasuk yang boleh diisi ulang.
TEXT_ATTRIBUTES = {
    ("meta", "content"),
    ("img", "alt"),
    ("amp-img", "alt"),
    ("time", "datetime"),
    ("a", "title"),
    ("html", "lang"),
    ("meta", "charset"),
}


def walk_attributes(raw: str):
    """
    Menyusuri atribut satu tag dari kiri ke kanan.

    Menggantikan pencarian nama atribut dengan regex. Regex mencocok
    di mana saja di dalam teks tag, dan itu salah dalam tiga cara
    yang semuanya menulis teks ke tempat yang bukan tujuannya:

      <meta data-content="x" content="y">   nama jadi bagian nama lain
      <meta name="a" content="alt=b">       nama ketemu di dalam nilai
      <img alt="p" alt="q">                 dua rentang untuk satu peran

    Penyusuran ini melewati nilai yang berkutip sebagai satu blok,
    jadi apa pun isinya tidak pernah dikira nama atribut.

    Menghasilkan (nama_kecil, awal_nilai, akhir_nilai, kutip).
    """
    total = len(raw)

    # Lewati "<" dan nama tagnya.
    position = 1

    while position < total and not raw[position].isspace() and raw[position] not in "/>":
        position += 1

    while position < total:
        while position < total and raw[position].isspace():
            position += 1

        if position >= total or raw[position] in "/>":
            return

        name_start = position

        while (
            position < total
            and not raw[position].isspace()
            and raw[position] not in "/>="
        ):
            position += 1

        name = raw[name_start:position]

        if not name:
            position += 1
            continue

        after_name = position

        while position < total and raw[position].isspace():
            position += 1

        if position >= total or raw[position] != "=":
            # Atribut boolean seperti amp atau hidden: tidak punya
            # nilai sama sekali, jadi tidak ada yang bisa diisi.
            position = after_name
            continue

        position += 1

        while position < total and raw[position].isspace():
            position += 1

        if position < total and raw[position] in "\"'":
            quote = raw[position]
            position += 1
            value_start = position
            closing = raw.find(quote, position)

            if closing == -1:
                return

            value_end = closing
            position = closing + 1
        else:
            quote = None
            value_start = position

            while (
                position < total
                and not raw[position].isspace()
                and raw[position] not in "/>"
            ):
                position += 1

            value_end = position

        yield name.lower(), value_start, value_end, quote


class SlotScanner(HTMLParser):
    """
    Mencatat letak setiap simpul teks dan atribut yang bisa diisi.

    Yang dicatat hanya rentang posisinya, bukan pohon dokumen, jadi
    tidak ada tahap penyerialisasian ulang di mana pun.
    """

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)

        self.source = source

        # Peta offset awal tiap baris, supaya (baris, kolom) yang
        # dilaporkan pengurai bisa diubah jadi indeks karakter.
        #
        # Dipecah di "\n" saja, BUKAN dengan splitlines(). HTMLParser
        # hanya menambah nomor barisnya di "\n", sedangkan splitlines
        # juga memecah di \r, \v, \f, \x1c-\x1e, \x85, dan dua
        # pemisah baris Unicode. Satu saja karakter itu ada di template - dan \r ada
        # di hampir semua berkas yang ditulis di Windows - peta baris
        # jadi lebih panjang daripada hitungan pengurai, semua offset
        # sesudahnya meleset, dan penggantian ditulis di tengah tag
        # yang salah.
        self.line_start: list[int] = []
        total = 0

        for line in source.split("\n"):
            self.line_start.append(total)
            total += len(line) + 1

        self.stack: list[dict] = []
        self.slots: list[dict] = []
        self.elements: list[dict] = []
        self.end_tags: list[dict] = []
        self.pending: int | None = None

        # Pencacah, bukan penelusuran tumpukan.
        #
        # Sebelumnya setiap tag memeriksa seluruh tumpukan induknya
        # untuk tahu apakah sedang di dalam <script> atau di dalam
        # blok iklan, dan menyimpan salinan seluruh jalur induk. Dua
        # duanya sebanding kedalaman, jadi biayanya kuadratik: satu
        # berkas 430KB dengan div bersarang dalam - jauh di bawah
        # batas unggah 2MB - menyita CPU berpuluh detik. Karena
        # pemindaian berjalan di dalam permintaan HTTP, yang membeku
        # bukan cuma permintaan itu, tapi seluruh server.
        self.opaque_depth = 0
        self.ad_depth = 0

    # ---------- posisi ----------

    def char_offset(self) -> int:
        line, column = self.getpos()

        if line - 1 >= len(self.line_start):
            return len(self.source)

        return self.line_start[line - 1] + column

    # ---------- konteks ----------

    def in_opaque(self) -> bool:
        return self.opaque_depth > 0

    def in_ad(self) -> bool:
        return self.ad_depth > 0

    def path(self) -> list[str]:
        return [item["tag"] for item in self.stack]

    def looks_like_ad(self, tag: str, attrs: dict) -> bool:
        if tag in AD_TAGS:
            return True

        haystack = " ".join(
            [tag]
            + list(attrs.keys())
            + [str(value or "") for key, value in attrs.items()
               if key in {"class", "id", "data-ad-client", "type"}]
        )

        return bool(AD_MARKERS.search(haystack))

    # ---------- simpul teks ----------

    def close_pending(self, end: int) -> None:
        if self.pending is None:
            return

        start = self.pending
        self.pending = None

        raw = self.source[start:end]

        if not raw.strip():
            return

        parent = self.stack[-1] if self.stack else None

        self.slots.append(
            {
                "kind": "text",
                "start": start,
                "end": end,
                "current": raw,
                "tag": parent["tag"] if parent else "",
                "attrs": dict(parent["attrs"]) if parent else {},
                "attr": None,
                "element_index": parent["index"] if parent else -1,
                "path": self.path(),
                # Atribut seluruh induk ikut dibawa karena penanda
                # seperti class="review-card" biasanya beberapa
                # tingkat di atas teksnya. Yang dipakai harus induk
                # sungguhan; memakai elemen yang kebetulan
                # mendahului di dokumen membuat paragraf tertular
                # penanda dari blok tetangganya.
                "ancestors": [
                    dict(item["attrs"]) for item in self.stack
                ],
                "in_ad": self.in_ad(),
                "depth": len(self.stack),
            }
        )

    def handle_data(self, data: str) -> None:
        if self.in_opaque() or self.in_ad():
            return

        if self.pending is None:
            self.pending = self.char_offset()

    # ---------- atribut ----------

    def attribute_spans(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        tag_start: int,
        element_index: int,
    ) -> None:
        """
        Mencari letak nilai atribut di dalam sumber tag aslinya.

        Nilai dicari di potongan sumber tag itu sendiri, bukan di
        seluruh dokumen, supaya atribut bernilai sama di tempat lain
        tidak ikut tertukar.
        """
        raw = self.get_starttag_text()

        if not raw:
            return

        wanted = {
            name.lower()
            for name, value in attrs
            if (tag, name) in TEXT_ATTRIBUTES and value is not None
        }

        if not wanted:
            return

        seen: set[str] = set()

        for name, value_start, value_end, quote in walk_attributes(raw):
            if name not in wanted:
                continue

            # Atribut kembar di satu tag hanya dihitung sekali.
            # Pengurai HTML memakai yang pertama, dan mencatat
            # keduanya akan menghasilkan dua rentang berbeda untuk
            # satu peran, lalu salah satunya menimpa nilai yang tidak
            # pernah dibaca siapa pun.
            if name in seen:
                continue

            seen.add(name)

            if value_end <= value_start:
                continue

            self.slots.append(
                {
                    "kind": "attribute",
                    "start": tag_start + value_start,
                    "end": tag_start + value_end,
                    "current": raw[value_start:value_end],
                    # Tanda kutip pengapitnya ikut dicatat karena
                    # penggantinya harus meng-escape kutip yang itu,
                    # dan atribut tanpa kutip sama sekali tidak boleh
                    # ditulisi: nilai baru yang memuat spasi akan
                    # terbaca sebagai atribut tambahan.
                    "quote": quote,
                    "tag": tag,
                    "attrs": {
                        key: val for key, val in attrs
                    },
                    "attr": name.lower(),
                    "element_index": element_index,
                    "path": self.path() + [tag],
                    "ancestors": [
                        dict(item["attrs"]) for item in self.stack
                    ],
                    "in_ad": self.in_ad(),
                    "depth": len(self.stack),
                }
            )

    # ---------- tag ----------

    def record_element(
        self,
        tag: str,
        attrs: dict,
        start: int,
        is_ad: bool,
    ) -> int:
        """
        Mencatat satu elemen dan mengembalikan nomor urutnya.

        Nomor ini yang menghubungkan nilai atribut dengan teks di
        dalam elemen yang sama. Tanpa itu, atribut datetime dan
        tanggal yang terbaca di layar bisa diisi dua tanggal
        berbeda untuk satu ulasan yang sama.

        Jalur induk sengaja TIDAK disimpan di sini. Tidak ada yang
        membacanya, dan menyalin daftar sepanjang kedalaman untuk
        setiap elemen membuat biaya pemindaian kuadratik.
        """
        self.elements.append(
            {
                "tag": tag,
                "attrs": attrs,
                "start": start,
                "is_ad": is_ad,
            }
        )

        return len(self.elements) - 1

    def handle_starttag(self, tag, attrs) -> None:
        start = self.char_offset()
        self.close_pending(start)

        attr_map = {key: (value or "") for key, value in attrs}
        is_ad = self.looks_like_ad(tag, attr_map)

        index = self.record_element(tag, attr_map, start, is_ad)

        if not self.in_opaque() and not self.in_ad():
            self.attribute_spans(tag, attrs, start, index)

        if tag not in VOID_TAGS:
            if len(self.stack) >= MAX_DEPTH:
                raise TemplateTooDeep(
                    f"Template ini punya tag bersarang lebih dari "
                    f"{MAX_DEPTH} tingkat. Halaman sungguhan tidak "
                    "pernah sedalam itu, dan memindainya menghabiskan "
                    "waktu server tanpa hasil yang berguna. Periksa "
                    "apakah ada tag penutup yang hilang."
                )

            self.stack.append(
                {
                    "tag": tag,
                    "attrs": attr_map,
                    "index": index,
                    "is_ad": is_ad,
                }
            )

            if tag in OPAQUE_TAGS:
                self.opaque_depth += 1

            if is_ad:
                self.ad_depth += 1

    def handle_startendtag(self, tag, attrs) -> None:
        start = self.char_offset()
        self.close_pending(start)

        attr_map = {key: (value or "") for key, value in attrs}
        is_ad = self.looks_like_ad(tag, attr_map)

        index = self.record_element(tag, attr_map, start, is_ad)

        if not self.in_opaque() and not self.in_ad():
            self.attribute_spans(tag, attrs, start, index)

    def handle_endtag(self, tag) -> None:
        offset = self.char_offset()

        self.close_pending(offset)

        # Letak tag penutup dicatat supaya penyisipan blok schema
        # bisa memakai posisi hasil pengurai, bukan hasil mencari
        # teks "</head>" di dalam dokumen. Teks itu bisa muncul di
        # dalam komentar atau di dalam string milik <script>, dan
        # menyisipkan di situ menaruh JSON-LD di tempat yang tidak
        # pernah dibaca mesin pencari sekaligus merusak skripnya.
        self.end_tags.append({"tag": tag, "start": offset})

        # Tag penutup yang tidak punya pasangan diabaikan, bukan
        # membuat tumpukan dikosongkan. HTML di dunia nyata sering
        # punya penutup nyasar, dan itu tidak boleh mengacaukan
        # seluruh sisa dokumen.
        if not any(item["tag"] == tag for item in self.stack):
            return

        while self.stack:
            item = self.stack.pop()

            if item["tag"] in OPAQUE_TAGS:
                self.opaque_depth -= 1

            if item["is_ad"]:
                self.ad_depth -= 1

            if item["tag"] == tag:
                break

    def handle_comment(self, data) -> None:
        self.close_pending(self.char_offset())

    def handle_decl(self, decl) -> None:
        self.close_pending(self.char_offset())

    def handle_pi(self, data) -> None:
        self.close_pending(self.char_offset())

    def unknown_decl(self, data) -> None:
        self.close_pending(self.char_offset())


def scan(html: str) -> dict:
    """
    Memindai template dan mengembalikan slot beserta daftar elemen.
    """
    scanner = SlotScanner(html)
    scanner.feed(html)
    scanner.close_pending(len(html))
    scanner.close()

    return {
        "slots": scanner.slots,
        "elements": scanner.elements,
        "end_tags": scanner.end_tags,
    }


def escape_text(value: str) -> str:
    """
    Menyiapkan teks untuk ditaruh di antara dua tag.
    """
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_attribute(value: str, quote: str) -> str:
    """
    Menyiapkan teks untuk ditaruh sebagai nilai atribut.

    Yang wajib dinetralkan adalah tanda kutip yang sedang mengapit
    nilainya. Tanpa itu, nilai seperti  x" onload="alert(1)  akan
    menutup atribut lebih awal dan sisanya terbaca sebagai atribut
    baru, sehingga penulis template mendapat handler kejadian yang
    tidak pernah dia tulis.
    """
    escaped = escape_text(value)

    if quote == '"':
        return escaped.replace('"', "&quot;")

    if quote == "'":
        return escaped.replace("'", "&#39;")

    return escaped


def prepare_replacement(edit: dict) -> str:
    """
    Menentukan bentuk akhir teks pengganti untuk satu slot.
    """
    text = str(edit["text"])
    kind = edit.get("kind", "text")

    if kind == "raw":
        # Satu-satunya jalur yang menulis HTML apa adanya, dipakai
        # hanya untuk blok yang disusun program ini sendiri. Isi dari
        # AI maupun dari template tidak pernah lewat sini. Blok
        # JSON-LD yang memakainya sudah melewati json_for_html, yang
        # mengubah kurung siku jadi escape \\u sehingga tidak ada
        # urutan huruf yang bisa terbaca sebagai tag.
        return text

    if kind == "attribute":
        quote = edit.get("quote")

        if not quote:
            raise ValueError(
                "Nilai atribut tanpa tanda kutip tidak boleh diisi. "
                "Teks baru yang memuat spasi akan terbaca sebagai "
                "atribut tambahan dan mengubah struktur tag."
            )

        return escape_attribute(text, quote)

    return escape_text(text)


def apply_edits(
    html: str,
    edits: list[dict],
) -> str:
    """
    Menerapkan penggantian pada teks asli.

    Diterapkan dari belakang ke depan supaya indeks slot yang belum
    diproses tidak bergeser oleh penggantian sebelumnya.

    Escape dilakukan di sini, bukan diserahkan ke pemanggil. Ini
    satu-satunya jalan masuk teks baru ke dalam dokumen, jadi
    menaruh pengamannya di sini berarti tidak ada pemanggil yang
    bisa lupa melakukannya.
    """
    ordered = sorted(
        edits,
        key=lambda item: item["start"],
        reverse=True,
    )

    last_start = None
    result = html

    for edit in ordered:
        start = int(edit["start"])
        end = int(edit["end"])

        if last_start is not None and end > last_start:
            raise ValueError(
                "Dua penggantian saling bertumpang tindih di posisi "
                f"{start}-{end}. Ini selalu berarti pemetaan slotnya "
                "salah, dan menerapkannya akan merusak dokumen."
            )

        result = result[:start] + prepare_replacement(edit) + result[end:]
        last_start = start

    return result
