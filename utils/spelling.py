"""
Membetulkan salah ketik pada istilah yang dipakai halaman ini.

Ini keluhan pengguna, dan yang dilaporkannya satu kata:

    deposit qrisk        seharusnya    deposit qris

Satu huruf, dan tidak ada satu tahap pun sebelum ini yang bisa
keberatan. Panjangnya sah, hurufnya sah, JSON-nya sah, dan tidak ada
kamus di mana pun di pipeline. Yang terbit adalah halaman yang di
mata pembaca ditulis orang yang tidak tahu nama alat bayarnya
sendiri - dan di mata mesin pencari, halaman yang tidak memuat kata
yang dicari orang.

Sebabnya model kecil yang menyusun teksnya. Grammar llama.cpp
menegakkan bentuk JSON dan panjang string, tidak pernah ejaan, jadi
huruf yang meleset lewat begitu saja.

Yang dibetulkan HANYA istilah yang tidak pernah jadi kata Indonesia
biasa. Itu batasan yang disengaja, bukan kemalasan: pembetul ejaan
umum yang bekerja dengan jarak satu huruf akan mengubah "plot" jadi
"slot", "aku" jadi "akun", dan "datar" jadi "daftar" - tiga kerusakan
untuk satu perbaikan. Daftar di bawah dipilih supaya salah ketiknya
tidak punya arti lain sama sekali.

Yang tidak disentuh sama sekali:
  - kata yang memuat angka, karena nama brand hampir selalu begitu
  - kata yang ada di nama brand atau keyword halaman ini
  - kata yang kebetulan sama dengan istilah lain di daftar
"""

import re


# Istilah yang ejaan bakunya ditegakkan, ditulis dalam bentuk
# tampilnya. Yang seluruhnya huruf besar diperlakukan sebagai
# singkatan: bentuk itu yang selalu dipakai, apa pun huruf besar
# kecil aslinya.
TERMS = (
    # alat bayar dan perbankan
    "QRIS",
    "e-wallet",
    "GoPay",
    "LinkAja",
    "ShopeePay",
    "OVO",
    "deposit",
    "withdraw",
    "penarikan",
    "transaksi",
    "rekening",
    "nominal",
    "potongan",
    "minimal",
    "transfer",
    "virtual",
    "otomatis",
    # istilah permainan
    "maxwin",
    "jackpot",
    "scatter",
    "freespin",
    "gacor",
    "rungkad",
    "provider",
    "pragmatic",
    "habanero",
    "RTP",
    # akun dan layanan
    "member",
    "login",
    "logout",
    "verifikasi",
    "keamanan",
    "enkripsi",
    "lisensi",
    "aplikasi",
    "browser",
    "android",
    "layanan",
    "pelanggan",
    "livechat",
    "whatsapp",
    "telegram",
    "notifikasi",
    "responsif",
)


# Kata Indonesia yang berjarak satu huruf dari salah satu istilah di
# atas, jadi tidak boleh dianggap salah ketik.
#
# Daftarnya pendek karena TERMS sudah dipilih supaya tetangganya
# sedikit. Yang tetap perlu disebut adalah kata yang benar-benar
# dipakai halaman seperti ini; kata langka yang secara teori bertabrakan
# dibiarkan, karena kalaupun muncul, muncul sekali.
SAFE_WORDS = frozenset(
    {
        "aku", "akun", "arisan", "bagian", "banyak", "cari", "dana",
        "dasar", "datar", "gambar", "kalian", "kamar", "kembar",
        "layanya", "lot", "main", "makin", "mawin", "member",
        "menarik", "minimal", "modal", "nomor", "pemain", "penarikan",
        "plot", "potong", "potongan", "sekali", "slot", "sot",
        "tanggal", "tawaran", "transfer", "wajar",
    }
)


def is_acronym(term: str) -> bool:
    return term.isupper()


def edits(term: str) -> set[str]:
    """
    Salah ketik yang mungkin terjadi pada satu istilah.

    Tiga macam saja: satu huruf tersisip, satu huruf hilang, dan dua
    huruf bersebelahan tertukar. Yang TIDAK diikutkan adalah penggantian
    satu huruf, dan itu justru pembatas terpentingnya - penggantian
    yang membuat "plot" berjarak satu langkah dari "slot", "kalian"
    dari "kalian", dan seluruh kerusakan yang membuat pembetul ejaan
    otomatis lebih merugikan daripada berguna.

    Ketiga macam yang tersisa hampir tidak pernah menghasilkan kata
    Indonesia dari istilah yang bukan kata Indonesia. "qrisk", "qrs",
    dan "qirs" tidak berarti apa-apa selain "qris" yang salah ketik.
    """
    dasar = term.casefold()
    huruf = "abcdefghijklmnopqrstuvwxyz"

    hasil: set[str] = set()

    for posisi in range(len(dasar) + 1):
        for tambahan in huruf:
            hasil.add(dasar[:posisi] + tambahan + dasar[posisi:])

    for posisi in range(len(dasar)):
        hasil.add(dasar[:posisi] + dasar[posisi + 1:])

    for posisi in range(len(dasar) - 1):
        hasil.add(
            dasar[:posisi]
            + dasar[posisi + 1]
            + dasar[posisi]
            + dasar[posisi + 2:]
        )

    hasil.discard(dasar)

    return hasil


def build_corrections() -> dict[str, str]:
    """
    Peta salah ketik ke ejaan bakunya.

    Salah ketik yang bisa berasal dari DUA istilah dibuang, bukan
    dipilih salah satunya. Kalau satu kata sama dekatnya ke dua
    istilah, tidak ada dasar untuk memilih, dan menebak berarti
    mengubah kata yang benar jadi kata lain yang benar - kerusakan
    yang jauh lebih sulit dilihat daripada salah ketik aslinya.
    """
    baku = {term.casefold() for term in TERMS}

    peta: dict[str, str] = {}
    bentrok: set[str] = set()

    for term in TERMS:
        for salah in edits(term):
            if salah in baku or salah in SAFE_WORDS or len(salah) < 4:
                continue

            if salah in peta and peta[salah] != term:
                bentrok.add(salah)
                continue

            peta[salah] = term

    for salah in bentrok:
        peta.pop(salah, None)

    return peta


CORRECTIONS = build_corrections()

# Kata dan angka, dipisah supaya tanda baca di sekelilingnya utuh.
# Tanda hubung ikut jadi bagian kata, karena "e-wallet" satu istilah.
WORD = re.compile(r"[0-9A-Za-zÀ-ɏ]+(?:-[0-9A-Za-zÀ-ɏ]+)*")


def match_case(salah: str, baku: str) -> str:
    """
    Memakai baku dengan huruf besar kecil seperti kata yang diganti.

    Singkatan tidak ikut aturan ini. "qris" yang ditulis huruf kecil
    tetap terbit "QRIS", karena bentuk itulah nama alat bayarnya -
    bukan pilihan gaya penulisnya.
    """
    if is_acronym(baku):
        return baku

    if salah.isupper():
        return baku.upper()

    if salah[:1].isupper():
        return baku[:1].upper() + baku[1:]

    return baku


def fix_terms(text, protected: set[str] | None = None) -> str:
    """
    Membetulkan salah ketik istilah di satu teks.

    "protected" berisi kata yang tidak boleh disentuh apa pun
    keadaannya - kata di nama brand dan di keyword halaman ini. Nama
    brand yang kebetulan berjarak satu huruf dari sebuah istilah
    adalah nama brand, bukan salah ketik, dan mengubahnya berarti
    menerbitkan halaman atas nama situs yang tidak ada.
    """
    isi = str(text or "")

    if not isi:
        return isi

    aman = protected or set()

    def ganti(cocok: re.Match) -> str:
        kata = cocok.group(0)
        kecil = kata.casefold()

        if kecil in aman or any(char.isdigit() for char in kata):
            return kata

        baku = CORRECTIONS.get(kecil)

        return match_case(kata, baku) if baku else kata

    return WORD.sub(ganti, isi)


def protected_words(*sources: str) -> set[str]:
    """
    Kata yang tidak boleh dibetulkan, dikumpulkan dari nama brand dan
    keyword.
    """
    aman: set[str] = set()

    for teks in sources:
        for kata in WORD.findall(str(teks or "")):
            aman.add(kata.casefold())

    return aman


def fix_content_terms(
    content: dict,
    keyword: str = "",
    brand_name: str = "",
) -> tuple[dict, int]:
    """
    Membetulkan salah ketik di seluruh isi halaman sekaligus.

    Dipakai di satu titik, sesudah semua giliran model selesai dan
    sebelum teksnya dipasang ke halaman, supaya tidak ada peran yang
    terlewat. Peran berawalan garis bawah dilewati: isinya penanda
    untuk riwayat, bukan teks yang terbit.
    """
    aman = protected_words(keyword, brand_name)

    hasil = dict(content)
    diperbaiki = 0

    for peran, nilai in content.items():
        if peran.startswith("_"):
            continue

        if isinstance(nilai, str):
            baru = fix_terms(nilai, aman)

            if baru != nilai:
                hasil[peran] = baru
                diperbaiki += 1

        elif isinstance(nilai, list):
            baru_list = [
                fix_terms(item, aman) if isinstance(item, str) else item
                for item in nilai
            ]

            if baru_list != nilai:
                hasil[peran] = baru_list
                diperbaiki += sum(
                    1
                    for lama, baru in zip(nilai, baru_list)
                    if lama != baru
                )

    return hasil, diperbaiki


# --------------------------------------------------------------------
# Ragam bahasa
# --------------------------------------------------------------------
#
# Halaman ini dibaca orang yang belum kenal situsnya, dan pengguna
# meminta bunyinya "tidak kaku, formal tapi tidak terlalu formal, dan
# jangan menggunakan bahasa yang santai" (21 Agustus 2026).
#
# Aturannya sudah ditulis di prompt, dan prompt saja tidak cukup - itu
# pola yang sudah berulang di berkas ini. Terukur pada halaman
# BATARATOTO yang terbit 21 Agustus 2026: sembilan kalimat dibuka
# "Kamu bisa ...", dan satu jawaban FAQ menutup dengan "sistem akan
# membuat akun untukmu".
#
# Yang disapu di sini hanya sapaan dan kata gaul yang padanan bakunya
# tidak pernah berubah arti. Kata yang artinya bergeser - "bikin" jadi
# "membuat" tidak selalu pas - tetap disapu karena bentuk gaulnya
# memang tidak boleh terbit; yang tidak disapu justru kata biasa
# seperti "langsung", "tinggal", dan "cukup".
CASUAL_WORDS = {
    "kamu": "Anda",
    "km": "Anda",
    "kalian": "Anda",
    "nggak": "tidak",
    "ngga": "tidak",
    "enggak": "tidak",
    "gak": "tidak",
    "ga": "tidak",
    "udah": "sudah",
    "udh": "sudah",
    "bikin": "membuat",
    "banget": "sekali",
    "bgt": "sekali",
    "gue": "saya",
    "gua": "saya",
    "lu": "Anda",
    "elo": "Anda",
    "yuk": "",
    "dong": "",
    "nih": "",
    "sih": "",
    "kok": "",
    "deh": "",
    "aja": "saja",
    "doang": "saja",
    "bakal": "akan",
    "kayak": "seperti",
    "kaya": "seperti",
    "gitu": "begitu",
    "gini": "begini",
    "emang": "memang",
}

# "tapi" sengaja TIDAK ikut disapu. Ia bukan bahasa gaul melainkan
# bentuk pendek yang lazim di tulisan setengah resmi, dan menukarnya
# jadi "tetapi" di setiap kalimat justru menarik bunyinya ke arah kaku
# - persis yang dikeluhkan pengguna di sisi sebelahnya.


# ==========================================================
# SISI SEBELAHNYA: BAHASA YANG TERLALU KAKU
# ==========================================================

# Sampai 30 Agustus 2026 penyapu ragam bahasa cuma punya satu arah.
# CASUAL_WORDS menaikkan yang terlalu santai, dan tidak ada apa pun
# yang menurunkan yang terlalu kaku - padahal aturan di prompt sudah
# menyebutkan daftar kata kakunya sejak awal. Untuk model 4B, aturan
# prompt tanpa penyapu berarti aturan yang diikuti kadang-kadang saja,
# dan yang terbit persis yang dikeluhkan pengguna: "bahasa yang
# digunakan terlalu kaku".
#
# Yang disapu di sini BENTUK SURAT DINAS, bukan kata baku. Bedanya
# menentukan: "dapat", "tersebut", dan "melakukan" adalah kata
# Indonesia biasa yang dipakai orang menulis halaman web, dan
# menukarnya berarti menulis ulang kalimat yang tidak ada
# masalahnya. Yang ada di daftar ini cuma bentuk yang hampir tidak
# pernah muncul di luar surat resmi dan skripsi.
#
# Frasa panjang didahulukan atas yang pendek, dan itu bukan
# kerapian: "namun demikian" harus tertangkap utuh sebelum "namun"
# sempat menangkap potongannya sendiri.
STIFF_PHRASES = {
    "sehubungan dengan hal tersebut": "karena itu",
    "sehubungan dengan hal ini": "karena itu",
    "berkenaan dengan hal tersebut": "karena itu",
    "oleh karena itu": "karena itu",
    "oleh sebab itu": "karena itu",
    "dengan demikian": "jadi",
    "namun demikian": "meski begitu",
    "akan tetapi": "tapi",
    "merupakan suatu": "adalah",
    "dalam rangka": "untuk",
    "dalam hal ini": "",
    "pada dasarnya": "",
    "perlu diketahui bahwa": "",
    "dapat dipastikan bahwa": "",
    "adapun": "",
    "bahwasanya": "bahwa",
    "sebagaimana": "seperti",
    "senantiasa": "selalu",
    "seyogyanya": "sebaiknya",
    "dikarenakan": "karena",
    "apabila": "kalau",
    "terdapat": "ada",
    "guna": "untuk",
}

# Kata yang tidak boleh ikut tersapu meski memuat potongan di atas.
#
# "guna" berdiri sendiri berarti "untuk", tapi ia juga potongan sah
# dari "berguna", "kegunaan", dan "menggunakan". Batas kata sudah
# menahan ketiganya; daftar ini untuk yang lolos batas kata.
STIFF_SAFE = frozenset({"guna-guna"})

STIFF_PATTERN = re.compile(
    r"\b("
    + "|".join(
        re.escape(frasa)
        for frasa in sorted(STIFF_PHRASES, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def fix_stiffness(text, protected: set[str] | None = None) -> str:
    """
    Menurunkan ragam bahasa dari kaku ke setengah resmi.

    Kembarannya fix_register, dan keduanya menuju tempat yang sama
    dari dua arah. Yang di sana menaikkan "nggak" jadi "tidak"; yang
    di sini menurunkan "dengan demikian" jadi "jadi".

    Nama situs dan keyword dilindungi lewat protected, dengan alasan
    yang sama persis: nama situs boleh saja kebetulan berbunyi
    seperti kata yang ada di daftar, dan membetulkannya berarti
    menulis ulang nama orang.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    aman = {kata.casefold() for kata in (protected or set())}

    def ganti(cocok: re.Match) -> str:
        asli = cocok.group(0)
        kunci = asli.casefold()

        if kunci in aman or kunci in STIFF_SAFE:
            return asli

        baku = STIFF_PHRASES.get(kunci)

        if baku is None:
            return asli

        if not baku:
            # Frasa pengisi yang tidak menyumbang arti - dibuang.
            return ""

        return match_case(asli, baku)

    hasil = STIFF_PATTERN.sub(ganti, text)

    # Kebersihan sesudah frasa dibuang. Frasa pembuka yang hilang
    # meninggalkan spasi ganda, koma yang menggantung di awal
    # kalimat, dan huruf kecil di tempat huruf besar - ketiganya
    # lebih kelihatan daripada frasa yang tadi dibuang.
    hasil = re.sub(r"\s{2,}", " ", hasil)
    hasil = re.sub(r"(^|(?<=[.!?]\s))\s*,\s*", r"\1", hasil)
    hasil = re.sub(r"\s+([,.!?;:])", r"\1", hasil)
    hasil = hasil.strip()

    if hasil and hasil[0].islower() and text[:1].isupper():
        hasil = hasil[0].upper() + hasil[1:]

    return hasil


def fix_content_stiffness(
    content: dict,
    keyword: str = "",
    brand_name: str = "",
) -> tuple[dict, int]:
    """
    Menurunkan ragam bahasa seluruh isi halaman sekaligus.

    Bentuknya sengaja sama persis dengan fix_content_register: satu
    titik panggil, sesudah semua giliran model selesai, peran
    berawalan garis bawah dilewati.
    """
    aman = protected_words(keyword, brand_name)

    hasil = dict(content)
    diperbaiki = 0

    for peran, nilai in content.items():
        if peran.startswith("_"):
            continue

        if isinstance(nilai, str):
            baru = fix_stiffness(nilai, aman)

            if baru != nilai:
                hasil[peran] = baru
                diperbaiki += 1

        elif isinstance(nilai, list):
            baru_list = [
                fix_stiffness(item, aman) if isinstance(item, str) else item
                for item in nilai
            ]

            if baru_list != nilai:
                hasil[peran] = baru_list
                diperbaiki += sum(
                    1
                    for lama, baru in zip(nilai, baru_list)
                    if lama != baru
                )

    return hasil, diperbaiki

# Akhiran milik yang membuat sapaan jadi santai: "untukmu", "akunmu".
POSSESSIVE = re.compile(
    r"\b(\w{3,})(mu)\b",
    re.IGNORECASE,
)

# Kata yang berakhiran "mu" tapi bukan kata milik. Tanpa daftar ini
# "ilmu", "kamu", "waktu" ikut dipotong jadi bentuk yang bukan kata.
POSSESSIVE_SAFE = frozenset(
    """
    ilmu kamu bermu jamu palmu telmu kelmu ramu samu lumu tamu
    """.split()
)


def fix_register(text, protected: set[str] | None = None) -> str:
    """
    Menaikkan ragam bahasa dari santai ke setengah resmi.

    Nama situs dan keyword dilindungi lewat protected, sama seperti
    fix_terms: nama situs boleh saja kebetulan berbunyi seperti kata
    gaul, dan membetulkannya berarti menulis ulang nama orang.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    aman = {kata.casefold() for kata in (protected or set())}

    def ganti_kata(cocok: re.Match) -> str:
        asli = cocok.group(0)
        kunci = asli.casefold()

        if kunci in aman:
            return asli

        baku = CASUAL_WORDS.get(kunci)

        if baku is None:
            return asli

        if not baku:
            # Kata pemanis yang tidak punya padanan - dibuang.
            return ""

        return match_case(asli, baku)

    hasil = WORD.sub(ganti_kata, text)

    def ganti_milik(cocok: re.Match) -> str:
        penuh = cocok.group(0)

        if penuh.casefold() in POSSESSIVE_SAFE or penuh.casefold() in aman:
            return penuh

        return f"{cocok.group(1)} Anda"

    hasil = POSSESSIVE.sub(ganti_milik, hasil)

    # Spasi ganda yang lahir dari kata yang dibuang.
    return re.sub(r"\s{2,}", " ", hasil).strip()


def fix_content_register(
    content: dict,
    keyword: str = "",
    brand_name: str = "",
) -> tuple[dict, int]:
    """
    Menaikkan ragam bahasa seluruh isi halaman sekaligus.

    Bentuknya sengaja sama persis dengan fix_content_terms: satu titik
    panggil, sesudah semua giliran model selesai, peran berawalan
    garis bawah dilewati.
    """
    aman = protected_words(keyword, brand_name)

    hasil = dict(content)
    diperbaiki = 0

    for peran, nilai in content.items():
        if peran.startswith("_"):
            continue

        if isinstance(nilai, str):
            baru = fix_register(nilai, aman)

            if baru != nilai:
                hasil[peran] = baru
                diperbaiki += 1

        elif isinstance(nilai, list):
            baru_list = [
                fix_register(item, aman) if isinstance(item, str) else item
                for item in nilai
            ]

            if baru_list != nilai:
                hasil[peran] = baru_list
                diperbaiki += sum(
                    1
                    for lama, baru in zip(nilai, baru_list)
                    if lama != baru
                )

    return hasil, diperbaiki
