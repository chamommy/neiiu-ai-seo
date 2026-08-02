"""
Pemeriksa bahwa template pengguna tidak rusak setelah diisi.

Janji ke pengguna ada tiga: strukturnya tidak berubah, link yang
sudah ada tidak hilang, dan iklan yang sudah ada tidak terhapus.
Janji seperti itu tidak cukup dijaga dengan hati-hati saat menulis
kode, karena satu pemetaan slot yang keliru sudah cukup untuk
melanggarnya tanpa ketahuan.

Di sini hasil isian dibandingkan langsung dengan template aslinya.
Kalau ada yang melanggar, hasilnya ditolak, bukan diperbaiki
diam-diam: template itu milik pengguna, dan menebak-nebak
perbaikannya justru merusak yang mau dijaga.
"""

from generators.template_scanner import prepare_replacement, scan


# Atribut yang menentukan perilaku atau tampilan elemen. Perubahan
# di sini berarti struktur berubah, bukan isi.
STRUCTURAL_ATTRS = (
    "href",
    "src",
    "srcset",
    "class",
    "id",
    "layout",
    "width",
    "height",
    "type",
    "rel",
    "data-ad-client",
    "data-ad-slot",
)


def element_signature(element: dict) -> str:
    """
    Menyusun sidik satu elemen dari hal-hal yang tidak boleh berubah.
    """
    attrs = element["attrs"]

    parts = [element["tag"]]

    for name in STRUCTURAL_ATTRS:
        if name in attrs:
            parts.append(f"{name}={attrs[name]}")

    return "|".join(parts)


def fingerprint(html: str) -> dict:
    """
    Merekam bentuk dokumen dalam ukuran yang bisa dibandingkan.
    """
    result = scan(html)
    elements = result["elements"]

    tag_counts: dict[str, int] = {}

    for element in elements:
        tag_counts[element["tag"]] = tag_counts.get(element["tag"], 0) + 1

    links = [
        element["attrs"]["href"]
        for element in elements
        if element["tag"] == "a" and "href" in element["attrs"]
    ]

    sources = [
        element["attrs"]["src"]
        for element in elements
        if "src" in element["attrs"]
    ]

    ads = [
        element_signature(element)
        for element in elements
        if element["is_ad"]
    ]

    return {
        "tag_counts": tag_counts,
        "tag_order": [element["tag"] for element in elements],
        "links": links,
        "sources": sources,
        "ads": ads,
        "signatures": [element_signature(element) for element in elements],
    }


def missing_items(before: list, after: list) -> list:
    """
    Mencari isi yang hilang, dengan menghitung pengulangan.

    Perbandingan himpunan tidak cukup: template yang punya tiga blok
    iklan identik dan kehilangan dua di antaranya tetap terlihat utuh
    kalau hanya nilai uniknya yang dibandingkan.
    """
    remaining = list(after)
    gone: list = []

    for item in before:
        if item in remaining:
            remaining.remove(item)
        else:
            gone.append(item)

    return gone


def verify_untouched_regions(
    original: str,
    filled: str,
    edits: list[dict],
) -> list[str]:
    """
    Membuktikan seluruh bagian di luar slot benar-benar tidak berubah.

    Ini bukti yang paling kuat dan paling murah yang bisa didapat.
    Karena pengisian dilakukan dengan menukar rentang tertentu di
    dalam teks asli, satu-satunya byte yang mungkin berbeda ada di
    dalam rentang itu. Jadi kalau potongan-potongan di antaranya
    disambung kembali dan hasilnya identik dengan potongan yang sama
    dari template asli, seluruh sisa dokumen terbukti utuh: iklan,
    skrip, link, komentar, atribut tanpa kutip, semuanya.

    Sidik jari struktural di verify() tetap dipakai sebagai lapis
    kedua, karena pemeriksaan ini tidak bisa melihat kalau slotnya
    sendiri yang salah dipetakan.
    """
    ordered = sorted(edits, key=lambda item: int(item["start"]))

    kept_original: list[str] = []
    kept_filled: list[str] = []

    cursor_original = 0
    cursor_filled = 0

    for edit in ordered:
        start = int(edit["start"])
        end = int(edit["end"])

        # Panjang yang benar-benar ditulis adalah panjang setelah
        # di-escape, bukan panjang teks mentahnya. Memakai yang
        # mentah membuat seluruh perbandingan sesudahnya bergeser
        # dan melaporkan kerusakan palsu.
        length = len(prepare_replacement(edit))

        kept_original.append(original[cursor_original:start])
        kept_filled.append(
            filled[cursor_filled:cursor_filled + (start - cursor_original)]
        )

        cursor_filled += (start - cursor_original) + length
        cursor_original = end

    kept_original.append(original[cursor_original:])
    kept_filled.append(filled[cursor_filled:])

    problems: list[str] = []

    for index, (before_part, after_part) in enumerate(
        zip(kept_original, kept_filled)
    ):
        if before_part == after_part:
            continue

        # Titik pertama yang berbeda jauh lebih berguna daripada
        # sekadar mengatakan potongannya tidak sama.
        position = next(
            (
                offset
                for offset, (left, right) in enumerate(
                    zip(before_part, after_part)
                )
                if left != right
            ),
            min(len(before_part), len(after_part)),
        )

        problems.append(
            f"Bagian di luar slot ke-{index} berubah pada karakter "
            f"{position}: {before_part[position:position + 40]!r} "
            f"jadi {after_part[position:position + 40]!r}"
        )

    return problems


def verify(
    original: str,
    filled: str,
    edits: list[dict] | None = None,
    allow_added_tags: dict[str, int] | None = None,
) -> dict:
    """
    Membandingkan template asli dengan hasil isian.

    allow_added_tags menyebutkan penambahan yang memang disengaja,
    misalnya {"script": 1} untuk satu blok JSON-LD. Izinnya sengaja
    berbentuk daftar tertutup dengan jumlahnya: penambahan yang
    tidak disebutkan tetap dianggap pelanggaran, jadi bug yang
    menyisipkan tag tak terduga tidak ikut lolos.

    Mengembalikan {"ok": bool, "violations": [...], "stats": {...}}.
    """
    before = fingerprint(original)
    after = fingerprint(filled)

    allowance = dict(allow_added_tags or {})

    violations: list[str] = []

    if edits is not None:
        violations.extend(
            verify_untouched_regions(original, filled, edits)
        )

    # 1. Jumlah dan urutan tag.
    if before["tag_order"] != after["tag_order"]:
        for tag in sorted(set(before["tag_counts"]) | set(after["tag_counts"])):
            count = before["tag_counts"].get(tag, 0)
            found = after["tag_counts"].get(tag, 0)
            permitted = allowance.get(tag, 0)

            if found == count + permitted:
                continue

            if tag not in before["tag_counts"]:
                violations.append(
                    f"Tag <{tag}> muncul {found} kali padahal tidak ada "
                    "di template asli."
                )
                continue

            violations.append(
                f"Jumlah <{tag}> berubah: {count} jadi {found}."
            )

        if not violations:
            # Jumlahnya cocok tapi urutannya tidak. Selama yang
            # bertambah hanya tag yang diizinkan, urutan yang
            # bergeser memang akibat penyisipan itu.
            if not allowance:
                violations.append(
                    "Urutan tag di dokumen berubah walau jumlahnya sama."
                )

    # 2. Link yang hilang.
    lost_links = missing_items(before["links"], after["links"])

    for href in lost_links[:10]:
        violations.append(f"Link hilang: href={href}")

    if len(lost_links) > 10:
        violations.append(
            f"...dan {len(lost_links) - 10} link lain ikut hilang."
        )

    # 3. Iklan yang hilang.
    lost_ads = missing_items(before["ads"], after["ads"])

    for signature in lost_ads[:10]:
        violations.append(f"Blok iklan hilang: {signature}")

    # 4. Sumber berkas (gambar, skrip) yang hilang.
    lost_sources = missing_items(before["sources"], after["sources"])

    for src in lost_sources[:10]:
        violations.append(f"src hilang: {src}")

    # 5. Atribut struktural yang berubah.
    lost_signatures = missing_items(
        before["signatures"],
        after["signatures"],
    )

    # Sidik yang hilang karena tagnya hilang sudah dilaporkan di
    # atas, jadi di sini hanya dilaporkan yang belum tercakup.
    reported = set(lost_links) | set(lost_ads) | set(lost_sources)

    for signature in lost_signatures[:10]:
        if any(str(item) in signature for item in reported):
            continue

        violations.append(f"Atribut elemen berubah: {signature}")

    return {
        "ok": not violations,
        "violations": violations,
        "stats": {
            "elements": len(before["tag_order"]),
            "links": len(before["links"]),
            "ads": len(before["ads"]),
            "bytes_before": len(original),
            "bytes_after": len(filled),
        },
    }
