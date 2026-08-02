"""
Memecah permintaan isi template jadi beberapa giliran.

Satu template sungguhan punya jauh lebih banyak teks daripada yang
muat dalam satu permintaan. Halaman 720 KB yang dipakai menguji
punya 658 potongan teks, seluruhnya 16.172 karakter; ditambah
promptnya sendiri, itu melewati context 16.384 token milik model
lokal. Selama semuanya diminta sekaligus, satu-satunya jalan adalah
memotong daftar permintaan - dan yang terpotong terbit dengan teks
asli milik template, persis yang tidak boleh terjadi kalau
halamannya harus bebas dari tuduhan menyalin.

Dipecah, batasnya hilang: yang perlu muat bukan lagi seluruh
halaman, melainkan satu giliran.

Dua hal yang membuat pemecahan ini murah:

1. Awalan promptnya sama persis di setiap giliran. Ollama menyimpan
   hasil pemrosesan prompt dan memakainya ulang selama awalannya
   sama - terukur di mesin ini, prompt 1389 token yang pertama kali
   makan 242 detik jadi 0,2 detik saat diulang. Jadi bagian brief
   yang panjang cuma dibayar sekali, dan giliran kedua dan
   seterusnya langsung menulis.

2. Urutannya menurut kepentingan. Judul, artikel, FAQ, dan ulasan
   dikerjakan lebih dulu; label menu paling belakang. Kalau
   prosesnya dihentikan di tengah, yang sudah jadi adalah bagian
   yang paling menentukan halaman.
"""


# Urutan pengerjaan giliran. Yang di depan dikerjakan lebih dulu.
ROLE_PRIORITY = (
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
    "caption",
    "list_item",
    "table_cell",
    "label",
    "nav_label",
)

# Peran yang jawabannya satu teks untuk semua slotnya, bukan daftar.
# Judul halaman muncul di <title>, og:title, dan twitter:title, dan
# ketiganya memang harus berbunyi sama.
SINGLE_ROLES = ("title", "meta_description", "meta_keywords", "h1")

# Tambahan karakter per teks untuk tanda kutip, koma, dan spasi di
# JSON. Kecil per teks, tapi untuk 658 teks jumlahnya menentukan
# apakah jawabannya masih muat atau terpotong di tengah.
JSON_OVERHEAD_PER_TEXT = 8

# Tambahan karakter per teks di SISI PROMPT: nomor urut, tanda baca,
# dan baris batas panjangnya. Dihitung terpisah dari sisi jawaban
# karena keduanya tumbuh dengan alasan berbeda - satu giliran bisa
# ringan jawabannya tapi berat promptnya, dan itulah yang terjadi
# pada peran yang teks lamanya ikut dikirim sebagai contoh.
PROMPT_OVERHEAD_PER_TEXT = 12


def role_order(spec: dict) -> list[str]:
    """
    Mengurutkan peran menurut kepentingannya di halaman.

    Peran yang tidak ada di daftar prioritas diletakkan di belakang,
    urut abjad, supaya hasilnya tetap sama tiap dijalankan.
    """
    dikenal = [role for role in ROLE_PRIORITY if role in spec]
    sisa = sorted(role for role in spec if role not in ROLE_PRIORITY)

    return dikenal + sisa


def slot_costs(rule: dict) -> list[tuple[int, int]]:
    """
    Biaya tiap slot, dipisah jadi (sisi jawaban, sisi prompt).

    Keduanya tinggal di context yang sama tapi tumbuh dengan alasan
    berbeda. Sisi jawaban adalah teks yang akan ditulis model. Sisi
    prompt adalah teks lama yang ikut dikirim sebagai contoh, untuk
    peran yang artinya harus dipertahankan.

    Menggabungkan keduanya jadi satu angka menyembunyikan giliran
    yang jawabannya ringan tapi promptnya berat - dan itulah yang
    terjadi pada 477 label menu, yang masing-masing membawa teks
    lamanya sendiri ke dalam prompt.
    """
    jumlah = rule["count"]

    jatah = list(rule.get("budgets") or [])
    seragam = rule.get("max_length_any") or rule.get("max_length") or 40

    while len(jatah) < jumlah:
        jatah.append(seragam)

    contoh = list(rule.get("samples") or [])

    return [
        (
            jatah[index] + JSON_OVERHEAD_PER_TEXT,
            (len(contoh[index]) if index < len(contoh) else 0)
            + PROMPT_OVERHEAD_PER_TEXT,
        )
        for index in range(jumlah)
    ]


def slice_rule(rule: dict, mulai: int, jumlah: int) -> dict:
    """
    Mengambil sepotong kebutuhan satu peran untuk satu giliran.

    offset ikut dibawa supaya hasilnya bisa dikembalikan ke urutan
    aslinya waktu semua giliran disatukan.
    """
    potongan = dict(rule)

    potongan["count"] = jumlah
    potongan["offset"] = mulai

    for kunci in ("samples", "budgets"):
        nilai = rule.get(kunci)

        if nilai:
            potongan[kunci] = list(nilai[mulai : mulai + jumlah])

    jatah = potongan.get("budgets")

    if jatah:
        # Batas panjang ikut menyempit ke potongan ini saja. Kalau
        # yang dikirim tetap batas seluruh kelompok, giliran yang
        # isinya slot-slot sempit akan diberi tahu batas milik slot
        # terlebar di halaman.
        potongan["max_length"] = min(jatah)
        potongan["max_length_any"] = max(jatah)

    return potongan


def plan_batches(
    spec: dict,
    answer_budget: int,
    prompt_budget: int,
) -> list[dict]:
    """
    Membagi kebutuhan jadi beberapa giliran yang masing-masing muat.

    Dua jatah, keduanya dalam karakter dan keduanya mengikat: berapa
    panjang jawaban yang masih aman diminta sekali kirim, dan berapa
    besar daftar permintaan boleh menambah promptnya. Giliran ditutup
    begitu salah satunya penuh.
    """
    answer_budget = max(200, answer_budget)
    prompt_budget = max(200, prompt_budget)

    batches: list[dict] = []
    berjalan: dict = {}
    jawab = 0
    tanya = 0

    def tutup() -> None:
        nonlocal berjalan, jawab, tanya

        if berjalan:
            batches.append(berjalan)

        berjalan = {}
        jawab = 0
        tanya = 0

    for role in role_order(spec):
        rule = spec[role]

        if rule["count"] < 1:
            continue

        if role in SINGLE_ROLES:
            # Jawabannya satu teks, sependek judul atau deskripsi.
            # Tidak pernah perlu dipecah, dan menaruhnya di giliran
            # pertama membuat bagian paling menentukan halaman
            # selesai lebih dulu.
            biaya = (
                rule.get("max_length_any") or rule["max_length"]
            ) + JSON_OVERHEAD_PER_TEXT

            if berjalan and jawab + biaya > answer_budget:
                tutup()

            berjalan[role] = slice_rule(rule, 0, rule["count"])
            jawab += biaya

            continue

        harga = slot_costs(rule)
        mulai = 0

        while mulai < rule["count"]:
            muat = 0
            tambah_jawab = 0
            tambah_tanya = 0

            while mulai + muat < rule["count"]:
                sisi_jawab, sisi_tanya = harga[mulai + muat]

                penuh = (
                    jawab + tambah_jawab + sisi_jawab > answer_budget
                    or tanya + tambah_tanya + sisi_tanya > prompt_budget
                )

                # Giliran yang masih kosong selalu mengambil minimal
                # satu teks, meskipun teks itu sendiri lebih besar
                # dari jatah. Tanpa syarat itu, satu slot raksasa
                # membuat pembagiannya berputar tanpa pernah maju.
                if penuh and (muat or berjalan):
                    break

                tambah_jawab += sisi_jawab
                tambah_tanya += sisi_tanya
                muat += 1

            if muat == 0:
                tutup()
                continue

            berjalan[role] = slice_rule(rule, mulai, muat)
            jawab += tambah_jawab
            tanya += tambah_tanya
            mulai += muat

            if jawab >= answer_budget or tanya >= prompt_budget:
                tutup()

    tutup()

    return batches


def answer_chars(spec: dict) -> int:
    """
    Panjang jawaban yang dibutuhkan satu spec, dalam karakter.

    Dijumlahkan dari jatah tiap slot, bukan dari jatah terlebar
    dikali jumlah slot. Cara kedua melebihkan jauh untuk kelompok
    yang isinya campur panjang-pendek, dan angka yang melebihkan
    membuat pembagian giliran dan perhitungan max_tokens memakai dua
    ukuran yang berbeda untuk hal yang sama.
    """
    return sum(
        sisi_jawab
        for rule in spec.values()
        for sisi_jawab, _ in slot_costs(rule)
    )


def merge_batch_content(hasil: list[dict], spec: dict) -> dict:
    """
    Menyatukan jawaban semua giliran kembali jadi satu isi halaman.

    Daftar disambung menurut urutan gilirannya, yang sama dengan
    urutan slot di dokumen. Peran bertekstunggal diambil dari
    giliran pertama yang mengisinya.
    """
    gabung: dict = {}
    peta_lama: dict = {}

    for bagian in hasil:
        if not bagian:
            continue

        for role, nilai in bagian.items():
            if role == "_by_old":
                for peran, pasangan in (nilai or {}).items():
                    peta_lama.setdefault(peran, {}).update(pasangan)

                continue

            if role.startswith("_"):
                continue

            if isinstance(nilai, list):
                gabung.setdefault(role, []).extend(nilai)
            elif nilai and not gabung.get(role):
                gabung[role] = nilai

    if peta_lama:
        gabung["_by_old"] = peta_lama

    return gabung
