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

ALAMAT TIDAK IKUT, satu pun tidak. "@id", "url", "mainEntityOfPage",
dan alamat di tiap tingkat BreadcrumbList dibiarkan persis seperti
yang tertulis di template.

Ini permintaan pengguna, dan alasannya kelihatan begitu halaman
terbit. Alamat halaman tidak pernah diketahui pipeline: yang dipakai
SITE_BASE_URL dari .env, yang bawaannya "https://example.com". Jadi
tiap pengenal di seluruh graph ditulis ulang jadi
"https://example.com/slug-halaman/#webpage" - puluhan kali dalam satu
berkas - dan yang terbit bukan halaman beralamat lama melainkan
halaman yang menyatakan dirinya milik contoh domain yang tidak pernah
ada. Pengguna mengganti domainnya sendiri sesudah berkasnya diunduh,
dan mencari-ganti satu alamat asli jauh lebih mudah daripada memburu
alamat karangan yang tersebar di setiap simpul.
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


def rewrite_breadcrumb(node: dict, trail: list[str]) -> int:
    """
    Menyesuaikan remah navigasi dengan topik halaman baru.

    Yang diganti nama tiap tingkat. Posisi, jumlah tingkat, dan
    ALAMAT tiap tingkat dibiarkan: jumlahnya ditentukan template, dan
    alamatnya ditentukan pengguna sesudah berkasnya diunduh.

    Alamat sempat ikut diurus di sini - tingkat pertama ditimpa
    beranda sendiri, sisanya dilepas kalau berdiri di luar domain
    sendiri. Yang terbit dari situ adalah remah beralamat
    "https://example.com/", karena "domain sendiri" tidak pernah
    benar-benar diketahui pipeline. Sekarang alamat template
    dibiarkan apa adanya dan pengguna menggantinya sekali dengan
    cari-ganti.

    Kalau jalur barunya lebih pendek daripada tingkat yang ada di
    template, tingkat terakhirlah yang dipakai untuk sisanya -
    bukan tingkat pertama - supaya remah tetap berakhir di halaman
    ini, bukan berhenti di kategori.
    """
    items = node.get("itemListElement")

    if not isinstance(items, list) or not items or not trail:
        return 0

    diganti = 0

    # Diurutkan menurut position kalau ada, karena JSON-LD tidak
    # menjamin urutan tulisnya sama dengan urutan jalurnya.
    urut = sorted(
        (x for x in items if isinstance(x, dict)),
        key=lambda x: x.get("position", 0)
        if isinstance(x.get("position"), int)
        else 0,
    )

    # Jalur yang lebih panjang daripada tingkat yang tersedia
    # dipendekkan dari TENGAH, bukan dari ekor.
    #
    # Memotong ekor terdengar wajar sampai dilihat apa yang hilang:
    # tingkat terakhir adalah halaman ini sendiri. Template pengguna
    # punya dua tingkat, sedangkan jalur yang disusun AI lazimnya
    # tiga - beranda, kategori, halaman ini. Memotong ekor
    # menerbitkan "Beranda > Panduan Belajar Python" dan menghapus
    # halamannya sendiri dari remah, padahal justru itu yang dibaca
    # orang di hasil pencarian.
    jalur = list(trail)

    if len(jalur) > len(urut):
        jalur = [jalur[0]] + jalur[-(len(urut) - 1):] if len(urut) > 1 else [jalur[-1]]

    for nomor, item in enumerate(urut):
        if "name" not in item:
            continue

        baru = jalur[nomor] if nomor < len(jalur) else jalur[-1]

        if item["name"] != baru:
            item["name"] = baru
            diganti += 1

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

    if tipe == "BreadcrumbList":
        diganti += rewrite_breadcrumb(
            node,
            [
                str(x).strip()
                for x in (content.get("breadcrumb") or [])
                if str(x).strip()
            ],
        )

    # Kata kunci dan nama rubrik menyatakan halaman ini TENTANG apa.
    # Keduanya ada di TEXT_KEYS, jadi selama ini cuma kena ganti nama
    # brand - dan yang terbit adalah kata kunci topik template lama
    # dengan brand baru menempel di ujungnya.
    # Dua jalur menyediakannya dengan bentuk berbeda: halaman yang
    # dirakit dari rencana punya daftar "keywords", sedangkan halaman
    # dari template punya satu string di peran "meta_keywords" -
    # persis seperti yang tertulis di <meta> template.
    mentah = content.get("keywords")

    if not mentah:
        mentah = [
            bagian
            for bagian in str(content.get("meta_keywords") or "").split(",")
        ]

    kunci_baru = [str(x).strip() for x in (mentah or []) if str(x).strip()]

    if kunci_baru and "keywords" in node:
        node["keywords"] = (
            ", ".join(kunci_baru[:12])
            if isinstance(node["keywords"], str)
            else kunci_baru[:12]
        )

        diganti += 1

    if "articleSection" in node and isinstance(node["articleSection"], str):
        # Rubrik diambil dari tingkat tengah remah navigasi, karena
        # di situlah kategori topiknya sudah disimpulkan dari riset.
        jalur = [
            str(x).strip()
            for x in (content.get("breadcrumb") or [])
            if str(x).strip()
        ]

        if len(jalur) >= 2:
            node["articleSection"] = jalur[-2]
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
                        anak,
                        content,
                        brand,
                        dates,
                        pola,
                        assets,
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


def breadcrumb_levels(scanned: dict, html: str) -> tuple[int, list[str]]:
    """
    Menghitung tingkat remah navigasi yang ada di JSON-LD template.

    Dipakai untuk memesan jalur ke AI dengan jumlah tingkat yang
    sama persis, supaya tidak ada tingkat template yang tertinggal
    memakai nama lama - dan tidak ada tingkat karangan yang tidak
    punya tempat.

    Mengembalikan jumlah tingkat beserta nama-nama lamanya. Nama
    lama ikut dikirim ke prompt sebagai contoh BENTUK, bukan untuk
    disalin: dari situ model tahu remah ini bergaya satu kata
    ("Promo") atau frasa ("Panduan Belajar Python").
    """
    terbanyak = 0
    contoh: list[str] = []

    def telusuri(node):
        nonlocal terbanyak, contoh

        if isinstance(node, dict):
            if node_type(node) == "BreadcrumbList":
                items = node.get("itemListElement")

                if isinstance(items, list):
                    nama = [
                        str(x.get("name")).strip()
                        for x in items
                        if isinstance(x, dict) and str(x.get("name") or "").strip()
                    ]

                    if len(nama) > terbanyak:
                        terbanyak = len(nama)
                        contoh = nama

            for nilai in node.values():
                telusuri(nilai)

        elif isinstance(node, list):
            for anak in node:
                telusuri(anak)

    for blok in jsonld_blocks(scanned, html):
        if blok["data"] is not None:
            telusuri(blok["data"])

    return terbanyak, contoh


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

    Alamat tidak termasuk yang diganti. Lihat keterangan di kepala
    berkas: pengenal halaman dibiarkan seperti tertulis di template,
    dan pengguna menggantinya sendiri.
    """
    edits: list[dict] = []
    total = 0

    pola = build_pattern(old_brand) if old_brand else None

    for blok in jsonld_blocks(scanned, html):
        if blok["data"] is None:
            continue

        diganti = rewrite_node(
            blok["data"],
            content,
            brand,
            dates,
            pola,
            assets,
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
