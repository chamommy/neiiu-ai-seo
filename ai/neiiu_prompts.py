"""
Prompt untuk pipeline NEIIU: analisis SERP dan rencana konten.

Prompt di sini sengaja memadatkan data hasil crawl jadi angka dan
daftar pendek. Model lokal punya jendela konteks terbatas, jadi
memberi ringkasan terstruktur jauh lebih akurat daripada
menempelkan seluruh isi halaman kompetitor.
"""

import hashlib
import re
from itertools import zip_longest

from pathlib import Path

from ai.brief import PURPOSES, brief_identity_lines, brief_rule_blocks
from ai.language_rules import (
    VOICE_RULES_ID,
    style_examples_fit,
    voice_rules,
)
from ai.niche import capability_lines, faq_topic_rules
from ai.schemas import META_MAX, META_MIN, TITLE_MAX, TITLE_MIN
from generators.content_batches import DISTINCT_ROLES
from utils.spelling import CASUAL_WORDS
from utils.text import content_tokens


# Contoh gaya milik pengguna. Isinya bukan bahan untuk disalin
# melainkan penunjuk nada: panjang kalimat, cara membuka, cara
# menutup, dan sudut pandang yang dipakai.
#
# Dipisah dua berkas karena dua slot ini punya batas panjang yang
# jauh berbeda. Title dipatok TITLE_MAX karakter; contoh deskripsi
# milik pengguna panjangnya 119-279 karakter dengan median 181, jadi
# tidak satu pun bisa dipakai sebagai contoh title tanpa mengajari
# model menulis dua kali lebih panjang dari ruang yang ada.
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

STYLE_FILES = {
    "title": KNOWLEDGE_DIR / "gaya_title.txt",
    "meta_description": KNOWLEDGE_DIR / "gaya_title_deskripsi.txt",
}

# Contoh artikel utuh milik pengguna, disimpan apa adanya.
#
# Berkasnya tidak bisa dibaca seperti dua berkas di atas. Yang itu
# satu contoh per baris; yang ini artikel sungguhan - paragrafnya
# dipisah baris kosong, judulnya diawali "#", subjudulnya "##", dan
# nama brandnya ditebalkan dengan "**". Karena "#" di sini berarti
# judul, bukan keterangan, berkasnya punya pembaca sendiri.
ARTICLE_FILE = KNOWLEDGE_DIR / "gaya_artikel.txt"

# Paragraf yang jauh lebih panjang dari jatah mana pun tidak dipakai
# sebagai contoh. Model menulis sepanjang contohnya, dan yang
# kepanjangan akan dipotong - jadi contoh yang terlalu panjang justru
# mengajari model menulis untuk dibuang.
#
# Angkanya dulu 420, dipatok dari lebar slot template. Sejak artikel
# punya bloknya sendiri, jatah paragrafnya justru diambil dari berkas
# ini - paragraf terpanjangnya 456 karakter - jadi batas 420 membuang
# contoh yang panjangnya PERSIS panjang yang diminta.
MAX_ARTICLE_SAMPLE = 520

# Penebalan markdown dibuang saat contohnya dikirim, bukan dihapus
# dari berkasnya. Slot template diisi teks biasa, dan contoh yang
# masih memakai ** mengajari model menulis bintang ke dalam halaman.
BOLD_MARK = re.compile(r"\*\*+")

# Berapa contoh yang ikut ke prompt. Cukup untuk menunjukkan pola,
# tidak cukup untuk membuat model menyalin salah satunya.
STYLE_SAMPLE_SIZE = 8

# Seberapa besar kumpulan contoh harus tetap, supaya dua halaman
# berbeda tidak berangkat dari delapan contoh yang sama persis.
#
# Tiga kali jumlah yang diambil. Di bawah itu, benih keberagaman di
# pick_style_examples tidak punya bahan untuk memilih apa pun.
MIN_STYLE_POOL = STYLE_SAMPLE_SIZE * 3

# Contoh yang memuat klaim seperti ini tidak ikut dikirim ke model.
#
# Daftar ini pernah jauh lebih panjang. Ia ikut membuang "jaminan",
# "lisensi internasional", dan "akreditasi" dengan alasan bahwa
# pipeline tidak punya datanya. Pengguna menyatakan sebaliknya:
# brandnya memang berlisensi dan memang sanggup memenuhi yang
# dijanjikan, jadi menahan kata-kata itu menahan hal yang benar.
# Kredibilitas brand sekarang urusan SITE_LICENSE di config.py, dan
# aturan promptnya ada di BRAND_CONFIDENCE_RULES.
#
# Yang tersisa cuma dua macam, dan keduanya tetap ditahan:
#
#   1. Janji HASIL bagi pemainnya - "kemenangan pasti", "menang
#      terus". Ini bukan soal berani atau tidak berani; halaman yang
#      menjanjikan kemenangan judi ditolak sebagian besar platform
#      iklan, dan brand yang berlisensi justru yang paling rugi kalau
#      halamannya memuat itu.
#   2. ANGKA yang tidak dipunyai siapa pun di pipeline ini - winrate,
#      angka RTP, "up to 90%". Brand boleh berlisensi tanpa membuat
#      angka RTPnya jadi ada.
CLAIM_FILTER = re.compile(
    r"kemenangan pasti|pasti akurat|"
    r"pasti cuan|menang terus|jalan pintas jadi jutawan|"
    r"kekayaan secara cepat|"
    r"winrate|rtp .{0,12}\d{2}\s*%|\bup to \d{2}\s*%|"
    r"kemenangan maksimal|kemenangan tertinggi",
    re.IGNORECASE,
)


# Contoh yang memuat angka persen tidak ikut dikirim ke model, apa
# pun nilainya.
#
# Terpisah dari CLAIM_FILTER dan memang harus terpisah: yang di atas
# baru saja dilonggarkan supaya kalimat yang percaya diri bisa lewat,
# dan "Jaminan Bayar 100%" akan ikut lewat bersamanya. Persennya yang
# tidak boleh lewat, bukan jaminannya.
#
# Dua baris di knowledge/gaya_title.txt kena saringan ini. Berkasnya
# tidak disunting - isinya milik pengguna - tapi kedua baris itu
# tidak pernah sampai ke prompt.
PERCENT_FILTER = re.compile(r"\d\s*%")


# Contoh yang bunyinya seperti brosur perusahaan juga tidak dikirim.
#
# Ini keluhan pengguna: "kata-katanya terlalu AI banget". Sebabnya
# bukan modelnya mengarang sendiri - ia menyalin gaya yang kita
# berikan. Dua dari tiga artikel di berkas contoh ditulis dengan
# register ini:
#
#     "Di era digital, kecepatan transaksi menjadi salah satu faktor
#      utama yang dicari oleh pengguna platform hiburan online."
#     "Sistem ini dirancang agar tetap stabil dan dapat digunakan
#      selama 24 jam setiap hari."
#
# Kalimat seperti itu tidak salah, tapi tidak ada orang yang menulis
# begitu tentang situsnya sendiri. Yang dikenali pembaca sebagai
# "tulisan mesin" persisnya ini: subjek yang selalu benda ("sistem",
# "teknologi", "proses"), kata kerja pasif, dan penghubung yang
# menyambungkan tanpa mengatakan apa-apa.
#
# Artikel PERTAMA di berkas yang sama justru bunyinya manusia -
# "withdraw nggak pernah bikin deg-degan", "tanpa lag, tanpa ribet" -
# jadi bahannya sudah ada, cuma tenggelam di antara yang lain.
# Saringan ini yang memilih.
#
# Berkasnya sendiri tidak diubah. Kosongkan daftar ini kalau
# saringannya tidak dikehendaki.
ROBOT_FILTER = re.compile(
    r"di era digital|hal ini (membuat|menjadikan)|"
    r"dirancang (agar|untuk|sedemikian)|salah satu faktor|"
    r"salah satu keunggulan utama|aspek (penting|utama)|"
    r"teknologi yang digunakan|dengan memanfaatkan teknologi|"
    r"memungkinkan pengguna|sehingga pengguna dapat|"
    r"tanpa perlu intervensi|seluruh proses|"
    r"secara (otomatis|real-?time) sehingga|"
    r"mengutamakan (efisiensi|kemudahan)|"
    r"fleksibilitas ini|kemudahan ini|efisiensi|"
    # Ditambahkan supaya saringan ini sejalan dengan daftar larangan
    # di prompt. Aturan yang melarang sebuah bentuk lalu menyodorkan
    # contoh yang memakainya membuat larangan itu batal sendiri -
    # model meniru contohnya, bukan aturannya.
    r"memungkinkan kamu|data kinerja|sistem pengolahan data|"
    r"bukan sekadar|"
    r"tidak hanya[^.]{0,60}\b(tapi|tetapi)\b juga|"
    r"pengalaman bermain yang optimal|solusi cerdas",
    re.IGNORECASE,
)


# Kata sehari-hari yang membuat sebuah contoh tidak lagi pantas
# ditiru. Diambil dari daftar yang sama dengan penyapu ragam bahasa,
# jadi yang dilarang terbit dan yang dilarang jadi contoh selalu satu
# daftar - bukan dua yang lambat laun berbeda.
#
# Ini saringan TEGAS, tidak seperti ROBOT_FILTER yang dilepas kalau
# menyisakan terlalu sedikit. Sebabnya beda sifat: contoh berbunyi
# brosur cuma membuat tulisan membosankan, sedangkan contoh berbahasa
# gaul melanggar permintaan pengguna 21 Agustus 2026 secara langsung -
# "jangan menggunakan bahasa yang santai". Lebih baik kolam contohnya
# tipis daripada model diperlihatkan persis bentuk yang dilarang.
CASUAL_FILTER = re.compile(
    r"\b("
    + "|".join(
        sorted(
            (
                kata
                for kata in CASUAL_WORDS
                if len(kata) >= 3 and kata not in {"kalian"}
            ),
            key=len,
            reverse=True,
        )
    )
    + r")\b",
    re.IGNORECASE,
)

# Kalau saringan bunyi menyisakan contoh sesedikit ini, ia dilepas.
#
# Berkas contoh milik pengguna, dan isinya bisa saja seluruhnya
# ditulis dengan register itu. Menyaring habis berarti mengirim
# prompt tanpa satu contoh gaya pun, dan model tanpa contoh menulis
# lebih kaku lagi - kebalikan dari yang dimaksud. Jadi kalau yang
# tersisa kurang dari ini, contoh aslinya dipakai apa adanya dan
# aturan bunyi di prompt yang bekerja sendirian.
MIN_VOICE_POOL = 2


def load_article_examples() -> dict[str, list[str]]:
    """
    Membaca contoh artikel milik pengguna, dipisah per jenis.

    Blok dipisah baris kosong. Yang diawali "##" adalah subjudul,
    yang diawali "#" adalah judul artikel, sisanya paragraf.

    Judul artikel tidak ikut dipakai sebagai contoh title halaman.
    Judul artikel milik pengguna panjang dan memakai huruf besar
    semua - "LINK LOGIN [ BRAND ] SITUS SLOT77 ONLINE TERBESAR
    PALING GACOR HARI INI 2026" - sementara title halaman dipatok
    TITLE_MAX karakter. Meniru bentuk itu berarti menulis judul yang
    hilang separuhnya di hasil pencarian.
    """
    try:
        isi = ARTICLE_FILE.read_text(encoding="utf-8")
    except OSError:
        return {"paragraph": [], "heading": []}

    paragraf: list[str] = []
    subjudul: list[str] = []

    for blok in isi.split("\n\n"):
        teks = " ".join(BOLD_MARK.sub("", blok).split()).strip()

        if not teks:
            continue

        if teks.startswith("## "):
            subjudul.append(teks[3:].strip())
            continue

        if teks.startswith("#"):
            continue

        if len(teks) > MAX_ARTICLE_SAMPLE:
            continue

        if CLAIM_FILTER.search(teks):
            continue

        # Contoh berbahasa gaul tidak pernah dipakai - lihat
        # CASUAL_FILTER.
        if CASUAL_FILTER.search(teks):
            continue

        paragraf.append(teks)

    # Saringan bunyi dijalankan BELAKANGAN, bukan di dalam gelung.
    #
    # Ia perlu tahu berapa banyak yang tersisa sebelum memutuskan
    # jadi dipakai atau tidak, dan itu baru bisa dihitung setelah
    # seluruh berkas terbaca.
    manusiawi = [
        teks for teks in paragraf if not ROBOT_FILTER.search(teks)
    ]

    if len(manusiawi) >= MIN_VOICE_POOL:
        paragraf = manusiawi

    return {"paragraph": paragraf, "heading": subjudul}


# Bentuk cadangan kalau berkas contoh tidak terbaca. Angkanya
# disalin dari berkas yang ada sekarang, jadi hilangnya berkas itu
# mengubah gaya kalimatnya saja - bukan membuat artikelnya lenyap.
DEFAULT_ARTICLE_SHAPE = (
    {"paragraphs": (450, 300, 270), "subsections": ()},
    {
        "paragraphs": (400, 350, 240, 220, 210, 220),
        "subsections": (),
    },
    {
        "paragraphs": (450, 360),
        "subsections": (
            {"paragraphs": (320, 230)},
            {"paragraphs": (250, 170)},
        ),
    },
)

# Lantai jatah satu paragraf artikel.
#
# Contoh milik pengguna punya beberapa paragraf pendek di antara yang
# panjang, dan itu memang irama tulisannya - tapi jatah yang terlalu
# kecil membuat kalimat kedua terpotong, dan paragraf yang terpotong
# ditutup titik terbaca seolah utuh padahal tidak mengatakan apa pun.
MIN_ARTICLE_PARAGRAPH = 120

# Dipakai kalau berkas contoh tidak terbaca sama sekali. Sekitar
# panjang rata-rata kata bahasa Indonesia beserta spasinya.
DEFAULT_CHARS_PER_WORD = 7.0


def default_article_shape() -> list[dict]:
    """
    Salinan bentuk cadangan yang boleh diubah pemanggilnya.
    """
    return [
        {
            "paragraphs": list(bagian["paragraphs"]),
            "subsections": [
                {"paragraphs": list(sub["paragraphs"])}
                for sub in bagian["subsections"]
            ],
        }
        for bagian in DEFAULT_ARTICLE_SHAPE
    ]


def load_article_shape() -> list[dict]:
    """
    Membaca BENTUK artikel milik pengguna, bukan isinya.

    Yang diambil: berapa bagian, berapa paragraf di tiap bagian,
    berapa subbagian, dan sepanjang apa tiap paragrafnya. Teksnya
    sendiri tidak ikut - itu urusan load_article_examples, yang
    memakai berkas yang sama untuk keperluan yang berbeda.

    Dipisah dari pembacaan contoh gaya karena keduanya menjawab
    pertanyaan yang berbeda tentang berkas yang sama. Contoh gaya
    menjawab "kalimatnya berbunyi seperti apa"; bentuk menjawab
    "artikelnya disusun seperti apa". Yang pertama boleh menyaring
    dan mengacak; yang kedua tidak boleh, karena urutan dan
    jumlahnya justru isinya.

    Mengembalikan daftar bagian:
      [{"paragraphs": [451, 300, 269], "subsections": [...]}, ...]
    """
    try:
        isi = ARTICLE_FILE.read_text(encoding="utf-8")
    except OSError:
        return default_article_shape()

    bagian: list[dict] = []

    for blok in isi.split("\n\n"):
        teks = " ".join(BOLD_MARK.sub("", blok).split()).strip()

        if not teks:
            continue

        if teks.startswith("## "):
            if bagian:
                bagian[-1]["subsections"].append({"paragraphs": []})

            continue

        if teks.startswith("#"):
            bagian.append({"paragraphs": [], "subsections": []})
            continue

        if not bagian:
            # Paragraf yang berdiri sebelum judul pertama. Berkasnya
            # boleh saja ditulis begitu, dan membuangnya berarti
            # artikel yang terbit lebih pendek daripada contohnya.
            bagian.append({"paragraphs": [], "subsections": []})

        panjang = max(MIN_ARTICLE_PARAGRAPH, len(teks))

        if bagian[-1]["subsections"]:
            bagian[-1]["subsections"][-1]["paragraphs"].append(panjang)
        else:
            bagian[-1]["paragraphs"].append(panjang)

    # Bagian dan subbagian yang tidak punya paragraf dibuang. Judul
    # tanpa isi di bawahnya cuma menyuruh model menulis judul yang
    # tidak akan pernah terpakai.
    bersih: list[dict] = []

    for item in bagian:
        subs = [
            sub for sub in item["subsections"] if sub["paragraphs"]
        ]

        if not item["paragraphs"] and not subs:
            continue

        bersih.append(
            {"paragraphs": item["paragraphs"], "subsections": subs}
        )

    # Berkasnya ada tapi tidak memuat satu paragraf pun - misalnya
    # baru berisi judul. Bentuk cadangan dipakai supaya blok artikel
    # tetap terbit, bukan hilang tanpa pesan.
    return bersih or default_article_shape()


# Batas atas jumlah bagian, apa pun target kata yang diminta.
#
# Bukan soal selera melainkan yang terukur: model kecil menulis makin
# banyak kalimat berulang begitu diminta puluhan paragraf sekaligus,
# dan penyaring kembar membatalkannya - jadi artikel yang diminta
# terlalu panjang justru terbit lebih pendek daripada yang diminta
# sedang. Angkanya dipasang jauh di atas kebutuhan wajar supaya tidak
# pernah terasa, tapi tetap menahan salah ketik.
MAX_ARTICLE_SECTIONS = 40


def article_shape(target_words: int = 0) -> list[dict]:
    """
    Bentuk artikel, diskalakan ke target jumlah kata.

    Bentuk dasarnya dibaca dari contoh milik pengguna. Yang dilakukan
    di sini bukan mengarang bentuk baru melainkan MENGULANG bentuk
    itu sampai targetnya tercapai: bagian pertama contoh, lalu kedua,
    lalu ketiga, lalu kembali ke bagian pertama, dan seterusnya.

    Diulang, bukan dipanjangkan paragrafnya. Irama contohnya - dua
    paragraf pembuka yang panjang, beberapa yang pendek di tengah,
    subbagian di bagian terakhir - adalah bagian dari gaya yang mau
    ditiru, dan memelarkan tiap paragraf sampai targetnya tercapai
    justru menghapus irama itu.

    target_words 0 berarti pakai contohnya apa adanya.
    """
    dasar = load_article_shape()

    if not dasar or target_words <= 0:
        return dasar

    per_kata = article_chars_per_word() or DEFAULT_CHARS_PER_WORD

    hasil: list[dict] = []
    kata = 0.0

    while kata < target_words and len(hasil) < MAX_ARTICLE_SECTIONS:
        bagian = dasar[len(hasil) % len(dasar)]

        hasil.append(
            {
                "paragraphs": list(bagian["paragraphs"]),
                "subsections": [
                    {"paragraphs": list(sub["paragraphs"])}
                    for sub in bagian["subsections"]
                ],
            }
        )

        huruf = sum(bagian["paragraphs"]) + sum(
            sum(sub["paragraphs"]) for sub in bagian["subsections"]
        )

        kata += huruf / per_kata

    return hasil


def article_word_estimate(shape: list[dict]) -> int:
    """
    Perkiraan jumlah kata satu bentuk artikel.

    Perkiraan, bukan janji: jatah tiap paragraf adalah batas atas,
    dan model kadang menulis lebih pendek. Dipakai untuk melaporkan
    apa yang direncanakan, bukan untuk menagih hasilnya.
    """
    per_kata = article_chars_per_word() or DEFAULT_CHARS_PER_WORD

    huruf = sum(
        sum(bagian["paragraphs"])
        + sum(sum(sub["paragraphs"]) for sub in bagian["subsections"])
        for bagian in shape
    )

    return int(huruf / per_kata)


def article_chars_per_word() -> float:
    """
    Berapa karakter satu kata, diukur dari contoh milik pengguna.

    Dipakai menerjemahkan target "sekian kata" jadi jatah karakter,
    karena jatah tiap paragraf dihitung dalam karakter sementara
    orang memikirkan panjang artikel dalam kata.

    Diukur, bukan dipatok. Angkanya berbeda antar bahasa dan antar
    gaya tulisan, dan berkas contohnya ditulis pengguna sendiri
    dalam bahasa yang dipakai halamannya.
    """
    try:
        isi = ARTICLE_FILE.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_CHARS_PER_WORD

    huruf = 0
    kata = 0

    for blok in isi.split("\n\n"):
        teks = " ".join(BOLD_MARK.sub("", blok).split()).strip()

        if not teks or teks.startswith("#"):
            continue

        huruf += len(teks)
        kata += len(teks.split())

    if not kata:
        return DEFAULT_CHARS_PER_WORD

    return huruf / kata


# Tanda bahwa sebuah contoh berhenti di tempat yang memang akhir.
SENTENCE_END = ".!?…"


def drop_cut_fragments(contoh: list[str]) -> list[str]:
    """
    Membuang contoh title yang sebenarnya potongan kalimat.

    Berkas contoh title tidak pernah ditulis pengguna sebagai daftar
    title. Ia DITURUNKAN dari berkas contoh deskripsi dengan cara
    memotong kalimat pembukanya di sekitar 60 huruf - keterangan itu
    tertulis di kepala berkasnya sendiri, dan bisa dibuktikan:
    seluruh 116 barisnya adalah awalan persis dari sebuah baris di
    gaya_title_deskripsi.txt.

    Sebagian potongan itu kebetulan jatuh tepat di akhir kalimat dan
    tetap berbunyi utuh. Sisanya berhenti di tengah -

        [ BRAND ] adalah pilihan tepat untuk menemukan titik
        Mainkan berbagai jenis slot online gratis dalam satu
        Raih Kemenangan Maxwin di [ BRAND ] sekarang bersama sang

    - dan yang seperti itu 75 dari 84 contoh yang lolos saringan
    panjang. Jadi hampir seluruh contoh yang dilihat model adalah
    kalimat yang berhenti sebelum selesai, dan model menulis
    sepanjang DAN seperti contohnya. Itu sebabnya title yang terbit
    datar dan menggantung: "WAYANGPLAY slot gacor – Pengalaman
    bermain terbaik", berhenti persis di lantai 50 huruf.

    Yang dibuang cuma yang TERBUKTI potongan: awalan dari sebuah
    baris deskripsi yang tidak berhenti di tanda titik. Title tulisan
    tangan yang memang tidak berakhiran tanda baca - dan itu bentuk
    title yang lazim - tidak akan pernah cocok dengan syarat pertama,
    jadi tidak ikut terbuang.

    Kalau yang tersisa terlalu sedikit untuk jadi contoh, daftarnya
    dikembalikan apa adanya: contoh yang kurang bagus masih lebih
    berguna daripada tidak ada contoh sama sekali.
    """
    try:
        sumber = [
            teks
            for teks in (
                item.strip()
                for item in STYLE_FILES["meta_description"]
                .read_text(encoding="utf-8")
                .splitlines()
            )
            if teks and not teks.startswith("#")
        ]
    except OSError:
        return contoh

    if not sumber:
        return contoh

    utuh = [
        teks
        for teks in contoh
        if teks.rstrip()[-1:] in SENTENCE_END
        or not any(
            baris.startswith(teks) and len(baris) > len(teks)
            for baris in sumber
        )
    ]

    return utuh if len(utuh) >= STYLE_SAMPLE_SIZE else contoh


def load_style_examples(slot: str = "meta_description") -> list[str]:
    """
    Membaca contoh gaya milik pengguna, tanpa baris keterangan.

    Berkas yang belum ada dianggap kosong, bukan kesalahan. Contoh
    gaya itu tambahan; tanpa berkasnya pipeline tetap jalan dengan
    aturan tertulis saja.
    """
    if slot in ("paragraph", "heading"):
        return load_article_examples().get(slot, [])

    berkas = STYLE_FILES.get(slot)

    if not berkas:
        return []

    try:
        baris = berkas.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    bersih = [
        teks
        for teks in (item.strip() for item in baris)
        if teks
        and not teks.startswith("#")
        and not CLAIM_FILTER.search(teks)
        and not PERCENT_FILTER.search(teks)
    ]

    if slot == "title":
        bersih = drop_cut_fragments(bersih)

    # Contoh disaring ke rentang panjang yang diminta.
    #
    # Model menulis sepanjang contohnya, jadi contoh di luar rentang
    # mengajari model menulis panjang yang akan ditolak. Berkas
    # pengguna memuat ketiga-tiganya sekaligus:
    #
    # Diukur 13 Agustus 2026, sesudah rentang deskripsi turun dari
    # 160-200 ke 140-180 dan sesudah PERCENT_FILTER dipasang. Yang
    # dihitung adalah baris yang sudah lolos kedua saringan:
    #
    #                     di bawah   di dalam   di atas   total
    #   title (50-70)            2         49        65     116
    #   deskripsi (140-180)      4         40        58     102
    #
    # Tabel di sini pernah berbunyi "title 31/85/0" - itu peninggalan
    # waktu rentang title masih 65-80, dan totalnya kebetulan sama
    # sehingga tidak kelihatan basi. Kalau rentangnya diubah lagi,
    # ukur ulang; jangan menyalin angka lama.
    #
    # Yang tersisa di kedua berkas masih lima kali lebih banyak
    # daripada yang dikirim per run (STYLE_SAMPLE_SIZE = 8), jadi
    # tidak ada keberagaman yang hilang.
    #
    # Title sempat tidak disaring, dan alasannya berlaku waktu itu:
    # lantainya 65, sedangkan contoh terpanjang milik pengguna 61
    # karakter, jadi menyaringnya berarti mengirim daftar kosong.
    # Sejak lantainya turun ke 50, sebagian besar contohnya justru
    # masuk - dan saringan yang cukup punya jalan mundur di bawah ini
    # tidak pernah bisa mengosongkan daftarnya.
    batas = {
        "title": (TITLE_MIN, TITLE_MAX),
        "meta_description": (META_MIN, META_MAX),
    }.get(slot)

    if batas:
        pas = [teks for teks in bersih if batas[0] <= len(teks) <= batas[1]]

        # Yang di dalam rentang selalu didahulukan, lalu ditambah yang
        # PALING DEKAT ke rentangnya sampai jumlahnya cukup beragam.
        #
        # Ini menutup kerugian yang muncul sesudah contoh potongan
        # dibuang. Contoh title yang utuh DAN masih di rentang 50-70
        # tinggal sembilan, sementara satu run mengambil delapan -
        # jadi tiap halaman berangkat dari contoh yang hampir sama,
        # dan seluruh halaman yang dibuat alat ini terbaca seperti
        # ditulis dari satu cetakan. Itu justru cacat yang benih
        # keberagaman di pick_style_examples ada untuk mencegahnya.
        #
        # Menambah dari luar rentang aman di sini: yang benar-benar
        # menegakkan panjang bukan contohnya melainkan minLength di
        # JSON Schema. Contohnya cuma mengajarkan nada.
        if len(pas) < MIN_STYLE_POOL:
            sisa = sorted(
                (teks for teks in bersih if teks not in pas),
                key=lambda teks: min(
                    abs(len(teks) - batas[0]),
                    abs(len(teks) - batas[1]),
                ),
            )

            pas = pas + sisa[: MIN_STYLE_POOL - len(pas)]

        if len(pas) >= STYLE_SAMPLE_SIZE:
            return pas

    return bersih


def pick_style_examples(
    keyword: str,
    brand_name: str,
    jumlah: int = STYLE_SAMPLE_SIZE,
    slot: str = "meta_description",
    variation: str = "",
) -> list[str]:
    """
    Memilih beberapa contoh gaya, tetap sama sepanjang satu run.

    Titik awalnya diturunkan, bukan diacak, dan itu mengikat: awalan
    prompt harus identik di setiap giliran supaya cache prompt Ollama
    tidak batal.

    Tiga bahan masuk ke benihnya, masing-masing menjawab soal yang
    berbeda:

    - keyword dan brand, supaya dua halaman brand berbeda tidak
      berangkat dari contoh yang sama persis - kalau iya, seluruh
      halaman yang dihasilkan alat ini terbaca seperti ditulis dari
      satu cetakan.
    - slot, supaya contoh title dan contoh deskripsi tidak jatuh di
      posisi yang sama di berkas masing-masing.
    - variation, penanda run dari build_brand. Ini yang membuat
      halaman kedua dari template dan keyword yang SAMA tidak
      berangkat dari delapan contoh yang sama seperti halaman
      pertama. Tanpa itu, satu-satunya sumber perbedaan tinggal suhu
      model, dan model yang membaca contoh yang persis sama cenderung
      kembali ke kalimat yang sama.
    """
    contoh = load_style_examples(slot)

    if not contoh:
        return []

    # Slot ikut ke dalam benih supaya contoh title dan contoh
    # deskripsi tidak jatuh di posisi yang sama di berkas
    # masing-masing.
    benih = hashlib.sha1(
        f"{keyword}|{brand_name}|{slot}|{variation}".encode("utf-8")
    ).digest()

    mulai = int.from_bytes(benih[:4], "big") % len(contoh)

    # Langkah dibuat besar dan ganjil supaya contohnya tersebar ke
    # seluruh berkas, bukan delapan baris berurutan. Baris yang
    # bertetangga di berkas biasanya ditulis dalam satu sesi dan
    # sudut pandangnya mirip - persis yang tidak berguna sebagai
    # contoh keberagaman gaya.
    langkah = (int.from_bytes(benih[4:8], "big") % 23) * 2 + 3

    dipilih: list[str] = []
    dilihat: set[int] = set()

    for putaran in range(min(jumlah, len(contoh))):
        index = (mulai + putaran * langkah) % len(contoh)

        while index in dilihat:
            index = (index + 1) % len(contoh)

        dilihat.add(index)
        dipilih.append(contoh[index])

    return dipilih


def format_style_examples(
    keyword: str,
    brand_name: str,
    variation: str = "",
    language_code: str = "id",
    niche: str = "gambling",
) -> str:
    """
    Bagian prompt berisi contoh gaya, siap ditempel ke brief.

    Contoh title dan contoh deskripsi ditulis di bawah keterangan
    yang berbeda. Digabung jadi satu daftar, model membaca contoh
    deskripsi 181 karakter sebagai contoh title juga, lalu menulis
    title yang dipotong di batasnya - potongan yang justru membuang
    ajakan di akhir kalimatnya.

    Contohnya tidak dikirim sama sekali kalau halaman ditulis dalam
    bahasa yang bukan bahasa berkas contoh, ATAU di bidang yang bukan
    bidang berkas contoh.

    Berkas contoh (knowledge/gaya_title.txt dan
    gaya_title_deskripsi.txt) seluruhnya bahasa Indonesia, dan
    keterangan di atasnya berbunyi "yang diambil dari sini CUMA
    BENTUKNYA: cara membuka, cara menyebut nama situs, ajakan di
    akhirnya". Untuk halaman Thai, perintah itu berarti: susunlah
    kalimat Thai mengikuti susunan kalimat Indonesia - yang persis
    definisi kalimat hasil terjemahan, dan persis yang dikeluhkan
    tentang halaman zona Thailand.

    Alasan bidang persis sama bentuknya. Ketiga berkas berisi contoh
    tentang situs slot, dan delapan baris "Situs Resmi Slot Gacor
    No.1" yang berdiri di prompt halaman kursus mengajari model
    susunan kalimatnya SEKALIGUS kosakatanya. Yang kedua tidak
    diminta siapa pun, dan model kecil tidak memisahkan keduanya.

    Yang tetap bekerja untuk zona dan bidang lain: bentuk title
    ditegakkan enforce_title_shape, rentang panjangnya ditegakkan
    minLength, dan bank kata dari SERP berisi title yang benar-benar
    sedang ngerank untuk keyword ITU - contoh yang justru lebih tepat
    daripada berkas milik bidang lain.
    """
    if not style_examples_fit(language_code, niche):
        return ""

    nama = brand_name or "situs ini"

    bagian: list[str] = []

    judul_contoh = pick_style_examples(
        keyword,
        brand_name,
        slot="title",
        variation=variation,
    )

    if judul_contoh:
        bagian.append(
            "Contoh title milik situs ini, semuanya sudah di rentang "
            f"{TITLE_MIN}-{TITLE_MAX} karakter yang diminta.\n"
            "Yang diambil dari sini CUMA BENTUKNYA: cara membuka, cara "
            "menyebut nama situs, ajakan di akhirnya, dan berhenti di "
            "titik yang sama.\n"
            "KATANYA JANGAN DIAMBIL. Menulis ulang salah satu baris di "
            "bawah - seluruhnya maupun separuhnya, dengan nama situs "
            "ditukar atau satu dua kata diganti - dihitung tidak "
            "menjawab, dan judulnya akan diminta ulang. Ini bukan "
            "daftar pilihan; ini contoh bentuk. Yang kamu tulis harus "
            f"tentang \"{keyword}\" dengan katamu sendiri:\n"
            + "\n".join(
                f"  - {teks.replace('[ BRAND ]', nama)}"
                for teks in judul_contoh
            )
        )

    deskripsi_contoh = pick_style_examples(
        keyword,
        brand_name,
        slot="meta_description",
        variation=variation,
    )

    if deskripsi_contoh:
        bagian.append(
            (
                "Contoh meta description:"
                if judul_contoh
                else "Contohnya:"
            )
            + " berlaku aturan yang sama - bentuknya ditiru, katanya "
            "ditulis baru. Deskripsi yang menyalin salah satu baris di "
            "bawah juga akan diminta ulang.\n"
            + "\n".join(
                f"  - {teks.replace('[ BRAND ]', nama)}"
                for teks in deskripsi_contoh
            )
        )

    # Contoh paragraf dibatasi lebih sedikit daripada title dan
    # deskripsi. Paragraf panjangnya berlipat, dan delapan di antaranya
    # memakan ruang prompt yang dibutuhkan jawabannya sendiri.
    artikel_contoh = pick_style_examples(
        keyword,
        brand_name,
        jumlah=4,
        slot="paragraph",
        variation=variation,
    )

    if artikel_contoh:
        bagian.append(
            "Contoh paragraf artikel. Panjangnya di sini bukan "
            "patokan - yang mengikat tetap batas karakter tiap slot. "
            "Yang ditiru cara membuka kalimat, cara menyebut nama "
            "situs di tengah kalimat, dan cara menutup dengan manfaat "
            "yang bisa dibayangkan pembaca:\n"
            + "\n".join(
                f"  - {teks.replace('[ BRAND ]', nama)}"
                for teks in artikel_contoh
            )
        )

    judul_bagian = pick_style_examples(
        keyword,
        brand_name,
        jumlah=4,
        slot="heading",
        variation=variation,
    )

    if judul_bagian:
        bagian.append(
            "Contoh judul bagian di dalam artikel:\n"
            + "\n".join(
                f"  - {teks.replace('[ BRAND ]', nama)}"
                for teks in judul_bagian
            )
        )

    if not bagian:
        return ""

    return (
        "\n## Gaya Tulisan Yang Dipakai Situs Ini\n"
        "Ini contoh tulisan milik situs ini. JANGAN disalin dan "
        "jangan diikuti topiknya - yang ditiru cuma gayanya: panjang "
        "kalimatnya, cara membukanya, ajakan di akhirnya, dan "
        "keberanian memakai satu sudut pandang yang khas alih-alih "
        "kalimat serba umum.\n\n"
        + "\n\n".join(bagian)
        + "\n"
    )


SERP_ANALYST_SYSTEM_PROMPT = """
Kamu adalah analis SEO yang membaca data halaman pertama Google.

Aturan:
- Gunakan hanya data crawl yang diberikan.
- Jangan mengarang metrik, backlink, atau otoritas domain.
- Jelaskan alasan ranking dari bukti yang terlihat di data.
- Kalau data tidak cukup untuk satu posisi, katakan apa adanya.
- Jangan menjanjikan ranking.
- Gunakan bahasa Indonesia yang jelas dan padat.
- Berikan hanya hasil akhir, tanpa proses berpikir.
- Ikuti JSON Schema yang diberikan sistem.
""".strip()


# Instruksi bahasa ditulis dua kali: sekali dalam bahasa Indonesia
# supaya konsisten dengan aturan lain, sekali dalam bahasa
# sasarannya sendiri. Model kecil cenderung menjawab dalam bahasa
# yang dipakai promptnya, dan satu baris perintah di tengah prompt
# berbahasa Indonesia sering kalah oleh kecenderungan itu.
LANGUAGE_ORDERS = {
    "id": "Tulis seluruh isi halaman dalam bahasa Indonesia.",
    "th": (
        "Tulis SELURUH isi halaman dalam bahasa Thai, memakai aksara "
        "Thai. Jangan memakai bahasa Indonesia atau Inggris untuk "
        "judul, paragraf, FAQ, maupun bagian lain.\n"
        "เขียนเนื้อหาทั้งหมดเป็นภาษาไทยโดยใช้อักษรไทยเท่านั้น "
        "ห้ามใช้ภาษาอินโดนีเซียหรือภาษาอังกฤษ"
    ),
}


def content_planner_system_prompt(language_code: str = "id") -> str:
    """
    System prompt penyusun konten, dengan bahasa sasaran ditegaskan.
    """
    order = LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])

    return f"""
Kamu adalah content strategist SEO yang menyusun landing page baru.

Aturan:
- Tulis konten orisinal. Jangan menyalin kalimat kompetitor.
- Ikuti target struktur dan panjang yang diberikan.
- Masukkan keyword utama secara wajar, jangan menumpuk.
- Setiap paragraf harus berisi informasi konkret, bukan basa-basi.
- Heading harus deskriptif dan menjawab kebutuhan pencari.
- Jangan memakai placeholder seperti "lorem ipsum" atau "xxx".
- Jangan menjanjikan hasil, keuntungan, atau kemenangan.
- Berikan hanya hasil akhir, tanpa proses berpikir.
- Ikuti JSON Schema yang diberikan sistem.

BAHASA (paling penting):
{order}
""".strip()


def metadata_system_prompt(language_code: str = "id") -> str:
    """
    System prompt untuk permintaan yang cuma menulis judul dan deskripsi.

    Dipisah dari yang di atas bukan karena rapi melainkan karena isinya
    salah untuk tugas ini. Yang di atas menyebut "menyusun landing page
    baru", lalu memberi aturan paragraf dan heading - tiga hal yang
    tidak dikerjakan permintaan ini sama sekali, dan yang justru
    mengarahkan model kecil menulis seperti sedang mengisi halaman.

    Blok BAHASA tetap dibawa apa adanya. Ia satu-satunya bagian yang
    ditandai "paling penting" di prompt aslinya, dan alasannya tidak
    berubah: halaman Thai yang terbit berbahasa Indonesia adalah
    kerusakan yang tidak bisa ditambal belakangan.
    """
    order = LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])

    return f"""
Kamu penulis metadata SEO: judul halaman dan meta description.

Aturan:
- Tulis baru. Jangan menyalin kalimat yang diperlihatkan kepadamu.
- Jangan menjanjikan hasil, keuntungan, atau kemenangan.
- Jangan mengarang angka, persen, atau nomor lisensi.
- Berikan hanya hasil akhir, tanpa proses berpikir.
- Ikuti JSON Schema yang diberikan sistem.

BAHASA (paling penting):
{order}
""".strip()


def format_list(
    items: list,
    limit: int = 10,
    empty: str = "- Tidak ada",
) -> str:
    clean = [
        str(item).strip()
        for item in items
        if str(item).strip()
    ]

    if not clean:
        return empty

    return "\n".join(f"- {item}" for item in clean[:limit])


def blok_daftar(judul: str, items: list, limit: int = 10) -> str:
    """
    Bagian brief yang hilang seluruhnya kalau isinya kosong.

    format_list() menulis "- Tidak ada" untuk daftar kosong. Di bawah
    judul biasa itu tidak apa-apa, tapi di bawah judul yang berbunyi
    perintah - "Pertanyaan Yang Harus Dijawab Di FAQ", "Tema Yang
    Wajib Disinggung" - hasilnya perintah tanpa isi, dan model kecil
    cenderung mengarang sesuatu untuk mengisinya.

    Tiga daftar itu sekarang memang bisa kosong: sejak kosakata cuma
    boleh datang dari halaman bersih, keyword yang halaman pertamanya
    dibajak semua tidak menyisakan bahan apa pun. Brief yang tidak
    menyebut bagiannya sama sekali lebih jujur daripada brief yang
    menyebutnya lalu bilang tidak ada.
    """
    isi = format_list(items, limit=limit, empty="")

    if not isi:
        return ""

    return f"\n{judul}\n{isi}\n"


def format_must_cover(insight: dict, with_reason: bool = True) -> str:
    """
    Menuliskan topik wajib hasil membaca halaman pertama.

    Ini penghubung yang selama ini putus. Analisis SERP berhenti
    sebagai laporan - dibaca manusia di file markdown, lalu selesai -
    sementara tahap menulis cuma menerima angka target dan daftar
    kosakata. Halaman barunya jadi benar panjangnya dan benar
    kata-katanya, tapi bagian-bagiannya dipilih model dari
    pengetahuan umumnya sendiri, bukan dari apa yang terbukti
    dibahas halaman yang sedang menang.

    with_reason dimatikan untuk prompt per-batch, yang dikirim
    berkali-kali dalam satu run. Di sana yang dibutuhkan cuma daftar
    topiknya; alasannya sudah dipakai waktu menyusun rencana.
    """
    daftar = [
        item
        for item in (insight.get("must_cover") or [])
        if isinstance(item, dict) and str(item.get("topic") or "").strip()
    ]

    if not daftar:
        return ""

    baris: list[str] = []

    for item in daftar[:8]:
        topik = str(item["topic"]).strip()
        alasan = str(item.get("reason") or "").strip()

        if with_reason and alasan:
            baris.append(f"  - {topik} — {alasan}")
        else:
            baris.append(f"  - {topik}")

    return (
        "\nTopik yang wajib terbahas, hasil membaca halaman pertama:\n"
        + "\n".join(baris)
        + "\n"
    )


def format_page_digest(digest: dict) -> str:
    """
    Menuliskan isi halaman kompetitor, bukan cuma ukurannya.

    Tanpa bagian ini prompt insight meminta model menjelaskan kenapa
    sebuah halaman menang sambil hanya menyodorkan jumlah kata dan
    jumlah H2. Pertanyaannya tidak bisa dijawab dari bahan seperti
    itu, dan yang keluar selama ini memang bukan jawaban - cuma
    angka yang sama dibacakan ulang dalam bentuk kalimat.
    """
    if not digest:
        return ""

    baris: list[str] = []

    outline = digest.get("outline") or []

    if outline:
        baris.append("    Kerangka halaman:")

        for item in outline:
            level = item.get("level") or 2
            baris.append(
                f"      {'  ' * max(0, level - 2)}"
                f"H{level} {item.get('heading', '')}"
            )

    if not digest.get("deep"):
        # Peringkat bawah berhenti di kerangka. Dikatakan supaya
        # model tidak menyimpulkan halamannya tipis padahal yang
        # terjadi cuma kita tidak mengirimkan isinya.
        if outline:
            baris.append(
                "    (hanya kerangka yang dikirim untuk peringkat ini)"
            )

        return "\n".join(baris)

    lead = digest.get("lead") or ""

    if lead:
        baris.append(f"    Pembuka: {lead}")

    kunci = digest.get("key_paragraphs") or []

    if kunci:
        baris.append("    Isi yang membahas keyword:")
        baris.extend(f"      - {teks}" for teks in kunci)

    faq = digest.get("faq") or []

    if faq:
        baris.append("    Tanya-jawab yang mereka pasang:")

        for item in faq:
            baris.append(f"      T: {item.get('question', '')}")
            baris.append(f"      J: {item.get('answer', '')}")

    return "\n".join(baris)


def format_competitor_table(pages: list[dict]) -> str:
    """
    Membuat ringkasan satu baris per kompetitor.
    """
    lines: list[str] = []

    for page in pages:
        if page["status"] != "ok":
            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— gagal di-crawl ({page['error']})"
            )
            continue

        hijack = page.get("hijack", {})

        if not page.get("usable", True) and not hijack.get("is_hijacked"):
            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— ISI TIDAK TERBACA (hanya {page['word_count']} kata "
                "sampai ke crawler, konten yang diindeks Google tidak "
                "dilayani ke kita)"
            )
            continue

        if hijack.get("is_hijacked"):
            cloaking = page.get("cloak", {}).get("cloaking")

            lines.append(
                f"[{page['position']}] {page['domain']} "
                f"— DOMAIN BAJAKAN (keyakinan {hijack['confidence']}%)"
                + (", terbukti cloaking" if cloaking else "")
                + "\n    "
                + "; ".join(hijack.get("reasons", [])[:2])
            )
            continue

        signals = page["signals"]
        headings = page["headings"]

        blok = (
            f"[{page['position']}] {page['domain']}\n"
            f"    title ({page['title_length']} char): "
            f"{page['title'][:90]}\n"
            f"    kata: {page['word_count']} | "
            f"H2: {headings['h2_count']} | "
            f"H3: {headings['h3_count']} | "
            f"internal link: {page['links']['internal_count']} | "
            f"gambar: {page['images']['total']}\n"
            f"    density keyword: "
            f"{page['content']['keyword_density']}% | "
            f"keyword di title: "
            f"{page['content']['keyword_in_title']} | "
            f"di H1: {page['content']['keyword_in_h1']}\n"
            f"    FAQ: {signals['faq']['has_faq']} | "
            f"AMP: {signals['amp']['is_amp'] or signals['amp']['has_amp_version']} | "
            f"tabel: {signals['table_count']} | "
            f"schema: {', '.join(signals['schema_types'][:5]) or 'tidak ada'}\n"
            f"    entity coverage: "
            f"{page['entity'].get('coverage_percentage', 0)}% | "
            f"skor SEO: {page['seo_score']}/100"
        )

        isi = format_page_digest(page.get("digest") or {})

        if isi:
            blok = f"{blok}\n{isi}"

        lines.append(blok)

    return "\n".join(lines) if lines else "- Tidak ada data"


def build_serp_insight_prompt(
    analysis: dict,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk menjelaskan kenapa rank 1–10 bisa naik.
    """
    keyword = analysis["keyword"]
    pages = analysis["pages"]
    blueprint = analysis["blueprint"]
    target = blueprint["target"]
    adoption = blueprint["adoption"]

    schema_text = format_list(
        [
            f"{item['type']} (dipakai {item['domain_count']} domain)"
            for item in blueprint["common_schema_types"]
        ],
        limit=8,
    )

    topic_text = format_list(
        [
            f"{item['term']} ({item['coverage_percentage']}% domain)"
            for item in blueprint["heading_topics"]
        ],
        limit=15,
    )

    # Heading utuh milik kompetitor. Sudah lama dikumpulkan
    # collect_common_headings() dan disimpan di blueprint, tapi tidak
    # pernah ada prompt yang membacanya - yang dikirim selama ini
    # cuma heading_topics di atas, yaitu kata tunggal beserta
    # persentase. "slot" muncul di 90% domain tidak memberi tahu apa
    # pun tentang bagaimana halaman disusun; "Cara Daftar dan Deposit
    # Minimal 10 Ribu" memberi tahu banyak.
    heading_text = format_list(
        [
            f"{item['heading']} ({item['count']} domain)"
            for item in blueprint.get("common_headings", [])
        ],
        limit=18,
        empty="- Tidak ada",
    )

    user_prompt = f"""
# DATA HALAMAN PERTAMA GOOGLE

Keyword: {keyword}
Halaman bersih yang dianalisis: {blueprint["analyzed_pages"]}
Halaman gagal di-crawl: {blueprint["failed_pages"]}
Halaman di domain bajakan: {blueprint.get("hijacked_count", 0)}
Halaman yang isinya tidak terbaca: {blueprint.get("unreadable_count", 0)}

## Detail Per Peringkat
{format_competitor_table(pages)}

## Catatan Domain Bajakan
{format_list(
    [
        f"Peringkat {item['position']} — {item['domain']} "
        f"(keyakinan {item['confidence']}%"
        + (", cloaking terdeteksi" if item["cloaking"] else "")
        + ")"
        for item in blueprint.get("hijacked_pages", [])
    ],
    limit=10,
    empty="- Tidak ada",
)}

## Median Halaman Pertama
Jumlah kata (semua): {target["word_count_median"]}
Jumlah kata (top 5): {target["word_count_top5_median"]}
Jumlah kata tertinggi: {target["word_count_max"]}
Panjang title: {target["title_length_median"]} karakter
Panjang meta: {target["meta_length_median"]} karakter
Jumlah H2: {target["h2_median"]}
Jumlah H3: {target["h3_median"]}
Internal link: {target["internal_links_median"]}
Keyword density: {target["keyword_density_median"]}%

## Tingkat Pemakaian Fitur
Punya FAQ: {adoption["faq_percentage"]}% halaman
Punya AMP: {adoption["amp_percentage"]}% halaman
Punya tabel: {adoption["table_percentage"]}% halaman

## Schema Yang Dipakai
{schema_text}

## Tema Heading Yang Sering Muncul
{topic_text}

## Heading Utuh Yang Dipakai Kompetitor
{heading_text}

## Pertanyaan Yang Diangkat Kompetitor
{format_list(blueprint["competitor_questions"], limit=12)}

## People Also Ask
{format_list(blueprint["people_also_ask"], limit=10)}

## Pencarian Terkait
{format_list(blueprint["related_searches"], limit=10)}

# TUGAS

1. serp_summary — ringkas karakter halaman pertama untuk keyword ini.
2. search_intent — kebutuhan apa yang sedang dilayani halaman-halaman
   itu. Tulis kebutuhannya saja, satu kalimat.
   intent_evidence — bukti tekstualnya, satu bukti per baris. Isinya
   kutipan atau pengamatan dari halaman yang dikirim di atas. Jangan
   mengulang kalimat search_intent di sini.
3. ranking_analysis — satu entri per peringkat, berisi:
   - why_ranking: kenapa halaman itu bisa naik, ditunjukkan dari
     isinya.
   - angle: sudut pembahasan halaman itu, ditulis sebagai KALIMAT.
     Bukan nama domain, bukan judulnya. Yang dicari: halaman itu
     menempatkan diri sebagai apa untuk pembaca. Contoh bentuk yang
     benar — "Menempatkan diri sebagai jalur belajar terurut dari nol
     sampai bisa kerja, lengkap dengan perkiraan waktunya."
   - strengths dan weaknesses.
4. content_gaps — celah yang belum digarap kompetitor.
5. must_cover — topik yang WAJIB ada di halaman baru supaya bisa
   bersaing. Ambil dari yang benar-benar berulang di halaman
   pertama, bukan dari pengetahuan umum tentang SEO. Kolom reason
   diisi bukti spesifik dari halaman mana topik itu terlihat, bukan
   kalimat umum seperti "sering muncul".
6. winning_strategy — langkah konkret untuk mengalahkan mereka.

Aturan tambahan:
- Kerangka halaman, pembuka, isi, dan tanya-jawab yang tertulis di
  Detail Per Peringkat adalah kutipan asli dari halaman yang sedang
  ngerank. Itu bukti utamamu. Pakai isinya untuk menyimpulkan sudut
  pembahasan dan kebutuhan pembaca.
- Alasan peringkat harus menunjuk ke ISI, bukan cuma ke ukuran.
  "Punya 9 H2 dan skor 82" bukan alasan sebuah halaman menang, itu
  cuma ukurannya. Yang dicari: pembahasan apa yang dia punya dan
  tidak dipunyai yang lain.
- Peringkat yang hanya dikirim kerangkanya jangan dinilai kedalaman
  isinya, karena isinya memang tidak dikirim. Kerangkanya tetap sah
  dipakai untuk melihat pola.
- Halaman yang gagal di-crawl tetap dibahas, tapi katakan bahwa
  datanya tidak tersedia.
- Jangan menyebut backlink atau domain authority karena tidak
  ada di data.
- Halaman yang ditandai DOMAIN BAJAKAN ngerank karena menumpang
  otoritas domain milik institusi lain, bukan karena kualitas
  halamannya. Katakan apa adanya dan jangan menyarankan menirunya.
- Kalau sebagian besar halaman pertama adalah domain bajakan,
  sebutkan bahwa keyword ini dikuasai spam dan halaman yang
  dibangun secara wajar bersaing dengan lapangan yang tidak setara.
- Halaman berlabel ISI TIDAK TERBACA jangan dinilai kualitas
  kontennya, karena datanya memang tidak ada. Sebut saja bahwa
  isinya disembunyikan dari crawler.
- Jangan menyimpulkan target jumlah kata dari halaman yang tidak
  terbaca atau dari domain bajakan.
""".strip()

    return (
        SERP_ANALYST_SYSTEM_PROMPT,
        user_prompt,
    )


ROLE_LABELS = {
    "title": "judul halaman (tag title)",
    "meta_description": "meta description",
    "meta_keywords": "daftar keyword dipisah koma",
    "h1": "heading utama H1",
    "heading": "heading bagian",
    "paragraph": "paragraf isi artikel",
    "faq_question": "pertanyaan FAQ",
    "faq_answer": "jawaban FAQ",
    "review_text": "isi ulasan pengguna",
    "review_author": "nama orang yang menulis ulasan",
    "review_tag": (
        "tag ulasan: dua sampai empat kata yang merangkum ulasan "
        "di atasnya, TANPA titik di akhir"
    ),
    "card_title": (
        "judul kartu keunggulan: dua sampai lima kata, menamai "
        "keterangan di bawahnya, TANPA titik di akhir"
    ),
    "caption": "keterangan gambar",
    "nav_label": (
        "label menu atau tombol, satu sampai tiga kata, "
        "TANPA titik di akhir"
    ),
    "breadcrumb": (
        "satu tingkat remah navigasi: letak halaman ini di dalam "
        "topiknya, dua sampai empat kata, TANPA titik di akhir dan "
        "TANPA tanda panah atau garis miring. Urutannya dari yang "
        "paling umum ke halaman ini: tingkat pertama beranda, "
        "tingkat terakhir halaman ini sendiri, tingkat di tengah "
        "kategori topiknya. Jangan memuat nama brand"
    ),
    "list_item": "satu butir daftar, satu kalimat pendek",
    "table_cell": "isi satu sel tabel, sangat singkat",
    "label": "satu baris keterangan pendek",
}


# Berapa banyak title dan deskripsi kompetitor yang ikut ke brief.
#
# Enam cukup untuk memperlihatkan kosakata yang sama-sama dipakai
# halaman pertama, dan masih di bawah jumlah yang membuat model
# menyalin salah satunya bulat-bulat.
SERP_TITLE_SAMPLES = 6

# Berapa istilah yang ikut sebagai bahan kata.
SERP_TERM_SAMPLES = 12


def ranking_titles(analysis: dict) -> list[tuple[int, str, str]]:
    """
    Title dan deskripsi halaman yang sedang ngerank, urut peringkat.

    Halaman yang gagal di-crawl, yang isinya tidak terbaca, dan yang
    berdiri di domain bajakan dikeluarkan. Ketiganya ngerank karena
    hal yang tidak ada hubungannya dengan pilihan katanya - domain
    curian, cloaking, atau kebetulan - jadi menirunya berarti meniru
    sesuatu yang bukan penyebabnya.
    """
    hasil: list[tuple[int, str, str]] = []

    for page in analysis.get("pages") or []:
        if page.get("status") != "ok":
            continue

        if page.get("hijack", {}).get("is_hijacked"):
            continue

        if not page.get("usable", True):
            continue

        judul = " ".join(str(page.get("title") or "").split())

        if not judul:
            continue

        deskripsi = " ".join(str(page.get("meta_description") or "").split())

        hasil.append((int(page.get("position") or 0), judul, deskripsi))

    return hasil


def serp_word_bank(analysis: dict) -> str:
    """
    Bahan kata untuk title dan meta_description, diambil dari SERP.

    Ini yang diluruskan pengguna: seluruh analisis di awal run - crawl
    sepuluh halaman, hitung median, kumpulkan entity - gunanya memang
    ini. Sebelumnya hasilnya cuma dipakai sebagai latar ("intent
    pencarian", "celah konten"), dan model menulis title dari
    kepalanya sendiri sementara data kosakata yang mahal itu tergeletak
    tanpa dibaca siapa pun.

    Yang ditaruh di sini kata dan frasa, bukan kalimat contoh. Title
    kompetitor ikut karena di situlah kosakatanya terlihat sedang
    dipakai, bukan supaya disalin - dan aturan di bawahnya menyebut
    perbedaan itu dengan tegas.
    """
    blueprint = analysis.get("blueprint") or {}
    target = blueprint.get("target") or {}

    bagian: list[str] = []

    judul = ranking_titles(analysis)[:SERP_TITLE_SAMPLES]

    if judul:
        bagian.append(
            "Title yang sedang ngerank, beserta panjangnya:\n"
            + "\n".join(
                f"  [{urut}] ({len(teks)} karakter) {teks}"
                for urut, teks, _ in judul
            )
        )

        # Yang terpanjang duluan, dan yang sangat pendek tidak ikut.
        #
        # Ini bank kata, jadi yang berguna adalah deskripsi yang
        # memuat banyak kata. Deskripsi 45 karakter tidak menyumbang
        # kosakata apa pun, dan yang disumbangkannya justru contoh
        # panjang yang bertentangan dengan lantai yang diminta.
        deskripsi = sorted(
            (teks for _, _, teks in judul if len(teks) >= 80),
            key=len,
            reverse=True,
        )

        if deskripsi:
            bagian.append(
                "Deskripsi yang mereka pasang:\n"
                + "\n".join(f"  - {teks}" for teks in deskripsi[:4])
            )

    dicari = [
        str(item).strip()
        for item in (blueprint.get("related_searches") or [])
        if str(item).strip()
    ]

    if dicari:
        bagian.append(
            "Yang juga dicari orang untuk keyword ini:\n"
            + "\n".join(f"  - {teks}" for teks in dicari[:SERP_TERM_SAMPLES])
        )

    entity = [
        str(item.get("entity") or "").strip()
        for item in (blueprint.get("common_entities") or [])
        if str(item.get("entity") or "").strip()
    ]

    if entity:
        bagian.append(
            "Kata yang muncul di banyak halaman sekaligus:\n"
            + "\n".join(
                f"  - {teks}" for teks in entity[:SERP_TERM_SAMPLES]
            )
        )

    if not bagian:
        return ""

    # Angka median disebutkan sebagai PELUANG, bukan sebagai patokan.
    #
    # Ini penting dan sempat salah. Menuliskannya apa adanya -
    # "panjang yang lazim: 54 karakter" - membuat satu-satunya angka
    # konkret di bagian ini justru membantah lantai yang diminta di
    # aturan, dan model memilih angka yang dilihatnya. Datanya tetap
    # jujur; yang berubah cuma apa artinya, dan artinya memang begitu:
    # kalau semua orang berhenti di 54, ruang sesudahnya kosong.
    lazim = ""

    median_judul = int(target.get("title_length_median") or 0)
    median_meta = int(target.get("meta_length_median") or 0)

    if median_judul or median_meta:
        lazim = (
            f"\nMereka berhenti di sekitar {median_judul} karakter "
            f"untuk title dan {median_meta} untuk deskripsi. Jatah "
            "yang diberikan ke kamu lebih besar dari itu, dan "
            "selisihnya bukan ruang kosong yang harus diisi kata "
            "pengisi - itu tempat satu hal konkret lagi yang tidak "
            "sempat mereka sebutkan.\n"
        )

    return (
        "\n## Bahan Kata Untuk Title Dan Deskripsi\n"
        "Seluruh analisis halaman pertama Google dikerjakan untuk "
        "bagian ini. Isinya kosakata yang terbukti dipakai orang "
        "mencari dan dipakai halaman yang sedang menang - dan dari "
        "situlah kata-kata di title dan meta_description diambil, "
        "bukan dikarang dari nol.\n"
        "Yang diambil KATA dan FRASA-nya, bukan kalimatnya. Menyalin "
        "satu title di bawah ini, atau menyusun ulang urutan katanya "
        "saja, menghasilkan halaman yang bersaing sebagai salinan "
        "pucat halaman yang sudah ada duluan.\n\n"
        + "\n\n".join(bagian)
        + "\n"
        + lazim
    )


# Sampai berapa banyak teks batas panjangnya disebut satu per satu.
MAX_PER_ITEM_LIMITS = 30

# Berapa pertanyaan orang yang ikut sebagai contoh bentuk.
#
# Sepuluh cukup memperlihatkan polanya - apa yang ditanyakan orang
# dan sependek apa - dan masih di bawah jumlah yang membuat model
# menyalin salah satunya bulat-bulat.
FAQ_SHAPE_SAMPLES = 10

# Sudut yang boleh diambil judul halaman, dipilih satu per halaman.
#
# Ini keluhan pengguna: judulnya selalu berangkat dari hal yang sama.
# Terukur dengan menjajarkan halaman yang terbit dengan 120 contoh
# title milik pengguna sendiri - di daftar miliknya, kata "RTP" cuma
# muncul di 6 baris (5%), sedangkan halaman yang dihasilkan NEIIU
# hampir selalu memakainya, lengkap dengan angka desimalnya.
#
# Sebabnya bukan model kehabisan ide melainkan brief yang cuma
# menyebut satu bahan: daftar angka RTP dikirim di setiap giliran,
# jadi itulah hal paling konkret yang tersedia waktu judul ditulis.
#
# Jadi sudutnya digilir, dan RTP tinggal salah satu dari dua belas.
# Dipilih dari benih - nama brand, keyword, dan penanda run - bukan
# diacak, karena dua alasan: awalan prompt harus identik di semua
# giliran supaya cache Ollama tidak batal, dan halaman kedua untuk
# keyword yang sama harus mendapat sudut yang lain.
# Tiap sudut punya EMPAT bagian, bukan satu kalimat.
#
# Sebelumnya sudut ditulis sebagai satu frasa penjelas - "link login
# dan cara masuk waktu link utama susah dibuka" - dan itu terbukti
# tidak cukup untuk model 4B. Terukur pada lima generate berturut-turut
# Berapa contoh gaya yang ikut ke prompt kepala halaman.
#
# Lebih sedikit daripada STYLE_SAMPLE_SIZE di jalur halaman penuh, dan
# itu disengaja: giliran ini menulis SATU baris, jadi delapan contoh
# mulai terbaca sebagai daftar yang harus dirangkum, bukan sebagai
# gaya yang ditiru.
HEAD_STYLE_SAMPLE = 5

# Pemisah baris sebagai nama, supaya blok di bawah bisa ditulis
# sebagai teks apa adanya tanpa satu escape pun di dalamnya.
NEWLINE = chr(10)


def head_style_block(
    slot: str,
    keyword: str,
    brand_name: str,
    variation: str = "",
    language_code: str = "id",
    niche: str = "gambling",
) -> str:
    """
    Contoh gaya untuk giliran yang cuma menulis judul atau deskripsi.

    Ini menambal ketimpangan yang terukur di run 30 Agustus 2026, dan
    ketimpangannya bukan soal panjang prompt melainkan soal adil.

    Judul dinilai title_penalty, dan dua ukuran di dalamnya membaca
    berkas contoh milik pengguna:

        vague_title_score  - menolak judul yang tidak memuat satu pun
                             kata dari topic_vocabulary(), dan
                             kosakata itu DIPANEN dari
                             knowledge/gaya_title.txt
        style_copy_score   - menolak judul yang menyalin contoh di
                             berkas yang sama

    Deskripsi dinilai description_penalty, yang juga memakai
    style_copy_score atas contohnya sendiri.

    Sampai sekarang tidak satu pun contoh itu dikirim ke model di
    jalur ramping. Modelnya dinilai atas berkas yang tidak pernah
    dilihatnya - dituntut menyebut hal yang ada di dalamnya sekaligus
    dilarang menyerupainya. Hasilnya terukur: judul ditolak tiga kali
    dengan alasan TIDAK MENYEBUT SATU HAL PUN YANG NYATA, lalu yang
    terbit kandidat yang paling sedikit bermasalah -

        ABECE # Togel Online untuk Pemain & Tanpa Pendaftaran

    Yang dikirim contoh utuh, BUKAN daftar kata. Bedanya sudah pernah
    dibayar: waktu sudut judul masih dikirim sebagai daftar kosakata
    wajib, yang terbit "RTP Slot Gacor Data, Sumber, dan Perbarui" -
    model mencentang daftarnya dengan patuh dan hasilnya terbaca
    persis seperti daftar yang dicentang. Contoh utuh tidak bisa
    dicentang; ia cuma bisa dibaca sebagai kalimat.

    Syarat kirimnya sama dengan jalur halaman penuh - style_examples_fit
    - jadi halaman Thai dan halaman di luar bidang judi tidak mendapat
    satu baris pun dari berkas berbahasa Indonesia tentang situs slot.
    """
    if not style_examples_fit(language_code, niche):
        return ""

    contoh = pick_style_examples(
        keyword,
        brand_name,
        jumlah=HEAD_STYLE_SAMPLE,
        slot=slot,
        variation=variation,
    )

    if not contoh:
        return ""

    nama = brand_name or "situs ini"
    sebutan = "JUDUL" if slot == "title" else "DESKRIPSI"

    baris = NEWLINE.join(
        f"- {teks.replace('[ BRAND ]', nama)}" for teks in contoh
    )

    return f"""
CONTOH {sebutan} MILIK SITUS INI
JANGAN disalin, dan JANGAN diikuti topiknya. Yang diambil dari sini
satu hal: contoh-contoh ini selalu menyebut sesuatu yang bisa
ditunjuk - cara masuk, cara bayar, apa yang terjadi sesudah menang,
kapan bisa dibuka. Tidak satu pun berhenti di rasa seperti "nyaman",
"pengalaman bermain", atau "dirancang untuk pemain". Punyamu juga
jangan.
{baris}
"""


def title_rules_block(
    brand_name: str,
    keyword: str,
    language_name: str,
) -> str:
    """
    Aturan menulis judul, satu sumber untuk kedua jalur.

    Isinya aturan yang sudah terbukti sejak 16
    Agustus 2026 dan terbukti di 20 generate: 0 salah sudut, 0 ditolak,
    0 keyword hilang. Dipindahkan ke sini bukan untuk diubah melainkan
    supaya jalur panjang memakai yang SAMA - dua daftar aturan yang
    berdiri sendiri-sendiri akan bergeser tanpa yang lain tahu, dan
    gejalanya judul yang lolos di satu jalur lalu ditolak di jalur lain
    dari perintah yang sama.

    Alasan yang sama sudah dipakai untuk enforce_title_shape dan
    title_penalty; ini melengkapi sisi promptnya.
    """
    return f"""
ATURAN JUDUL
1. SUDUT JUDULNYA KAMU YANG MENENTUKAN. Orang yang mengetik
   "{keyword}" sedang mencari sesuatu; putuskan sendiri apa yang
   paling berguna dijanjikan kepadanya, lalu tulis judul yang
   menjanjikan hal itu. Tidak ada daftar kata yang harus kamu
   centang di sini.
2. SATU gagasan, bukan tiga. Judul yang menyebut akses, bonus, dan
   kecepatan sekaligus tidak menjanjikan apa pun - pembaca hasil
   pencarian membacanya sambil lalu dan cuma menangkap yang pertama.
3. Jangan memaksakan kosakata apa pun. Angka, persen, "sumber data",
   "terbaru", "diperbarui", "RTP" - kalau sudut yang kamu pilih tidak
   benar-benar membutuhkannya, jangan ditulis. Judul yang menempelkan
   kata-kata itu supaya terlihat lengkap justru terbaca seperti
   daftar keyword, bukan seperti kalimat.
4. Tulis nama situs "{brand_name or "situs ini"}" persis seperti itu.
5. Keyword "{keyword}" ditulis SEKALI. Ia TIDAK harus di depan -
   taruh di tempat yang membuat kalimatnya paling wajar dibaca.
6. Satu kalimat yang SELESAI. Jangan menempelkan kata di ujung cuma
   supaya panjangnya cukup.
7. Paling banyak SATU koma di seluruh judul. Judul yang berisi
   daftar - "Akses, Blokir, dan Link Cadangan" - adalah tiga
   potongan yang didempetkan, bukan satu janji. Pilih satu.
8. Huruf besar seperti judul yang wajar dalam bahasa {language_name}.
9. Jangan mengarang angka, persen, jaminan menang, atau lisensi.
10. JANGAN menyalin kalimat perintah di atas ke dalam judul. Judul
    ditulis untuk pembaca hasil pencarian, bukan untuk menjawab
    daftar ini.
"""


def title_history_block(riwayat: dict | None, keep: int = 6) -> str:
    """
    Judul yang sudah terbit, beserta pembukanya secara terpisah.

    Bentuknya: daftar judul,
    lalu daftar pembuka yang dilarang, lalu larangan bertanya kalau
    yang sebelumnya sudah bertanya. Ketiganya menyasar tiga ukuran
    yang benar-benar diperiksa Python sesudahnya - title_echo_score,
    opening_repeat_score, dan shape_repeat_score - jadi yang dikatakan
    ke model sama persis dengan yang dinilai darinya.
    """
    terakhir = [
        " ".join(str(teks).split())
        for teks in ((riwayat or {}).get("title") or [])
        if str(teks).strip()
    ][:keep]

    if not terakhir:
        return ""

    pembuka = []

    for teks in terakhir:
        potong = teks.split()

        if len(potong) > 3:
            pembuka.append(" ".join(potong[1:4]))

    blok = "\nJUDUL YANG SUDAH KELUAR (jangan diulang):\n"
    blok += "\n".join(f"- {teks}" for teks in terakhir)

    if pembuka:
        blok += "\nJANGAN membuka dengan: " + "; ".join(
            f"\"{x}\"" for x in dict.fromkeys(pembuka)
        )

    if any("?" in teks for teks in terakhir):
        blok += (
            "\nJudul sebelumnya sudah bertanya. Kali ini JANGAN bertanya."
        )

    return blok + "\n"


def meta_history_block(riwayat: dict | None, keep: int = 6) -> str:
    """
    Deskripsi yang sudah terbit, beserta pembukanya secara terpisah.

    Bentuknya sengaja sama dengan title_history_block: daftar
    deskripsi lalu daftar pembuka yang dilarang. Sebabnya juga sama -
    yang paling cepat terbaca sebagai halaman kembar bukan seluruh
    kalimatnya, melainkan tiga kata pertamanya. Deskripsi di jalur
    ini SELALU dibuka nama situs, jadi yang diadu kata KEDUA sampai
    keempat; kalau yang diadu kata pertama, seluruhnya sama dan tidak
    ada yang bisa dilarang.
    """
    terakhir = [
        " ".join(str(teks).split())
        for teks in ((riwayat or {}).get("meta_description") or [])
        if str(teks).strip()
    ][:keep]

    if not terakhir:
        return ""

    pembuka = []

    for teks in terakhir:
        potong = teks.split()

        if len(potong) > 4:
            pembuka.append(" ".join(potong[1:4]))

    blok = "\nDESKRIPSI YANG SUDAH KELUAR (jangan diulang):\n"
    blok += "\n".join(f"- {teks}" for teks in terakhir)

    if pembuka:
        blok += "\nJANGAN melanjutkan nama situs dengan: " + "; ".join(
            f'"{x}"' for x in dict.fromkeys(pembuka)
        )

    return blok + "\n"


def meta_rules_block(
    brand_name: str,
    keyword: str,
    language_name: str = "Indonesia",
) -> str:
    """
    Aturan meta description, disalin dari blok aturan halaman penuh.

    Setiap butir di sini sudah berdiri di build_template_content_prompt
    dan tidak satu pun diubah artinya - yang berbeda cuma butir-butir
    yang TIDAK ikut, yaitu semua yang mengatur paragraf, heading, FAQ,
    dan ajakan daftar. Tidak satu pun dari itu berlaku untuk giliran
    yang cuma menulis satu baris deskripsi.
    """
    return f"""
ATURAN DESKRIPSI

- Deskripsi WAJIB DIBUKA NAMA SITUS. Kata pertamanya "{brand_name}",
  lalu satu kata kerja yang menyatakan apa yang disediakannya:
  menyediakan, menghadirkan, menyajikan, menawarkan, menjamin, atau
  adalah.
    salah : "Pemain baru bisa mulai bermain di {brand_name} ..."
    benar : "{brand_name} menghadirkan {keyword} yang bisa dibuka ..."
  Jangan dibuka dengan menyapa pembaca, dan jangan dibuka dengan kata
  kerja tanpa pelakunya.
- Deskripsi BUKAN versi panjang dari judul. Judul adalah papan nama:
  siapa ini dan tentang apa. Deskripsi adalah alasan mengklik: apa
  yang didapat pembaca kalau masuk, hal yang TIDAK muat di judul.
  Kalau judulnya tinggal disambung jadi deskripsimu, deskripsinya
  salah.
- SATU KALIMAT PENUH SAMPAI SELESAI, atau dua kalimat yang keduanya
  selesai. Deskripsi yang berhenti di tengah - "cocok untuk pemain
  yang ingin" - terbit apa adanya di hasil pencarian dan terbaca
  seperti halaman yang rusak. Kalau tidak yakin muat, tulis lebih
  pendek; jangan memulai kalimat yang tidak akan sempat selesai.
- JANGAN menulis angka persen. Tidak satu angka pun yang diikuti
  tanda persen, berapa pun nilainya.
- Ditulis dalam bahasa {language_name}, seluruhnya.
""".rstrip()


def build_meta_only_prompt(
    analysis: dict,
    brand: dict,
    spec: dict,
    sudah: dict | None = None,
    riwayat: dict | None = None,
) -> tuple[str, str]:
    """
    Prompt khusus giliran yang isinya HANYA meta description.

    Kembaran build_title_only_prompt, dan ada karena alasan yang sama
    persis - diukur di run 30 Agustus 2026, pada permintaan yang cuma
    minta satu judul dan satu deskripsi:

        giliran title (jalur ramping) : 22 detik
        giliran deskripsi (jalur penuh) : 472 detik

        prompt giliran deskripsi : 11.811 token
        yang diminta             : satu kalimat 140-180 karakter

    Dua puluh satu kali lebih lama untuk teks yang panjangnya dua kali
    lipat. Sebabnya satu baris di generators/content_planner.py:
    jalur ramping menyala hanya kalau gilirannya berisi title
    SENDIRIAN, jadi deskripsi selalu berangkat dengan prompt seluruh
    halaman - aturan paragraf, heading, FAQ, daftar, CTA, bank kata
    SERP, dan pertanyaan kompetitor - untuk giliran yang tidak menulis
    satu pun dari itu.

    Yang TETAP dikirim di sini, karena deskripsi memang membutuhkannya:
    judul yang baru saja ditulis (deskripsi melanjutkan sudutnya, dan
    dilarang mengulanginya), daftar kata khas judul yang tidak boleh
    dipakai lagi, dan deskripsi yang sudah terbit di halaman
    sebelumnya.
    """
    keyword = analysis["keyword"]

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")

    aturan_slot = spec.get("meta_description") or {}

    lantai = int(aturan_slot.get("min_length") or 0)
    plafon = int(
        aturan_slot.get("max_length_any")
        or aturan_slot.get("max_length")
        or META_MAX
    )

    batas = (
        f"Panjang deskripsi : {lantai} sampai {plafon} karakter — "
        f"WAJIB melewati {lantai} karakter dan WAJIB berhenti "
        f"sebelum {plafon}"
        if lantai
        else f"Panjang deskripsi : maksimal {plafon} karakter"
    )

    # Judul yang baru ditulis, beserta larangan mengulanginya.
    #
    # Ini bagian yang TIDAK boleh hilang waktu prompt dirampingkan.
    # Tanpa judulnya, deskripsi ditulis tanpa tahu sudut apa yang
    # sedang dilanjutkan; dengan judulnya tapi tanpa larangan, cara
    # paling malas melanjutkan sebuah kalimat adalah menuliskannya
    # lagi.
    blok_judul = ""

    daftar_judul = (sudah or {}).get("title") or []
    judul = str(daftar_judul[0]).strip() if daftar_judul else ""

    if judul:
        blok_judul = (
            f"\nJUDUL HALAMAN INI (sudah ditulis)\n{judul}\n"
            "\nDeskripsimu MELANJUTKAN sudut judul itu, dan DILARANG "
            "mengulanginya. Judulnya sudah terbaca sendiri di hasil "
            "pencarian, tepat di atas deskripsimu; mengulangnya "
            "berarti membuang seluruh baris pertama untuk mengatakan "
            "sesuatu yang barusan dibaca orang. Buka dengan hal yang "
            "BELUM disebut judulnya - langkahnya, syaratnya, siapa "
            "yang memakainya, atau apa yang dirasakan sesudahnya.\n"
            + kata_terlarang(judul, keyword, brand_name)
        )

    permintaan = f"""
Kamu menulis SATU meta description SEO. Tidak menulis isi halaman,
tidak menulis paragraf, tidak menulis FAQ, tidak menulis heading.

DATA
Brand             : {brand_name or "-"}
Keyword target    : {keyword}
Bahasa            : {language_name}
Negara sasaran    : {brand.get("region_label", "Indonesia")}
{batas}
{blok_judul}{head_style_block(
        "meta_description",
        keyword,
        brand_name,
        brand.get("variation", ""),
        language_code,
        brand.get("niche", "gambling"),
    )}{meta_history_block(riwayat)}{meta_rules_block(brand_name, keyword, language_name)}

YANG HARUS KAMU TULIS

- meta_description: 1 teks

Jawab HANYA dengan JSON berisi bidang di atas. Jangan menerangkan
apa pun di luar JSON.
""".strip()

    return metadata_system_prompt(language_code), permintaan


def build_title_only_prompt(
    analysis: dict,
    brand: dict,
    spec: dict,
    riwayat: dict | None = None,
) -> tuple[str, str]:
    """
    Prompt khusus giliran yang isinya HANYA title.

    Kenapa ini ada, dengan angkanya. plan_batches menaruh title di
    giliran sendiri - giliran pertama, isinya satu peran - lalu giliran
    itu berangkat dengan prompt lengkap milik seluruh halaman:

        prompt giliran 1 : 15.423 token
        yang diminta     : satu judul 50-70 karakter

    Sebelas koma enam kali lebih besar daripada prompt judul saja
    untuk permintaan yang isinya sama. Blok "# ATURAN" sendirian 11.734
    token - aturan paragraf, heading, FAQ, daftar, CTA - untuk giliran
    yang tidak menulis satu pun dari itu.

    Akibatnya terukur end-to-end dua run berturut-turut (job 93 dan
    94): model gagal menghasilkan judul sama sekali, penambalan gagal
    dua kali, dan yang terbit judul cadangan.

    Ini BUKAN prompt lengkap yang ditambahi aturan judul. Ia berdiri
    sendiri dan cuma menerima yang benar-benar dipakai untuk menulis
    judul: nama situs, keyword, bahasa, jenis halaman, judul yang
    sudah terbit, dan batas panjangnya.

    Yang TIDAK dikirim, dan tidak satu pun dibutuhkan judul: aturan
    paragraf, aturan artikel, aturan FAQ, aturan heading, aturan CTA,
    aturan bagian halaman, bank kata SERP, pertanyaan kompetitor, dan
    daftar teks yang sudah terpakai.

    Sudut halaman TIDAK ikut dikirim, dan itu perubahan yang
    disengaja. Dulu di sini berdiri satu blok bertajuk "SUDUT",
    lalu dua baris kosakata wajib dan terlarang - daftar kata yang harus
    dan tidak boleh muncul di judul. Yang terbit karenanya judul
    seperti "RTP Slot Gacor Data, Sumber, dan Perbarui": model
    mencentang daftarnya dengan patuh, dan hasilnya terbaca persis
    seperti daftar yang dicentang. Sudutnya sekarang ditentukan model
    sendiri; yang tinggal di sini cuma bahannya dan judul yang sudah
    terbit supaya yang baru tidak mengulanginya.
    """
    keyword = analysis["keyword"]

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")


    # Jenis halaman, kalau pengguna memilihnya. Satu baris, bukan blok
    # aturan - yang dibutuhkan judul cuma tahu halaman ini untuk apa.
    tujuan = ""
    pilihan_brief = brand.get("brief") or {}

    if pilihan_brief.get("purpose"):
        label = PURPOSES.get(pilihan_brief["purpose"], {}).get(
            "label", pilihan_brief["purpose"]
        )

        tujuan = f"Jenis halaman   : {label}\n"

    aturan_slot = spec.get("title") or {}

    lantai = int(aturan_slot.get("min_length") or 0)
    plafon = int(
        aturan_slot.get("max_length_any")
        or aturan_slot.get("max_length")
        or TITLE_MAX
    )

    batas = (
        f"Panjang judul   : {lantai} sampai {plafon} karakter — "
        f"WAJIB melewati {lantai} karakter"
        if lantai
        else f"Panjang judul   : maksimal {plafon} karakter"
    )

    permintaan = f"""
Kamu menulis SATU judul SEO. Tidak menulis isi halaman, tidak menulis
paragraf, tidak menulis FAQ, tidak menulis heading.

DATA
Brand           : {brand_name or "-"}
Keyword target  : {keyword}
Bahasa          : {language_name}
Negara sasaran  : {brand.get("region_label", "Indonesia")}
{tujuan}{batas}
{head_style_block(
        "title",
        keyword,
        brand_name,
        brand.get("variation", ""),
        language_code,
        brand.get("niche", "gambling"),
    )}{title_history_block(riwayat)}{title_rules_block(brand_name, keyword, language_name)}
YANG HARUS KAMU TULIS

- title: 1 teks

Jawab HANYA dengan JSON berisi bidang di atas. Jangan menerangkan
apa pun di luar JSON.
""".strip()

    return metadata_system_prompt(language_code), permintaan


# Cara bercerita judul, digilir terpisah dari sudutnya.
#
# Sudut menjawab "judulnya tentang apa"; ini menjawab "diceritakan
# bagaimana". Dua halaman yang sudutnya sama tapi caranya beda tetap
# terbaca sebagai dua halaman berbeda - dan dua halaman yang caranya
# sama akan terasa mirip berapa pun sudutnya digilir.
#
# Isinya dibaca dari 120 contoh title milik pengguna sendiri, dan
# itulah yang membedakannya dari judul yang selama ini terbit.
# Miliknya berkiasan dan bercerita:
#
#   [ BRAND ] : Kisah Si Miskin Berubah Jadi Dewa Slot Kaya Raya
#   [ BRAND ] Raja Iblis Berhati Malaikat Sering Kasih JACKPOT
#   [ BRAND ]: Fakultas Smart Tempat Belajar Slot Gacor
#   [ BRAND ] Tempat Perkumpulan Investor Tambang Slot Online
#
# Yang terbit: "Slot Gacor Update Harian RTP Terbaru" - benar, rapi,
# dan persis sama dengan judul mana pun untuk topik ini. Pengguna
# menyebutnya "kata katanya udah pernah dipakai".
# Sepuluh tetapan di bawah ini sempat ikut terbawa waktu mesin sudut
# judul dibuang, padahal tidak satu pun bagian dari mesin itu - mereka
# cuma kebetulan berdiri di antara fungsi terakhir mesin itu dan fungsi
# berikutnya. Dikembalikan apa adanya dari versi sebelumnya, tanpa satu
# huruf pun diubah.
# Peran yang contoh teks lamanya dikirim untuk menunjukkan FUNGSI
# bagiannya, bukan untuk dipertahankan artinya. Harus sama dengan
# KEEP_FUNCTION_ROLES di generators/template_filler.py.
FUNCTION_SAMPLE_ROLES = {"heading"}

# Peran bertekstunggal yang teks lamanya dikirim sebagai cetakan
# BENTUK: susunannya, tanda pisahnya, dan panjangnya - bukan artinya.
#
# Ini permintaan pengguna: "contoh gayanya pakai dari template, tapi
# kata-katanya generate sendiri". Keduanya dipisahkan dari daftar
# padanan karena daftar itu memerintahkan mempertahankan ARTI teks
# lama, dan untuk judul halaman itu perintah yang salah.
#
# Hanya dua peran ini yang masih diperlihatkan teks lamanya. Judul
# kartu dan tag ulasan sempat ikut dan justru jadi bahan salinan;
# penjelasannya di cabang PARTNER_SOURCE di bawah.
HEAD_SHAPE_ROLES = ("title", "meta_description")

# Peran yang tiap teksnya menerangkan satu teks milik peran lain.
# Harus sama dengan PARTNER_ROLES di generators/template_filler.py.
PARTNER_SOURCE = {
    "card_title": "paragraph",
    "review_tag": "review_text",
}

PARTNER_ORDERS = {
    "card_title": (
        "tulis satu judul untuk tiap keterangan kartu di bawah, "
        "urut nomornya:"
    ),
    "review_tag": (
        "tulis satu tag untuk tiap ulasan di bawah, urut nomornya:"
    ),
}

# Berapa banyak teks yang sudah terpakai disebutkan lagi di giliran
# berikutnya. Cukup untuk memberi tahu model apa yang sudah dipakai
# tanpa memakan ruang yang dibutuhkan jawabannya sendiri.
MAX_USED_REMINDERS = 60

# Berapa LEBAR daftar itu boleh tumbuh, dalam karakter.
#
# Batas jumlah saja tidak cukup, dan itu terukur pada job 61 -
# template LEGO berisi 9 paragraf, 7 ulasan, dan 6 jawaban FAQ, dan
# enam puluh potong teks sepanjang itu adalah belasan ribu karakter.
# Daftarnya tumbuh tiap giliran, dan di giliran ketiga promptnya
# melewati seluruh context: log job berbunyi "sisa context -715
# token". Jawaban yang terpotong lalu diminta ulang berkali-kali,
# dan slot yang tidak kebagian terbit dengan teks pemilik template.
#
# Tiga ribu karakter menahan daftarnya di sekitar 750-1500 token
# berapa pun besar templatenya.
MAX_USED_CHARS = 3000

# Tiap teks di daftar itu dipotong sependek ini.
#
# Daftar ini TIDAK menegakkan apa pun - penolak kalimat kembar
# dikerjakan Python lewat "terpakai" di generators/content_planner.py,
# dan ia membandingkan teks utuh. Gunanya di sini cuma memberi tahu
# model ke mana halaman ini sudah pergi, dan untuk itu awal
# kalimatnya sudah cukup mengenali. Mengirim paragraf 500 karakter
# utuh membayar ruang context untuk ketelitian yang tidak dipakai
# siapa pun.
USED_REMINDER_WIDTH = 110

# Berapa banyak teks dari halaman-halaman SEBELUMNYA yang disebutkan.
#
# Lebih sedikit daripada MAX_USED_REMINDERS, dan itu disengaja.
# Daftar ini ada di dalam brief, jadi ia dibayar sekali per run - tapi
# tugasnya juga berbeda: yang di atas menjaga jangan sampai satu
# halaman menulis kalimat yang sama dua kali, sedangkan yang ini cuma
# perlu memberi tahu model ke arah mana halaman sebelumnya sudah
# pergi. Untuk itu, contoh dari tiap peran sudah cukup - penolakan
# yang sebenarnya dikerjakan Python lewat riwayat yang sama.
MAX_HISTORY_REMINDERS = 40

# Urutan peran di daftar riwayat, dari yang paling menentukan sudut
# pandang halaman. Kalau daftarnya kepanjangan, yang terpotong yang
# paling belakang - jadi judul dan heading selalu terbawa.
HISTORY_PROMPT_ORDER = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "faq_question",
    "card_title",
    "review_tag",
    "review_text",
    "paragraph",
)

# Peran yang daftar teks terpakainya ikut dikirim ke giliran
# berikutnya.
#
# Dua kelompok, dengan alasan yang berbeda.
#
# Label pendek yang jumlahnya ratusan dan dikerjakan berpuluh giliran:
# tanpa daftar ini, halaman terbit dengan ratusan menu berbunyi mirip.
#
# Pertanyaan FAQ, ulasan, dan judul bagian: yang ini bukan soal
# lintas giliran melainkan soal GILIRAN ULANG. Model rutin menutup
# daftarnya lebih awal - 5 dari 7 pertanyaan - dan sisanya diminta
# lagi lewat permintaan susulan. Selama permintaan itu tidak membawa
# apa yang sudah ditulis, model menulis variasi dari pertanyaan yang
# sama, penyaring kembar membuangnya, dan slotnya tetap kosong
# meskipun sudah diminta dua kali. Terukur persis begitu di sini.
REPEAT_PRONE_ROLES = (
    "nav_label",
    "label",
    "table_cell",
    "faq_question",
    "review_text",
    "heading",
    # Judul kartu dan tag ulasan jumlahnya sedikit dan topiknya
    # sempit, jadi giliran ulang yang tidak melihat yang sudah
    # tertulis hampir pasti menulis variasi dari yang barusan dibuang
    # penyaring kembar.
    "card_title",
    "review_tag",
)

# Peran PROSA yang juga harus diingatkan, dengan jatah sendiri.
#
# Ketiganya dulu tidak ada di daftar di atas sama sekali, dan itu
# lubang yang terbaca di halaman terbit - berkas
# output/siam123-slot-gacor-20260819_054058/index.html:
#
#   deskripsi        : "Pemain baru bisa daftar dengan QRIS langsung,
#                       tanpa perlu verifikasi tambahan. Setelah
#                       login, tampilan slot gacor sudah update
#                       sebelum pagi hari."
#   paragraf pertama : kalimat yang sama, dua-duanya.
#   paragraf keempat : kalimat kedua yang sama lagi.
#
# Giliran yang menulis paragraf memang tidak pernah melihat satu pun
# paragraf yang sudah ditulis, dan tidak pernah melihat deskripsinya.
# Ia mengulang bukan karena membandel, melainkan karena tidak ada
# yang memberitahunya.
#
# Berdiri TERPISAH, bukan disambung ke daftar di atas, karena
# keduanya berebut jatah lebar yang sama. Disambung begitu saja,
# paragraf yang panjangnya 300 karakter akan mengusir seluruh label
# menu dari daftar ingatan - dan label menu yang berbunyi sama
# adalah cacat yang sudah pernah terbit juga.
PROSE_REPEAT_ROLES = (
    "meta_description",
    "paragraph",
    "faq_answer",
)



def kata_terlarang(judul: str, keyword: str, brand: str) -> str:
    """
    Kata khas judul yang tidak boleh dipakai lagi di baris pertama.

    Melarang secara umum ternyata tidak menutup apa-apa: di job 35
    deskripsi tetap terbit membuka dengan kalimat judul, sesudah
    diminta dua kali. Yang berbeda di sini larangannya SEBUT NAMA -
    model tidak perlu menebak bagian mana dari judul yang dianggap
    pengulangan.

    Nama brand dan kata keyword sengaja DIKELUARKAN dari daftar.
    Keduanya memang harus muncul lagi di deskripsi; melarangnya
    berarti menukar satu cacat dengan cacat yang lebih mahal.
    """
    # Kata sambung dibuang lewat penokenan SELURUH judul, bukan per
    # kata. Ditokenkan satu per satu, "dengan" balik lagi lewat jalan
    # mundur di content_tokens - kalimat yang seluruhnya kata sambung
    # tetap harus bisa dibandingkan, dan satu kata sambung sendirian
    # adalah kalimat semacam itu.
    isi = content_tokens(judul)
    aman = content_tokens(f"{keyword} {brand}")

    khas = [
        kata
        for kata in dict.fromkeys(str(judul or "").split())
        if (kata.casefold() in isi) and kata.casefold() not in aman
    ]

    if not khas:
        return ""

    return (
        "Kata-kata ini sudah terpakai di judul, jadi JANGAN dipakai "
        "lagi di kalimat pertama deskripsimu: "
        + ", ".join(khas)
        + ". Nama situs dan kata pencariannya justru harus tetap "
        "disebut - yang dilarang cuma daftar di atas.\n"
    )


def rentang_teks(nomor: int, plafon: int, lantai: int = 0) -> str:
    """
    Satu butir keterangan panjang untuk satu slot.

    Ditulis sebagai rentang kalau slotnya punya lantai. Bedanya bukan
    kosmetik: "ke-1 maksimal 542" dijawab model dengan 90 karakter
    tanpa melanggar apa pun yang tertulis, dan slot berjatah 542 yang
    diisi 90 karakter meninggalkan empat perlima ruangnya kosong.
    """
    if lantai and lantai < plafon:
        return f"ke-{nomor} {lantai}-{plafon}"

    return f"ke-{nomor} maksimal {plafon}"


# Aturan bunyi tulisan, dipakai BERSAMA oleh jalur bertemplate dan
# jalur tanpa template.
#
# Dulu hanya ada di prompt template, dan pengguna tidak pernah
# membatasi keluhannya ke halaman bertemplate: "jangan menyusun
# landing page dan amp yang sangat terlihat AI banget". Halaman yang
# dirakit tanpa template terbit dengan aturan bunyi dari sebelum
# keluhan itu ada.
#
# Isinya pindah ke ai/language_rules.py supaya tiap bahasa punya
# daftarnya sendiri. Nama lama dibiarkan berdiri sebagai penunjuk ke
# daftar Indonesia: ia masih dipakai di luar berkas ini, dan
# daftarnya sendiri tidak berubah sehuruf pun.
#
# Yang memilih daftar sekarang voice_rules(kode_bahasa), dipanggil di
# kedua penyusun prompt. Sebelum ini daftar Indonesia dikirim juga ke
# halaman Thai - lengkap dengan barisnya yang menyuruh memakai
# "nggak" dan "udah" - dan itu salah satu sebab halaman Thai terbaca
# seperti terjemahan.
VOICE_RULES = VOICE_RULES_ID


def brand_confidence_rules(brand: dict) -> str:
    """
    Aturan cara halaman berbicara tentang brandnya sendiri.

    Dipakai BERSAMA oleh jalur bertemplate dan jalur tanpa template,
    sama seperti VOICE_RULES, karena keluhan yang melahirkannya juga
    tidak membedakan keduanya: "kalau AI bikin landing page dan amp,
    AI-nya ngomongin BRAND itu menjanjikan, soalnya BRAND-nya emang
    beneran bisa dan ada lisensinya".

    Dulu kedua jalur menahan hal ini dengan alasan yang sama - "tidak
    ada datanya" - dan alasan itu benar untuk ANGKA, tapi tidak benar
    untuk kesanggupan brandnya. Yang satu tidak diketahui pipeline;
    yang lain diketahui pemiliknya, dan pemiliknya yang menyatakan.
    Jadi yang dilonggarkan kesanggupannya, dan yang tetap ditahan
    angkanya.
    """
    brand_name = brand.get("site_name", "")
    lisensi = str(brand.get("license") or "").strip()

    # Daftar kesanggupan diambil dari bidang halamannya, bukan
    # dipatok.
    #
    # Isinya dulu ditulis langsung di sini dan seluruhnya tentang
    # situs judi - "yang menang dibayar", "deposit dan withdraw
    # diproses cepat". Untuk halaman kursus atau toko, kalimat itu
    # bukan cuma janggal: ia menyuruh model menuliskan kesanggupan
    # yang tidak ada hubungannya dengan apa yang dijual halaman itu.
    #
    # Bidang "gambling" mengembalikan daftar yang sama persis seperti
    # sebelum dipisah, jadi halaman judi tidak bergeser sehuruf pun.
    kesanggupan = capability_lines(
        brand.get("niche", "generic"),
        brand.get("region", "id"),
        brand.get("niche_text", ""),
    )

    # Dua larangan penutup ikut mengikuti bidang, dengan alasan yang
    # sama dengan daftar kesanggupan di atasnya: "angka RTP" dan
    # "hasil judi" tidak menunjuk apa pun di halaman kursus, dan
    # menyebutkannya di situ justru menaruh kosakata judi di depan
    # model yang sedang menulis tentang kursus.
    #
    # Yang dilarang tidak berubah - angka karangan dan janji hasil
    # tetap tidak boleh di bidang mana pun. Yang berubah cuma contoh
    # angkanya dan sebutan untuk "hasil".
    judi = str(brand.get("niche") or "gambling").strip().lower() == "gambling"

    # Seluruh butirnya ikut disubstitusi, bukan cuma daftar angkanya.
    #
    # Kalau yang diganti cuma daftarnya, tempat baris barunya bergeser
    # dan teks bidang judi tidak lagi sama huruf per huruf dengan yang
    # sudah diukur. Perbedaannya cuma pembungkus baris, dan justru
    # karena itu ia mudah lolos - yang menahannya di sini bentuk
    # kodenya, bukan kewaspadaan.
    if judi:
        larangan_angka = (
            f'- ANGKA yang tidak diberikan ke halaman ini: jumlah member, tahun\n'
            f'  berdiri, nomor lisensi, angka RTP, winrate, jumlah penghargaan,\n'
            f'  lama proses dalam detik. "{brand_name}" boleh berlisensi tanpa\n'
            f'  membuat angka-angka itu jadi ada, dan angka karangan adalah satu-\n'
            f'  satunya klaim di halaman ini yang bisa dibantah orang lain dengan\n'
            f'  bukti.'
        )

        janji_hasil = (
            f'- Janji bahwa PEMBACANYA akan menang, untung, atau balik modal.\n'
            f'  Menulis "{brand_name}" sanggup membayar adalah pernyataan tentang\n'
            f'  brandnya dan itu boleh; menulis pembacanya pasti menang adalah\n'
            f'  pernyataan tentang hasil judi dan itu ditolak hampir semua\n'
            f'  platform iklan - yang rugi justru brand berlisensi, karena ia yang\n'
            f'  punya sesuatu untuk dicabut.'
        )
    else:
        larangan_angka = (
            f'- ANGKA yang tidak diberikan ke halaman ini: jumlah pelanggan,\n'
            f'  tahun berdiri, nomor izin, persentase kepuasan, jumlah\n'
            f'  penghargaan, lama proses dalam menit atau detik. "{brand_name}"\n'
            f'  boleh beroperasi resmi tanpa membuat angka-angka itu jadi ada,\n'
            f'  dan angka karangan adalah satu-satunya klaim di halaman ini yang\n'
            f'  bisa dibantah orang lain dengan bukti.'
        )

        janji_hasil = (
            f'- Janji tentang HASIL yang akan didapat pembacanya.\n'
            f'  Menulis "{brand_name}" mengerjakan sesuatu sampai selesai adalah\n'
            f'  pernyataan tentang brandnya dan itu boleh; menjanjikan pembacanya\n'
            f'  pasti berhasil, pasti puas, atau pasti untung adalah pernyataan\n'
            f'  tentang sesuatu yang tidak ada di tangan brandnya.'
        )

    if lisensi:
        baris_lisensi = (
            f'- "{brand_name}" berlisensi {lisensi}, dan itu ditulis\n'
            f"  sebagai fakta memakai nama itu - bukan \"konon\", bukan\n"
            f'  "diklaim berlisensi". JANGAN menulis NOMOR lisensinya.\n'
            f"  Nomornya tidak ada di sini, dan nomor karangan adalah\n"
            f"  nomor milik perusahaan lain.\n"
        )
    else:
        baris_lisensi = (
            f'- "{brand_name}" beroperasi resmi dan berlisensi, dan itu\n'
            f"  boleh ditulis sebagai fakta. Yang TIDAK boleh adalah\n"
            f"  menyebut nama badan pengawasnya - PAGCOR, Curacao, BMM,\n"
            f"  nama mana pun - karena namanya tidak diberikan ke sini.\n"
            f"  Pengawas yang salah nama lebih buruk daripada pengawas\n"
            f"  yang tidak disebut.\n"
        )

    return f"""Aturan cara berbicara tentang "{brand_name}" — berlaku untuk SEMUA teks di atas:
- Tulis seperti orang yang tahu situsnya sanggup memenuhi yang
  barusan ditulisnya. Halaman ini milik "{brand_name}", bukan ulasan
  pihak ketiga yang sedang menimbang-nimbang, jadi kalimatnya
  selesai: "Withdraw diproses langsung", bukan "withdraw diharapkan
  dapat diproses dengan cepat".
{baris_lisensi}- Ini semua BOLEH ditulis sebagai kemampuan yang memang ada:
{kesanggupan}
- Kata ragu berikut DILARANG dipakai untuk hal-hal di atas:
  "mungkin", "diharapkan", "berusaha untuk", "berupaya", "konon",
  "diklaim", "sebisa mungkin", "cenderung". Kata-kata itu membuat
  pembaca bertanya-tanya apa yang sedang disembunyikan.
- Jangan menulis kalimat sanggahan yang tidak diminta siapa pun -
  "hasil dapat berbeda", "tidak ada yang bisa menjamin apa pun".
  Itu bunyi penulis yang sedang berhati-hati, bukan bunyi halaman
  milik brand yang berdiri sendiri.

Dua hal ini tetap TIDAK boleh, dan sebabnya bukan kurang percaya
diri:
{larangan_angka}
{janji_hasil}"""


def title_examples(brand_name: str, niche: str = "gambling") -> dict:
    """
    Contoh judul benar dan salah, mengikuti bidang halaman.

    Aturan bentuk title diajarkan lewat pasangan salah/benar, dan
    contoh yang bidangnya lain mengajarkan dua hal sekaligus:
    bentuknya - yang memang dimaksud - dan kosakatanya, yang tidak.
    Model kecil tidak memisahkan keduanya, jadi halaman kursus yang
    diberi contoh "Update Pola Slot Gacor Tiap Pagi" akan menulis
    judul tentang slot.

    Isian bidang "gambling" sama huruf per huruf dengan yang dulu
    ditulis langsung di dalam prompt.
    """
    nama = brand_name or "situs ini"

    if str(niche or "").strip().lower() != "gambling":
        return {
            "benar_bentuk": (
                f"{nama} Kelas Malam Buat Yang Kerja Siang"
            ),
            "salah_tengah": (
                f"Rahasia Belajar di {nama} Yang Jarang Diketahui"
            ),
            "tumpukan": (
                f"{nama} | Kelas Online Tiap Pagi 2026 Lengkap 24 Jam "
                "Hari"
            ),
            "salah_sifat": (
                f"{nama} Kelas Online Cepat Mudah Terpercaya Resmi"
            ),
            "benar_sifat": (
                f"{nama} Kelas Online Tanpa Biaya Daftar Buat Pemula"
            ),
            "datar": "Kelas Online Terbaru Update Harian",
            "salah_tumpuk": (
                f"{nama} Kelas Online 2026 Update Harian Terlengkap "
                "Paling Murah"
            ),
            "benar_tunggal": (
                f"{nama} Kelas Online Tiap Malam Buat Yang Baru Mulai"
            ),
        }

    return {
        "benar_bentuk": f"{nama} Update Pola Slot Gacor Tiap Pagi Buat\n            Pemain Baru",
        "salah_tengah": f"Rahasia Spin di {nama} Yang Membuka Peluang",
        "tumpukan": f"{nama} | Update Pola Slot Gacor Tiap Pagi 2026 Akurat 24\n    Jam Hari",
        "salah_sifat": f"{nama} Deposit QRIS Cepat Aman Terpercaya Resmi",
        "benar_sifat": f"{nama} Deposit QRIS Tanpa Potongan Buat Pemain Baru",
        "datar": "Slot Gacor Update Harian RTP Terbaru",
        "salah_tumpuk": f"{nama} Slot Gacor 2026 Update Harian Live Terbaru\n            Paling Akurat",
        "benar_tunggal": f"{nama} Update Pola Slot Gacor Tiap Pagi Buat\n            Pemain Baru",
    }


def forbidden_claims_block(
    brand_name: str = "",
    language_code: str = "id",
    niche: str = "gambling",
) -> str:
    """
    Daftar larangan terakhir, ditaruh PALING BAWAH di prompt.

    Isinya tidak baru - brand_confidence_rules sudah melarang semua
    ini di tengah prompt. Yang baru letaknya dan bentuknya, dan
    keduanya diubah karena aturan di tengah prompt terbukti tidak
    cukup untuk model 4B.

    Terukur 14 Agustus 2026: dengan brand_confidence_rules terpasang
    lengkap, permintaan feature-boxes pertama terbit dengan
    "Transaksi terjadi dalam hitungan detik" - lama proses dalam
    satuan waktu, salah satu dari enam hal yang dilarang di prompt
    yang sedang dibacanya.

    Tiga perbedaan yang disengaja dari aturan di tengah:

      1. Berdiri di akhir. Yang dibaca terakhir yang paling
         berpengaruh pada model kecil.
      2. Berbentuk pasangan SALAH/BENAR, bukan larangan saja. Model
         kecil butuh tahu apa yang ditulis sebagai gantinya; dilarang
         tanpa pengganti membuatnya memilih sendiri, dan yang
         dipilihnya biasanya bentuk lain dari hal yang sama.
      3. Pendek. Enam baris yang dibaca mengalahkan tiga puluh baris
         yang dilewati.

    Ini tetap lapis pertama, bukan satu-satunya. Yang benar-benar
    menegakkannya generators/claim_guard.py, yang bekerja atas
    jawaban model - karena aturan prompt seberapa pun tegasnya
    diikuti model kecil kadang-kadang saja.
    """
    nama = brand_name or "situs ini"

    # Butir 4 dan 5 menyebut RTP dan kemenangan, dan keduanya cuma
    # ada di halaman judi. Untuk bidang lain, larangannya tetap
    # berlaku - persen karangan dan janji hasil sama tidak bolehnya -
    # tapi contohnya harus dari bidang yang sedang ditulis, kalau
    # tidak model kecil justru mengambil kosakata judi dari daftar
    # larangan yang seharusnya menahannya.
    judi = str(niche or "").strip().lower() == "gambling"

    if language_code == "th":
        if judi:
            empat = f"""4. ตัวเลข RTP อัตราชนะ และเปอร์เซ็นต์ทุกชนิด
   ผิด : RTP 96.4%
   ถูก : ช่วงนี้ตัวเลขกำลังดี
5. คำสัญญาว่าผู้อ่านจะชนะหรือได้กำไร
   ผิด : เล่นที่นี่ได้เงินแน่นอน
   ถูก : {nama} จ่ายจริงเมื่อชนะ"""
        else:
            empat = f"""4. เปอร์เซ็นต์และคะแนนทุกชนิดที่ไม่ได้ให้ไว้กับหน้านี้
   ผิด : ลูกค้าพึงพอใจ 98%
   ถูก : ลูกค้าส่วนใหญ่กลับมาใช้ซ้ำ
5. คำสัญญาถึงผลลัพธ์ที่ผู้อ่านจะได้รับ
   ผิด : ใช้แล้วได้ผลแน่นอน
   ถูก : {nama} ดูแลจนจบกระบวนการ"""

        return f"""
# ห้ามเขียนสิ่งเหล่านี้ (ตรวจก่อนตอบทุกครั้ง)

1. ระยะเวลาดำเนินการเป็นตัวเลข
   ผิด : ฝากถอนภายใน 30 วินาที
   ถูก : ฝากถอนแล้วเข้าบัญชีเลย
2. จำนวนสมาชิก ผู้เล่น หรือผู้ใช้
   ผิด : สมาชิกกว่า 50,000 คน
   ถูก : มีคนเลือกใช้ {nama} ทุกวัน
3. ปีที่ก่อตั้ง และเลขที่ใบอนุญาต
   ผิด : เปิดให้บริการตั้งแต่ปี 2015
   ถูก : {nama} เปิดให้บริการอย่างถูกต้อง
{empat}

ถ้าไม่แน่ใจตัวเลขไหน ให้เขียนโดยไม่ใส่ตัวเลขนั้น
""".strip()

    empat = (
        f"""4. Angka RTP, winrate, dan persen apa pun.
   salah : RTP 96,4%
   benar : angkanya lagi bagus
5. Janji bahwa PEMBACANYA akan menang atau untung.
   salah : main di sini pasti menang
   benar : {nama} membayar yang menang"""
        if judi
        else f"""4. Angka persen dan skor yang tidak diberikan ke halaman ini.
   salah : 98% pelanggan puas
   benar : kebanyakan yang mencoba kembali lagi
5. Janji tentang HASIL yang akan didapat pembacanya.
   salah : dijamin berhasil
   benar : {nama} mengurusnya sampai selesai"""
    )

    return f"""
# JANGAN MENULIS INI (periksa sekali lagi sebelum menjawab)

1. Lama proses dalam satuan waktu.
   salah : diproses dalam hitungan detik / dalam 2 menit
   benar : diproses langsung / begitu dikonfirmasi
2. Jumlah member, pemain, atau pengguna.
   salah : lebih dari 10.000 member aktif
   benar : dipakai orang setiap hari
3. Tahun berdiri dan nomor lisensi.
   salah : berdiri sejak 2015 / Lisensi No. 8048
   benar : {nama} beroperasi resmi
{empat}

Kalau ada angka yang kamu tidak yakin dari mana asalnya, tulis
kalimatnya tanpa angka itu. Kalimat tanpa angka tetap terbit;
kalimat berangka karangan dibuang seluruhnya oleh pemeriksa.
""".strip()


def build_template_content_prompt(
    analysis: dict,
    insight: dict,
    spec: dict,
    brand: dict,
    sudah: dict | None = None,
    riwayat: dict | None = None,
    angka: dict | None = None,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk mengisi template milik pengguna.

    Bedanya dengan brief biasa: di sini bentuk halamannya sudah
    ditentukan template, jadi yang diminta adalah sejumlah potongan
    teks dengan jumlah dan panjang yang persis, bukan rencana
    halaman yang bebas bentuk.
    """
    keyword = analysis["keyword"]
    blueprint = analysis["blueprint"]

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")
    aturan_brand = brand_confidence_rules(brand)

    # Pilihan pengguna yang mengubah bunyi dan bentuk isi: nada,
    # jenis halaman, pembaca yang dituju, dan keyword pendukung.
    #
    # Keduanya KOSONG kalau pengguna tidak memilih apa pun, dan itu
    # disengaja - job yang dijalankan tanpa menyentuh kolom-kolom baru
    # menghasilkan prompt yang sama persis dengan prompt sebelum brief
    # ada. Seluruh penyetelan yang sudah terukur berdiri di atas
    # prompt itu, jadi ia tidak boleh bergeser tanpa ada yang meminta.
    #
    # Keduanya berdiri di dalam brief, BUKAN di blok permintaan.
    # Isinya tetap sepanjang satu run, jadi awalan prompt tiap giliran
    # tetap identik dan cache prompt Ollama tidak batal - alasan yang
    # sama dengan riwayat dan daftar angka halaman.
    kreatif = brand.get("brief") or {}
    baris_brief = brief_identity_lines(kreatif)
    aturan_brief = brief_rule_blocks(kreatif, language_code)

    # Isi FAQ mengikuti bidang halamannya. Bidang "gambling"
    # mengembalikan kalimat yang sama persis seperti waktu daftarnya
    # masih dipatok di sini.
    #
    # Namanya "topik_faq", bukan "aturan_faq". Nama yang kedua sudah
    # dipakai jauh di bawah untuk hal yang sama sekali lain - spec
    # slot faq_answer - dan memakainya di sini menimpa teks aturan
    # ini dengan dict, atau dengan None kalau templatenya tidak punya
    # slot jawaban FAQ. Terukur: seluruh aturan isi FAQ terbit sebagai
    # kata "None" di dalam prompt, dan tidak ada yang gagal - promptnya
    # tetap terkirim, cuma tanpa aturan yang paling menentukan isi FAQ.
    topik_faq = faq_topic_rules(
        brand.get("niche", "generic"),
        language_code,
        brand.get("niche_text", ""),
    )

    # Bidang halaman, dipakai memilih contoh di aturan bunyi dan di
    # daftar larangan terakhir. Bawaannya "gambling" karena seluruh
    # teks itu ditulis dan diukur di halaman judi - lihat keterangan
    # di voice_rules().
    bidang = brand.get("niche", "gambling")

    # Topik halaman ditulis sebagai satu frasa, bukan dua keterangan
    # terpisah.
    #
    # Sebelumnya keyword dan nama brand disebut di dua baris berbeda,
    # dan model memperlakukannya sebagai dua hal: seluruh artikel
    # ditulis tentang keyword sebagai topik umum, sementara nama
    # brandnya cuma muncul di judul. Terukur di halaman jadi - nama
    # brand cuma 9 kali di seluruh halaman, dan paragrafnya berbunyi
    # "Slot online kini bisa diakses dari mana saja", kalimat yang
    # cocok untuk situs mana pun dan tidak memperkenalkan siapa pun.
    topik = " ".join(x for x in (brand_name, keyword) if x).strip()

    kebutuhan: list[str] = []
    padanan: list[str] = []
    fungsi: list[str] = []
    bentuk: list[str] = []
    cetakan: list[tuple[str, str]] = []

    for role, rule in sorted(spec.items()):
        label = ROLE_LABELS.get(role, role)
        count = rule["count"]
        limit = rule.get("max_length_any") or rule["max_length"]
        jatah = rule.get("budgets") or []

        # Nomor urut selalu dimulai dari satu, karena tiap giliran
        # menerima daftar contoh dan daftar pertanyaannya sendiri -
        # nomor di prompt menunjuk posisi di dalam giliran itu, bukan
        # posisi di seluruh halaman.
        awal = 1

        if role in {"title", "meta_description", "meta_keywords", "h1"}:
            # Peran yang punya lantai disebut sebagai RENTANG, bukan
            # plafon. Bedanya terukur: "maksimal 80 karakter" dijawab
            # model dengan 52 karakter, karena berhenti lebih awal
            # tidak melanggar apa pun yang tertulis di situ.
            lantai = int(rule.get("min_length") or 0)

            kebutuhan.append(
                f"- {role}: 1 teks, panjangnya {lantai} sampai "
                f"{limit} karakter — WAJIB melewati {lantai} "
                f"karakter ({label})"
                if lantai
                else f"- {role}: 1 teks, maksimal {limit} karakter ({label})"
            )
        elif (
            len(set(jatah)) > 1
            and len(jatah) == count
            and count <= MAX_PER_ITEM_LIMITS
        ):
            # Slot dalam satu kelompok jarang sama lebarnya. Batas
            # per teks disebutkan supaya model menakar sendiri, bukan
            # menulis semuanya sepanjang slot terlebar lalu dipotong.
            #
            # Hanya untuk kelompok kecil. Menyebut batas satu per satu
            # untuk 355 label menghabiskan ribuan token prompt demi
            # keterangan yang selisihnya beberapa karakter, dan ruang
            # itu jauh lebih berguna dipakai menulis jawabannya.
            kebutuhan.append(
                f"- {role}: tepat {count} teks ({label}), "
                "panjang per teks: "
                + ", ".join(
                    rentang_teks(nomor, nilai, lantai)
                    for nomor, nilai, lantai in zip(
                        range(awal, awal + count),
                        jatah,
                        list(rule.get("floors") or [0] * count),
                    )
                )
                + " karakter"
            )
        else:
            batas_bawah = min(
                (nilai for nilai in (rule.get("floors") or []) if nilai),
                default=0,
            )

            kebutuhan.append(
                f"- {role}: tepat {count} teks, "
                + (
                    f"masing-masing {batas_bawah} sampai {limit} karakter"
                    if batas_bawah
                    else f"masing-masing maksimal {limit} karakter"
                )
                + f" ({label})"
            )

        # Peran yang tiap butirnya menunjuk tempat berbeda diminta
        # berbeda SEJAK AWAL, bukan cuma diperbaiki belakangan.
        #
        # Penolak kembar di content_planner tetap ada dan tetap
        # perlu - model kecil mengulang sendiri betapapun jelas
        # perintahnya - tapi memperbaiki belakangan berarti satu
        # giliran tambahan untuk tiap kelompok yang bertabrakan.
        # Terukur pada halaman Thai terbit: empat belas tautan footer
        # berbunyi sama, dan tidak satu baris pun di prompt yang
        # pernah menyuruh model membedakannya.
        if role in DISTINCT_ROLES and count > 1:
            kebutuhan[-1] += (
                " — tiap teks WAJIB berbeda satu sama lain; dua teks "
                "yang sama, atau yang cuma beda satu kata di ujungnya, "
                "dihitung salah"
            )

        contoh = rule.get("samples")

        # Peran berpasangan diperiksa SEBELUM syarat bercontoh.
        # Bagiannya tidak dibangun dari contoh teks lama sama sekali,
        # jadi ia harus tetap muncul meski contohnya tidak ada.
        if role in PARTNER_SOURCE:
            # Teks lamanya sengaja TIDAK ikut ditampilkan.
            #
            # Sempat ikut, sebagai cetakan bentuk, dan hasilnya
            # kebalikan dari yang dimaksud: model menyalin balik
            # contohnya dikurangi awalannya - "1. Deposit QRIS 1
            # Detik" dijawab "Deposit QRIS 1 Detik" - lalu Python
            # memasang nomornya kembali dan yang terbit teks lama
            # PERSIS. Terukur di halaman jadi: kartu 1 sampai 3 dan
            # tag 1 sampai 4 tidak bergeser sehuruf pun, sementara
            # log melaporkan semuanya sudah terisi.
            #
            # Nomor urut dan awalan "Tag:" tidak perlu diperlihatkan
            # sama sekali, karena bukan model yang menulisnya.
            # Ditutup di sini, satu-satunya yang bisa disalin model
            # tinggal keterangannya sendiri - dan itu memang yang
            # harus dinamainya.
            pasangan = str(PARTNER_SOURCE.get(role, ""))
            sumber = list((sudah or {}).get(pasangan) or [])
            nomor_pasangan = list(rule.get("partners") or [])

            bentuk.append(f"\n{role} — {PARTNER_ORDERS.get(role, '')}")

            for nomor in range(1, count + 1):
                index = (
                    nomor_pasangan[nomor - 1]
                    if nomor - 1 < len(nomor_pasangan)
                    else -1
                )

                teks = (
                    str(sumber[index]).strip()
                    if 0 <= index < len(sumber)
                    else ""
                )

                bentuk.append(
                    f"  [{nomor}] {teks}"
                    if teks
                    else f"  [{nomor}] (teksnya belum ditulis)"
                )

            continue

        if not contoh:
            continue

        # Judul dan deskripsi halaman punya bagiannya sendiri.
        # Keduanya cuma satu teks, dan menaruhnya di daftar bernomor
        # membuat model membacanya sebagai satu butir di antara
        # butir-butir lain alih-alih sebagai cetakan bentuk.
        if role in HEAD_SHAPE_ROLES:
            cetakan.append((role, str(contoh[0]).strip()))
            continue

        # Judul bagian dikirim dengan alasan yang berbeda dari menu:
        # bukan supaya artinya bertahan, melainkan supaya fungsinya
        # bertahan. Kalau keduanya dikirim di bawah satu keterangan,
        # model menerjemahkan judul apa adanya dan halamannya terbit
        # dengan judul "FAQ OSB99" cuma berganti nama brand.
        tujuan = fungsi if role in FUNCTION_SAMPLE_ROLES else padanan

        # Penanda posisi ditulis [1], bukan "1.".
        #
        # Bentuk "1." tidak bisa dibedakan dari nomor yang memang
        # bagian teksnya, dan template ini punya keduanya sekaligus:
        # daftar fitur bernomor "1. Deposit QRIS 1 Detik" berdiri di
        # antara teks biasa. Model diminta mempertahankan penomoran
        # yang memang isi, lalu ikut menuliskan nomor daftarnya juga -
        # terbit di halaman jadi sebagai "26. Cara Pesan" dan
        # "38. Inggris" di sepanjang menu.
        # Di giliran ulang, teks lama berubah arti: dari cetakan
        # bentuk jadi daftar larangan.
        #
        # Posisi yang diminta ulang adalah posisi yang jawabannya
        # BARU SAJA dibuang karena menyalin teks lamanya bulat-bulat.
        # Memperlihatkan teks yang sama sekali lagi di bawah keterangan
        # yang sama meminta kesalahan yang sama, dan itu yang terukur
        # di run 12 Agustus: 14 heading diminta tiga kali, tiga kali
        # dijawab dengan judul template apa adanya, dan halamannya
        # terbit dengan "Keunggulan OSB99" di situs WAYANGPLAY.
        if rule.get("forbid_samples"):
            # Slot milik situs lain tetap tidak diperlihatkan, bahkan
            # sebagai larangan. Larangan pun sebuah contoh: yang
            # dilarang menyalin "Gift Cards" masih bisa menuliskan
            # padanannya, dan itu sama tidak diinginkannya.
            ulang = list(rule.get("fresh") or [])

            tujuan.append(
                f"\n{role} — tulis ulang, JANGAN salin yang di bawah:"
            )
            tujuan.extend(
                (
                    f"  [{nomor}] slot milik template asal - tulis teks "
                    f"BARU tentang halaman ini"
                    if nomor - 1 < len(ulang) and ulang[nomor - 1]
                    else f"  [{nomor}] DILARANG menulis ini lagi: {teks}"
                )
                for nomor, teks in enumerate(contoh, start=1)
            )
            continue

        # Penanda posisi ditulis [1], bukan "1.".
        #
        # Bentuk "1." tidak bisa dibedakan dari nomor yang memang
        # bagian teksnya, dan template ini punya keduanya sekaligus:
        # daftar fitur bernomor "1. Deposit QRIS 1 Detik" berdiri di
        # antara teks biasa. Model diminta mempertahankan penomoran
        # yang memang isi, lalu ikut menuliskan nomor daftarnya juga -
        # terbit di halaman jadi sebagai "26. Cara Pesan" dan
        # "38. Inggris" di sepanjang menu.
        # Teks milik situs lain diminta DIGANTI ISINYA, bukan
        # dialihbahasakan.
        #
        # Bedanya terlihat di halaman jadi. Contoh "Gift Cards" di
        # footer template toko mainan, diminta seperti contoh lain,
        # dijawab dengan padanannya dalam bahasa halaman - dan
        # halaman judi terbit dengan menu kartu hadiah yang rapi.
        # Yang dibutuhkan dari contoh itu cuma bentuk dan panjangnya;
        # isinya justru harus ditinggalkan.
        # Teks milik situs lain TIDAK diperlihatkan sama sekali.
        #
        # Menandainya saja tidak cukup, dan itu terukur. Contohnya
        # tetap ditampilkan dengan keterangan "jangan diterjemahkan"
        # di sebelahnya, lalu halaman Indonesia 15 Agustus 2026 terbit
        # dengan footer "Kartu Hadiah", "Ikuti Pesanan",
        # "Pengembalian", dan "Kurang" - terjemahan rapi dari Gift
        # Cards, Track My Order, Returns, dan Missing Pieces, di
        # halaman baccarat. Model menuruti bentuk yang dilihatnya,
        # bukan larangan yang dibacanya.
        #
        # Yang dibutuhkan dari contoh cuma dua hal: nomor urut supaya
        # jawabannya jatuh di slot yang benar, dan panjangnya supaya
        # muat di kotaknya. Keduanya bisa disebut tanpa memperlihatkan
        # teks aslinya. Contohnya tetap ada di spec - pair_by_old_text
        # memasangkan jawaban lewat teks lama itu - dan hanya prompt
        # yang tidak melihatnya.
        segar = list(rule.get("fresh") or [])
        jatah_slot = list(rule.get("budgets") or [])

        def tampil(nomor: int, teks: str) -> str:
            if nomor - 1 < len(segar) and segar[nomor - 1]:
                lebar = (
                    jatah_slot[nomor - 1]
                    if nomor - 1 < len(jatah_slot)
                    else limit
                )

                return (
                    f"  [{nomor}] (slot milik template asal - tulis teks "
                    f"BARU tentang halaman ini, maksimal {lebar} karakter)"
                )

            return f"  [{nomor}] {teks}"

        tujuan.append(f"\n{role} — ganti berurutan:")
        tujuan.extend(
            tampil(nomor, teks) for nomor, teks in enumerate(contoh, start=1)
        )

    # Pertanyaan yang benar-benar dipakai halaman yang sedang ngerank.
    #
    # Ini keluhan pengguna: pertanyaan FAQ-nya kurang menarik, dan
    # yang diminta persisnya "contoh sesuai website yang sudah ngerank
    # di pencarian Google". Bahannya sudah ada sejak awal - People
    # Also Ask dan pertanyaan yang dipakai halaman pertama ikut
    # dikumpulkan analisis SERP - tapi selama ini masuk brief cuma
    # sebagai sepuluh baris di antara belasan daftar lain, lalu
    # ditimpa aturan "data SERP adalah bahan KATA, bukan teks untuk
    # disalin". Aturan itu benar untuk kalimat isi dan salah untuk
    # yang satu ini: yang perlu ditiru dari pertanyaan orang justru
    # BENTUKNYA - apa yang ditanyakan, dari sudut mana, dan sependek
    # apa.
    #
    # Ditulis di gilirannya sendiri, tepat di atas permintaannya, dan
    # cuma muncul di giliran yang memang menulis pertanyaan.
    bagian_contoh_tanya = ""

    if "faq_question" in spec:
        orang_tanya = [
            " ".join(str(teks).split())
            for teks in (
                blueprint["people_also_ask"]
                + blueprint["competitor_questions"]
            )
            if str(teks).strip()
        ]

        orang_tanya = list(dict.fromkeys(orang_tanya))[:FAQ_SHAPE_SAMPLES]

        if orang_tanya:
            bagian_contoh_tanya = (
                "\n## Bentuk Pertanyaan Yang Dipakai Halaman Ngerank\n"
                "Ini pertanyaan yang benar-benar diketik orang di "
                "Google dan yang dipasang halaman-halaman di peringkat "
                "atas untuk pencarian ini.\n"
                "JANGAN menyalin satu pun. Yang ditiru bentuknya: "
                "sependek itu, sekonkret itu, dan bertanya dari sudut "
                "orang yang mau memakai layanannya - bukan dari sudut "
                "orang yang sedang menulis ensiklopedia.\n"
                "Perhatikan apa yang ditanyakan orang: langkahnya, "
                "syaratnya, berapa lama, berapa biayanya, aman atau "
                "tidak, apa yang terjadi kalau gagal. Itu yang dicari "
                "orang, dan itu yang membuat blok FAQ dibaca sampai "
                "habis.\n"
                "Pertanyaanmu menanyakan hal serupa, tapi tentang "
                f"\"{topik or keyword}\" dan dengan kalimatmu sendiri.\n"
                + "\n".join(f"  - {teks}" for teks in orang_tanya)
                + "\n"
            )

    # Pertanyaan yang sudah ditulis di giliran sebelumnya, supaya
    # jawabannya benar-benar menjawab.
    #
    # Tanpa ini, pertanyaan dan jawaban jatuh di giliran berbeda dan
    # jawabannya ditulis tanpa pernah melihat pertanyaannya. Terukur
    # pada halaman jadi: "Apakah perlu verifikasi?" dijawab
    # "Permainan berjalan secara real-time tanpa gangguan", sementara
    # kalimat yang menjawabnya justru terpasang di kartu lain.
    # Strukturnya sempurna, isinya tidak nyambung - dan pembaca
    # melihatnya lebih dulu daripada mesin pencari mana pun.
    bagian_tanya = ""
    aturan_faq = spec.get("faq_answer")

    if aturan_faq and sudah:
        semua_tanya = list(sudah.get("faq_question") or [])

        # Posisi yang benar-benar diminta di giliran ini.
        #
        # Untuk giliran biasa itu deretan berurutan mulai dari offset.
        # Untuk giliran susulan - yang mengisi jawaban yang tadi
        # dilewati model - posisinya BERSERAK, dan gap_spec sudah
        # mencatatnya di "positions". Memakai potongan berurutan di
        # situ menampilkan pertanyaan ke-3 dan ke-4 untuk lubang yang
        # sebenarnya ada di posisi ke-3 dan ke-6, dan jawaban yang
        # ditulis dengan benar dipasang ke pertanyaan yang salah -
        # persis cacat yang bagian ini ada untuk mencegahnya.
        posisi = aturan_faq.get("positions")

        if posisi:
            mulai = 0
            urutan = list(posisi)
        else:
            mulai = int(aturan_faq.get("offset", 0))
            urutan = list(range(mulai, mulai + aturan_faq["count"]))

        # Pertanyaan yang berdiri di atas jawaban, dibaca dari
        # halaman. Dipakai kalau daftar pertanyaan yang ditulis model
        # tidak sampai ke nomor itu - lihat keterangan "asks" di
        # derive_spec.
        dibaca = list(aturan_faq.get("asks") or [])

        def pertanyaan_ke(index: int) -> str:
            if index < len(semua_tanya) and str(semua_tanya[index]).strip():
                return str(semua_tanya[index])

            if index < len(dibaca):
                return str(dibaca[index])

            return ""

        tanya = [pertanyaan_ke(index) for index in urutan]

        if any(str(teks).strip() for teks in tanya):
            bagian_tanya = (
                "\n## Pertanyaan Yang Harus Dijawab Berurutan\n"
                "Ini pertanyaan yang sudah tertulis di halaman, dan "
                "tugas giliran ini HANYA menjawabnya. faq_answer ke-N "
                "adalah jawaban untuk pertanyaan ke-N di daftar ini.\n"
                "Baca dulu pertanyaannya, baru tulis jawabannya. "
                "Jawaban yang benar tapi dipasang di nomor yang salah "
                "sama rusaknya dengan jawaban yang ngawur: pembaca "
                "melihat pertanyaan tentang deposit dijawab dengan "
                "cara login.\n"
                "Kalau pertanyaannya menanyakan CARA, jawabannya "
                "berisi langkahnya. Kalau menanyakan APAKAH, "
                "jawabannya dimulai dengan ya atau tidak. Kalau "
                "menanyakan BERAPA LAMA, jawabannya menyebut "
                "waktunya.\n"
                # Sesudah ya/tidak, LANGSUNG ke isinya.
                #
                # Tanpa baris ini, cara termurah menuruti aturan di
                # atas adalah menyalin balik pertanyaannya sebagai
                # kalimat berita. Terukur pada halaman terbit
                # output/wayangplay-slot-gacor-20260819_232939:
                #
                #   tanya  : "Apakah deposit via QRIS di WAYANGPLAY
                #             bisa langsung diproses?"
                #   jawab  : "Ya, deposit via QRIS di WAYANGPLAY bisa
                #             langsung diproses. Setelah kamu
                #             konfirmasi transaksi, dana langsung
                #             masuk ke akun."
                #
                # Kalimat pertamanya tidak menambah satu keterangan
                # pun - pembaca sudah membacanya persis di atas.
                "Sesudah kata ya atau tidak, langsung ke keterangannya. "
                "JANGAN menulis ulang kalimat pertanyaannya sebagai "
                "kalimat berita - pembaca baru saja membacanya tepat "
                "di atas jawabanmu, dan mengulangnya menghabiskan "
                "kalimat pertama untuk mengatakan yang sudah "
                "diketahui.\n"
                "Tanda [N] cuma penunjuk posisi, jangan ikut ditulis.\n"
                + "\n".join(
                    f"  [{nomor}] {teks}"
                    for nomor, teks in enumerate(tanya, start=1)
                )
                + "\n"
            )

    # Judul bagian yang sudah berdiri di atas paragraf-paragraf ini.
    #
    # Alasannya sama dengan daftar pertanyaan FAQ di atas, dan
    # akibatnya sama parahnya: judul dan paragraf yang dikepalainya
    # sering jatuh di giliran yang berbeda, dan paragraf yang ditulis
    # tanpa pernah melihat judulnya berbunyi tentang apa saja yang
    # kebetulan setopik halaman - judul "Keamanan Akun dan Riwayat
    # Transaksi" berdiri di atas tiga paragraf tentang kecepatan
    # deposit, dan pembaca melihatnya lebih dulu daripada mesin
    # pencari mana pun.
    bagian_artikel = ""
    aturan_paragraf = spec.get("paragraph")

    if aturan_paragraf and sudah:
        judul_tertulis = [
            str(teks).strip()
            for teks in (sudah.get("heading") or [])
            if str(teks).strip()
        ]

        if judul_tertulis:
            bagian_artikel = (
                "\n## Judul Yang Sudah Berdiri Di Halaman Ini\n"
                "Judul bagiannya sudah ditulis di giliran sebelumnya. "
                "Paragraf yang kamu tulis sekarang berdiri di "
                "bawahnya, jadi isinya harus membahas apa yang "
                "dijanjikan judulnya - bukan topik lain yang kebetulan "
                "sama-sama tentang halaman ini.\n"
                + "\n".join(f"  - {teks}" for teks in judul_tertulis)
                + "\n"
            )

    bagian_padanan = (
        "\n## Teks Lama Yang Harus Diganti Berurutan\n"
        "Baris [N] di daftar bawah ini diganti oleh teks ke-N yang "
        "kamu tulis. Tanda [N] itu penunjuk posisi, bukan bagian dari "
        "teksnya - jangan pernah ikut ditulis di jawabanmu. "
        f"Tulis padanannya dalam {language_name} dengan "
        "ARTI YANG SAMA, bukan tulisan baru yang bebas. Ini teks "
        "menu dan tombol; kalau artinya berubah, tautannya jadi "
        "menyesatkan meskipun alamatnya tidak berubah.\n"
        "Contoh yang benar: \"Mens\" jadi \"Pria\", \"View All\" jadi "
        "\"Lihat Semua\", \"Contact Us\" jadi \"Hubungi Kami\".\n"
        "Contoh yang SALAH: ketiganya ditulis jadi variasi "
        f"\"{keyword}\". Menu yang seluruh isinya berbunyi mirip "
        "tidak menunjuk ke mana-mana.\n"
        "Bentuk teks lamanya ikut dipertahankan: nomor urut, angka, "
        "tanda pisah, dan simbol bintang ditulis lagi di tempat yang "
        "sama. \"[3] 1. Deposit Cepat\" dijawab \"1. \" ditambah "
        "padanannya - angka 3 tidak ikut karena itu penunjuk posisi, "
        "angka 1 ikut karena itu memang tertulis di teksnya. "
        "\"[4] Rina — Malang • ★★★★★\" tetap "
        "berbentuk nama, tanda pisah, kota, lalu bintang yang sama "
        "banyaknya.\n"
        "Nama orang diganti nama yang wajar di "
        f"{brand.get('region_label', 'Indonesia')}. Nama merek atau "
        "produk milik perusahaan lain disalin apa adanya.\n"
        + "\n".join(padanan)
        + "\n"
        if padanan
        else ""
    )

    # Title dan deskripsi yang sudah ditulis di giliran pertama,
    # dipasang sebagai patokan untuk seluruh giliran sesudahnya.
    #
    # Ini permintaan pengguna dan sekaligus perbaikan: tanpa patokan,
    # tiap giliran memilih sudut pandangnya sendiri, dan halamannya
    # terbit dengan judul bernada promosi di atas paragraf bernada
    # ensiklopedia, FAQ yang menjawab pertanyaan lain, dan ulasan
    # yang membicarakan hal yang tidak ada di halaman itu. Title dan
    # deskripsi ditulis paling awal justru supaya bisa jadi patokan.
    bagian_tema = ""

    if sudah:
        tema = [
            (nama, str(nilai[0]).strip())
            for nama, nilai in (
                ("Judul halaman", sudah.get("title")),
                ("H1", sudah.get("h1")),
                ("Deskripsi", sudah.get("meta_description")),
            )
            if nilai and str(nilai[0]).strip()
        ]

        if tema:
            # Peringatan tambahan khusus untuk giliran yang menulis
            # deskripsi.
            #
            # Bagian ini menyuruh melanjutkan sudut pandang judulnya,
            # dan cara paling malas melanjutkan sebuah kalimat adalah
            # menuliskannya lagi. Terukur di halaman jadi - judul
            # "JUHI88 Slot Gacor Terpercaya dengan Deposit QRIS Cepat
            # dan Aman", deskripsi dibuka "JUHI88 slot gacor
            # terpercaya dengan deposit QRIS cepat dan aman." Kalimat
            # yang sama, huruf kecil, lalu disambung.
            larangan = (
                "PENTING untuk deskripsi yang kamu tulis sekarang: "
                "JANGAN membukanya dengan kalimat judul di atas, "
                "dan jangan menuliskan ulang judul itu dalam susunan "
                "kata yang berbeda. Judulnya sudah terbaca sendiri di "
                "hasil pencarian, tepat di atas deskripsimu; "
                "mengulangnya berarti membuang seluruh baris pertama "
                "untuk mengatakan sesuatu yang barusan dibaca orang. "
                "Buka dengan hal yang BELUM disebut judulnya - "
                "langkahnya, syaratnya, siapa yang memakainya, atau "
                "apa yang dirasakan sesudahnya.\n"
                + kata_terlarang(
                    dict(tema).get("Judul halaman", ""),
                    keyword,
                    brand_name,
                )
                if "meta_description" in spec
                else ""
            )

            bagian_tema = (
                "\n## Sudut Pandang Halaman Ini\n"
                "Judulnya sudah ditulis lebih dulu, dan DARI SITULAH "
                "seluruh isi halaman ini mengalir. Bukan sekadar "
                "patokan nada: sudut yang dipilih di sana adalah "
                "sudut yang harus dilanjutkan paragraf, heading, FAQ, "
                "dan ulasan yang kamu tulis sekarang.\n"
                "Kalau judulnya menonjolkan kecepatan, isinya bicara "
                "kecepatan. Kalau judulnya menonjolkan keamanan, "
                "isinya bicara keamanan. Jangan memilih sudut sendiri "
                "dan jangan menambah sudut baru.\n"
                + larangan
                + "\n".join(f"  {nama}: {teks}" for nama, teks in tema)
                + "\n"
            )

    # Cetakan bentuk judul dan deskripsi, diambil dari template yang
    # diunggah pengguna.
    #
    # Ini permintaan pengguna, dan sebelumnya tidak ada sama sekali:
    # kedua teks itu satu-satunya bagian template yang TIDAK pernah
    # diperlihatkan ke model. Akibatnya satu-satunya patokan bentuk
    # yang tersisa adalah berkas contoh gaya, dan yang ditiru model
    # dari situ bukan gayanya melainkan frame yang paling sering
    # muncul - "[ BRAND ] menghadirkan ..." terulang belasan kali di
    # berkas itu, dan judul yang terbit "TIMAH33 menghadirkan slot
    # gacor dengan sistem spin modern".
    #
    # Yang diminta di sini kebalikannya: susunannya ditiru, katanya
    # ditulis baru.
    bagian_cetakan = (
        "\n## Bentuk Judul Dan Deskripsi Di Template Ini\n"
        "Ini judul dan deskripsi yang SEKARANG terpasang di template "
        "yang sedang diisi. Isinya milik pemilik template dan tidak "
        "boleh dipakai lagi - yang diambil cuma BENTUKNYA.\n"
        "Yang ditiru: susunan kalimatnya, seberapa konkret janji yang "
        "disebut, dan berapa kalimat yang dipakai deskripsinya.\n"
        "Yang TIDAK ditiru dari sini: letak nama situs dan tanda "
        "pisahnya di title. Dua hal itu sudah dipatok di aturan title "
        "di atas, dan aturan itu menang atas bentuk template ini.\n"
        "Yang TIDAK ikut: topiknya, katanya, dan angkanya. Kalau "
        "bentuk lamanya \"NAMA - Janji Konkret yang Sifat dan "
        "Sifat\", yang kamu tulis juga berbentuk begitu, tapi "
        f"janjinya tentang \"{topik or keyword}\" dan disusun dengan "
        "katamu sendiri.\n"
        "Menyalin salah satu baris di bawah, seluruhnya atau "
        "separuhnya, dihitung tidak menjawab.\n"
        + "\n".join(f"  {nama} lama: {teks}" for nama, teks in cetakan)
        + "\n"
        if cetakan
        else ""
    )

    bagian_bentuk = (
        "\n## Teks Yang Harus Kamu Namai\n"
        "Tiap baris [N] di bawah adalah teks yang SUDAH tertulis di "
        "halaman ini. Teks ke-N yang kamu tulis sekarang menamai "
        "baris ke-N itu. Tanda [N] penunjuk posisi, jangan ikut "
        "ditulis.\n"
        "Bacalah dulu barisnya, baru tulis namanya. Yang benar bisa "
        "dicocokkan orang: baris yang bercerita tentang setor jam "
        "dua pagi dinamai soal waktu, baris yang bercerita tentang "
        "main dari ponsel dinamai soal ponsel. Nama yang sama-sama "
        "cocok ditempel di baris mana pun berarti tidak menamai "
        "apa-apa.\n"
        "Jangan menyalin kalimat barisnya. Yang diminta namanya, "
        "beberapa kata saja, bukan ringkasannya.\n"
        "Jangan menulis nomor urut atau awalan apa pun di depan "
        "jawabanmu - itu sudah diurus di luar, dan kalau kamu ikut "
        "menuliskannya halaman terbit dengan nomor dobel.\n"
        + "\n".join(bentuk)
        + "\n"
        if bentuk
        else ""
    )

    # Larangan menulis angka persen.
    #
    # Keterangan di sini pernah menjelaskan yang sebaliknya - "melarang
    # angka sama sekali tidak berhasil, yang berhasil adalah memberi
    # angkanya lalu menutup pilihan" - dan itu memang cara kerjanya
    # dulu, waktu daftar angka yang boleh dipakai ikut dikirim.
    # Daftarnya sudah tidak dikirim sejak angka persen dilarang, tapi
    # keterangannya tertinggal dan bertolak belakang dengan larangan
    # yang ditulis persis di bawahnya.
    #
    # Yang menangkap angka yang tetap lolos ada di
    # generators/page_numbers.py, sesudah semua giliran selesai.
    # Contoh angkanya mengikuti bidang. Aturannya tidak berubah -
    # persen tetap dilarang di bidang mana pun - tapi contoh "RTP
    # 96,4%" di halaman kursus menaruh kosakata judi di dalam
    # larangan yang seharusnya menahannya.
    contoh_persen = (
        '"RTP 96,4%", bukan "RTP di atas 96%"'
        if bidang == "gambling"
        else '"98% pelanggan puas", bukan "kepuasan di atas 90%"'
    )

    contoh_samar = (
        '"RTP-nya lagi tinggi", "angkanya lagi stabil", '
        '"lagi bagus sejak pagi"'
        if bidang == "gambling"
        else '"lagi banyak yang pakai", "sedang ramai", '
        '"responsnya lagi cepat"'
    )

    bagian_angka = (
        "- JANGAN menulis angka persen sama sekali. Bukan "
        f"{contoh_persen}, bukan angka apa pun yang "
        "diikuti tanda persen.\n"
        "  Pengguna sudah menyatakannya dengan jelas: berapa persis "
        "angkanya tidak penting. Yang dicari pembaca bukan angkanya "
        "melainkan apakah sedang bagus atau tidak, jadi tulis "
        f"{contoh_samar} - kalimat yang memang dipakai orang.\n"
        "  Angka desimal yang sama diulang di sepanjang halaman adalah "
        "tanda paling cepat bahwa halaman ditulis mesin, karena tidak "
        "ada orang yang menulis satu angka persis sama di enam tempat "
        "berbeda.\n"
    )

    if angka and angka.get("cadence"):
        bagian_angka += (
            "- Kalau menyebut seberapa sering datanya diperbarui, "
            f"tulis \"{angka['cadence']}\" - bukan \"setiap 10 "
            "detik\" atau kekerapan lain yang kamu karang sendiri.\n"
        )

    bagian_fungsi = (
        "\n## Judul Bagian Yang Ditulis Ulang\n"
        "Nomor ke-N diganti oleh judul ke-N yang kamu tulis. Yang "
        "dipertahankan di sini BUKAN arti judul lamanya, melainkan "
        "bagian apa yang dikepalainya. Isi di bawah tiap judul tidak "
        "ikut berpindah tempat.\n"
        "Judul yang tadinya mengepalai daftar keunggulan tetap "
        "menamai daftar keunggulan. Judul blok tanya-jawab tetap "
        "menamai tanya-jawab. Judul blok ulasan tetap menamai "
        "ulasan. Yang berganti topiknya, jadi tentang "
        f"\"{' '.join(x for x in (brand_name, keyword) if x)}\".\n"
        "Nama brand lama di dalam judul diganti "
        f"\"{brand_name or '-'}\", bukan dibiarkan.\n"
        # Larangan menyalin ditulis terpisah dari perintah mengganti.
        #
        # "Ganti topiknya" ternyata dibaca model kecil sebagai izin
        # menyalin selama topiknya kebetulan mirip, dan hasilnya judul
        # template kembali apa adanya. Judul yang sama persis dibuang
        # penyaring, slotnya terbit dengan teks lama, dan itulah yang
        # dilaporkan pengguna sebagai "H1 H2 H3 ada yang tidak
        # berubah".
        "Judul yang sama persis dengan judul lamanya DIBUANG. Tiap "
        "judul harus berbeda kata-katanya, bukan cuma berbeda nama "
        "brand.\n"
        + "\n".join(fungsi)
        + "\n"
        if fungsi
        else ""
    )

    # Teks yang sudah tertulis di giliran sebelumnya, supaya giliran
    # ini tidak menulis ulang yang sama.
    #
    # Tanpa ini tiap giliran menulis tanpa melihat giliran lain, dan
    # untuk peran yang jumlahnya ratusan hasilnya halaman yang
    # ratusan menunya berbunyi sama - terukur di halaman jadi:
    # "Slot Terdepan", "Slot Terbaik", "Slot Terlaris", "Slot
    # Terkini", "Slot Terpopuler" berulang sampai keyword density
    # halaman naik ke 3,25%.
    bagian_terpakai = ""

    if sudah:
        def kumpulkan(daftar_peran, saring_spec: bool) -> list[str]:
            """
            Teks yang sudah tertulis untuk sekelompok peran.

            saring_spec menentukan apakah peran yang TIDAK diminta di
            giliran ini ikut dikumpulkan. Untuk label dan menu
            jawabannya tidak: yang diingatkan cuma peran yang sedang
            ditulis, karena yang dijaga di sana adalah dua label
            bersebelahan yang berbunyi sama.

            Untuk prosa jawabannya ya. Deskripsi ditulis di giliran
            PERTAMA dan tidak pernah diminta lagi sesudahnya, jadi
            menyaringnya dengan spec giliran ini berarti giliran yang
            menulis paragraf tidak pernah melihat deskripsi yang
            sedang disalinnya.
            """
            hasil: list[str] = []

            for role in daftar_peran:
                if saring_spec and role not in spec:
                    continue

                hasil.extend(
                    str(teks).strip()
                    for teks in (sudah.get(role) or [])
                    if str(teks).strip()
                )

            # Yang terakhir ditulis yang paling perlu diingat, karena
            # itulah yang paling mungkin diulang.
            return list(dict.fromkeys(reversed(hasil)))[
                :MAX_USED_REMINDERS
            ]

        label_terpakai = kumpulkan(REPEAT_PRONE_ROLES, True)
        prosa_terpakai = kumpulkan(PROSE_REPEAT_ROLES, False)

        # Diselang-seling, bukan disambung.
        #
        # Jatah lebarnya dipotong di MAX_USED_CHARS, dan daftar yang
        # disambung berarti kelompok yang berdiri di belakang tidak
        # pernah kebagian sama sekali begitu kelompok pertama sudah
        # menghabiskan jatahnya. Diselang-seling, keduanya kebagian
        # yang paling baru lebih dulu.
        terpakai: list[str] = []

        for kiri, kanan in zip_longest(prosa_terpakai, label_terpakai):
            for satu in (kiri, kanan):
                if satu:
                    terpakai.append(satu)

        terpakai = list(dict.fromkeys(terpakai))[:MAX_USED_REMINDERS]

        # Dipotong dua kali: tiap teks dipendekkan, lalu daftarnya
        # berhenti begitu jatah lebarnya habis. Lihat MAX_USED_CHARS
        # untuk sebabnya - tanpa ini prompt giliran ketiga melewati
        # seluruh context pada template yang paragrafnya banyak.
        ringkas: list[str] = []
        lebar = 0

        for teks in terpakai:
            potong = teks[:USED_REMINDER_WIDTH].rstrip()

            if len(teks) > USED_REMINDER_WIDTH:
                potong += "..."

            if lebar + len(potong) > MAX_USED_CHARS:
                break

            ringkas.append(potong)
            lebar += len(potong)

        terpakai = ringkas

        if terpakai:
            bagian_terpakai = (
                "\n## Teks Yang Sudah Terpakai Di Halaman Ini\n"
                "Jangan menulis satu pun dari daftar ini lagi. Tiap "
                "teks yang kamu tulis sekarang harus berbeda dari "
                "daftar ini DAN berbeda satu sama lain.\n"
                + "\n".join(f"  - {teks}" for teks in terpakai)
                + "\n"
            )

    # Halaman yang sudah pernah terbit untuk topik ini.
    #
    # Isinya TETAP sepanjang satu run - dibaca sekali dari database
    # sebelum giliran pertama - jadi aman ditaruh di dalam brief yang
    # di-cache. Yang berubah tiap giliran adalah bagian_terpakai di
    # atas, dan itu memang ada di blok permintaan.
    bagian_riwayat = ""

    if riwayat:
        lama: list[str] = []

        for role in HISTORY_PROMPT_ORDER:
            for teks in (riwayat.get(role) or []):
                bersih = " ".join(str(teks).split())

                if bersih:
                    lama.append(f"  [{ROLE_LABELS.get(role, role)}] {bersih}")

        lama = list(dict.fromkeys(lama))[:MAX_HISTORY_REMINDERS]

        if lama:
            bagian_riwayat = (
                "\n## Halaman Yang Sudah Pernah Kamu Tulis\n"
                "Teks di bawah SUDAH TERBIT di halaman lain untuk topik "
                "ini. Halaman yang kamu tulis sekarang berdiri di "
                "sebelahnya, dan dua halaman yang isinya sama tidak ada "
                "gunanya bagi siapa pun - pembaca membaca hal yang sama "
                "dua kali, dan mesin pencari memilih salah satu lalu "
                "membuang yang lain.\n"
                "Jadi bukan sekadar 'jangan menyalin'. Yang diminta "
                "SUDUT YANG LAIN: kalau halaman sebelumnya bicara "
                "kecepatan deposit, yang ini bicara hal lain - cara "
                "memilihnya, apa yang terjadi kalau gagal, siapa yang "
                "memakainya, bandingannya dengan cara lama. Judul, "
                "heading, pertanyaan, dan ulasan yang kamu tulis harus "
                "membahas hal yang berbeda, bukan hal yang sama dengan "
                "kata yang ditukar.\n"
                + "\n".join(lama)
                + "\n"
            )

    # Bagian ini SAMA PERSIS di setiap giliran, dan harus tetap
    # begitu. Ollama menyimpan hasil pemrosesan prompt dan memakainya
    # ulang selama awalannya identik; terukur di mesin ini, prompt
    # 1389 token yang pertama kali makan 242 detik jadi 0,2 detik
    # saat diulang. Karena itu seluruh brief dan seluruh aturan
    # ditaruh di depan, dan daftar yang berubah-ubah tiap giliran
    # ditaruh paling belakang. Menyisipkan apa pun yang berbeda per
    # giliran ke dalam blok ini akan membatalkan cache-nya dan
    # membuat setiap giliran membayar prefill dari nol.
    blok_tema_serp = blok_daftar(
        "Tema yang sering muncul di heading kompetitor:",
        [item["term"] for item in blueprint["heading_topics"]],
        limit=10,
    )

    blok_tanya_serp = blok_daftar(
        "Pertanyaan yang dicari orang:",
        blueprint["people_also_ask"] + blueprint["competitor_questions"],
        limit=10,
    )

    # Tetap sama di seluruh giliran satu run - diturunkan dari benih dan
    # dari riwayat, dan dua-duanya sudah tetap sebelum giliran pertama
    # berangkat - jadi ia aman berdiri di dalam brief yang di-cache.
    #
    # Riwayatnya yang menentukan pergantian topik: sudut yang sudah
    # dipakai halaman sebelumnya dilewati, bukan sekadar diharapkan
    # tidak terpilih lagi oleh benih.
    contoh_judul = title_examples(brand_name, bidang)

    contoh_angka_karangan = (
        '"100.000+ spin per hari" atau "diproses dalam 2 detik"'
        if bidang == "gambling"
        else '"10.000+ pemakai per hari" atau "diproses dalam 2 detik"'
    )

    contoh_tur_fitur = (
        '"Setelah lihat RTP live, saya pilih slot\n'
        '  dengan angka 94,3% lalu bermain"'
        if bidang == "gambling"
        else '"Setelah membaca daftar fiturnya, saya memilih\n'
        '  paket yang skornya paling tinggi lalu memakainya"'
    )

    # Contoh persen di aturan TITLE ditulis terpisah dari contoh di
    # aturan isi. Keduanya sempat memakai satu variabel, dan itu
    # menukar kalimat aturan title yang sudah disetel ("Bonus 100%",
    # 'Cukup "RTP" atau "Bonus"') dengan kalimat dari blok lain.
    # Aturannya sama, tapi kata-katanya sudah diukur di tempatnya
    # masing-masing.
    contoh_persen_judul = (
        '"RTP 96,4%", bukan "Bonus 100%"'
        if bidang == "gambling"
        else '"98% pelanggan puas", bukan "Diskon 100%"'
    )

    contoh_kata_saja = (
        '"RTP" atau "Bonus"'
        if bidang == "gambling"
        else '"Diskon" atau "Promo"'
    )

    brief = f"""
# MENGISI TEMPLATE HALAMAN

Topik halaman ini: {topik or keyword}

Seluruh halaman membahas satu topik itu saja, dari awal sampai
akhir. Bukan "{keyword}" sebagai bahasan umum, melainkan
"{keyword}" milik {brand_name or "situs ini"} - apa yang
ditawarkannya, bagaimana cara memakainya, apa yang dialami
pemakainya.

Keyword utama: {keyword}
Nama brand: {brand_name or "-"}
Bahasa isi halaman: {language_name}
Negara sasaran: {brand.get("region_label", "Indonesia")}
{baris_brief}
{LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])}
{aturan_brief}
## Yang Perlu Diketahui Dari Halaman Pertama Google
Intent pencarian: {insight.get("search_intent", "-")}
Ringkasan SERP: {insight.get("serp_summary", "-")}

Celah konten yang bisa diambil:
{format_list(insight.get("content_gaps", []), limit=6)}
{format_must_cover(insight, with_reason=False)}{blok_tema_serp}{blok_tanya_serp}{serp_word_bank(analysis)}{format_style_examples(keyword, brand_name, brand.get("variation", ""), language_code, bidang)}
# ATURAN

- Teks artikel — title, meta_description, h1, heading, paragraph,
  faq_question, faq_answer, review_text, caption, list_item —
  harus tentang "{topik or keyword}" dan tidak boleh melenceng ke
  topik lain, apa pun bunyi teks lama yang digantikan.
- Data SERP di atas adalah bahan KATA, bukan teks untuk disalin.
  Kosakatanya dipakai - istilah, sebutan, cara orang menamai hal
  yang dicarinya - tapi kalimatnya tidak. Jangan memindahkan judul,
  pertanyaan, atau kalimat milik situs lain ke halaman ini. Kalau
  ada bahan di daftar itu yang tidak nyambung dengan
  "{keyword}", abaikan bahannya - lebih baik menulis lebih
  sedikit daripada menempelkan kalimat yang tidak ada
  hubungannya dengan halaman ini.
- nav_label, table_cell, dan label BUKAN tempat menaruh
  "{keyword}". Itu tulisan di menu, tombol, dan sel tabel, dan
  masing-masing menunjuk ke sesuatu yang benar-benar ada di situs
  ini. Yang diminta di situ padanan dari teks lamanya: artinya
  tetap, bahasanya yang menyesuaikan. Halaman dengan ratusan menu
  yang seluruhnya berbunyi variasi "{keyword}" tidak bisa dipakai
  siapa pun dan terbaca sebagai spam oleh mesin pencari.
- Jangan menulis teks yang sama dua kali, dan jangan menulis dua
  teks yang isinya sama dengan susunan kata berbeda. Yang diperiksa
  isinya, bukan hurufnya.
- Tulis ulang dengan kalimatmu sendiri. Jangan menyalin susunan
  kalimat teks lama, karena halaman ini harus berdiri sebagai
  tulisan baru, bukan versi ubahan.
- Batas karakter itu keras. Teks yang lebih panjang akan merusak
  tata letak halaman, karena kolom dan kartunya sudah dipatok.
- nav_label, table_cell, dan label ditulis sesingkat mungkin,
  tanpa titik di akhir, dan jangan berupa kalimat. Menu yang
  isinya kalimat akan memecah header halaman ke dua baris.
- faq_question harus benar-benar berupa pertanyaan, diakhiri tanda
  tanya, dan pertanyaan yang wajar diajukan orang yang hendak
  memakai {brand_name or "situs ini"} - bukan pertanyaan
  ensiklopedia tentang "{keyword}" pada umumnya.
{topik_faq}
  Ini permintaan pengguna, dan sebabnya ada di halaman yang terbit:
  blok FAQ-nya berisi "What Sets ASG Apart?" dan "Why Study at
  ASG??" - pertanyaan milik pemilik template, tentang sebuah
  sekolah, di halaman yang topiknya sudah lain sama sekali.
  Pertanyaan yang tidak nyambung dengan topik halaman ini lebih baik
  tidak ditulis sama sekali; yang kosong ditambal NEIIU sendiri.
- Jangan menyalin, menerjemahkan, atau menata ulang pertanyaan yang
  sudah berdiri di template. Pertanyaan yang cuma ditukar nama
  brandnya dihitung sebagai tidak menjawab.
- Yang ditanyakan harus hal yang DIJANJIKAN TITLE halaman ini.
  Orang membuka FAQ karena judulnya menjanjikan sesuatu dan mereka
  ingin tahu syaratnya. Kalau judulnya tentang deposit sekejap,
  pertanyaannya soal cara, syarat, batas, dan apa yang terjadi
  kalau gagal - bukan soal grafis permainan atau sejarah situsnya.
- Tulis pertanyaan yang PENDEK, di bawah batas karakternya. Pertanyaan
  yang melewati batas dibuang seluruhnya, bukan dipotong - memotong
  pertanyaan menghasilkan pertanyaan yang rusak, bukan yang lebih
  pendek - dan slotnya lalu terbit dengan pertanyaan lama.
- Tiap faq_question menanyakan HAL YANG BERBEDA. Dua pertanyaan
  yang menanyakan hal sama dengan susunan kata berbeda dihitung
  satu dan akan dibuang. "Apa perbedaan A dan B?" dan "Apakah A
  sama dengan B?" adalah satu pertanyaan, bukan dua.
- Tiap faq_question dibuka KATA TANYA YANG BERBEDA. Kalau yang
  pertama dibuka "Apa", yang kedua TIDAK boleh dibuka "Apa" lagi -
  pakai "Bagaimana", "Berapa", "Kapan", "Di mana", "Bisakah",
  "Perlukah", atau padanannya dalam bahasa halaman. Blok FAQ yang
  seluruh pertanyaannya dibuka kata yang sama terbaca seperti satu
  pertanyaan yang ditulis ulang berkali-kali, dan itu justru yang
  membuat pembaca berhenti membacanya.
- faq_answer ke-N adalah jawaban untuk faq_question ke-N. Jawab
  yang ditanyakan, jangan menulis kalimat lain yang kebetulan
  sama topiknya.
- Jangan menambah nomor urut atau awalan seperti "1." yang tidak
  ada di teks lamanya. Kalau teks lamanya memang diawali nomor,
  nomor itu tetap ditulis.
- Setiap teks berdiri sendiri dan langsung berisi, tanpa pembuka.
- Sebut "{brand_name}" di sekitar separuh paragraf, di sebagian
  jawaban FAQ, dan di sebagian ulasan. Bukan di setiap kalimat -
  itu terbaca seperti spam - tapi halaman yang menyebut namanya
  cuma di judul juga gagal, karena pembacanya selesai membaca
  tanpa tahu situs apa yang barusan dibacanya.
- Paragraf yang tidak menyebut namanya pun tetap harus berbicara
  tentang layanannya, bukan tentang "{keyword}" pada umumnya.
  Tulis apa yang bisa dilakukan pemakai di sini, bagaimana
  langkahnya, dan apa bedanya - bukan penjelasan ensiklopedia yang
  cocok ditempel di situs mana pun.
- Nama penulis ulasan tulis sebagai nama orang yang wajar di
  {brand.get("region_label", "Indonesia")}.

{aturan_brand}

{voice_rules(language_code, bidang)}{bagian_angka}- JANGAN mengarang angka DI LUAR yang disebutkan di atas. Angka
  seperti {contoh_angka_karangan}
  yang muncul begitu saja adalah tanda paling cepat bahwa halaman
  ditulis mesin, karena angkanya saling bertabrakan antar paragraf.
  Tulis tanpa angka kalau ragu.

Aturan paragraf artikel:
- paragraph BUKAN kalimat tunggal. Tiap paragraf berisi 3 sampai 6
  kalimat yang saling menyambung: satu kalimat membuka gagasannya,
  kalimat berikutnya menjelaskan atau memberi contohnya, kalimat
  terakhir menutup dengan apa artinya buat pemakai. Paragraf satu
  kalimat terbaca sebagai potongan, bukan sebagai tulisan.
- ISI jatah panjangnya sampai hampir penuh. Jatah tiap paragraf
  disebutkan satu per satu di daftar permintaan, dan angka itu bukan
  plafon yang sebaiknya dijauhi melainkan ukuran yang diminta.
  Paragraf 90 karakter di slot berjatah 500 meninggalkan empat
  perlima ruangnya kosong, dan halaman yang seperti itu di seluruh
  badannya terbaca tipis oleh pembaca maupun mesin pencari.
- Batas panjang tiap paragraf berbeda-beda dan itu disengaja. Yang
  jatahnya besar ditulis panjang, yang jatahnya kecil ditulis
  pendek. Artikel yang seluruh paragrafnya sama panjang terbaca
  seperti daftar yang disamarkan.
- Tiap paragraf melanjutkan sudut pandang yang dipilih di title,
  bukan memulai sudut baru. Kalau titlenya tentang deposit QRIS satu
  detik, paragrafnya membahas deposit itu dari sisi yang
  berbeda-beda - caranya, syaratnya, apa yang terjadi kalau gagal,
  bedanya dengan cara lama - bukan berpindah ke bonus, ke keamanan
  data, lalu ke tampilan ponsel.
- Sebut "{brand_name or 'situs ini'}" satu sampai dua kali dalam
  satu paragraf, bukan di setiap kalimat. Paragraf yang menyebut
  namanya di tiap kalimat terbaca sebagai spam, dan mesin pencari
  menghitungnya begitu juga.
- Tiap paragraf membahas hal yang BERBEDA. Tiga paragraf yang
  ketiganya berbunyi tentang kecepatan deposit adalah satu paragraf
  yang ditulis tiga kali.

Aturan ulasan:
- review_text ISINYA PENGALAMAN, bukan pujian. Tulis satu hal yang
  benar-benar dipakai orang itu, bagaimana jalannya, dan apa yang
  dirasakannya sesudah itu. "Situsnya bagus dan cepat" bukan ulasan;
  "Saya setor lewat QRIS jam dua pagi dan saldonya masuk sebelum
  aplikasi banknya sempat saya tutup" ulasan.
- Kebanyakan ulasan mengisi jatah panjangnya, TAPI jangan semuanya.
  Satu atau dua di antaranya ditulis pendek saja, seperti orang yang
  buru-buru. Lima ulasan yang panjangnya sama persis dan susunannya
  sama persis adalah tanda paling gampang dikenali bahwa ulasannya
  dibuat sekaligus oleh satu mesin - dan itu keluhan pengguna
  tentang halaman ini.
- Jangan semuanya memuji. Satu di antaranya menyebut hal yang
  sempat mengganggu - antre sebentar, harus login ulang, tampilan
  agak sempit di layar kecil - lalu bagaimana akhirnya. Halaman yang
  semua ulasannya bintang lima dan tidak ada satu pun keluhan tidak
  dipercaya siapa pun.
- Ulasan BUKAN tur fitur. {contoh_tur_fitur} itu bunyi orang yang
  sedang memperagakan produk, bukan orang yang sedang bercerita. Yang
  ditulis: apa yang dia lakukan, apa yang terjadi, dan bagaimana
  rasanya - dengan kata-katanya sendiri.
- Yang diceritakan harus hal yang DISEBUT DI TITLE halaman ini.
  Halaman yang judulnya tentang deposit QRIS satu detik tapi
  ulasannya membicarakan grafis permainan sedang memuji hal yang
  bukan janjinya sendiri.
- Setiap ulasan menyoroti hal yang berbeda dan memakai gaya bicara
  yang berbeda. Lima ulasan yang susunan kalimatnya sama terbaca
  sebagai lima ulasan yang ditulis satu orang - dan memang begitu
  adanya.
- review_tag adalah label dua sampai empat kata yang merangkum
  ulasan di ATASNYA, bukan slogan halaman. Ulasan yang bercerita
  tentang setor jam dua pagi ditandai "Proses Malam Hari", bukan
  "Terbaik Dan Terpercaya". Tag yang cocok ditempel di ulasan mana
  pun tidak menandai apa-apa.

Aturan judul kartu:
- card_title menamai keterangan yang berdiri di BAWAHNYA, dan cuma
  itu tugasnya. Judul yang benar bisa dibaca sendirian dan sudah
  memberi tahu isi kartunya; judul yang salah adalah kalimat promosi
  yang sama-sama enak dibaca di kartu mana pun.
- Panjangnya dua sampai lima kata, tanpa titik di akhir. Ini judul
  di dalam kotak, bukan kalimat.
- Keenam judul kartu menyebut hal yang BERBEDA. Enam judul yang
  semuanya berbunyi tentang kecepatan adalah satu judul yang ditulis
  enam kali, dan pembaca berhenti membaca di kartu kedua.
- Nomor urut di depan judul lama tetap ditulis kalau memang ada di
  situ. Satu kartu tanpa nomor di antara lima kartu bernomor lebih
  kelihatan daripada enam kartu yang semuanya tidak bernomor.

Aturan title dan meta_description:
- KEDUANYA BUKAN TEKS YANG SAMA, dan bukan versi panjang-pendek dari
  satu kalimat. Title adalah papan nama: siapa ini dan tentang apa,
  dibaca dalam satu tarikan napas. Deskripsi adalah alasan mengklik:
  apa yang didapat pembaca kalau masuk, hal yang TIDAK muat di
  judul. Kalau deskripsimu bisa dipotong jadi title, atau titlemu
  tinggal disambung jadi deskripsi, dua-duanya salah.
- Contoh title dan contoh deskripsi di bawah ditulis dari dua berkas
  yang berbeda, dan bedanya sengaja. Tiru yang sesuai peruntukannya,
  jangan dicampur.
- Kalau title halaman ini sudah tertulis di bagian "Sudut Pandang
  Halaman Ini", deskripsinya melanjutkan sudut itu dengan
  KETERANGAN BARU - cara pakainya, syaratnya, apa yang dirasakan
  pemakainya - bukan menuliskan ulang kalimat judulnya.
- Katanya diambil dari "Bahan Kata Untuk Title Dan Deskripsi" di
  atas. Itu sebabnya halaman pertama Google dianalisis lebih dulu:
  supaya kedua teks ini ditulis dengan kata yang memang dipakai
  orang mencari, bukan dengan kata yang kebetulan terpikir.
- Panjangnya sudah ditentukan di daftar permintaan dan itu bukan
  saran. Teks yang berhenti di separuh jatahnya membuang baris yang
  diberikan Google, dan separuh yang terbuang itu justru tempat kata
  pencarian tambahan seharusnya berdiri.
- Cara mengisi jatah itu BERBEDA untuk keduanya, dan jangan
  dipertukarkan. Deskripsi diisi dengan menambah keterangan: cara
  pakainya, siapa yang memakainya, apa yang didapat. Title diisi
  dengan memilih kata yang lebih tepat untuk SATU janji yang sama -
  bukan dengan menambah janji kedua. Judul yang jatahnya dipenuhi
  dengan cara menumpuk janji adalah judul yang dikeluhkan pembacanya
  sebagai "kaku dan terputus".
- Untuk keduanya, jangan memakai kata pengisi seperti "terbaik" atau
  "terpercaya" untuk mengejar panjang.
- Bagian yang paling penting ditulis di DEPAN. Google memotong
  tampilannya di sekitar 60 karakter untuk title dan 155 untuk
  deskripsi, jadi nama situs dan janji utamanya harus sudah lewat
  sebelum titik itu. Sisanya tetap dibaca mesin pencari.
- Keduanya menentukan nada seluruh halaman, jadi tulis dengan
  gaya di bagian contoh: langsung, bertenaga, dan memakai satu
  sudut pandang yang khas. Kalimat serba umum yang cocok untuk
  situs mana pun adalah kegagalan di sini.
- BENTUK TITLE SUDAH DIPATOK dan bukan pilihanmu. Tiga bagian, urut,
  tidak boleh ditukar dan tidak boleh ditambah bagian keempat:

    1. nama situs "{brand_name}", berdiri PALING DEPAN dan sendirian
    2. topik halaman ini, sekali saja
    3. SATU manfaat atau keterangan - apa yang didapat pembaca, atau
       hal yang belum diketahuinya sebelum membuka halaman ini

  Tanda pisah antara bagian 1 dan 2 dipasang NEIIU sesudah jawabanmu,
  jadi kamu tidak perlu - dan tidak boleh - menulis tanda pisah
  sendiri.
    benar : {contoh_judul["benar_bentuk"]}
    salah : {contoh_judul["salah_tengah"]}
    salah : {brand_name} menghadirkan layanan dengan sistem modern
  Yang kedua salah karena nama situs berdiri di tengah kalimat. Yang
  ketiga salah karena namanya melebur jadi subjek kalimat. Keduanya
  membuat pembaca hasil pencarian tidak punya satu titik pun untuk
  berhenti dan tahu ini situs apa - dan itulah satu-satunya tugas
  sebuah title.
- Bagian 3 diisi KETERANGAN, bukan kata sifat. Ini aturan terpenting
  di seluruh brief ini, dan yang paling sering dilanggar. Judul yang
  terbit dari sini pernah berbunyi:

    {contoh_judul["tumpukan"]}

  Enam kata pertamanya sudah judul yang utuh. "Akurat 24 Jam Hari"
  bukan kelanjutannya melainkan empat kata yang didempetkan di
  belakangnya supaya jatah panjangnya terpenuhi. Susunan itu tidak
  berbunyi seperti bahasa Indonesia sama sekali: tidak ada kata
  sambung, tidak ada yang diterangkan, dan "24 Jam" berdiri tanpa
  menyebut apa yang berlangsung 24 jam. Pembaca hasil pencarian
  langsung tahu judul seperti itu ditulis untuk mesin.
  Kalau judulmu masih kurang panjang, yang ditambah keterangan yang
  MENERANGKAN sesuatu - untuk siapa, dipakai kapan, apa yang tidak
  perlu disiapkan, berapa lama - bukan kata sifat berikutnya:
    salah : {contoh_judul["salah_sifat"]}
    benar : {contoh_judul["benar_sifat"]}
  Kalau tidak ada keterangan yang benar-benar kamu ketahui, judulnya
  berhenti lebih pendek. Judul pendek yang berbahasa Indonesia jauh
  lebih baik daripada judul panjang yang ekornya tumpukan kata.
- Kata ini TIDAK BOLEH berdiri dua-dua atau tiga-tiga berdampingan di
  ekor judul: akurat, terbaru, terkini, terupdate, terpercaya,
  terbaik, resmi, asli, lengkap, mantap, pasti, dijamin, aman, cepat,
  mudah, hari ini, 24 jam, nonstop, nomor satu. Satu boleh, kalau
  memang menutup kalimatnya. Dua ke atas berarti judulnya diminta
  ulang.
- Janjinya ditulis Dengan Huruf Kapital Di Tiap Kata, kecuali kata
  sambung pendek seperti "dan", "di", "untuk", "dengan". Bentuk itu
  yang dipakai seluruh contoh title di bawah.
- SUDUT JUDUL HALAMAN INI KAMU YANG MENENTUKAN. Orang yang mengetik
  "{keyword}" sedang mencari sesuatu yang tertentu; putuskan sendiri
  apa yang paling berguna dijanjikan kepadanya - bisa soal cara
  masuk, cara mulai, apa yang tersedia, apa yang perlu disiapkan,
  atau hal lain yang benar-benar ada di halaman ini - lalu tulis satu
  judul yang menjanjikan hal itu saja.
- JANGAN memaksakan kosakata apa pun ke dalam judul. Angka, persen,
  "sumber data", "terbaru", "diperbarui", "RTP", "maxwin", "gampang
  menang" - kalau sudut yang kamu pilih tidak benar-benar
  membutuhkannya, jangan ditulis. Judul yang menempelkan kata-kata
  itu supaya terlihat lengkap terbaca seperti daftar keyword, bukan
  seperti kalimat yang ditulis orang.
- SATU gagasan untuk satu judul. Dua atau tiga janji yang
  didempetkan bukan judul yang lebih kaya - ia judul yang tidak
  menjanjikan apa-apa, karena pembaca hasil pencarian membacanya
  sambil lalu dan cuma menangkap yang pertama.
- JANGAN menyalin kalimat perintah ini ke dalam judul. Judul ditulis
  untuk pembaca hasil pencarian, bukan untuk menjawab daftar ini.
- Judulnya harus SELESAI sebagai kalimat. Jangan menempelkan kata di
  ujungnya cuma supaya panjangnya cukup - judul yang berakhir
  "..., Kemenangan" atau "..., Aman" adalah judul yang ekornya tidak
  terikat ke kalimat sebelumnya, dan itu dihitung gagal meskipun
  panjangnya pas. Kalau kehabisan bahan, berhenti lebih pendek.
- Judul yang "benar tapi datar" dihitung GAGAL di sini. "{contoh_judul["datar"]}" tidak salah satu kata pun, dan justru
  itu soalnya: ia cocok untuk situs mana saja, jadi pembaca sudah
  pernah membacanya di tempat lain. Contoh title di bawah ini milik
  pengguna, dan lihat betapa jauh bedanya - ada yang menjulukinya
  tambang, kampus, atau markas; ada yang membuka seperti kabar; ada
  yang bercerita tentang seseorang. Tiru KEBERANIANNYA, jangan tiru
  kalimatnya.
- Judul yang kata-katanya sama dengan judul halaman lain untuk topik
  ini akan DIBUANG dan diminta ulang, meskipun urutan katanya kamu
  tukar. Yang diperiksa kosakatanya, bukan susunannya.
- Judul ditulis SATU TARIKAN NAPAS: satu janji, bukan tiga janji yang
  ditumpuk. Judul yang menyebutkan dua atau tiga hal sekaligus
  terbaca sebagai potongan yang disambung, dan pembaca hasil
  pencarian berhenti di potongan pertama.
    salah : {contoh_judul["salah_tumpuk"]}
    benar : {contoh_judul["benar_tunggal"]}
  Yang salah bukan panjangnya melainkan bahwa ia tiga judul yang
  didempetkan. Yang benar panjangnya hampir sama, tapi seluruhnya
  satu kalimat: satu topik, satu keterangan, dan tiap katanya
  menerangkan kata di sebelahnya. Kalau sebuah kata bisa dibuang
  tanpa mengubah janjinya, buang.
- JANGAN menulis angka persen di title MAUPUN di meta description.
  Bukan {contoh_persen_judul}, bukan "88%" - tidak satu
  angka pun yang diikuti tanda persen, berapa pun nilainya. Cukup
  {contoh_kata_saja}, dan itu pun hanya kalau sudut halaman ini
  memang tentang hal itu.
  Angka di dua tempat ini memakan ruang yang seharusnya dipakai
  janjinya, angka persisnya bukan yang dicari orang di hasil
  pencarian, dan angka yang sama muncul di puluhan halaman adalah
  tanda paling cepat bahwa halamannya dibuat mesin.
- meta_description WAJIB DIBUKA NAMA SITUS. Kata pertamanya nama
  situs, lalu satu kata kerja yang menyatakan apa yang
  disediakannya: menyediakan, menghadirkan, menyajikan, menawarkan,
  menjamin, atau adalah.
    salah : "Pemain baru bisa mulai bermain slot online di NAMA ..."
    benar : "NAMA menghadirkan slot online yang bisa dibuka ..."
  Jangan dibuka dengan menyapa pembaca dan jangan dibuka dengan
  kata kerja tanpa pelakunya. Nama situs berdiri di depan supaya
  pembaca hasil pencarian tahu situs mana yang sedang menawarkan,
  sebelum ia membaca apa yang ditawarkan.
- Sudut pandang yang dipilih di title dipakai lagi di h1,
  paragraf, FAQ, dan ulasan. Satu halaman satu sudut pandang.
{bagian_riwayat}""".strip()

    # Mulai dari sini isinya berbeda tiap giliran.
    permintaan = f"""
# YANG HARUS KAMU TULIS SEKARANG

Halamannya memakai template yang sudah jadi, jadi jumlah teksnya
tidak boleh dikira-kira. Tulis persis sebanyak ini:

{chr(10).join(kebutuhan)}
{bagian_tema}{bagian_cetakan}{bagian_artikel}{bagian_contoh_tanya}{bagian_tanya}{bagian_fungsi}{bagian_bentuk}{bagian_padanan}{bagian_terpakai}""".rstrip()

    # Daftar larangan berdiri PALING BAWAH, sesudah blok permintaan.
    #
    # Isinya sudah disebut di brief, dan diulang di sini bukan karena
    # lupa: yang dibaca terakhir yang paling berpengaruh pada model
    # kecil, dan brief di jalur ini panjangnya ribuan token. Aturan
    # yang berdiri di sepertiga awal prompt selebar itu terbukti
    # dilewati - lihat keterangan di forbidden_claims_block.
    #
    # Diletakkan di blok permintaan, BUKAN di brief. Brief harus tetap
    # identik antar giliran supaya cache prompt Ollama tidak batal,
    # dan blok ini memang berubah-ubah panjangnya mengikuti bidang.
    # Isinya sendiri tetap sepanjang satu run, jadi tidak ada yang
    # hilang dari sisi mutu.
    larangan = forbidden_claims_block(brand_name, language_code, bidang)

    return (
        content_planner_system_prompt(language_code),
        f"{brief}\n\n{permintaan}\n\n{larangan}",
    )

