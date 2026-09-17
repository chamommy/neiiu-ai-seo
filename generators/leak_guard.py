"""
Menemukan kalimat yang menyalin ISI PERINTAH ke dalam teks yang
terbit.

Model 4B kadang tidak memisahkan "apa yang harus kamu tulis" dari
"apa yang harus kamu tulis TENTANG". Terukur 14
Agustus 2026, meta description terbit berbunyi:

    "... Tidak ada penundaan, tidak ada kata 'mungkin'."

Kalimat kedua bukan tentang brandnya melainkan tentang aturan yang
baru saja dibacanya - brand_confidence_rules melarang kata "mungkin",
dan model menuliskan larangannya alih-alih mematuhinya.

Yang dipakai di sini BUKAN daftar hitam frasa.

Daftar hitam cuma menangkap contoh yang sudah pernah terjadi, dan
kebocoran berikutnya akan berbunyi lain. Yang dipakai perbandingan
dengan PROMPT YANG BENAR-BENAR DIKIRIM di permintaan itu: kalau
sebuah kalimat memuat kosakata yang cuma ada di dalam blok perintah,
kalimat itu berasal dari perintah, apa pun bunyinya.

Empat sinyal, dan tiap sinyal punya alasannya sendiri:

  A. Mengutip istilah yang dikutip perintah. Prompt memuat daftar
     kata terlarang di dalam tanda kutip ("mungkin", "diharapkan").
     Teks terbit yang mengutip salah satunya sedang membicarakan
     kata itu, bukan memakainya.
  B. Berbicara TENTANG kata, bukan dengan kata. "tidak ada kata X",
     "tanpa frasa Y" - bentuk metabahasa yang tidak pernah ditulis
     orang di halaman jualan.
  C. Menyalin potongan panjang dari baris perintah. Diukur dengan
     tumpang tindih tiga-kata terhadap tiap baris perintah.
  D. Berbentuk perintah. "JANGAN ...", "salah :", "maksimal 70
     karakter" - bentuk yang datang dari brief, bukan dari halaman.

Sinyal C dan D berdiri sendiri karena keduanya sudah cukup khas.
Sinyal A digabung dengan B atau dengan konteks, karena mengutip satu
kata saja belum tentu salah - lihat MIN_QUOTED_LENGTH dan
keterangan di leaking_sentences().
"""

import re

# Panjang minimal istilah yang dikutip sebelum dianggap penanda.
#
# Kutipan pendek ("di", "ya") muncul di kalimat biasa dan tidak
# menunjuk apa pun. Empat huruf memisahkan kutipan yang berarti dari
# kutipan yang kebetulan.
MIN_QUOTED_LENGTH = 4

# Tumpang tindih tiga-kata sebelum sebuah kalimat dianggap salinan.
#
# 0.55 diukur terhadap dua kumpulan: kalimat yang benar-benar bocor
# di uji 14 Agustus (0.6-1.0) dan kalimat jualan biasa yang kebetulan
# memakai kosakata yang sama dengan brief - "halaman ini menjelaskan
# cara daftar" terhadap baris brief tentang cara daftar (0.2-0.4).
# Di bawah 0.5 kalimat isi yang wajar mulai ikut tertangkap.
NGRAM_OVERLAP = 0.55

# Panjang n-gram. Tiga kata cukup panjang untuk tidak cocok secara
# kebetulan, cukup pendek untuk tetap cocok saat model menyalin
# sambil menukar satu dua kata.
NGRAM = 3

# Kalimat yang lebih pendek dari ini tidak diadu dengan n-gram.
# Kalimat empat kata cuma punya dua tiga-gram, dan satu yang cocok
# sudah membuat skornya melewati ambang apa pun.
MIN_NGRAM_WORDS = 8

WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# Kutipan di dalam prompt. Tiga bentuk tanda kutip sekaligus karena
# prompt memakai ketiganya.
QUOTED = re.compile(r"[\"“”']([^\"“”'\n]{2,60})[\"“”']")

# Baris yang berbentuk perintah di dalam prompt.
#
# Yang dicari baris yang MENYURUH, bukan baris yang menerangkan.
# Baris data - daftar keyword, contoh title, potongan halaman
# kompetitor - sengaja tidak ikut: isinya memang kosakata yang
# seharusnya dipakai model, dan mengadukannya dengan hasil akan
# menandai setiap kalimat yang menurut.
INSTRUCTION_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s+\S"
    r"|^\s*#{1,3}\s+\S"
    r"|\b(?:JANGAN|DILARANG|WAJIB|HARUS|TIDAK BOLEH)\b",
)

# Metabahasa: kalimat yang berbicara tentang kata, bukan memakainya.
#
# Kata benda bahasanya WAJIB ada. Tanpa itu, "jangan ragu hubungi
# kami" - kalimat ajakan yang wajar - ikut tertangkap hanya karena
# memuat "jangan".
META_TALK = re.compile(
    r"\b(?:kata|frasa|kalimat|istilah|ungkapan|bahasa)\s*"
    r"(?:seperti|semacam|yaitu|:)?\s*"
    r"[\"“”']"
    r"|\b(?:tanpa|tidak ada|tidak memakai|hindari|jangan (?:pakai|memakai|gunakan|menggunakan|tulis|menulis))\s+"
    r"(?:kata|frasa|kalimat|istilah|ungkapan)\b"
    r"|\b(?:คำว่า|ห้ามใช้คำ|ไม่ใช้คำ)\b",
    re.IGNORECASE,
)

# Bentuk perintah yang terbawa apa adanya ke teks terbit.
#
# Dipisah dua karena besar-kecil huruf menentukan di salah satunya.
RULE_SHAPE = re.compile(
    r"^\s*(?:salah|benar|ผิด|ถูก)\s*:"
    r"|\b(?:maksimal|minimal|paling banyak|paling sedikit)\s+\d+\s*"
    r"(?:karakter|kata|kalimat|ตัวอักษร|คำ)\b"
    r"|\b(?:aturan|instruksi|perintah|brief|prompt)\s+"
    r"(?:di atas|berikut ini|yang diberikan)\b"
    r"|\b(?:sesuai|mengikuti|menuruti)\s+"
    r"(?:aturan|instruksi|perintah|brief)\b"
    # Aksara Thai tidak punya batas kata, jadi \b di sekitarnya tidak
    # pernah cocok - diuji: "ห้ามเขียนตัวเลขเปอร์เซ็นต์" lolos
    # seluruhnya selama polanya masih memakai \b. Dicocokkan sebagai
    # potongan, dan itu aman karena rangkaian aksara ini tidak muncul
    # di dalam kata lain.
    r"|(?:ห้ามเขียน|ห้ามใช้คำ|ต้องเขียน|ตามกฎ|ตามคำสั่ง|ตามที่กำหนด"
    r"|กฎด้านบน|ตัวอักษรไม่เกิน)",
    re.IGNORECASE | re.MULTILINE,
)

# Perintah berhuruf besar, dan HURUF BESARNYA yang menandai.
#
# Prompt menulis larangannya kapital untuk penekanan ("JANGAN menulis
# angka persen"), dan kebocoran membawa kapitalnya ikut. Kalimat
# jualan yang wajar menulisnya biasa - "Jangan ragu hubungi tim kami"
# - dan itu idiom yang sering dipakai, bukan perintah yang bocor.
#
# Sempat dicocokkan tanpa memandang besar-kecil huruf, dan "Jangan
# ragu hubungi tim kami kalau ada kendala saat mendaftar" tertangkap
# sebagai bocor. Satu kalimat ajakan yang wajar dibuang adalah harga
# yang lebih mahal daripada satu kebocoran berhuruf kecil yang lolos,
# karena sinyal lain masih menangkap yang kedua.
SHOUTED_RULE = re.compile(
    r"^\s*(?:JANGAN|DILARANG|WAJIB|HARUS|TIDAK BOLEH)\b"
    r"|\b(?:JANGAN|DILARANG|WAJIB)\s+(?:MENULIS|MEMAKAI|PAKAI)\b",
)

# Pemisah kalimat. Sama bentuknya dengan yang dipakai claim_guard,
# termasuk syarat huruf sesudah titik supaya "No. 8048" tidak pecah.
SENTENCE_SPLIT = re.compile(
    r"(?<!\bNo\.)(?<=[.!?])\s+(?=[^\W\d_])|\n+",
    re.IGNORECASE,
)


def words(text: str) -> list[str]:
    return [w.casefold() for w in WORD.findall(str(text or ""))]


def shingles(text: str, n: int = NGRAM) -> set:
    """
    Kumpulan n-gram kata, dipakai mengukur tumpang tindih.
    """
    isi = words(text)

    if len(isi) < n:
        return set()

    return {tuple(isi[i:i + n]) for i in range(len(isi) - n + 1)}


def instruction_index(prompt: str) -> dict:
    """
    Menyusun bahan pembanding dari prompt yang benar-benar dikirim.

    Dipanggil sekali per permintaan, bukan per kalimat: promptnya
    puluhan ribu karakter dan menyusunnya ulang untuk tiap kalimat
    mengubah pemeriksaan murah jadi mahal.
    """
    baris_perintah: list[set] = []
    dikutip: set[str] = set()

    # Baris sambungan ikut dihitung sebagai bagian perintahnya.
    #
    # Ini bukan kerapian melainkan syarat supaya sinyal terkuat
    # bekerja. Larangan di prompt ditulis begini:
    #
    #     - Kata ragu berikut DILARANG dipakai untuk hal-hal di atas:
    #       "mungkin", "diharapkan", "berusaha untuk", "konon",
    #
    # Kata terlarangnya berdiri di baris KEDUA, yang diawali spasi
    # dan bukan tanda hubung. Tanpa menyambungnya, tidak satu pun
    # kata terlarang masuk ke daftar kutipan - dan kebocoran yang
    # justru paling sering terjadi, yaitu model menuliskan kata
    # terlarangnya, tidak punya sinyal yang menangkapnya.
    dalam_perintah = False

    for baris in str(prompt or "").splitlines():
        bersih = baris.strip()

        if not bersih:
            dalam_perintah = False
            continue

        if INSTRUCTION_LINE.search(baris):
            dalam_perintah = True
        elif not (dalam_perintah and baris[:1] in " \t"):
            dalam_perintah = False
            continue

        gram = shingles(bersih)

        if gram:
            baris_perintah.append(gram)

        for kutipan in QUOTED.findall(bersih):
            teks = kutipan.strip()

            if len(teks) >= MIN_QUOTED_LENGTH:
                dikutip.add(teks.casefold())

    return {"lines": baris_perintah, "quoted": dikutip}


def quoted_terms(text: str) -> set[str]:
    """
    Istilah yang DIKUTIP di dalam teks terbit.
    """
    return {
        kutipan.strip().casefold()
        for kutipan in QUOTED.findall(str(text or ""))
        if len(kutipan.strip()) >= MIN_QUOTED_LENGTH
    }


def overlap_score(kalimat: str, baris_perintah: list[set]) -> float:
    """
    Berapa bagian kalimat ini yang juga ada di salah satu baris
    perintah, diukur per tiga kata.
    """
    gram = shingles(kalimat)

    if not gram:
        return 0.0

    tertinggi = 0.0

    for perintah in baris_perintah:
        if not perintah:
            continue

        sama = len(gram & perintah)

        if not sama:
            continue

        skor = sama / len(gram)

        if skor > tertinggi:
            tertinggi = skor

    return tertinggi


def sentence_leaks(kalimat: str, index: dict) -> str:
    """
    Alasan satu kalimat dianggap bocor, atau kosong kalau bersih.

    Dikembalikan sebagai alasan, bukan sebagai True/False, supaya log
    job bisa menyebutkan sinyal mana yang menyalakannya - tanpa itu
    ambang yang salah setel tidak bisa ditelusuri.
    """
    teks = str(kalimat or "").strip()

    if not teks:
        return ""

    # D. Bentuk perintah. Berdiri sendiri: tidak ada halaman jualan
    # yang menulis "maksimal 70 karakter" kepada pembacanya.
    if RULE_SHAPE.search(teks) or SHOUTED_RULE.search(teks):
        return "berbentuk perintah"

    kutipan = quoted_terms(teks) & index["quoted"]

    # B. Metabahasa, TAPI hanya kalau istilah yang dibicarakannya
    # memang berasal dari perintah.
    #
    # Metabahasa sendirian bukan bukti. Halaman yang menjelaskan
    # istilah kepada pembacanya - "Istilah 'gacor' dipakai pemain
    # untuk menyebut game yang lagi ramai" - berbentuk persis sama,
    # dan itu justru kalimat yang berguna. Terukur: tanpa syarat ini
    # kalimat tersebut dibuang sebagai kebocoran.
    #
    # Yang membedakan keduanya asal istilahnya. "mungkin" ada di
    # daftar kata terlarang di prompt; "gacor" tidak ada di mana pun
    # kecuali di kepala penulisnya.
    if kutipan and META_TALK.search(teks):
        return f"membicarakan istilah perintah: {sorted(kutipan)}"

    # A. Mengutip istilah perintah tanpa metabahasa. Lebih lemah,
    # jadi butuh teman: kalimat pendek yang seluruhnya berputar di
    # sekitar kutipan itu.
    if kutipan and len(words(teks)) <= 14:
        return f"mengutip istilah perintah: {sorted(kutipan)}"

    # C. Menyalin potongan panjang.
    if len(words(teks)) >= MIN_NGRAM_WORDS:
        skor = overlap_score(teks, index["lines"])

        if skor >= NGRAM_OVERLAP:
            return f"menyalin baris perintah ({skor:.0%})"

    return ""


# Token yang tidak pernah datang dari orang yang menulis halaman.
#
# Bocornya beda watak dari kebocoran perintah yang diurus modul ini
# sejak awal. Yang itu kalimat yang MASUK AKAL tapi isinya perintah,
# jadi ia cuma bisa dikenali dengan membandingkannya ke prompt asli.
# Yang ini token yang tidak masuk akal di mana pun - potongan kerangka
# obrolan model, penanda template yang belum terisi, atau nama pustaka
# Python yang tersesat ke dalam kalimat:
#
#     Slot Gac tqdm di WAYANGPLAY
#
# Karena tidak bergantung pada prompt, ia diperiksa tanpa index - dan
# justru karena itu ia bisa dipakai memeriksa halaman yang SUDAH
# terbit, yang promptnya tidak ikut tersimpan.
#
# Daftarnya sengaja pendek. Pengguna memintanya begitu, dan alasannya
# nyata: daftar hitam yang panjang akan memuat kata yang kebetulan
# juga kata biasa, lalu membuang kalimat yang tidak salah apa pun.
# Yang masuk cuma yang mustahil ditulis orang Indonesia atau Thailand
# yang sedang menulis halaman - bukan kata yang "mencurigakan".

# 1. Kerangka obrolan model dan penanda kendalinya. Semuanya
#    berbentuk, jadi tidak ada kata biasa yang bisa tersangkut.
CONTROL_TOKEN = re.compile(
    r"<\|[^|>]{0,40}\|>"
    r"|<\/?s>"
    r"|\[/?INST\]"
    r"|<<\/?SYS>>"
    r"|\bim_(?:start|end)\b"
    r"|\bend_of_turn\b"
    r"|<\|?(?:endoftext|eot_id|start_header_id|end_header_id)\|?>",
    re.IGNORECASE,
)

# 2. Penanda template yang belum terisi. Juga berbentuk.
#
#    Kurung kurawal tunggal TIDAK ikut: "{keyword}" memang bentuk
#    penanda, tapi tanda kurung kurawal tunggal juga dipakai orang
#    menulis biasa, dan yang benar-benar bocor dari pipeline ini
#    selalu berkurawal dua.
PLACEHOLDER_TOKEN = re.compile(
    r"\{\{[^}]{0,60}\}\}"
    r"|\{%[^%]{0,60}%\}"
    r"|\$\{[^}]{0,60}\}"
    r"|\[\[[^\]]{0,60}\]\]"
    r"|\b(?:lorem ipsum|dolor sit amet)\b"
    r"|\b(?:TODO|FIXME|TBD|XXX)\b"
    r"|\[(?:isi|tulis|masukkan|ganti)[^\]]{0,40}\]",
    re.IGNORECASE,
)

# 3. Nama pustaka dan potongan kode yang tersesat ke dalam kalimat.
#
#    Tiap nama di sini diperiksa satu per satu terhadap kemungkinan
#    ia juga kata Indonesia atau Thai. Tidak satu pun yang lolos
#    pemeriksaan itu masuk daftar - itu sebabnya daftarnya berhenti
#    di sini dan tidak diteruskan ke nama pustaka yang lebih umum.
LIBRARY_TOKEN = re.compile(
    r"\b(?:tqdm|numpy|scipy|sklearn|matplotlib|pytorch|tensorflow|"
    r"huggingface|langchain|ollama|llama\.cpp|transformers\.|"
    r"NoneType|Traceback|json\.dumps|json\.loads)\b"
    r"|\b(?:def|import|elif|lambda)\s+\w+\s*[:(=]"
    r"|\bprint\s*\(",
    re.IGNORECASE,
)

GARBAGE_TOKENS = (
    ("token kendali model", CONTROL_TOKEN),
    ("penanda belum terisi", PLACEHOLDER_TOKEN),
    ("nama pustaka/kode", LIBRARY_TOKEN),
)


def garbage_tokens(text: str) -> list[tuple[str, str]]:
    """
    Token sampah yang masih berdiri di sebuah teks, beserta jenisnya.

    Tidak menerima index, tidak seperti sisi modul ini yang lain:
    yang dicari di sini tidak pernah sah dalam keadaan apa pun, jadi
    tidak ada yang perlu dibandingkan ke prompt.

    Mengembalikan daftar (jenis, potongan yang kena). Kosong berarti
    bersih.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    kena: list[tuple[str, str]] = []

    for jenis, pola in GARBAGE_TOKENS:
        for cocok in pola.finditer(text):
            potongan = cocok.group(0).strip()

            if potongan:
                kena.append((jenis, potongan))

    return kena


def strip_garbage(text: str) -> tuple[str, int]:
    """
    Membuang kalimat yang memuat token sampah.

    Sekalimat penuh, bukan tokennya saja. Kalimat yang memuat
    "Slot Gac tqdm di WAYANGPLAY" tidak jadi benar dengan mencabut
    "tqdm" - yang tertinggal "Slot Gac di WAYANGPLAY", dengan
    keywordnya tetap terpenggal. Bocornya menandakan seluruh kalimat
    itu tersusun salah.

    Kalau semua kalimatnya kena, teksnya dikosongkan - alasannya sama
    dengan strip_leaks: yang kosong terdeteksi kependekan lalu diminta
    ulang, dan itu jalan keluar yang lebih baik daripada menerbitkan
    kalimat yang memuat potongan kerangka model.
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0

    simpan: list[str] = []
    dibuang = 0

    for kalimat in SENTENCE_SPLIT.split(text):
        bersih = kalimat.strip()

        if not bersih:
            continue

        if garbage_tokens(bersih):
            dibuang += 1
            continue

        simpan.append(bersih)

    if not dibuang:
        return text, 0

    return " ".join(simpan).strip(), dibuang


def leaking_sentences(text: str, index: dict) -> list[tuple[str, str]]:
    """
    Kalimat yang bocor beserta alasannya.
    """
    hasil: list[tuple[str, str]] = []

    for kalimat in SENTENCE_SPLIT.split(str(text or "")):
        alasan = sentence_leaks(kalimat, index)

        if alasan:
            hasil.append((kalimat.strip(), alasan))

    return hasil


def has_leak(text: str, index: dict) -> bool:
    return bool(leaking_sentences(text, index))


def strip_leaks(text: str, index: dict) -> tuple[str, int]:
    """
    Membuang kalimat yang bocor dari satu potong teks.

    Kalimatnya dibuang utuh, tidak ditambal. Isi kalimat bocor
    seluruhnya milik perintah - tidak ada bagian yang bisa
    diselamatkan, tidak seperti klaim berangka yang kalimatnya masih
    menyatakan sesuatu sesudah angkanya dicabut.

    Kalau SEMUA kalimatnya bocor, teksnya dikosongkan. Itu disengaja:
    yang kosong akan terdeteksi kependekan lalu diminta ulang, dan
    teks yang seluruhnya berisi perintah memang tidak layak terbit
    dalam bentuk apa pun.
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0

    simpan: list[str] = []
    dibuang = 0

    for kalimat in SENTENCE_SPLIT.split(text):
        bersih = kalimat.strip()

        if not bersih:
            continue

        if sentence_leaks(bersih, index):
            dibuang += 1
            continue

        simpan.append(bersih)

    if not dibuang:
        return text, 0

    return " ".join(simpan).strip(), dibuang


def scrub_leaks(content, index: dict) -> tuple[object, int]:
    """
    Membersihkan seluruh isi halaman, seberapa pun dalam.

    Peran berawalan garis bawah dilewati - isinya penanda riwayat,
    bukan teks yang terbit. Aturan yang sama dengan
    claim_guard.scrub_content dan spelling.fix_content_terms.
    """
    if isinstance(content, str):
        # Dua penyapuan berturut-turut, bukan satu. Keduanya membuang
        # kalimat utuh, jadi urutannya tidak mengubah hasil - yang
        # penting keduanya benar-benar lewat.
        bersih, a = strip_leaks(content, index)
        bersih, b = strip_garbage(bersih)

        return bersih, a + b

    if isinstance(content, list):
        hasil = []
        total = 0

        for item in content:
            bersih, jumlah = scrub_leaks(item, index)
            hasil.append(bersih)
            total += jumlah

        return hasil, total

    if isinstance(content, dict):
        hasil = {}
        total = 0

        for kunci, nilai in content.items():
            if isinstance(kunci, str) and kunci.startswith("_"):
                hasil[kunci] = nilai
                continue

            bersih, jumlah = scrub_leaks(nilai, index)
            hasil[kunci] = bersih
            total += jumlah

        return hasil, total

    return content, 0
