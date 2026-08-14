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
