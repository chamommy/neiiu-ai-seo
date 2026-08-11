"""
Panjang artikel: memperlebar jatah paragraf yang sudah ada.

Halaman ini SUDAH punya artikel, di tempat yang disediakan
templatenya. Yang diatur di sini bukan berapa paragraf yang ada,
melainkan seberapa panjang masing-masing paragraf itu ditulis.

Kolom "Panjang artikel (kata)" karena itu tidak pernah menambah satu
paragraf pun. Ia menaikkan jatah karakter tiap slot paragraf yang
memang sudah berdiri di template, dan model menulis lebih panjang di
tempat yang sama. Jumlah paragraf di halaman terbit persis sama
dengan jumlah paragraf di template unggahan - sebelum dan sesudah
target dinaikkan.

Dua cara yang sudah dicoba dan ditolak pengguna, dicatat supaya tidak
diulang orang ketiga:

1. Satu <section> utuh ditempel sebelum </main>, lengkap dengan judul
   dan gayanya sendiri. Halaman terbit dengan DUA artikel berjejer:
   "artikelnya 1 aja, di tempat biasa itu."
2. Lanjutan berupa <h2> dan <p> polos disisipkan ke dalam blok
   artikel yang sama, sebelum judul FAQ. Tetap salah, karena tetap
   menambah paragraf: "bukan menambah paragraf baru tetapi
   memperpanjang isi paragraf yang sudah ada."

Yang berlaku sekarang cara ketiga, dan tidak ada satu byte pun yang
disisipkan ke HTML template.
"""

from ai.neiiu_prompts import article_chars_per_word
from generators.template_slots import MAX_LENGTH_BUDGET, length_floor


# Peran yang jatahnya boleh dilebarkan.
#
# "paragraph" adalah peran yang dipakai slot artikel di template
# sungguhan; article_paragraph cuma muncul di template yang blok
# artikelnya sudah ditandai khusus. Keduanya ikut supaya kolom
# panjangnya bekerja di dua-duanya.
STRETCH_ROLES = ("article_paragraph", "paragraph")


# Panjang teks lama paling pendek yang masih boleh dilebarkan.
#
# Ini pengaman tata letak, dan angkanya bukan tebakan. Di template
# yang dipakai menguji, lima belas slot berperan "paragraph" punya
# jatah 542, 473, 299, 298, 278, 209, 202, 172, 157, 155, 153, 152,
# 124, 120, dan 79 karakter. Yang di atas dua ratus itu paragraf
# artikel sungguhan - dilebarkan, ia cuma memanjang ke bawah. Yang di
# bawahnya keterangan kartu fitur yang berdiri di kolom sempit, dan
# kartu berisi 79 karakter yang dipaksa memuat 300 akan mendorong
# kartu di sebelahnya keluar dari barisnya.
#
# Jadi yang dilebarkan hanya slot yang teks lamanya memang sudah
# berupa paragraf. Sisanya dibiarkan persis seperti sebelumnya.
MIN_STRETCH_BUDGET = 200


# Sejauh mana satu slot boleh melar dari jatah aslinya.
#
# Tanpa batas ini, target 3.000 kata di template yang muat 400
# membuat tiap paragraf diminta tujuh setengah kali lipat - dan
# paragraf 4.000 karakter bukan paragraf lagi, melainkan satu blok
# teks yang tidak dibaca siapa pun. Tiga kali lipat masih terbaca
# sebagai paragraf yang panjang.
MAX_STRETCH = 3.0


# Sepanjang apa satu slot boleh jadi, dalam karakter.
#
# Batas kedua di samping MAX_STRETCH, dan dua-duanya perlu: yang satu
# menjaga perbandingan, yang ini menjaga angka mutlaknya. Slot yang
# jatah aslinya 542 karakter melar jadi 1626 kalau cuma dibatasi tiga
# kali lipat, dan itu bukan paragraf lagi melainkan satu blok teks
# yang tidak dibaca siapa pun.
#
# Angkanya disamakan dengan MAX_LENGTH_BUDGET, yang sudah jadi
# pengertian "selebar-lebarnya satu teks" di seluruh proyek ini.
#
# Ada alasan teknis yang menguatkannya juga: jatah yang lebih besar
# dari ini, dikali kelonggaran grammar, menabrak batas yang bisa
# diproses llama.cpp - dan hasilnya bukan teks yang kepanjangan
# melainkan run yang batal dengan "failed to parse grammar". Terukur
# satu kali di sini, dan yang hangus belasan menit.
MAX_SLOT_BUDGET = MAX_LENGTH_BUDGET


def stretch_plan(spec: dict, target_words: int = 0) -> dict:
    """
    Berapa jatah baru tiap slot paragraf, untuk mengejar target kata.

    Yang dikembalikan peta peran ke daftar jatah baru, siap dipasang
    ke spec. Kosong berarti tidak ada yang berubah - dan itu keadaan
    normalnya, karena kolom targetnya memang boleh dikosongkan.

    Pelebarannya SEBANDING, bukan rata. Paragraf pembuka yang
    jatahnya 542 karakter dan keterangan yang jatahnya 298 punya
    peran berbeda di halaman, dan menyamakan keduanya jadi 400
    menghapus irama yang sudah ada di templatenya. Dikali faktor yang
    sama, selisihnya tetap.
    """
    if target_words <= 0 or not spec:
        return {}

    per_kata = article_chars_per_word() or 1.0
    target_chars = target_words * per_kata

    # Yang dihitung hanya slot yang memang boleh dilebarkan. Slot
    # pendek tetap menyumbang panjang ke halaman, tapi bukan ke
    # perhitungan ini - kalau ikut, target 800 kata terpenuhi di atas
    # kertas oleh empat puluh kartu fitur, dan paragraf artikelnya
    # tidak bertambah satu kata pun.
    sekarang = 0

    for role in STRETCH_ROLES:
        for jatah in role_budgets(spec, role):
            if jatah >= MIN_STRETCH_BUDGET:
                sekarang += jatah

    if sekarang <= 0 or target_chars <= sekarang:
        return {}

    faktor = min(MAX_STRETCH, target_chars / sekarang)

    rencana: dict[str, list[int]] = {}

    for role in STRETCH_ROLES:
        jatah = role_budgets(spec, role)

        if not jatah:
            continue

        baru = [
            min(MAX_SLOT_BUDGET, int(nilai * faktor))
            if nilai >= MIN_STRETCH_BUDGET
            else nilai
            for nilai in jatah
        ]

        if baru != jatah:
            rencana[role] = baru

    return rencana


def role_budgets(spec: dict, role: str) -> list[int]:
    """
    Jatah tiap slot satu peran, urut dokumen.

    Peran yang jatahnya tidak dirinci per slot dibentangkan dulu jadi
    daftar sepanjang jumlah slotnya, supaya pemanggilnya tidak perlu
    tahu bedanya.
    """
    aturan = (spec or {}).get(role)

    if not aturan:
        return []

    jatah = list(aturan.get("budgets") or [])

    if jatah:
        return jatah

    seragam = aturan.get("max_length_any") or aturan.get("max_length") or 0

    return [int(seragam)] * int(aturan.get("count", 0))


def stretch_spec(spec: dict, target_words: int = 0) -> int:
    """
    Memasang jatah baru ke spec, di tempat.

    Mengembalikan berapa slot yang jadi lebih panjang, supaya
    pemanggilnya bisa mencatatnya ke log job. Nol berarti tidak ada
    yang berubah, dan itu jawaban yang benar untuk target kosong.
    """
    rencana = stretch_plan(spec, target_words)

    if not rencana:
        return 0

    berubah = 0

    for role, jatah in rencana.items():
        aturan = spec[role]

        lama = role_budgets(spec, role)

        aturan["budgets"] = jatah
        aturan["max_length"] = min(jatah)
        aturan["max_length_any"] = max(jatah)

        # Lantai dihitung ULANG dari jatah yang baru, bukan dibiarkan
        # memakai angka lama.
        #
        # Kalau tidak, seluruh gunanya melebarkan jatah hilang di
        # kalimat terakhir prompt: slot yang jatahnya naik 542 jadi
        # 1626 tetap membawa lantai 298, dan yang sampai ke model
        # adalah "tulis antara 298 dan 1626 karakter" - rentang yang
        # begitu longgar sehingga model memilih ujung bawahnya, persis
        # panjang yang sama dengan sebelum targetnya dinaikkan.
        batas = [length_floor(role, nilai) for nilai in jatah]

        if any(batas):
            aturan["floors"] = batas
        else:
            aturan.pop("floors", None)

        berubah += sum(
            1
            for sebelum, sesudah in zip(lama, jatah)
            if sesudah > sebelum
        )

    return berubah


def reachable_words(spec: dict, target_words: int = 0) -> int:
    """
    Berapa kata yang sebenarnya bisa dicapai dengan melebarkan slot.

    Dipakai untuk melaporkan apa adanya kalau targetnya di luar
    jangkauan. Satu template yang cuma punya tujuh slot paragraf tidak
    bisa memuat 1.500 kata tanpa menambah paragraf, dan menambah
    paragraf justru yang tidak boleh dilakukan - jadi yang benar
    adalah mengatakan sampai berapa yang tercapai, bukan diam-diam
    berhenti di situ.

    Dihitung dari rencana yang benar-benar akan dipakai, bukan dari
    rumus. Dua batas berbeda bisa menahannya - perbandingan tiga kali
    lipat dan plafon mutlak satu slot - dan mana yang lebih dulu kena
    berbeda dari template ke template.
    """
    if target_words <= 0:
        return 0

    rencana = stretch_plan(spec, target_words)

    if not rencana:
        return min(target_words, template_article_words(spec))

    per_kata = article_chars_per_word() or 1.0

    total = sum(
        nilai
        for role in STRETCH_ROLES
        for nilai in (rencana.get(role) or role_budgets(spec, role))
        if nilai >= MIN_STRETCH_BUDGET
    )

    return min(target_words, int(total / per_kata))


def template_article_words(spec: dict) -> int:
    """
    Berapa kata yang muat di slot artikel milik template sekarang.

    Dihitung dari jatah slot, bukan dari teks lamanya: yang menentukan
    berapa panjang artikel yang BISA terbit adalah ruang yang
    disediakan untuk teks baru, dan jatah itu sudah memuat toleransi
    terhadap teks aslinya.

    Dipakai untuk melaporkan ke pengguna, bukan untuk menghitung
    kekurangan - tidak ada lagi yang namanya kekurangan sejak
    panjangnya dikejar dengan melebarkan slot yang sama.
    """
    total = 0

    for role in STRETCH_ROLES:
        for jatah in role_budgets(spec, role):
            if jatah >= MIN_STRETCH_BUDGET:
                total += jatah

    return int(total / (article_chars_per_word() or 1.0))
