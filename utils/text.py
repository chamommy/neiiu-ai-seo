"""
Perhitungan teks yang sadar aksara.

Seluruh analisis NEIIU bersandar pada tiga angka: berapa kata satu
halaman, berapa kali keywordnya muncul, dan seberapa mirip dua
versi halaman. Ketiganya ditulis dengan anggapan teksnya memakai
spasi antar kata dan hurufnya Latin.

Bahasa Thai melanggar keduanya. Kalimatnya ditulis tanpa spasi, dan
hurufnya di luar rentang a-z. Akibatnya bukan hasil yang meleset
sedikit, melainkan angka yang salah arah: jumlah kata jadi
seperlima, density jadi berlipat, dan kemiripan dua halaman selalu
1.0 sehingga cloaking tidak pernah terdeteksi.

Aksara ditentukan dari teksnya sendiri, bukan dari zona yang
dipilih pengguna. Halaman berbahasa Thai yang muncul di pencarian
Indonesia tetap harus dihitung sebagai teks Thai.
"""

import re
import unicodedata


THAI_RANGE = re.compile(r"[฀-๿]")

# Rata-rata panjang satu kata Thai setelah tanda vokal dan nada
# dibuang. Angka ini perkiraan, bukan pemenggalan kata sungguhan,
# dan hanya dipakai untuk membandingkan panjang antar halaman.
THAI_CHARS_PER_WORD = 3.5

# Kalau sebagian kecil saja teksnya beraksara Thai, biasanya itu
# cuma nama atau kutipan di halaman berbahasa lain, jadi cara
# hitung berspasi masih yang benar.
THAI_SHARE_THRESHOLD = 0.15

# Panjang potongan untuk membandingkan dua teks tanpa spasi.
# Empat karakter kira-kira sepanjang satu kata Thai, jadi irisannya
# bermakna seperti irisan kata pada teks berspasi.
THAI_GRAM = 4

LATIN_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)

# Kategori Unicode yang tidak memakan ruang mendatar sama sekali.
# Aksara Thai menumpuk sara dan tanda nada di atas atau di bawah
# huruf induknya, jadi "ช่วยเหลือ" panjangnya sembilan karakter tapi
# lebarnya cuma lima kolom.
ZERO_WIDTH_CATEGORIES = {"Mn", "Me", "Cf"}

# Aksara yang satu hurufnya selebar dua kolom: Han, Kana, Hangul.
WIDE_CLASSES = {"W", "F"}


def char_width(char: str) -> int:
    if unicodedata.category(char) in ZERO_WIDTH_CATEGORIES:
        return 0

    return 2 if unicodedata.east_asian_width(char) in WIDE_CLASSES else 1


def display_width(text: str) -> int:
    """
    Lebar teks kalau ditampilkan, dihitung dalam kolom.

    Inilah ukuran yang benar untuk membandingkan panjang teks lama
    dengan teks penggantinya, karena yang dijaga adalah tata letak.
    len() salah untuk urusan itu: ia menghitung tanda vokal Thai
    sebagai karakter penuh padahal tanda itu tidak menambah lebar
    sedikit pun, sehingga label yang sebenarnya muat dinilai
    kepanjangan lalu dipotong.
    """
    return sum(char_width(char) for char in text or "")


def trim_to_width(text: str, limit: int, tolerance: float = 1.0) -> str:
    """
    Memotong teks sampai muat lebar tertentu tanpa merusak hurufnya.

    Tiga hal yang dijaga. Pertama, potongan tidak pernah jatuh di
    tengah satu huruf: tanda vokal yang kehilangan huruf induknya
    tampil sebagai tanda menggantung, dan itu yang membuat
    "ช่วยเหลือ" terpotong jadi "ช่วยเหล็". Kedua, kalau teksnya
    memakai spasi, potongan digeser ke batas kata terdekat.

    Ketiga, kalau tidak ada batas kata sama sekali - keadaan biasa di
    aksara Thai, yang memang ditulis tanpa spasi antar kata - maka
    memotong berarti pasti memenggal kata. Di situ kelebihan sebesar
    tolerance dibiarkan lewat, karena label yang sedikit lebih lebar
    dari jatahnya jauh lebih mudah dimaafkan daripada kata terpenggal.
    """
    body = " ".join(str(text or "").split())

    if limit <= 0 or display_width(body) <= limit:
        return body

    lebar = 0
    potong = len(body)

    for index, char in enumerate(body):
        tambah = char_width(char)

        if lebar + tambah > limit:
            potong = index
            break

        lebar += tambah

    # Kalau potongannya jatuh tepat di atas tanda yang menempel,
    # huruf induknya ikut dibuang. Menyisakan tandanya saja
    # menghasilkan karakter menggantung yang tidak terbaca.
    while 0 < potong < len(body) and char_width(body[potong]) == 0:
        potong -= 1

    trimmed = body[:potong]
    spasi = trimmed.rfind(" ")

    # Batas kata hampir selalu lebih baik daripada potongan di tengah
    # kata, jadi ambangnya sengaja rendah: "Daftar Sekaran" terbaca
    # seperti halaman rusak, "Daftar" tidak. Ambangnya tidak nol
    # karena teks yang isinya satu kata sangat panjang - tautan, nama
    # berkas - akan habis sama sekali kalau digeser ke spasi pertama.
    if spasi > potong * 0.35:
        return trimmed[:spasi].rstrip(" ,.;:-")

    if display_width(body) <= limit * tolerance:
        return body

    return trimmed.rstrip(" ,.;:-")


# Tanda yang mengakhiri kalimat, termasuk bentuk lebar milik aksara
# CJK yang lazim ikut tersalin ke teks Indonesia.
SENTENCE_END = re.compile(r"[.!?。！？]")

# Seberapa banyak teks yang masih boleh disisakan saat potongan
# digeser mundur ke akhir kalimat.
#
# Jawaban tiga kalimat yang jatahnya cuma muat satu setengah lebih
# baik terbit satu kalimat utuh daripada satu setengah kalimat yang
# berhenti di tengah. Tapi kalau kalimat pertamanya sendiri sudah
# lebih panjang dari jatah, menggesernya berarti membuang hampir
# seluruh isi - dan kartu yang isinya satu potong kata jauh lebih
# buruk daripada kalimat yang kepanjangan sedikit.
SENTENCE_KEEP_RATIO = 0.55


def trim_to_sentence(
    text: str,
    limit: int,
    tolerance: float = 1.0,
    floor: int = 0,
) -> str:
    """
    Memotong teks di batas kalimat, bukan di batas kata.

    trim_to_width menjaga hurufnya tetap utuh, dan itu perlu tapi
    tidak cukup untuk teks yang berupa kalimat. Terukur di halaman
    jadi: 7 dari 24 jawaban FAQ terbit berhenti di tengah kalimat -
    "Pastikan situs memiliki sistem enkripsi dan layanan dukungan" -
    dan pembaca melihatnya sebagai halaman yang rusak, bukan sebagai
    teks yang dipotong rapi.

    Kalau tidak ada satu kalimat pun yang muat, potongannya ditutup
    sendiri lewat close_clause: kata sambung yang menggantung di
    ujung dibuang, lalu diberi titik.

    Batas kalimat dicari di teks ASLINYA, bukan di hasil trim_to_width.
    Bedanya menentukan, dan ini bug yang sempat terbit: trim_to_width
    menggeser potongannya ke batas kata, dan geseran itu membuang
    tanda titik yang kebetulan berdiri persis di ujung jatah. Jawaban
    FAQ berjatah 244 karakter yang kalimat keduanya berakhir tepat di
    karakter ke-244 karena itu kehilangan kata terakhirnya lebih dulu,
    lalu dicarikan titik di sisa yang sudah tidak punya titik -
    hasilnya "prosesnya selesai dalam waktu kurang dari satu."
    padahal "satu detik." muat seluruhnya.
    """
    body = " ".join(str(text or "").split())

    if not body:
        return body

    if display_width(body) <= limit:
        # Muat seluruhnya, jadi tidak ada yang dipotong di sini. Tapi
        # model juga bisa berhenti sendiri di tengah kalimat saat jatah
        # tokennya habis, dan hasilnya sama menggantungnya.
        return close_clause(body, limit, tolerance, hanya_gantung=True)

    batas = 0

    for cocok in SENTENCE_END.finditer(body):
        if display_width(body[: cocok.end()]) > limit:
            break

        batas = cocok.end()

    dipotong = trim_to_width(body, limit, tolerance)

    if not dipotong:
        return dipotong

    if dipotong == body:
        return close_clause(body, limit, tolerance, hanya_gantung=True)

    # "floor" menahan mundurnya potongan, dan hanya dipakai title dan
    # meta description.
    #
    # Untuk teks di badan halaman, mundur ke kalimat utuh selalu
    # menang: jawaban FAQ 87 karakter yang utuh lebih baik daripada
    # 159 karakter yang berhenti di "sehingga pemain bisa melakukan."
    #
    # Untuk deskripsi, tidak. Panjangnya bukan selera melainkan
    # permintaan pengguna - 160 sampai 200 karakter - dan mundur ke
    # titik terakhir bisa jatuh jauh di bawahnya. Terukur: model
    # menulis 210 karakter, kalimat keduanya berakhir di 116, dan yang
    # terbit deskripsi 116 karakter dari jatah 200. Di situ yang benar
    # adalah menutup sendiri di batas kata.
    if batas and batas >= max(len(dipotong) * SENTENCE_KEEP_RATIO, floor):
        return body[:batas].strip()

    # Potongan yang jatuh di tengah kata tidak boleh langsung diberi
    # titik: "dari" yang terpotong jadi "dar" akan terbit sebagai
    # "dar." - lebih rusak daripada sebelum diperbaiki.
    utuh = body[len(dipotong):len(dipotong) + 1] in ("", " ")

    return close_clause(dipotong, limit, tolerance, kata_utuh=utuh)


# Kata yang tidak boleh berdiri sebagai kata terakhir sebuah kalimat.
# Semuanya menuntut kelanjutan, jadi kalimat yang berhenti di situ
# terbaca sebagai halaman rusak, bukan sebagai teks yang dipotong.
#
# Terukur di halaman jadi: tiga paragraf terbit berakhiran "dari",
# "oleh pihak", dan "pada lokasi". Ketiganya lolos dari penggeseran
# batas kalimat karena modelnya menulis satu kalimat panjang tanpa
# titik sama sekali - tidak ada batas kalimat sebelumnya yang bisa
# dituju, sehingga potongan mentahnya terpakai apa adanya.
DANGLING_WORDS = {
    "adalah", "agar", "akan", "antara", "atau", "atas", "bagi", "bahwa",
    "bila", "bisa", "dalam", "dan", "dapat", "dari", "demi", "dengan",
    "di", "hingga", "ialah", "jika", "juga", "kalau", "karena", "ke",
    "kepada", "ketika", "maupun", "melalui", "namun", "oleh", "pada",
    "para", "saat", "sampai", "sebagai", "sebelum", "secara", "sehingga",
    "selama", "sementara", "serta", "setelah", "seperti", "supaya",
    "tanpa", "tapi", "terhadap", "tetapi", "tentang", "untuk", "yaitu",
    "yakni", "yang",
    # Kata takaran. Semuanya menjanjikan sebuah kata benda sesudahnya
    # dan tidak pernah menutup judul: "RTP Terupdate Setiap" berhenti
    # sebelum mengatakan setiap apa.
    "setiap", "tiap", "per", "sekitar", "hampir", "kurang",
    "a", "an", "and", "as", "at", "because", "but", "by", "for", "from",
    "every", "in", "of", "on", "or", "that", "the", "to", "which",
    "while", "with",
}

# Angka yang berdiri di ujung potongan.
#
# Angka selalu ditulis bersama satuannya, jadi angka yang berakhir
# sendirian adalah angka yang satuannya kena potong: "RTP Terupdate
# Setiap 15" dulunya "... Setiap 15 Detik". Hanya berlaku pada teks
# yang memang baru dipotong - judul yang utuh dan kebetulan berakhir
# "Slot Gacor 2026" tidak disentuh sama sekali.
TRAILING_NUMBER = re.compile(r"^\d+([.,]\d+)?$")

# Tanda yang sudah menutup kalimat, jadi tidak perlu ditambahi titik.
CLOSERS = ".!?…。！？"


def drop_dangling(text: str, dipotong: bool = False) -> str:
    """
    Membuang kata sambung yang menggantung di ujung, tanpa memberi titik.

    Dipakai peran yang bukan kalimat - judul halaman, heading, dan
    pertanyaan FAQ - karena ketiganya memang tidak diakhiri titik tapi
    sama tidak bolehnya berhenti di kata sambung. Terukur di halaman
    jadi, ketiganya kena sekaligus:

        <title>  ASOKASLOT: Slot Online Terpercaya dengan Fitur Cepat dan
        <h3>     Bagaimana Slot Online Berfungsi Secara
        FAQ      Apakah slot online bisa diakses tanpa?

    Yang terakhir paling parah: tanda tanyanya dipasang balik SESUDAH
    dipotong, jadi kalimat yang putus tetap terbit berbentuk
    pertanyaan yang utuh dilihat sekilas.
    """
    kata = str(text or "").split()

    # Angka yang kehilangan satuannya waktu dipotong, dibuang lebih
    # dulu supaya kata takaran di depannya ikut terlihat menggantung.
    if dipotong and kata and TRAILING_NUMBER.match(kata[-1].strip(".,;:-–—")):
        kata.pop()

    # Kata terakhir yang menggantung sendirian, misalnya "... Cepat dan".
    while kata and kata[-1].strip(".,;:-–—").lower() in DANGLING_WORDS:
        kata.pop()

    # Kata terakhir yang TIDAK menggantung tapi kata sebelumnya iya,
    # misalnya "... Tanpa Ribet di Era". Hanya kalau teksnya memang
    # baru dipotong.
    #
    # Syarat "baru dipotong" itu yang membuat aturan ini aman. Judul
    # yang ditulis utuh dan kebetulan berakhir "... Deposit Cepat dan
    # Praktis" sama sekali tidak disentuh, karena tidak ada yang
    # dipotong darinya. Yang disasar cuma sisa potongan: kata depan
    # yang membuka keterangan, lalu satu kata yang sempat tertulis
    # sebelum jatahnya habis - "di Era", "dan Transaksi", "untuk
    # Semua". Ketiganya menjanjikan kelanjutan yang tidak pernah
    # datang, dan pembaca melihatnya sebagai judul yang rusak.
    if dipotong and len(kata) >= 2:
        if kata[-2].strip(".,;:-–—").lower() in DANGLING_WORDS:
            kata = kata[:-2]

            while kata and kata[-1].strip(".,;:-–—").lower() in DANGLING_WORDS:
                kata.pop()

    if not kata:
        return str(text or "")

    return " ".join(kata).rstrip(" ,;:-–—")


def close_clause(
    text: str,
    limit: int,
    tolerance: float = 1.0,
    hanya_gantung: bool = False,
    kata_utuh: bool = True,
) -> str:
    """
    Menutup kalimat yang berhenti di kata sambung.

    Kata gantung di ujung dibuang lalu diberi titik, sehingga
    "dijalankan secara independen dari" jadi "dijalankan secara
    independen." - utuh dibaca, dan tetap muat di jatah lebarnya.

    hanya_gantung dipakai saat teksnya tidak dipotong siapa pun.
    Di situ titik hanya ditambahkan kalau memang ada kata gantung
    yang dibuang, karena label dan butir daftar yang wajar memang
    tidak diakhiri titik dan tidak boleh dipaksa.

    kata_utuh=False berarti potongannya jatuh di tengah kata, jadi
    kata terakhirnya dibuang lebih dulu - menempelkan titik ke kata
    yang terpenggal justru memperburuk.
    """
    kata = str(text or "").split()

    if not kata:
        return ""

    dibuang = 0

    if not kata_utuh:
        if len(kata) < 2:
            # Satu kata dan kata itu sendiri terpenggal. Tidak ada
            # kalimat yang bisa ditutup, cuma potongan huruf, dan
            # titik di belakangnya membuatnya tampak disengaja.
            return str(text or "")

        kata.pop()
        dibuang += 1

    while kata and kata[-1].strip(".,;:-–—").lower() in DANGLING_WORDS:
        kata.pop()
        dibuang += 1

    if not kata:
        # Seluruhnya kata sambung. Tidak ada yang bisa diselamatkan,
        # jadi potongan aslinya dikembalikan apa adanya.
        return str(text or "")

    hasil = " ".join(kata).rstrip(" ,;:-–—")

    if not hasil:
        return str(text or "")

    if hanya_gantung and not dibuang:
        return hasil

    if hasil[-1] not in CLOSERS:
        hasil = f"{hasil}."

    # Titiknya menambah satu kolom, jadi hasilnya bisa melewati jatah
    # yang tadinya pas. Kata terakhir dibuang sampai muat lagi.
    while len(kata) > 1 and display_width(hasil) > limit * tolerance:
        kata.pop()
        hasil = " ".join(kata).rstrip(" ,;:-–—")

        if hasil and hasil[-1] not in CLOSERS:
            hasil = f"{hasil}."

    return hasil


# Berapa karakter yang muat dalam satu token, per jenis aksara.
#
# Angka Latin di bawah sengaja jauh lebih kecil dari 3 karakter per
# token yang berlaku untuk prosa biasa. Prompt pengisian template
# bukan prosa: isinya potongan label, deretan spasi dan baris baru,
# tanda baca, dan nama menu yang dipecah tokenizer jauh lebih halus.
# Diukur pada prompt sungguhan, 26.916 karakter jadi 13.838 token -
# 1,95 karakter per token, bukan 3.
#
# Melebihkan perkiraan hanya membuat context sedikit lebih besar dari
# perlunya. Mengecilkannya berakibat fatal: num_ctx dipasang kekecilan,
# jawaban model putus di tengah JSON, dan seluruh langkah gagal
# setelah satu jam menunggu - bukan sekadar hasilnya lebih pendek.
LATIN_CHARS_PER_TOKEN = 2.0
THAI_CHARS_PER_TOKEN = 1.0


def estimate_tokens(text: str) -> int:
    """
    Memperkirakan jumlah token satu potongan teks.

    Dihitung per jenis aksara, bukan dengan satu angka pembagi.
    Aksara Thai satu hurufnya tiga byte di UTF-8 dan tokenizer BPE
    tingkat byte memecahnya sekitar satu token per huruf, sehingga
    prompt Thai yang diperkirakan memakai angka Latin keluar tiga
    kali lebih kecil dari sebenarnya.

    Dipakai di dua tempat yang keduanya tidak boleh kekecilan: saat
    menentukan num_ctx, dan saat menghitung berapa lama menunggu
    Ollama memproses prompt sebelum token pertama keluar.
    """
    body = text or ""

    if not body:
        return 0

    thai = sum(1 for char in body if THAI_RANGE.match(char))
    lain = len(body) - thai

    return int(
        thai / THAI_CHARS_PER_TOKEN + lain / LATIN_CHARS_PER_TOKEN
    ) + 1


def thai_share(text: str) -> float:
    """
    Porsi karakter beraksara Thai dalam satu teks.
    """
    clean = [char for char in text if not char.isspace()]

    if not clean:
        return 0.0

    thai = sum(1 for char in clean if THAI_RANGE.match(char))

    return thai / len(clean)


def is_unspaced(text: str) -> bool:
    """
    Menentukan apakah teks ini ditulis tanpa spasi antar kata.
    """
    return thai_share(text) >= THAI_SHARE_THRESHOLD


def strip_marks(text: str) -> str:
    """
    Membuang tanda vokal dan nada yang menempel pada huruf.

    Di aksara Thai tanda ini ditulis di atas atau di bawah huruf
    induknya dan tidak menambah panjang kata, jadi menghitungnya
    akan melebih-lebihkan jumlah kata.
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def count_words(text: str) -> int:
    """
    Menghitung jumlah kata dengan cara yang sesuai aksaranya.

    Untuk teks tanpa spasi, bagian beraksara Thai diperkirakan dari
    jumlah hurufnya sedangkan bagian Latin (nama brand, angka)
    tetap dihitung biasa, karena halaman Thai hampir selalu
    bercampur keduanya.
    """
    clean = (text or "").strip()

    if not clean:
        return 0

    if not is_unspaced(clean):
        return len(clean.split())

    thai_chars: list[str] = []
    other_parts: list[str] = []
    buffer: list[str] = []

    for char in clean:
        if THAI_RANGE.match(char):
            if buffer:
                other_parts.append("".join(buffer))
                buffer = []

            thai_chars.append(char)
        else:
            buffer.append(char)

    if buffer:
        other_parts.append("".join(buffer))

    thai_words = round(
        len(strip_marks("".join(thai_chars))) / THAI_CHARS_PER_WORD
    )

    other_words = sum(len(part.split()) for part in other_parts)

    return max(thai_words + other_words, 1)


def count_keyword(text: str, keyword: str) -> int:
    """
    Menghitung kemunculan keyword di dalam teks.

    Batas kata (\\b) hanya dipasang kalau keywordnya memang punya
    batas kata. Di teks Thai tidak ada peralihan huruf-ke-bukan-huruf
    di antara kata, jadi \\b tidak pernah cocok dan hasilnya selalu
    nol, seolah keywordnya tidak ada di halaman mana pun.
    """
    clean = (keyword or "").strip().lower()
    body = (text or "").lower()

    if not clean or not body:
        return 0

    if is_unspaced(clean):
        return body.count(clean)

    # Batasnya diperiksa terhadap huruf Latin saja, bukan lewat \b.
    # \b menandai peralihan antara \w dan bukan \w, dan aksara Thai
    # termasuk \w, sehingga keyword Latin yang menempel pada teks
    # Thai seperti "เว็บslot gacorที่ดี" tidak pernah dianggap punya
    # batas kata dan hasilnya nol. Padahal keyword Latin di halaman
    # Thai justru lazim: nama brand dan istilah teknis.
    return len(
        re.findall(
            rf"(?<![0-9A-Za-z_]){re.escape(clean)}(?![0-9A-Za-z_])",
            body,
        )
    )


def keyword_tokens(keyword: str) -> list[str]:
    """
    Memecah keyword jadi potongan yang bisa dicari di dalam teks.

    Untuk keyword Thai tidak ada yang bisa dipecah, jadi keywordnya
    dipakai utuh. Memaksakan pemecahan lewat regex Latin
    menghasilkan daftar kosong, dan setiap pemeriksaan yang memakai
    daftar itu jadi dilewati diam-diam.
    """
    clean = (keyword or "").strip().lower()

    if not clean:
        return []

    if is_unspaced(clean):
        return [clean]

    return [
        token
        for token in re.findall(r"[^\W_]+", clean, re.UNICODE)
        if len(token) >= 3
    ]


def token_set(text: str, limit: int = 4000) -> set[str]:
    """
    Kumpulan potongan teks untuk membandingkan dua halaman.

    Teks berspasi dipecah per kata. Teks tanpa spasi dipecah jadi
    potongan empat karakter, karena tanpa itu himpunannya kosong
    dan dua halaman yang sama sekali berbeda akan dinilai identik.
    """
    body = (text or "").lower()

    if not body:
        return set()

    if is_unspaced(body):
        thai_only = "".join(
            char for char in body if THAI_RANGE.match(char)
        )

        grams = {
            thai_only[index:index + THAI_GRAM]
            for index in range(max(len(thai_only) - THAI_GRAM + 1, 0))
        }

        latin = set(LATIN_WORD.findall(body))

        # Diurutkan dulu sebelum dipotong. Urutan iterasi himpunan
        # Python ikut acak hash string yang berbeda tiap proses, jadi
        # tanpa ini potongan 4000 pertama berubah tiap kali server
        # dijalankan ulang dan vonis cloaking untuk halaman yang sama
        # bisa berbeda antar run.
        return set(sorted(grams | latin)[:limit])

    return set(sorted(set(LATIN_WORD.findall(body)))[:limit])


# Kata yang tidak membedakan isi satu kalimat dari kalimat lain.
#
# Dipakai membandingkan dua teks berdasarkan yang dibicarakannya, bukan
# berdasarkan hurufnya. Tanpa membuang kata-kata ini, dua pertanyaan
# yang menanyakan hal yang persis sama tapi disusun beda tampak cuma
# 40% mirip, karena "apa", "yang", "dengan", dan "bagaimana" ikut
# dihitung sebagai isi.
CONTENT_STOPWORDS = {
    "ada", "adalah", "agar", "akan", "aku", "anda", "antara", "apa",
    "apakah", "atas", "atau", "bagaimana", "bagi", "bahwa", "banyak",
    "bila", "bisa", "boleh", "bolehkah", "buat", "cara", "dalam", "dan",
    "dapat", "dari", "demi", "dengan", "di", "dia", "gimana", "hal",
    "harus", "hingga", "ini", "itu", "jadi", "jika", "juga", "kalau",
    "kami", "kamu", "kapan", "karena", "ke", "kenapa", "kepada",
    "ketika", "kita", "lagi", "lalu", "lebih", "maka", "mana", "masih",
    "maupun", "melalui", "mengapa", "mereka", "nya", "oleh", "pada",
    "para", "perlu", "pun", "saat", "saja", "sama", "sampai", "sangat",
    "saya", "sebagai", "sebelum", "secara", "sehingga", "selama",
    "sementara", "seperti", "serta", "setelah", "siapa", "sudah",
    "supaya", "tanpa", "tapi", "telah", "tentang", "terhadap", "tetapi",
    "tidak", "untuk", "yaitu", "yakni", "yang",
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do",
    "does", "for", "from", "how", "in", "is", "it", "of", "on", "or",
    "should", "that", "the", "this", "to", "was", "what", "when",
    "where", "which", "who", "why", "will", "with", "would",
}

WORD_CHARS = re.compile(r"[^\W\d_]+", re.UNICODE)


def content_tokens(text: str) -> set[str]:
    """
    Kata isi sebuah teks, tanpa kata sambung dan kata tanya.

    Teks tanpa spasi dipecah jadi potongan empat karakter seperti di
    token_set, karena memecah per kata mustahil di aksara Thai.
    """
    body = (text or "").lower()

    if not body:
        return set()

    if is_unspaced(body):
        thai_only = "".join(
            char for char in body if THAI_RANGE.match(char)
        )

        return {
            thai_only[index:index + THAI_GRAM]
            for index in range(max(len(thai_only) - THAI_GRAM + 1, 0))
        }

    kata = WORD_CHARS.findall(body)
    isi = {k for k in kata if k not in CONTENT_STOPWORDS}

    # Kalimat yang seluruhnya kata sambung tetap harus bisa
    # dibandingkan dengan sesamanya.
    return isi or set(kata)


# Berapa kata berurutan yang dianggap satu potongan frasa.
#
# Tiga cukup untuk membedakan "kalimat yang sama" dari "topik yang
# sama". Dua terlalu sering muncul kebetulan; empat melewatkan
# kalimat yang disalin lalu diganti satu katanya.
PHRASE_GRAM = 3


def content_shingles(text: str, n: int = PHRASE_GRAM) -> set:
    """
    Potongan frasa sebuah teks: tiap n kata berurutan.

    Dipakai membandingkan paragraf, sementara content_tokens dipakai
    membandingkan teks pendek. Bedanya bukan selera melainkan yang
    terukur pada tiga kumpulan teks:

                                       irisan kata   frasa 3 kata
      tulisan asli pengguna, 16 par         0,396          0,101
      kerangka kalimat sama, 20 par         1,000          0,829
      beragam tapi sekosakata, 42 par       0,880          0,500

    Baris kedua harus dibatalkan dan baris ketiga harus lolos. Dengan
    irisan kata tidak ada satu pun ambang yang bisa memisahkan
    keduanya - 0,880 dan 1,000 praktis berimpit - karena paragraf
    yang membahas satu topik memang memakai kata yang itu-itu juga.
    Yang membedakan paragraf yang mengulang dari paragraf yang cuma
    setopik adalah apakah URUTAN katanya ikut sama, dan itu yang
    diukur di sini.

    Teks tanpa spasi memakai potongan huruf, sama seperti
    content_tokens: memecah per kata mustahil di aksara Thai.
    """
    body = (text or "").lower()

    if not body:
        return set()

    if is_unspaced(body):
        return content_tokens(body)

    kata = WORD_CHARS.findall(body)

    if len(kata) <= n:
        # Terlalu pendek untuk punya frasa. Dikembalikan sebagai satu
        # potongan utuh supaya dua teks pendek yang sama persis tetap
        # dikenali kembar.
        return {tuple(kata)} if kata else set()

    return {
        tuple(kata[index:index + n])
        for index in range(len(kata) - n + 1)
    }


def overlap_ratio(first: str, second: str) -> float:
    """
    Seberapa besar irisan isi dua teks, 0 sampai 1.

    Yang dibandingkan kata isinya, jadi "Apa perbedaan slot online dan
    slot fisik?" dan "Apa perbedaan utama antara slot online dan slot
    fisik?" bernilai 0,8 - dua pertanyaan yang menanyakan hal yang
    sama, meski tidak satu hurufnya pun sama persis.
    """
    kiri = content_tokens(first)
    kanan = content_tokens(second)

    if not kiri or not kanan:
        return 0.0

    gabungan = kiri | kanan

    if not gabungan:
        return 0.0

    return len(kiri & kanan) / len(gabungan)


def anchor_id(value: str, fallback: str = "bagian") -> str:
    """
    Membuat id anchor dari teks heading.

    Aksara non-Latin dipertahankan. Kalau dibuang, semua heading
    Thai menghasilkan id yang sama, seluruh tautan daftar isi
    menunjuk ke satu tempat, dan HTML-nya punya id kembar.
    """
    # Tanda vokal dan nada Thai termasuk kategori Mn dan tidak
    # dianggap \w oleh Python, padahal tanda itu bagian dari
    # hurufnya. Kalau ikut dibuang, anchornya penuh tanda hubung
    # dan sulit dikenali saat muncul di bilah alamat.
    kept = "".join(
        char
        if (char.isalnum() or unicodedata.category(char) == "Mn")
        else "-"
        for char in str(value or "").lower()
    )

    slug = re.sub(r"-{2,}", "-", kept).strip("-")

    return slug[:60] or fallback


# Pemisah yang lazim dipakai template di dalam satu baris pengulas:
# "Mikaela Hyakuya — Malang • ★★★★★".
#
# Spasi di kiri-kanan ikut DITANGKAP, bukan dibuang. Potongan hasil
# split disambung lagi apa adanya, dan pemisah yang kehilangan
# spasinya menerbitkan "Bagus Setiawan—Semarang•★★★★★".
NAME_PARTS = re.compile(r"(\s*[—–|•·]\s*|\s+-\s+)")


def author_name(text: str) -> str:
    """
    Nama orangnya saja, tanpa kota dan tanpa bintang.

    Dipakai data terstruktur, yang menanyakan siapa penulis ulasannya
    dan bukan bagaimana template menghiasnya. Person bernama
    "Mikaela Hyakuya — Malang • ★★★★★" adalah nama yang tidak dipakai
    siapa pun, dan Google membaca schema itu apa adanya.

    Ditulis di sini, bukan di generators/template_filler.py, supaya
    penulis JSON-LD bisa memakainya juga - berkas itu justru yang
    diimpor template_filler, jadi arah sebaliknya tidak mungkin.
    """
    return NAME_PARTS.split(" ".join(str(text or "").split()))[0].strip()
