"""
Mengganti teks yang tertanam di dalam <script> dan <style>.

Isi <script> bukan teks untuk pembaca, dan itulah alasan seluruh
blok ini selama ini dilewati. Tapi sebagian isinya tetap sampai ke
pembaca lewat jalan lain, dan template unggahan sungguhan
membuktikannya: blok konfigurasi

    window.SEO_GEO_CONFIG = { BRAND: "OSB99", META_TITLE: "OSB99 - ..." }

menimpakan judul itu ke document.title begitu halaman dibuka. Jadi
halaman yang <title>-nya sudah berganti tetap kembali ke judul lama
di layar pengunjung, dan tidak ada satu pun pemeriksa struktur yang
bisa melihatnya karena strukturnya memang tidak rusak.

Yang disentuh hanya ISI STRING, tidak pernah kodenya. Bahkan di
dalam string pun ada dua tempat yang sengaja dilewati, karena
menggantinya merusak halaman alih-alih memperbaruinya:

  "https://ik.imagekit.io/xxx/osb99banner10.png"   alamat berkas
  "osb99-deposit-qris"                             slug atau id

Keduanya dipakai memuat gambar dan memanggil data. Nama brand di
situ bukan tulisan yang dibaca orang, melainkan bagian dari alamat.
"""

import re

from generators.brand_swap import (
    build_pattern,
    match_case,
    normalize,
    variants,
)


# Kunci konfigurasi yang namanya sudah menyatakan isinya. Blok
# seperti ini lazim di template siap pakai: sebuah objek berisi judul
# dan deskripsi yang ditimpakan ke halaman lewat JavaScript saat
# dibuka. Karena namanya menyebut sendiri apa yang disimpannya, isinya
# bisa diisi dari konten baru dengan pasti - tidak perlu menebak lewat
# pencocokan teks lama, yang gagal begitu nilai di konfigurasi berbeda
# sedikit saja dari nilai di dalam <head>.
CONFIG_KEYS = {
    "brand": "site_name",
    "meta_title": "title",
    "page_title": "title",
    "product_name": "title",
    "meta_description": "meta_description",
    "page_description": "meta_description",
}

# Kunci dicari tepat sebelum stringnya, dalam bentuk KUNCI: " atau
# "KUNCI": - dua bentuk yang dipakai objek JavaScript dan JSON.
KEY_BEFORE = re.compile(
    r"[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*:\s*$"
)


QUOTES = "\"'`"

# String yang bentuknya identifier: tanpa spasi, cuma huruf, angka,
# titik, garis bawah, dan tanda hubung. Ini bentuk slug, nama berkas,
# id, dan sku - bukan kalimat.
SLUG = re.compile(r"^[A-Za-z0-9._-]+$")


def string_spans(source: str):
    """
    Menyusuri letak isi tiap string di dalam kode.

    Komentar dilewati supaya nama brand yang kebetulan ditulis di
    dalam catatan pengembang tidak dikira string.

    Menghasilkan (awal_isi, akhir_isi) - tanpa tanda kutipnya.
    """
    index = 0
    total = len(source)

    while index < total:
        char = source[index]

        if char == "/" and index + 1 < total:
            berikut = source[index + 1]

            if berikut == "/":
                putus = source.find("\n", index)
                index = total if putus < 0 else putus + 1
                continue

            if berikut == "*":
                putus = source.find("*/", index + 2)
                index = total if putus < 0 else putus + 2
                continue

        if char in QUOTES:
            ujung = index + 1

            while ujung < total:
                sekarang = source[ujung]

                if sekarang == "\\":
                    ujung += 2
                    continue

                if sekarang == char:
                    break

                ujung += 1

            if ujung >= total:
                # Kutip yang tidak pernah ditutup berarti penyusuran
                # sudah kehilangan jejak. Berhenti daripada menebak.
                return

            yield index + 1, ujung
            index = ujung + 1
            continue

        index += 1


def is_address(text: str) -> bool:
    """
    Apakah string ini alamat atau pengenal, bukan kalimat.
    """
    clean = text.strip()

    if not clean:
        return True

    if "/" in clean or "\\" in clean:
        return True

    return bool(SLUG.match(clean))


def config_key(source: str, quote_at: int) -> str:
    """
    Nama kunci yang mendahului sebuah string, kalau ada.
    """
    cocok = KEY_BEFORE.search(source[max(0, quote_at - 60) : quote_at])

    return cocok.group(1).lower() if cocok else ""


def script_edits(
    scanned: dict,
    html: str,
    diganti: dict,
    old_brand: str,
    new_brand: str,
    content: dict | None = None,
) -> tuple[list[dict], int]:
    """
    Menyusun penggantian teks di dalam blok skrip dan gaya.

    diganti memetakan teks lama ke teks barunya, dipakai supaya judul
    dan deskripsi di blok konfigurasi ikut memakai kalimat baru yang
    sama dengan yang terbit di halaman - bukan sekadar nama brand
    yang ditukar.
    """
    pola = build_pattern(old_brand) if old_brand and new_brand else None

    nama_lama = {
        normalize(bentuk) for bentuk in variants(old_brand)
    } if old_brand else set()

    isi_baru = {
        "site_name": str(new_brand or "").strip(),
        "title": str(
            (content or {}).get("title")
            or (content or {}).get("h1")
            or ""
        ).strip(),
        "meta_description": str(
            (content or {}).get("meta_description") or ""
        ).strip(),
    }

    if not pola and not diganti:
        return [], 0

    edits: list[dict] = []
    jumlah = 0

    for blok in scanned.get("opaque", []):
        if blok.get("tag") not in {"script", "style"}:
            continue

        tipe = str(blok.get("attrs", {}).get("type", "")).lower()

        # JSON-LD ditangani jsonld_filler, yang menulis ulang isinya
        # sebagai data - jauh lebih tepat daripada tukar kata.
        if "ld+json" in tipe:
            continue

        awal = blok["body_start"]
        akhir = blok.get("body_end", awal)
        badan = html[awal:akhir]

        for mulai, henti in string_spans(badan):
            asli = badan[mulai:henti]

            # Kunci konfigurasi diisi lebih dulu, sebelum pemeriksaan
            # bentuk. Nilainya sering berupa satu kata tanpa spasi -
            # nama brand - yang bentuknya persis seperti slug dan akan
            # dilewati kalau urutannya dibalik.
            kunci = CONFIG_KEYS.get(config_key(badan, mulai - 1))
            baru = isi_baru.get(kunci) if kunci else None

            # Nama brand yang berdiri sendiri juga diganti meski
            # bentuknya seperti slug. "OSB99" di BRAND: "OSB99" adalah
            # nama yang dibaca orang, bukan bagian dari alamat.
            if not baru and normalize(asli) in nama_lama:
                baru = match_case(asli.strip(), new_brand)

            if not baru and is_address(asli):
                continue

            if baru is None:
                baru = diganti.get(normalize(asli))

            if baru is None and pola:
                baru = pola.sub(
                    lambda cocok: match_case(cocok.group(0), new_brand),
                    asli,
                )

            if not baru or baru == asli:
                continue

            # Tanda kutip di dalam nilai baru akan menutup stringnya
            # lebih awal dan mengubah sisa berkas jadi kode rusak.
            if any(tanda in baru for tanda in QUOTES) or "\\" in baru:
                continue

            edits.append(
                {
                    "kind": "raw",
                    "start": awal + mulai,
                    "end": awal + henti,
                    "text": baru,
                    "current": asli,
                }
            )

            jumlah += 1

    return edits, jumlah
