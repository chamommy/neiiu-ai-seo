"""
Prompt untuk pipeline NEIIU: analisis SERP dan rencana konten.

Prompt di sini sengaja memadatkan data hasil crawl jadi angka dan
daftar pendek. Model lokal punya jendela konteks terbatas, jadi
memberi ringkasan terstruktur jauh lebih akurat daripada
menempelkan seluruh isi halaman kompetitor.
"""

import hashlib
import re

from pathlib import Path

from ai.schemas import META_MAX, META_MIN, TITLE_MAX, TITLE_MIN
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
    r"bukan sekadar[^.]{0,60}\b(tapi|tetapi|melainkan)\b|"
    r"tidak hanya[^.]{0,60}\b(tapi|tetapi)\b juga|"
    r"pengalaman bermain yang optimal|solusi cerdas",
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
MIN_VOICE_POOL = 3


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
) -> str:
    """
    Bagian prompt berisi contoh gaya, siap ditempel ke brief.

    Contoh title dan contoh deskripsi ditulis di bawah keterangan
    yang berbeda. Digabung jadi satu daftar, model membaca contoh
    deskripsi 181 karakter sebagai contoh title juga, lalu menulis
    title yang dipotong di batasnya - potongan yang justru membuang
    ajakan di akhir kalimatnya.
    """
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
TITLE_ANGLES = (
    "jam main dan pola yang lagi jalan hari ini",
    "link login dan cara masuk waktu link utama susah dibuka",
    "cara daftar akun dan apa saja yang disiapkan",
    "deposit dan penarikan - QRIS, e-wallet, dan berapa lama cair",
    "bonus dan promo, terutama untuk yang baru gabung",
    "daftar permainan dan penyedia yang tersedia",
    "main dari HP: aplikasi, browser, dan kuota yang dipakai",
    "keamanan akun dan data yang dipegang situs",
    "RTP live dan dari mana datanya diambil",
    "layanan bantuan dan berapa cepat dibalas",
    "komunitas pemain dan tempat bertukar pola",
    "panduan buat yang baru pertama kali main slot",
)


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
TITLE_FRAMES = (
    "julukan atau kiasan - situsnya diibaratkan sesuatu "
    "(tambang, kampus, markas, pasar, bengkel)",
    "kabar atau pengumuman, seperti berita yang baru masuk",
    "cerita satu orang, seperti kalimat pembuka sebuah kisah",
    "ajakan langsung ke pembaca, memakai kata \"kamu\"",
    "perbandingan sebelum dan sesudah",
    "pertanyaan yang langsung dijawab di judul itu juga",
    "pernyataan pendek dan tegas, tanpa hiasan sama sekali",
    "sebutan tempat atau markas, seolah situsnya sebuah lokasi",
)


# Nama penanda yang dipakai mencatat sudut dan cara judul halaman ini
# ke riwayat, supaya halaman berikutnya bisa menghindarinya.
#
# Berawalan garis bawah karena ia bukan slot: tidak pernah terbit di
# halaman, cuma dititipkan di dalam isi supaya ikut tersimpan. Harus
# sama dengan MARK_ROLES di database/neiiu_history_db.py.
TITLE_ANGLE_MARK = "_title_angle"
TITLE_FRAME_MARK = "_title_frame"


def rotate_pick(daftar: tuple, benih: int, dipakai=()) -> str:
    """
    Satu pilihan dari daftar, digilir dan MENGHINDARI yang sudah dipakai.

    Benih menentukan dari mana giliran dimulai; riwayat menentukan mana
    yang dilewati. Pengguna memintanya dengan kalimat "kalau sudah pakai
    topik A, berikutnya jangan dipakai lagi, ganti topik B".

    Benih saja tidak cukup untuk itu. sha1 tidak tahu apa yang sudah
    terbit, jadi halaman kedua punya satu dari dua belas kemungkinan
    mendarat di sudut yang persis sama dengan halaman pertama - dan
    kemungkinan itu tetap ada berapa pun rapinya benih disusun. Yang
    memastikan topiknya berganti cuma daftar apa yang sudah dipakai.

    Kalau seluruh daftar sudah pernah dipakai, yang diambil yang PALING
    LAMA tidak dipakai. Riwayat berurut dari yang terbaru, jadi urutan
    daftarnya sekaligus umurnya.
    """
    urutan = [
        daftar[(benih + langkah) % len(daftar)]
        for langkah in range(len(daftar))
    ]

    umur: dict[str, int] = {}

    for nomor, teks in enumerate(dipakai or ()):
        # setdefault, bukan penugasan: kalau satu pilihan muncul dua
        # kali di riwayat, yang berlaku pemakaian TERBARU.
        umur.setdefault(" ".join(str(teks).split()).casefold(), nomor)

    paling_tua = len(daftar) + len(umur) + 1

    # Yang belum pernah dipakai dihitung paling tua, jadi ia menang
    # lebih dulu. Seri dimenangkan yang paling awal di urutan benih,
    # karena max() mempertahankan yang pertama ditemukannya.
    return max(
        urutan,
        key=lambda pilihan: umur.get(
            " ".join(str(pilihan).split()).casefold(),
            paling_tua,
        ),
    )


def pick_title_frame(
    brand_name: str,
    keyword: str,
    variation: str = "",
    dipakai=(),
) -> str:
    """
    Memilih satu cara bercerita untuk judul halaman ini.

    Benihnya dibedakan dari pick_title_angle supaya sudut dan caranya
    tidak bergerak bersamaan - kalau benihnya sama, dua belas sudut
    kali delapan cara cuma menghasilkan dua belas kombinasi, bukan
    sembilan puluh enam.

    "dipakai" adalah cara bercerita halaman-halaman sebelumnya, terbaru
    lebih dulu.
    """
    benih = hashlib.sha1(
        "{}|{}|{}|cara".format(
            brand_name.strip().casefold(),
            keyword.strip().casefold(),
            variation,
        ).encode("utf-8")
    ).digest()

    return rotate_pick(TITLE_FRAMES, benih[3], dipakai)


def pick_title_angle(
    brand_name: str,
    keyword: str,
    variation: str = "",
    dipakai=(),
) -> str:
    """
    Memilih satu sudut judul untuk halaman ini.

    Benihnya sama bentuknya dengan title_separator() dan
    build_number_set(), dan alasannya sama: hasilnya tetap sama tiap
    kali halaman yang sama dibuat ulang, tapi berbeda antara satu
    halaman dan halaman berikutnya.

    "dipakai" adalah sudut halaman-halaman sebelumnya untuk topik ini,
    terbaru lebih dulu; yang ada di situ tidak dipilih lagi selama
    masih ada sudut yang belum pernah dipakai.
    """
    benih = hashlib.sha1(
        "{}|{}|{}|sudut".format(
            brand_name.strip().casefold(),
            keyword.strip().casefold(),
            variation,
        ).encode("utf-8")
    ).digest()

    return rotate_pick(TITLE_ANGLES, benih[0], dipakai)

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
VOICE_RULES = """Aturan bunyi tulisan — berlaku untuk SEMUA teks di atas:
- Tulis seperti orang yang mengurus situs ini sendiri dan sedang
  menjelaskannya ke calon pemakai. Bukan seperti brosur perusahaan,
  bukan seperti dokumen produk.
- Subjek kalimatnya ORANG, bukan benda. Tulis "kamu bisa lihat
  angkanya di layar", bukan "sistem menampilkan angka kepada
  pengguna". Kalimat yang subjeknya "sistem", "teknologi", "proses",
  "layanan", atau "platform" berturut-turut adalah tanda paling jelas
  bahwa tulisannya dibuat mesin.
- Kalimat berikut DILARANG dipakai, termasuk bentuk miripnya:
  "di era digital", "hal ini membuat", "dirancang untuk",
  "salah satu faktor utama", "salah satu keunggulan utama",
  "teknologi yang digunakan", "memungkinkan pengguna",
  "memungkinkan kamu", "sehingga pengguna dapat", "aspek penting",
  "seluruh proses", "mengutamakan efisiensi",
  "tanpa perlu intervensi manusia", "data kinerja",
  "sistem pengolahan data", "secara transparan", "terukur dan",
  "berbasis data", "solusi cerdas", "pengalaman bermain yang optimal".
- DUA SUSUNAN KALIMAT INI DILARANG, dan keduanya diambil dari halaman
  yang dikeluhkan pengguna karena "terlihat AI banget":
    "Tidak hanya menampilkan angka, tapi juga menggambarkan pola ..."
    "Slot gacor bukan sekadar permainan yang sering menang, tapi ..."
  Bentuk "bukan sekadar X, tapi Y" dan "tidak hanya X, tapi juga Y"
  adalah cara mesin membuat satu gagasan terdengar seperti dua. Orang
  menulis gagasannya langsung: "Yang ditampilkan bukan cuma angkanya.
  Polanya kelihatan juga." Kalau sebuah kalimat butuh dua sisi untuk
  berdiri, pecah jadi dua kalimat.
- Kata "secara" hampir selalu bisa dibuang. "Diperbarui secara
  otomatis" sama artinya dengan "diperbarui sendiri", dan yang kedua
  itu yang ditulis orang. Satu halaman paling banyak memakai "secara"
  dua kali.
- ANGKA PERSEN PALING BANYAK DISEBUT DUA KALI di seluruh halaman, dan
  tidak sekali pun di ulasan. Terukur pada halaman yang dikeluhkan
  pengguna: satu angka desimal yang sama muncul 18 kali di teks yang
  dibaca orang, termasuk di kelima ulasan sekaligus. Tidak ada lima
  orang yang menulis pengalamannya dan kelimanya menyebut angka
  desimal yang sama persis - itu satu-satunya tanda yang bisa dilihat
  pembaca tanpa membandingkan apa pun. Sebut "RTP-nya lagi bagus" atau
  "angkanya lagi tinggi"; angka persisnya biar berdiri di tabel.
- Panjang kalimatnya berganti-ganti. Kalimat pendek boleh berdiri
  sendiri. Paragraf yang semua kalimatnya sama panjang dan sama
  susunannya terbaca seperti daftar yang disamarkan.
- Boleh memakai kata sehari-hari yang memang dipakai orang untuk
  topik ini - "nggak", "udah", "bikin", "langsung", "tinggal" - asal
  tidak berlebihan. Bahasa yang terlalu rapi justru mencurigakan."""


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
  dana dan data pemain aman, deposit dan withdraw diproses cepat,
  yang menang dibayar, layanan bisa dihubungi kapan saja,
  pilihan permainannya lengkap, situsnya bisa dibuka dari mana saja.
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
- ANGKA yang tidak diberikan ke halaman ini: jumlah member, tahun
  berdiri, nomor lisensi, angka RTP, winrate, jumlah penghargaan,
  lama proses dalam detik. "{brand_name}" boleh berlisensi tanpa
  membuat angka-angka itu jadi ada, dan angka karangan adalah satu-
  satunya klaim di halaman ini yang bisa dibantah orang lain dengan
  bukti.
- Janji bahwa PEMBACANYA akan menang, untung, atau balik modal.
  Menulis "{brand_name}" sanggup membayar adalah pernyataan tentang
  brandnya dan itu boleh; menulis pembacanya pasti menang adalah
  pernyataan tentang hasil judi dan itu ditolak hampir semua
  platform iklan - yang rugi justru brand berlisensi, karena ia yang
  punya sesuatu untuk dicabut."""


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
            tujuan.append(
                f"\n{role} — tulis ulang, JANGAN salin yang di bawah:"
            )
            tujuan.extend(
                f"  [{nomor}] DILARANG menulis ini lagi: {teks}"
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
        tujuan.append(f"\n{role} — ganti berurutan:")
        tujuan.extend(
            f"  [{nomor}] {teks}"
            for nomor, teks in enumerate(contoh, start=1)
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

        tanya = [
            semua_tanya[index] if index < len(semua_tanya) else ""
            for index in urutan
        ]

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
    bagian_angka = (
        "- JANGAN menulis angka persen sama sekali. Bukan \"RTP "
        "96,4%\", bukan \"RTP di atas 96%\", bukan angka apa pun yang "
        "diikuti tanda persen.\n"
        "  Pengguna sudah menyatakannya dengan jelas: berapa persis "
        "angkanya tidak penting. Yang dicari pembaca bukan angkanya "
        "melainkan apakah sedang bagus atau tidak, jadi tulis "
        "\"RTP-nya lagi tinggi\", \"angkanya lagi stabil\", \"lagi "
        "bagus sejak pagi\" - kalimat yang memang dipakai orang.\n"
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
        terpakai: list[str] = []

        for role in REPEAT_PRONE_ROLES:
            if role not in spec:
                continue

            terpakai.extend(
                str(teks).strip()
                for teks in (sudah.get(role) or [])
                if str(teks).strip()
            )

        # Yang terakhir ditulis yang paling perlu diingat, karena
        # itulah yang paling mungkin diulang.
        terpakai = list(dict.fromkeys(reversed(terpakai)))[
            :MAX_USED_REMINDERS
        ]

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
    sudut_judul = pick_title_angle(
        brand_name,
        keyword,
        brand.get("variation", ""),
        (riwayat or {}).get(TITLE_ANGLE_MARK) or (),
    )

    cara_judul = pick_title_frame(
        brand_name,
        keyword,
        brand.get("variation", ""),
        (riwayat or {}).get(TITLE_FRAME_MARK) or (),
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

{LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])}

## Yang Perlu Diketahui Dari Halaman Pertama Google
Intent pencarian: {insight.get("search_intent", "-")}
Ringkasan SERP: {insight.get("serp_summary", "-")}

Celah konten yang bisa diambil:
{format_list(insight.get("content_gaps", []), limit=6)}
{format_must_cover(insight, with_reason=False)}{blok_tema_serp}{blok_tanya_serp}{serp_word_bank(analysis)}{format_style_examples(keyword, brand_name, brand.get("variation", ""))}
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
- ISI FAQ SEPUTAR SLOT, dan cuma itu: cara mainnya, cara daftar,
  deposit dan penarikan, bonus, main dari HP, keamanan akun, arti
  istilah yang dipakai pemain. Ini permintaan pengguna, dan sebabnya
  ada di halaman yang terbit: blok FAQ-nya berisi "What Sets ASG
  Apart?" dan "Why Study at ASG??" - pertanyaan milik pemilik
  template, tentang sebuah sekolah, di halaman slot. Pertanyaan yang
  tidak nyambung dengan slot lebih baik tidak ditulis sama sekali;
  yang kosong ditambal NEIIU dengan tanya-jawab seputar slot.
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

{VOICE_RULES}{bagian_angka}- JANGAN mengarang angka DI LUAR yang disebutkan di atas. Angka
  seperti "100.000+ spin per hari" atau "diproses dalam 2 detik"
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
- Ulasan BUKAN tur fitur. "Setelah lihat RTP live, saya pilih slot
  dengan angka 94,3% lalu bermain" itu bunyi orang yang sedang
  memperagakan produk, bukan orang yang sedang bercerita. Yang
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
    benar : {brand_name} Update Pola Slot Gacor Tiap Pagi Buat
            Pemain Baru
    salah : Rahasia Spin di {brand_name} Yang Membuka Peluang
    salah : {brand_name} menghadirkan layanan dengan sistem modern
  Yang kedua salah karena nama situs berdiri di tengah kalimat. Yang
  ketiga salah karena namanya melebur jadi subjek kalimat. Keduanya
  membuat pembaca hasil pencarian tidak punya satu titik pun untuk
  berhenti dan tahu ini situs apa - dan itulah satu-satunya tugas
  sebuah title.
- Bagian 3 diisi KETERANGAN, bukan kata sifat. Ini aturan terpenting
  di seluruh brief ini, dan yang paling sering dilanggar. Judul yang
  terbit dari sini pernah berbunyi:

    {brand_name} | Update Pola Slot Gacor Tiap Pagi 2026 Akurat 24
    Jam Hari

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
    salah : {brand_name} Deposit QRIS Cepat Aman Terpercaya Resmi
    benar : {brand_name} Deposit QRIS Tanpa Potongan Buat Pemain Baru
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
- SUDUT JUDUL HALAMAN INI SUDAH DIPILIH, dan bukan pilihanmu:
  {sudut_judul}.
  Judulnya berangkat dari situ. Ini bukan saran - halaman lain untuk
  keyword yang sama mendapat sudut yang berbeda, dan kalau semuanya
  kembali ke sudut yang sama, halaman-halaman itu saling berebut
  pembaca yang sama.
- CARA BERCERITANYA JUGA SUDAH DIPILIH: {cara_judul}.
  Sudut menentukan judulnya tentang apa; ini menentukan bagaimana ia
  diucapkan. Keduanya harus terasa di judul yang kamu tulis.
- Judul yang "benar tapi datar" dihitung GAGAL di sini. "Slot Gacor
  Update Harian RTP Terbaru" tidak salah satu kata pun, dan justru
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
    salah : {brand_name} Slot Gacor 2026 Update Harian Live Terbaru
            Paling Akurat
    benar : {brand_name} Update Pola Slot Gacor Tiap Pagi Buat
            Pemain Baru
  Yang salah bukan panjangnya melainkan bahwa ia tiga judul yang
  didempetkan. Yang benar panjangnya hampir sama, tapi seluruhnya
  satu kalimat: satu topik, satu keterangan, dan tiap katanya
  menerangkan kata di sebelahnya. Kalau sebuah kata bisa dibuang
  tanpa mengubah janjinya, buang.
- JANGAN menulis angka persen di title MAUPUN di meta description.
  Bukan "RTP 96,4%", bukan "Bonus 100%", bukan "88%" - tidak satu
  angka pun yang diikuti tanda persen, berapa pun nilainya. Cukup
  "RTP" atau "Bonus", dan itu pun hanya kalau sudut halaman ini
  memang tentang hal itu.
  Angka di dua tempat ini memakan ruang yang seharusnya dipakai
  janjinya, angka persisnya bukan yang dicari orang di hasil
  pencarian, dan angka yang sama muncul di puluhan halaman adalah
  tanda paling cepat bahwa halamannya dibuat mesin.
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

    return (
        content_planner_system_prompt(language_code),
        f"{brief}\n\n{permintaan}",
    )


def build_content_plan_prompt(
    analysis: dict,
    insight: dict,
    template: dict,
    brand: dict,
) -> tuple[str, str]:
    """
    Menyusun prompt untuk membuat isi landing page baru.
    """
    keyword = analysis["keyword"]
    blueprint = analysis["blueprint"]
    target = blueprint["target"]

    # Target panjang diambil dari top 5, bukan rata-rata semua,
    # supaya halaman baru mengejar yang benar-benar menang.
    word_target = int(
        max(
            target["word_count_top5_median"],
            target["word_count_median"],
            900,
        )
    )

    section_target = max(int(target["h2_median"]), 5)
    section_target = min(section_target, 9)

    structure_text = format_list(
        [
            f"{section['order']}. {section['type']} "
            f"({section['level']}, {section['subheading_count']} subheading)"
            for section in template["structure"]
        ],
        limit=12,
    )

    disclaimer_rule = (
        "- Sisipkan nada informatif dan netral, bukan ajakan berlebihan."
        if brand.get("disclaimer")
        else "- Fokus ke informasi yang berguna untuk pembaca."
    )

    brand_name = brand.get("site_name", "").strip()
    language_code = brand.get("region", "id")
    language_name = brand.get("language_name", "Indonesia")
    aturan_brand = brand_confidence_rules(brand)

    blok_tema_wajib = blok_daftar(
        "## Tema Yang Wajib Disinggung",
        [item["term"] for item in blueprint["heading_topics"]],
        limit=12,
    )

    blok_entity = blok_daftar(
        "## Entity Yang Sering Muncul Di Kompetitor",
        [item["entity"] for item in blueprint["common_entities"]],
        limit=12,
    )

    blok_tanya_faq = blok_daftar(
        "## Pertanyaan Yang Harus Dijawab Di FAQ",
        blueprint["people_also_ask"] + blueprint["competitor_questions"],
        limit=10,
    )

    user_prompt = f"""
# BRIEF LANDING PAGE BARU

Keyword utama: {keyword}
Nama brand: {brand_name or "-"}
Bahasa isi halaman: {language_name}
Negara sasaran: {brand.get("region_label", "Indonesia")}

{LANGUAGE_ORDERS.get(language_code, LANGUAGE_ORDERS["id"])}

## Bedanya Keyword dan Brand
Keyword "{keyword}" adalah topik yang dicari orang di Google.
Brand "{brand_name}" adalah nama situs yang menyajikan halaman ini.
Keduanya berbeda dan tidak boleh dipertukarkan.

## Hasil Analisis SERP
Intent pencarian: {insight.get("search_intent", "-")}
Ringkasan SERP: {insight.get("serp_summary", "-")}

Bukti yang mendasari intent itu:
{format_list(insight.get("intent_evidence", []), limit=5)}

Celah konten yang bisa diambil:
{format_list(insight.get("content_gaps", []), limit=8)}

Strategi menang:
{format_list(insight.get("winning_strategy", []), limit=8)}
{format_must_cover(insight)}

## Target Yang Harus Dikejar
Total kata halaman: sekitar {word_target} kata
Jumlah section (H2): {section_target} section
Panjang title: {TITLE_MIN} sampai {TITLE_MAX} karakter
Panjang meta description: {META_MIN} sampai {META_MAX} karakter
Keyword density wajar: 0.8% sampai 2%
{serp_word_bank(analysis)}

## Struktur Halaman Acuan Yang Ngerank
Sumber acuan: {template["source_domain"]}
{structure_text}
{blok_tema_wajib}{blok_entity}{blok_tanya_faq}
# TUGAS

Susun isi landing page lengkap:

1. title — memuat brand "{brand_name}" DAN keyword "{keyword}",
   panjangnya {TITLE_MIN} sampai {TITLE_MAX} karakter dan WAJIB
   melewati {TITLE_MIN}. Katanya diambil dari "Bahan Kata Untuk
   Title Dan Deskripsi" di atas, bukan dikarang dari nol.
   Bentuknya dipatok tiga bagian, urut: nama situs "{brand_name}"
   berdiri PALING DEPAN dan sendirian, lalu topiknya, lalu SATU
   keterangan - "{brand_name} {keyword.title()} ...".
   Tanda pisah di antara keduanya dipasang NEIIU sesudah jawabanmu,
   jadi jangan menulis tanda pisah sendiri. Nama situs yang berdiri
   di tengah kalimat, seperti "{keyword.title()} di {brand_name}
   ...", tidak dipakai: pembaca hasil pencarian jadi tidak punya
   satu titik pun untuk berhenti dan tahu ini situs apa.
   Jatah panjangnya diisi KETERANGAN, bukan kata sifat. Kalau
   judulnya masih kurang panjang, yang ditambah untuk siapa, dipakai
   kapan, apa yang tidak perlu disiapkan - bukan "akurat",
   "terpercaya", "24 jam", "hari ini" yang ditumpuk di ekornya.
   Dua kata penyangat berdampingan di ujung judul membuat judulnya
   diminta ulang, dan judul yang berhenti lebih pendek karena
   keterangannya memang tidak ada jauh lebih baik daripada judul
   panjang yang ekornya tumpukan kata.
2. meta_description — {META_MIN} sampai {META_MAX} karakter dan
   WAJIB melewati {META_MIN}, memuat keyword dan sebutkan brand
   "{brand_name}" sekali. Bagian terpentingnya ditulis di depan,
   karena Google memotong tampilannya di sekitar 155 karakter.
3. slug — huruf kecil, dipisah tanda hubung, memuat keyword.
4. h1 — berbeda susunan kata dari title, tetap memuat keyword dan
   brand "{brand_name}".
4b. breadcrumb — jalur letak halaman ini, 2 sampai 4 tingkat, urut
   dari yang paling umum ke halaman ini sendiri.
   - Tingkat pertama selalu beranda: tulis "Beranda" untuk bahasa
     Indonesia, atau padanannya dalam bahasa halaman.
   - Tingkat terakhir adalah halaman ini. Tulis ringkas, 2 sampai 5
     kata, bukan seluruh title.
   - Tingkat di tengah adalah kategori topiknya, diambil dari
     "Topik yang wajib terbahas" dan intent pencarian di atas.
     Ini yang dimaksud jalur berdasarkan riset: kategorinya
     mengikuti apa yang benar-benar dicari orang untuk
     "{keyword}", bukan nama menu yang kebetulan ada di template.
   - Jangan memuat nama brand di tingkat mana pun.
5. intro — 2 sampai 3 paragraf pembuka yang langsung menjawab intent.
6. sections — {section_target} section. Setiap section punya:
   - heading deskriptif
   - type: paragraph, list, table, steps, atau cta
   - paragraphs: isi penjelasan
   - items: poin-poin kalau tipenya list, table, atau steps
   Kalau tipenya paragraph, biarkan items kosong.
   Kalau tipenya list atau steps, isi minimal 4 item.
   Pilihan sectionnya BUKAN karangan bebas: dahulukan "Topik yang
   wajib terbahas" di atas, karena daftar itu hasil membaca halaman
   yang sedang menang di keyword ini. Sisa jatah section baru diisi
   celah konten yang belum digarap kompetitor. Kalau satu topik
   wajib tidak masuk akal untuk halaman ini, lewati topiknya - tapi
   jangan melewatinya cuma karena ada ide lain yang terdengar lebih
   menarik.
7. faq — 6 sampai 8 pertanyaan beserta jawabannya.
8. keywords — variasi keyword turunan yang dipakai di halaman.
9. reviews — 4 ulasan pemakai. Tiap ulasan punya:
   - name: satu nama depan yang lazim di zona ini
   - rating: angka 4.0 sampai 5.0, jangan semuanya 5.0
   - text: 2 sampai 3 kalimat tentang pengalaman memakai
     halaman atau layanannya
   Jangan menulis tanggal. NEIIU yang memasangnya.
10. ratings — 3 aspek layanan yang dinilai. Tiap aspek punya:
   - label: nama aspeknya, misalnya kecepatan akses atau
     kelengkapan pilihan
   - value: angka 4.0 sampai 5.0

Aturan tambahan:
- Total seluruh teks harus mendekati {word_target} kata.
- Jangan mengulang kalimat yang sama di section berbeda.
- Setiap section membahas sudut yang berbeda.
{disclaimer_rule}

{VOICE_RULES}

{aturan_brand}

Aturan brand:
- Sebut "{brand_name}" di paragraf pembuka, sekali saja.
- Sebut "{brand_name}" di section penutup atau CTA.
- Di seluruh halaman, brand cukup muncul 3 sampai 5 kali.
  Menyebutnya di setiap paragraf membuat halaman terbaca seperti
  iklan dan menurunkan kualitasnya di mata pembaca.
- Jangan menulis brand sebagai bagian dari keyword, misalnya
  "{brand_name} gacor". Keduanya berdiri sendiri.

Aturan ulasan:
- Tulis ulasan yang membahas hal yang bisa dilihat sendiri oleh
  pembaca: kecepatan halaman, kemudahan mencari sesuatu,
  kelengkapan informasi, tampilan di ponsel.
- Ulasan boleh menyebut hal yang memang disanggupi "{brand_name}" -
  withdrawnya cair, bantuannya dibalas, situsnya bisa dibuka - dan
  menyebutnya sebagai pengalaman yang sudah terjadi, bukan sebagai
  harapan.
- Jangan menulis ulasan yang menjanjikan hasil, keuntungan, atau
  kemenangan bagi pembacanya. Ulasan semacam itu melanggar aturan
  sebagian besar platform iklan.
- Setiap ulasan menyoroti hal yang berbeda. Empat ulasan yang
  isinya sama terbaca sebagai ulasan yang dibuat satu orang.
""".strip()

    return (
        content_planner_system_prompt(language_code),
        user_prompt,
    )
