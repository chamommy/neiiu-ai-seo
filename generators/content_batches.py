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
    # Remah navigasi ikut giliran awal meski isinya cuma beberapa
    # kata. Ia menyatakan halaman ini berdiri di mana, dan kalau
    # prosesnya berhenti di tengah, remah yang belum terisi terbit
    # menunjuk topik - bahkan situs - milik pemilik template.
    "breadcrumb",
    # Isi halaman didahulukan atas perkakas situsnya. Kalau prosesnya
    # berhenti di tengah, yang sudah jadi harus artikel dan ulasannya,
    # bukan label menunya.
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "review_author",
    # Keduanya menerangkan teks yang ditulis di atasnya, jadi
    # gilirannya berdiri sesudah giliran yang menulis teks itu.
    "review_tag",
    "card_title",
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

# Berapa banyak teks yang boleh diminta dalam satu giliran.
#
# Jatah karakter saja tidak cukup menjaga giliran tetap sanggup
# dijawab. Label menu panjangnya 16 karakter, jadi 243 di antaranya
# masih muat di jatah 7000 karakter - dan giliran seperti itulah yang
# terukur gagal: model menutup daftarnya di teks ke-169, lalu dua kali
# diminta ulang tanpa menambah satu pun.
#
# Yang membuatnya berat bukan panjang jawabannya melainkan banyaknya
# butir yang harus dihitung model sampai tuntas. Giliran 86 butir di
# run yang sama selesai hampir penuh, giliran 243 butir tidak pernah.
# Batasnya dipasang di antara keduanya.
MAX_ITEMS_PER_BATCH = 80

# Peran yang daftarnya dipasangkan menurut nomor urut, jadi tidak
# boleh terbelah dua giliran. Jawaban FAQ ke-N adalah jawaban untuk
# pertanyaan ke-N, dan pasangan itu putus begitu daftarnya dipotong.
UNSPLIT_ROLES = ("faq_question", "faq_answer")


# Peran yang WAJIB ditulis di giliran terpisah, sesudah pasangannya.
#
# Ini perbaikan untuk cacat yang paling kelihatan di halaman jadi:
# "ditanya A dijawab B". Terukur pada halaman terbit - pertanyaan
# "Bagaimana proses deposit di TIMAH33?" dijawab "Proses login di
# TIMAH33 dilakukan secara otomatis melalui browser", sementara
# kalimat yang menjawabnya justru terpasang di kartu lain.
#
# Sebabnya bukan model yang bodoh, melainkan cara memintanya. Selama
# faq_question dan faq_answer muat di satu giliran, keduanya diminta
# dalam SATU objek JSON: model menulis tujuh pertanyaan berturut-turut,
# lalu tujuh jawaban berturut-turut, dan harus mengingat sendiri
# jawaban keempat itu milik pertanyaan yang mana. Model 4B tidak
# sanggup, dan urutannya melenceng di tengah daftar.
#
# Dipisah, soalnya hilang sama sekali. Pertanyaannya selesai lebih
# dulu, lalu giliran berikutnya menerima daftar bernomor lewat bagian
# "Pertanyaan Yang Harus Dijawab Berurutan" di prompt - jawaban ke-N
# ditulis sambil melihat pertanyaan ke-N.
#
# Harganya satu giliran tambahan. Awalan promptnya sama persis, jadi
# yang dibayar cuma jawabannya sendiri.
AFTER_ROLES = {
    "faq_answer": "faq_question",
    # Deskripsi ikut dengan alasan yang sama, dan gejalanya sama
    # kelihatannya: pengguna menemukan title dan meta description
    # berbunyi hal yang sama.
    #
    # Selama keduanya diminta dalam satu objek JSON, model menulis
    # title lalu langsung menulis deskripsi di baris berikutnya - dan
    # yang paling mungkin ditulis sesudah sebuah kalimat adalah
    # kalimat itu lagi, sedikit lebih panjang. Ditulis di giliran
    # terpisah, titlenya sudah jadi dan berdiri di bagian "Sudut
    # Pandang Halaman Ini", jadi deskripsinya ditulis sambil
    # melihatnya - dan bisa diperintahkan untuk TIDAK mengulangnya.
    "meta_description": "title",
    # Tag ulasan dan judul kartu menerangkan teks milik peran lain.
    # Ditulis di giliran yang sama, keduanya cuma bisa menebak apa
    # yang sedang diterangkannya - dan yang keluar adalah tag yang
    # setopik halaman tapi tidak menandai ulasan di atasnya.
    "review_tag": "review_text",
    "card_title": "paragraph",
}


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

    for kunci in ("samples", "budgets", "floors", "partners"):
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
    butir = 0

    def tutup() -> None:
        nonlocal berjalan, jawab, tanya, butir

        if berjalan:
            batches.append(berjalan)

        berjalan = {}
        jawab = 0
        tanya = 0
        butir = 0

    for role in role_order(spec):
        rule = spec[role]

        if rule["count"] < 1:
            continue

        # Peran berpasangan selalu MEMULAI giliran baru, tidak pernah
        # menumpang di ekor giliran orang lain.
        #
        # Terukur, dan ini penyebab pertanyaan FAQ yang terbit kosong:
        # satu giliran berisi 3 heading, 15 paragraf, lalu 7
        # pertanyaan di ekornya. Paragrafnya panjang-panjang, model
        # kehabisan napas sebelum sampai ke daftar terakhir, dan yang
        # kembali cuma 5 dari 7 pertanyaan. Diminta ulang dua kali,
        # tetap 5 - karena permintaan ulangnya menumpang di ekor yang
        # sama.
        #
        # Sendirian di gilirannya, daftar itu yang pertama ditulis
        # model, bukan yang terakhir.
        if role in UNSPLIT_ROLES and berjalan:
            tutup()

        # Peran yang harus melihat jawaban peran lain ditutup dulu
        # gilirannya, supaya pasangannya sudah selesai ditulis waktu
        # gilirannya sendiri berangkat.
        #
        # Diperiksa di ATAS cabang SINGLE_ROLES, bukan di bawahnya.
        # Title dan meta_description dua-duanya peran bertekstunggal,
        # dan pemeriksaan yang berdiri di bawah cabang itu tidak
        # pernah dijalankan untuk keduanya.
        pasangan = AFTER_ROLES.get(role)

        if pasangan and pasangan in berjalan:
            tutup()

        if role in SINGLE_ROLES:
            # Jawabannya satu teks, sependek judul atau deskripsi.
            # Tidak pernah perlu dipecah, dan menaruhnya di giliran
            # pertama membuat bagian paling menentukan halaman
            # selesai lebih dulu.
            biaya = (
                rule.get("max_length_any") or rule["max_length"]
            ) + JSON_OVERHEAD_PER_TEXT

            if berjalan and (
                jawab + biaya > answer_budget
                or butir + rule["count"] > MAX_ITEMS_PER_BATCH
            ):
                tutup()

            berjalan[role] = slice_rule(rule, 0, rule["count"])
            jawab += biaya
            butir += rule["count"]

            continue

        # Judul dan deskripsi diselesaikan sendirian di giliran
        # pertama, sebelum satu paragraf pun ditulis.
        #
        # Keduanya yang menentukan sudut pandang seluruh halaman, dan
        # sudut pandang itu baru bisa diikuti kalau sudah ada. Selama
        # judul dan paragraf ditulis dalam satu permintaan yang sama,
        # 27 paragraf, 7 heading, dan 3 pertanyaan FAQ di giliran
        # pertama disusun tanpa pernah melihat judul yang jadi -
        # masing-masing memilih sudutnya sendiri, dan halaman terbit
        # sebagai kumpulan tulisan yang kebetulan setopik.
        #
        # Sesudah dipisah, tiap giliran berikutnya menerima judul dan
        # deskripsi yang sudah jadi lewat bagian "Sudut Pandang
        # Halaman Ini", termasuk giliran yang menulis paragraf.
        if berjalan and all(
            nama in SINGLE_ROLES for nama in berjalan
        ):
            tutup()

        harga = slot_costs(rule)

        # Peran berpasangan tidak boleh terbelah dua giliran.
        #
        # Jawaban FAQ dipasangkan ke pertanyaannya menurut nomor urut,
        # dan pasangan itu putus begitu daftarnya dipotong di tengah.
        # Terukur di halaman jadi: enam jawaban terakhir jatuh di
        # giliran yang menerima daftar pertanyaannya, dan keenamnya
        # menjawab dengan tepat; satu jawaban yang tertinggal di
        # giliran sebelumnya ditulis berbarengan dengan 41 teks lain -
        # pertanyaannya "Cara daftar akun di ASOKASLOT?", jawabannya
        # tentang enkripsi dan verifikasi dua langkah.
        #
        # Kalau tidak muat di sisa jatah, gilirannya ditutup dulu,
        # bukan daftarnya yang dipotong.
        if role in UNSPLIT_ROLES and berjalan:
            butuh_jawab = sum(sisi for sisi, _ in harga)
            butuh_tanya = sum(sisi for _, sisi in harga)

            if (
                jawab + butuh_jawab > answer_budget
                or tanya + butuh_tanya > prompt_budget
                or butir + rule["count"] > MAX_ITEMS_PER_BATCH
            ):
                tutup()

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
                    or butir + muat >= MAX_ITEMS_PER_BATCH
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
            butir += muat
            mulai += muat

            if (
                jawab >= answer_budget
                or tanya >= prompt_budget
                or butir >= MAX_ITEMS_PER_BATCH
            ):
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
