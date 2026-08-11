"""
Menulis ulang data terstruktur milik template.

Blok <script type="application/ld+json"> selama ini tidak pernah
disentuh, karena isi <script> memang bukan teks untuk pembaca dan
menggantinya bisa merusak perilaku halaman. Untuk JSON-LD alasan itu
tidak berlaku: isinya murni data, dan justru data itulah yang dibaca
mesin pencari untuk menyusun rich result.

Akibat dibiarkan, halaman terbit dengan dua wajah yang berbeda.
Diukur pada hasil generate sungguhan:

  yang terlihat  : "Slot Gacor: Penjelasan Teknis"
  yang dibaca    : FAQPage berisi "Apa yang dimaksud dengan deposit
                   QRIS 1 detik di OSB99?" dan Article berjudul
                   "ORI99: Cepat, Aman & Instan 24 Jam"

Jadi rich result di Google menampilkan pertanyaan, ulasan, dan nama
brand milik template lama - lengkap dengan brand pemilik sebelumnya.

Yang ditulis ulang hanya NILAI, tidak pernah bentuknya: kunci, tipe,
urutan, dan seluruh cabang yang tidak dikenali dibiarkan apa adanya.
Angka rating dan jumlah ulasan milik template juga dipertahankan,
karena itu klaim pemilik halaman, bukan sesuatu yang boleh dikarang
ulang tiap kali generate.
"""

import json

from generators.brand_swap import build_pattern, match_case
from utils.text import author_name
from generators.schema_generator import json_for_html


# Tipe yang namanya adalah nama halaman, bukan nama brand. Dipisah
# karena keduanya butuh isi berbeda: satu diisi judul, satu diisi
# nama situs.
PAGE_TYPES = {"WebPage", "Article", "NewsArticle", "BlogPosting", "Product"}
BRAND_TYPES = {"Organization", "WebSite", "Brand"}

# Kunci yang isinya kalimat deskripsi halaman.
DESCRIPTION_KEYS = ("description", "abstract")

# Kunci yang isinya tulisan untuk dibaca orang, bukan alamat. Nama
# brand lama di sini harus ikut berganti; nama brand di "url",
# "image", "@id", atau "sameAs" justru tidak boleh disentuh karena
# di situ ia bagian dari alamat berkas.
#
# Yang menyelinap lewat tanpa daftar ini: BreadcrumbList. Remah
# navigasinya terbit sebagai ListItem.name, muncul di hasil
# pencarian tepat di bawah judul, dan tipenya bukan Organization
# maupun WebPage sehingga tidak tersentuh aturan mana pun di atas.
# Terukur pada halaman jadi: satu ListItem masih bernama "OSB99"
# padahal seluruh halaman sudah berganti ke TIMAH33.
TEXT_KEYS = {
    "name",
    "alternateName",
    "legalName",
    "headline",
    "description",
    "abstract",
    "text",
    "reviewBody",
    "caption",
    "slogan",
    "articleSection",
    "keywords",
}


# Kunci JSON-LD yang isinya alamat gambar, dipetakan ke peran gambar
# yang diisi pengguna di formulir.
#
# Perlu diikutkan karena rich result memakai gambar dari SINI, bukan
# dari <img> di badan halaman. Logo yang sudah diganti di header tapi
# masih beralamat lama di Organization.logo membuat Google
# menampilkan logo pemilik template sebelumnya di hasil pencarian.
IMAGE_KEYS = {
    "logo": "logo",
    "image": "poster",
    "thumbnailUrl": "poster",
    "primaryImageOfPage": "poster",
}


def rewrite_images(node: dict, assets: dict | None) -> int:
    """
    Mengganti alamat gambar di satu simpul, apa pun bentuk nilainya.

    Bentuknya tiga macam di data sungguhan: alamat polos, daftar
    alamat, dan ImageObject dengan url di dalamnya. Ketiganya
    dipertahankan bentuknya - yang tadinya daftar tetap daftar,
    yang tadinya objek tetap objek.
    """
    if not assets:
        return 0

    diganti = 0

    for kunci, peran in IMAGE_KEYS.items():
        url = str((assets or {}).get(peran) or "").strip()

        if not url or kunci not in node:
            continue

        nilai = node[kunci]

        if isinstance(nilai, str):
            node[kunci] = url
        elif isinstance(nilai, list):
            node[kunci] = [url]
        elif isinstance(nilai, dict):
            if "url" in nilai:
                nilai["url"] = url
            elif "contentUrl" in nilai:
                nilai["contentUrl"] = url
            else:
                continue
        else:
            continue

        diganti += 1

    return diganti


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def node_type(node: dict) -> str:
    tipe = node.get("@type")

    if isinstance(tipe, list):
        return tipe[0] if tipe else ""

    return str(tipe or "")


def rewrite_faq(node: dict, questions: list[str], answers: list[str]) -> int:
    """
    Mengganti isi FAQPage dengan tanya jawab baru.

    Jumlah kartu tidak ditambah maupun dikurangi. Kalau teks barunya
    lebih sedikit daripada kartu yang ada, sisanya dibiarkan; kartu
    yang isinya teks lama masih lebih baik daripada kartu kosong yang
    membuat schema-nya tidak valid.
    """
    diganti = 0

    for index, item in enumerate(as_list(node.get("mainEntity"))):
        if not isinstance(item, dict):
            continue

        if index < len(questions):
            item["name"] = questions[index]
            diganti += 1

        jawaban = item.get("acceptedAnswer")

        if isinstance(jawaban, dict) and index < len(answers):
            jawaban["text"] = answers[index]
            diganti += 1

    return diganti


def rewrite_reviews(
    node: dict,
    texts: list[str],
    authors: list[str],
    dates: list[dict],
) -> int:
    """
    Mengganti isi ulasan, tanpa menyentuh angka ratingnya.

    ratingValue dan reviewCount milik template dipertahankan. Angka
    itu klaim pemilik halaman; menggantinya dengan angka kita sendiri
    berarti mengarang data tentang brand orang.
    """
    diganti = 0

    for index, ulasan in enumerate(as_list(node.get("review"))):
        if not isinstance(ulasan, dict):
            continue

        if index < len(texts):
            ulasan["reviewBody"] = texts[index]
            diganti += 1

        penulis = ulasan.get("author")

        if isinstance(penulis, dict) and index < len(authors):
            # Namanya saja. Baris pengulas di halaman memuat nama,
            # kota, dan bintang sekaligus; Person bernama "Bagus
            # Setiawan — Semarang • ★★★★★" adalah nama yang tidak
            # dipakai siapa pun, dan Google membacanya apa adanya.
            penulis["name"] = author_name(authors[index])
            diganti += 1

        if index < len(dates):
            ulasan["datePublished"] = dates[index]["iso"]

    return diganti


def swap_brand_text(node: dict, pola, new_brand: str) -> int:
    """
    Mengganti nama brand lama di nilai yang dibaca orang.

    Cuma menyentuh kunci di TEXT_KEYS, jadi nama brand yang jadi
    bagian dari alamat gambar tetap utuh dan gambarnya tetap termuat.
    """
    if pola is None or not new_brand:
        return 0

    diganti = 0

    for kunci, nilai in node.items():
        if kunci not in TEXT_KEYS or not isinstance(nilai, str) or not nilai:
            continue

        baru = pola.sub(
            lambda cocok: match_case(cocok.group(0), new_brand),
            nilai,
        )

        if baru != nilai:
            node[kunci] = baru
            diganti += 1

    return diganti


def rewrite_node(
    node: dict,
    content: dict,
    brand: dict,
    dates: list[dict],
    pola=None,
    assets: dict | None = None,
) -> int:
    """
    Menulis ulang satu simpul beserta seluruh cabangnya.
    """
    if not isinstance(node, dict):
        return 0

    diganti = 0

    tipe = node_type(node)
    judul = str(content.get("title") or content.get("h1") or "").strip()
    ringkas = str(content.get("meta_description") or "").strip()
    nama_situs = str(brand.get("site_name", "")).strip()

    if tipe in BRAND_TYPES and nama_situs and "name" in node:
        node["name"] = nama_situs
        diganti += 1

    if tipe in PAGE_TYPES and judul:
        for kunci in ("name", "headline"):
            if kunci in node:
                node[kunci] = judul
                diganti += 1

    if ringkas:
        for kunci in DESCRIPTION_KEYS:
            if kunci in node and isinstance(node[kunci], str):
                node[kunci] = ringkas
                diganti += 1

    if tipe == "FAQPage":
        diganti += rewrite_faq(
            node,
            [str(x) for x in content.get("faq_question", [])],
            [str(x) for x in content.get("faq_answer", [])],
        )

    if node.get("review"):
        diganti += rewrite_reviews(
            node,
            [str(x) for x in content.get("review_text", [])],
            [str(x) for x in content.get("review_author", [])],
            dates,
        )

    # Terakhir, supaya nama brand lama yang masih tersisa di nilai
    # mana pun ikut berganti - termasuk yang tipenya tidak dikenali
    # aturan di atas.
    diganti += swap_brand_text(node, pola, nama_situs)
    diganti += rewrite_images(node, assets)

    for nilai in node.values():
        if isinstance(nilai, dict):
            diganti += rewrite_node(
                nilai, content, brand, dates, pola, assets
            )
        elif isinstance(nilai, list):
            for anak in nilai:
                if isinstance(anak, dict):
                    diganti += rewrite_node(
                        anak, content, brand, dates, pola, assets
                    )

    return diganti


def has_reviews(scanned: dict, html: str) -> bool:
    """
    Apakah template sudah punya blok ulasan berdata terstruktur.

    Dipakai supaya blok Review buatan sendiri tidak ditambahkan di
    atas blok yang sudah ada. Dua Product dengan aggregateRating
    berbeda di satu halaman bukan cuma mubazir - mesin pencari
    melihat dua klaim rating yang saling bertentangan.
    """
    for blok in jsonld_blocks(scanned, html):
        if blok["data"] is None:
            continue

        for simpul in walk(blok["data"]):
            if simpul.get("review") or simpul.get("aggregateRating"):
                return True

    return False


def walk(data):
    """
    Menyusuri seluruh simpul objek di dalam data JSON.
    """
    if isinstance(data, dict):
        yield data

        for nilai in data.values():
            yield from walk(nilai)
    elif isinstance(data, list):
        for anak in data:
            yield from walk(anak)


def jsonld_blocks(scanned: dict, html: str) -> list[dict]:
    """
    Mengumpulkan blok JSON-LD beserta letak dan isinya yang terurai.
    """
    hasil = []

    for blok in scanned.get("opaque", []):
        if blok.get("tag") != "script":
            continue

        tipe = str(blok.get("attrs", {}).get("type", "")).lower()

        if "ld+json" not in tipe:
            continue

        awal = blok["body_start"]
        akhir = blok.get("body_end", awal)
        mentah = html[awal:akhir]

        try:
            data = json.loads(mentah)
        except (ValueError, TypeError):
            # JSON-LD yang tidak bisa diurai dibiarkan utuh. Menulis
            # ulang sesuatu yang tidak dipahami lebih berbahaya
            # daripada membiarkannya.
            data = None

        hasil.append(
            {
                "start": awal,
                "end": akhir,
                "raw": mentah,
                "data": data,
            }
        )

    return hasil


def jsonld_edits(
    scanned: dict,
    html: str,
    content: dict,
    brand: dict,
    dates: list[dict],
    old_brand: str = "",
    assets: dict | None = None,
) -> tuple[list[dict], int]:
    """
    Menyusun penggantian untuk seluruh blok JSON-LD di halaman.

    Setiap blok diganti sebagai satu rentang utuh, bukan potong
    sana-sini, supaya JSON-nya dijamin tetap valid.
    """
    edits: list[dict] = []
    total = 0

    pola = build_pattern(old_brand) if old_brand else None

    for blok in jsonld_blocks(scanned, html):
        if blok["data"] is None:
            continue

        diganti = rewrite_node(
            blok["data"], content, brand, dates, pola, assets
        )

        if not diganti:
            continue

        edits.append(
            {
                "kind": "raw",
                "start": blok["start"],
                "end": blok["end"],
                "text": json_for_html(blok["data"]),
                "current": blok["raw"],
            }
        )

        total += diganti

    return edits, total
