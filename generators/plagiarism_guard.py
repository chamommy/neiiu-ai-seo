"""
Kalimat yang disalin dari halaman pesaing.

Ini lubang yang terbuka sejak analisis SERP disambungkan ke tahap
menulis. Sebelum sambungan itu ada, model menulis dari pengetahuan
umumnya sendiri dan tidak punya bahan untuk disalin. Sesudahnya,
prompt tahap menulis memuat bacaan halaman yang sedang menang -
paragraf pembukanya, paragraf kuncinya, jawaban FAQ-nya, seluruhnya
kalimat utuh milik orang lain - dan model 4B yang melihat kalimat
bagus di dalam perintahnya kadang memakainya apa adanya.

Akibatnya dua, dan yang kedua lebih mahal:

  1. Halaman terbit dengan kalimat milik situs lain. Pengguna yang
     menerbitkannya tidak pernah tahu, karena tidak ada yang
     membandingkan.
  2. Halaman itu tidak punya alasan untuk ditaruh di atas halaman
     yang disalinnya. Mesin pencari sudah punya kalimat itu, dari
     sumber yang lebih dulu ada dan lebih tua.

Aturannya sudah ikut dipasang di prompt - lihat baris "JANGAN
MENYALIN KALIMAT" di ai/language_rules.py. Berkas ini jaring
pengamannya, dengan alasan yang sama seperti seluruh penyapu lain di
pipeline ini: aturan prompt untuk model 4B diikuti kadang-kadang
saja.

Yang dipakai membandingkan RANGKAIAN KATA, bukan kemiripan makna.
Kemiripan makna memang yang ingin dijaga, tapi ia tidak bisa diukur
tanpa model kedua - dan rangkaian delapan kata berturut-turut yang
sama persis bukan kebetulan dalam bahasa apa pun. Dua halaman satu
bidang wajar berbagi istilah dan frasa pendek; yang tidak wajar
adalah berbagi kalimat.
"""

import re


# Panjang rangkaian kata yang dianggap bukan kebetulan lagi.
#
# Delapan, bukan empat. Prompt menyuruh model menghindari empat kata
# berturut-turut, dan angka itu benar sebagai perintah - lebih ketat
# dari yang perlu, supaya yang lolos masih aman. Sebagai PENGUKUR ia
# salah: "situs slot online terpercaya yang bisa dimainkan" adalah
# rangkaian yang muncul di ratusan halaman satu bidang tanpa satu pun
# menyalin yang lain, dan penyapu yang membuangnya akan membuang
# kalimat yang benar-benar ditulis sendiri.
#
# Delapan kata berturut-turut yang sama persis tidak punya penjelasan
# selain penyalinan.
NGRAM = 8

# Ambang kedua, untuk kalimat panjang yang ditiru hampir seluruhnya
# tapi disela satu-dua kata berbeda sehingga tidak ada satu pun
# rangkaian delapan yang utuh.
#
# Diukur dengan rangkaian yang lebih pendek, jadi ambangnya harus
# tinggi: bagian terbesar rangkaian lima kata sebuah kalimat harus
# sudah ada di halaman lain sebelum ia disebut salinan.
NEAR_NGRAM = 5
NEAR_RATIO = 0.6
NEAR_MIN_WORDS = 12

# Panjang minimal satu potong bahan supaya ikut dibandingkan.
#
# Potongan pendek adalah judul menu, label tombol, dan nama bagian -
# "Cara Deposit", "Syarat dan Ketentuan". Semua halaman satu bidang
# memakainya, dan tidak satu pun menyalinnya dari yang lain.
SOURCE_MIN_WORDS = NGRAM

WORD = re.compile(r"[0-9A-Za-zÀ-ɏ฀-๿]+", re.UNICODE)

# Pemisah kalimat. Bentuknya sama dengan yang dipakai leak_guard dan
# claim_guard, termasuk syarat huruf sesudah titik supaya "No. 8048"
# tidak pecah jadi dua kalimat.
SENTENCE_SPLIT = re.compile(
    r"(?<!\bNo\.)(?<=[.!?])\s+(?=[^\W\d_])|\n+",
    re.IGNORECASE,
)


def words(text: str) -> list[str]:
    """
    Kata satu potong teks, dinormalkan.

    Aksara Thai ikut dicakup pola katanya. Thai tidak memberi spasi
    antar kata, jadi satu "kata" di sini sebenarnya satu frasa utuh -
    dan itu justru membuat pembandingannya lebih ketat, bukan lebih
    longgar: rangkaian delapan frasa Thai yang sama persis adalah
    bukti yang lebih kuat lagi.
    """
    return [w.casefold() for w in WORD.findall(str(text or ""))]


def shingles(text: str, n: int = NGRAM) -> set:
    """
    Kumpulan rangkaian n kata berturut-turut.
    """
    isi = words(text)

    if len(isi) < n:
        return set()

    return {tuple(isi[i:i + n]) for i in range(len(isi) - n + 1)}


def source_texts(analysis: dict) -> list[str]:
    """
    Seluruh kalimat pesaing yang benar-benar sampai ke prompt.

    Yang dikumpulkan cuma yang dibaca model. Bagian analisis yang
    berhenti sebagai laporan - skor SEO, jumlah tautan, sinyal
    teknis - tidak pernah bisa disalin siapa pun, dan memasukkannya
    cuma memperbesar kumpulan tanpa menambah satu pun deteksi.
    """
    hasil: list[str] = []

    for halaman in (analysis or {}).get("pages") or []:
        if not isinstance(halaman, dict):
            continue

        for kunci in ("title", "meta_description", "serp_snippet"):
            nilai = halaman.get(kunci)

            if isinstance(nilai, str):
                hasil.append(nilai)

        digest = halaman.get("digest") or {}

        if not isinstance(digest, dict):
            continue

        pembuka = digest.get("lead")

        if isinstance(pembuka, str):
            hasil.append(pembuka)

        for paragraf in digest.get("key_paragraphs") or []:
            if isinstance(paragraf, str):
                hasil.append(paragraf)

        for tanya_jawab in digest.get("faq") or []:
            if not isinstance(tanya_jawab, dict):
                continue

            for kunci in ("question", "answer"):
                nilai = tanya_jawab.get(kunci)

                if isinstance(nilai, str):
                    hasil.append(nilai)

        for bagian in digest.get("outline") or []:
            if isinstance(bagian, dict):
                judul = bagian.get("heading")

                if isinstance(judul, str):
                    hasil.append(judul)

    return [teks for teks in hasil if teks and teks.strip()]


def source_index(analysis: dict) -> dict:
    """
    Menyusun bahan pembanding sekali untuk seluruh run.

    Dipanggil sekali, bukan per kalimat. Sepuluh halaman pesaing
    berisi ribuan rangkaian kata, dan menyusunnya ulang untuk tiap
    kalimat yang diperiksa mengubah pemeriksaan murah jadi mahal -
    persoalan yang sama persis dengan instruction_index di
    generators/leak_guard.py.
    """
    panjang: set = set()
    pendek: set = set()
    dipakai = 0

    for teks in source_texts(analysis):
        if len(words(teks)) < SOURCE_MIN_WORDS:
            continue

        dipakai += 1
        panjang |= shingles(teks, NGRAM)
        pendek |= shingles(teks, NEAR_NGRAM)

    return {
        "long": panjang,
        "short": pendek,
        "sources": dipakai,
    }


def has_sources(index: dict) -> bool:
    """
    Apakah ada bahan pembanding sama sekali.

    Run yang halaman pesaingnya gagal di-crawl - atau mode manual
    tanpa isi - menghasilkan kumpulan kosong, dan kumpulan kosong
    tidak boleh diperlakukan sebagai "tidak ada yang menyalin".
    Pemanggilnya yang memutuskan apa yang dilaporkan.
    """
    return bool((index or {}).get("long"))


def copied_run(kalimat: str, index: dict) -> str:
    """
    Rangkaian kata terpanjang yang sama persis dengan halaman lain.

    Mengembalikan rangkaiannya sebagai teks, atau "" kalau tidak ada.
    Rangkaiannya dikembalikan, bukan cuma True, supaya laporan bisa
    menunjukkan apa yang tertangkap - pengguna yang membaca "1
    kalimat disalin" tanpa contohnya tidak punya cara memeriksanya.
    """
    if not (index or {}).get("long"):
        return ""

    isi = words(kalimat)

    if len(isi) < NGRAM:
        return ""

    panjang = index["long"]

    for awal in range(len(isi) - NGRAM + 1):
        if tuple(isi[awal:awal + NGRAM]) in panjang:
            # Diperpanjang ke kanan selama masih cocok, supaya yang
            # dilaporkan seluruh potongan yang sama - bukan delapan
            # kata pertamanya saja.
            akhir = awal + NGRAM

            while (
                akhir < len(isi)
                and tuple(isi[akhir - NGRAM + 1:akhir + 1]) in panjang
            ):
                akhir += 1

            return " ".join(isi[awal:akhir])

    return ""


def near_copy(kalimat: str, index: dict) -> bool:
    """
    Kalimat panjang yang hampir seluruhnya sama dengan halaman lain.

    Menangkap bentuk yang lolos copied_run: kalimat yang ditiru utuh
    lalu disela satu-dua kata berbeda, sehingga tidak ada satu pun
    rangkaian delapan yang utuh sementara seluruh sisanya sama.
    """
    if not (index or {}).get("short"):
        return False

    isi = words(kalimat)

    if len(isi) < NEAR_MIN_WORDS:
        return False

    milik_kalimat = shingles(kalimat, NEAR_NGRAM)

    if not milik_kalimat:
        return False

    sama = len(milik_kalimat & index["short"])

    return (sama / len(milik_kalimat)) >= NEAR_RATIO


def sentence_copies(kalimat: str, index: dict) -> str:
    """
    Alasan satu kalimat dianggap salinan, atau "".
    """
    potongan = copied_run(kalimat, index)

    if potongan:
        return potongan

    if near_copy(kalimat, index):
        return " ".join(words(kalimat)[:NGRAM])

    return ""


def strip_copied(text: str, index: dict) -> tuple[str, int, list[str]]:
    """
    Membuang kalimat salinan dari satu potong teks.

    Kalimatnya dibuang utuh, tidak ditambal, dengan alasan yang sama
    seperti kalimat bocor di leak_guard: tidak ada bagian yang bisa
    diselamatkan dari kalimat yang seluruhnya milik orang lain.

    Kalau SEMUA kalimatnya salinan, teksnya dikosongkan. Yang kosong
    akan terdeteksi kependekan lalu diminta ulang ke model, dan itu
    memang hasil yang benar - teks yang seluruhnya salinan tidak
    layak terbit dalam bentuk apa pun.
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0, []

    if not has_sources(index):
        return text, 0, []

    simpan: list[str] = []
    contoh: list[str] = []
    dibuang = 0

    for kalimat in SENTENCE_SPLIT.split(text):
        bersih = kalimat.strip()

        if not bersih:
            continue

        potongan = sentence_copies(bersih, index)

        if potongan:
            dibuang += 1

            if len(contoh) < 3:
                contoh.append(potongan)

            continue

        simpan.append(bersih)

    if not dibuang:
        return text, 0, []

    return " ".join(simpan).strip(), dibuang, contoh


def scrub_copied(content, index: dict) -> tuple[object, int, list[str]]:
    """
    Membersihkan seluruh isi halaman, seberapa pun dalam.

    Peran berawalan garis bawah dilewati - isinya penanda riwayat,
    bukan teks yang terbit. Aturan yang sama dengan
    leak_guard.scrub_leaks dan claim_guard.scrub_content.
    """
    if isinstance(content, str):
        bersih, jumlah, contoh = strip_copied(content, index)

        return bersih, jumlah, contoh

    if isinstance(content, list):
        hasil = []
        total = 0
        contoh: list[str] = []

        for item in content:
            bersih, jumlah, sampel = scrub_copied(item, index)
            hasil.append(bersih)
            total += jumlah
            contoh.extend(sampel)

        return hasil, total, contoh

    if isinstance(content, dict):
        hasil = {}
        total = 0
        contoh: list[str] = []

        for kunci, nilai in content.items():
            if isinstance(kunci, str) and kunci.startswith("_"):
                hasil[kunci] = nilai
                continue

            bersih, jumlah, sampel = scrub_copied(nilai, index)
            hasil[kunci] = bersih
            total += jumlah
            contoh.extend(sampel)

        return hasil, total, contoh

    return content, 0, []
