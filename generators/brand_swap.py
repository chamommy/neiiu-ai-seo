"""
Mengganti brand lama milik template dengan brand baru.

Mengisi slot saja tidak cukup. Nama brand lama tersebar di tempat
yang bukan slot isi mana pun: di teks logo, di alt gambar, di
kalimat hak cipta, di judul yang diulang di beberapa tempat. Kalau
hanya slot yang diisi, halaman baru terbit dengan nama brand lama
masih menempel di sana-sini - dan itu justru bagian yang paling
cepat terlihat orang.

Dua hal dikerjakan di sini, keduanya HANYA pada rentang teks yang
sudah dinyatakan aman oleh pemindai. Tidak ada satu pun karakter di
luar rentang itu yang tersentuh, jadi jaminan strukturnya tetap
sama seperti sebelumnya.

1. Ganti nama. Setiap kemunculan brand lama jadi brand baru, tanpa
   memandang huruf besar-kecilnya, dan bentuk penulisannya diikuti:
   ABECEDE jadi DEEFGE, Abecede jadi Deefge, abecede jadi deefge.

2. Samakan teks kembar. Kalimat milik template yang muncul di lebih
   dari satu tempat - judul yang diulang di h1, di alt gambar, di
   footer - ikut memakai teks baru yang sama dengan yang dipakai di
   tempat pertamanya. Tanpa ini, judul baru muncul di <title>
   sementara kalimat lamanya yang persis sama masih terbaca di
   badan halaman.
"""

import re


# Teks sependek ini terlalu umum untuk dicocokkan sebagai "kalimat
# yang sama". Kata seperti "Promo" bisa muncul di mana saja dengan
# maksud yang sama sekali berbeda.
MIN_ECHO_CHARS = 12


def variants(name: str) -> list[str]:
    """
    Bentuk penulisan nama brand yang perlu ikut dikenali.

    Nama brand rutin ditulis tanpa spasi di URL dan di logo, jadi
    "Abece De" juga harus ketemu saat tertulis "AbeceDe".
    """
    clean = " ".join((name or "").split())

    if not clean:
        return []

    bentuk = {clean, clean.replace(" ", ""), clean.replace(" ", "-")}

    return sorted(
        (item for item in bentuk if item),
        key=len,
        reverse=True,
    )


def match_case(sumber: str, pengganti: str) -> str:
    """
    Menyesuaikan huruf besar-kecil pengganti dengan yang digantikan.

    Logo yang ditulis ABECEDE harus jadi DEEFGE, bukan Deefge,
    supaya tampilannya tidak berubah bentuk di tengah halaman.
    """
    if sumber.isupper():
        return pengganti.upper()

    if sumber.islower():
        return pengganti.lower()

    if sumber[:1].isupper():
        return pengganti[:1].upper() + pengganti[1:]

    return pengganti


def build_pattern(old_brand: str) -> re.Pattern | None:
    """
    Menyusun pola pencarian nama brand lama.

    Batas kata tidak dipakai. Aksara Thai seluruhnya masuk kategori
    \\w bagi Python, jadi \\b tidak pernah cocok di antara dua aksara
    Thai dan nama brand yang menempel pada teks Thai tidak akan
    pernah ketemu. Yang dipakai batas buatan: karakter di kiri dan
    kanan tidak boleh berupa huruf Latin atau angka.
    """
    bentuk = variants(old_brand)

    if not bentuk:
        return None

    return re.compile(
        r"(?<![0-9A-Za-z])(" + "|".join(re.escape(b) for b in bentuk) + r")"
        r"(?![0-9A-Za-z])",
        re.IGNORECASE,
    )


def swap_brand(text: str, pattern: re.Pattern, new_brand: str) -> str:
    """
    Mengganti seluruh kemunculan brand lama di satu potongan teks.
    """
    return pattern.sub(
        lambda m: match_case(m.group(0), new_brand),
        text,
    )


def normalize(text: str) -> str:
    return " ".join((text or "").split()).strip().casefold()


def brand_edits(
    slot_map: dict,
    sudah: dict,
    old_brand: str,
    new_brand: str,
) -> tuple[list[dict], int]:
    """
    Menyusun penggantian brand untuk slot yang belum terisi.

    Slot yang sudah dapat teks baru tidak disentuh lagi di sini;
    teksnya memang sudah ditulis ulang dari nol. Yang dikerjakan
    hanya slot yang tertinggal - termasuk yang tertinggal karena
    isinya tidak cukup untuk semua slot.
    """
    pattern = build_pattern(old_brand)

    if pattern is None or not (new_brand or "").strip():
        return [], 0

    edits: list[dict] = []

    for slots in slot_map["roles"].values():
        for slot in slots:
            if (slot["start"], slot["end"]) in sudah:
                continue

            asli = slot["current"]
            baru = swap_brand(asli, pattern, new_brand)

            if baru != asli:
                edits.append({**slot, "text": baru})

    for slot in slot_map["skipped"]:
        # Slot yang dilewati kebijakan tetap ikut diganti namanya.
        # Alasan melewatinya adalah "belum tentu ini isi artikel",
        # bukan "boleh menyebut brand orang lain". Blok iklan dan
        # atribut tanpa kutip tetap tidak disentuh.
        if slot.get("in_ad"):
            continue

        if slot["kind"] == "attribute" and not slot.get("quote"):
            continue

        asli = slot["current"]
        baru = swap_brand(asli, pattern, new_brand)

        if baru != asli:
            edits.append({**slot, "text": baru})

    return edits, len(edits)


def echo_edits(
    slot_map: dict,
    sudah: dict,
    diganti: dict[str, str],
) -> tuple[list[dict], int]:
    """
    Menyamakan teks lama yang kembar dengan teks barunya.

    "diganti" berisi teks lama -> teks baru dari slot yang sudah
    terisi. Slot lain yang teks lamanya sama persis ikut memakai
    teks baru yang sama, jadi kalimat yang di template muncul dua
    kali tetap muncul dua kali dengan bunyi yang sama.
    """
    peta = {
        kunci: nilai
        for kunci, nilai in diganti.items()
        if len(kunci) >= MIN_ECHO_CHARS
    }

    if not peta:
        return [], 0

    edits: list[dict] = []

    semua = [
        slot
        for slots in slot_map["roles"].values()
        for slot in slots
    ] + slot_map["skipped"]

    for slot in semua:
        if (slot["start"], slot["end"]) in sudah:
            continue

        if slot.get("in_ad"):
            continue

        if slot["kind"] == "attribute" and not slot.get("quote"):
            continue

        baru = peta.get(normalize(slot["current"]))

        if baru and normalize(baru) != normalize(slot["current"]):
            edits.append({**slot, "text": baru})

    return edits, len(edits)
