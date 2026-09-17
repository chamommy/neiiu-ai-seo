"""
Mengganti brand lama milik template dengan brand baru.

Mengisi slot saja tidak cukup. Nama brand lama tersebar di tempat
yang bukan slot isi mana pun: di teks logo, di alt gambar, di
kalimat hak cipta, di judul yang diulang di beberapa tempat. Kalau
hanya slot yang diisi, halaman baru terbit dengan nama brand lama
masih menempel di sana-sini - dan itu justru bagian yang paling
cepat terlihat orang.

Dua hal dikerjakan di sini, keduanya HANYA pada rentang teks yang
sudah dinyatakan aman oleh pemindai. Tidak ada satu pun karakter di
luar rentang itu yang tersentuh, jadi jaminan strukturnya tetap
sama seperti sebelumnya.

1. Ganti nama. Setiap kemunculan brand lama jadi brand baru, tanpa
   memandang huruf besar-kecilnya, dan bentuk penulisannya diikuti:
   ABECEDE jadi DEEFGE, Abecede jadi Deefge, abecede jadi deefge.

2. Samakan teks kembar. Kalimat milik template yang muncul di lebih
   dari satu tempat - judul yang diulang di h1, di alt gambar, di
   footer - ikut memakai teks baru yang sama dengan yang dipakai di
   tempat pertamanya. Tanpa ini, judul baru muncul di <title>
   sementara kalimat lamanya yang persis sama masih terbaca di
   badan halaman.
"""

import re


# Teks sependek ini terlalu umum untuk dicocokkan sebagai "kalimat
# yang sama". Kata seperti "Promo" bisa muncul di mana saja dengan
# maksud yang sama sekali berbeda.
MIN_ECHO_CHARS = 12


# Pemisah antar beberapa nama brand lama di satu kolom.
#
# Satu template bisa memuat LEBIH DARI SATU brand lama, berlapis.
# Terukur pada template 616 milik pengguna: struktur aslinya milik
# TeePublic, lalu di atasnya sudah ditempeli BATARATOTO. Diisi salah
# satunya saja, yang lain lolos utuh - 48 sebutan "TeePublic" bertahan
# di halaman jadi, termasuk di og:site_name dan product:brand.
#
# Titik koma dan baris baru ikut, bukan cuma koma: nama brand
# kadang-kadang memuat koma di dalamnya, dan pengguna yang menempel
# daftar dari tempat lain menempelnya per baris.
BRAND_SPLIT = re.compile(r"[,;\r\n]+")


def brand_names(value: str) -> list[str]:
    """
    Memecah isi kolom brand lama jadi daftar nama.

    Satu nama tanpa pemisah menghasilkan daftar berisi satu - jadi
    pemanggil yang mengirim satu nama mendapat perilaku yang sama
    persis seperti sebelum daftar ini ada.
    """
    return [
        " ".join(potong.split())
        for potong in BRAND_SPLIT.split(str(value or ""))
        if potong.strip()
    ]


def variants(name: str) -> list[str]:
    """
    Bentuk penulisan nama brand yang perlu ikut dikenali.

    Nama brand rutin ditulis tanpa spasi di URL dan di logo, jadi
    "Abece De" juga harus ketemu saat tertulis "AbeceDe".

    Menerima beberapa nama sekaligus, dipisah koma atau baris baru -
    lihat brand_names.
    """
    bentuk: set[str] = set()

    for clean in brand_names(name):
        bentuk.update(
            {clean, clean.replace(" ", ""), clean.replace(" ", "-")}
        )

    return sorted(
        (item for item in bentuk if item),
        key=len,
        reverse=True,
    )


# Pemisah yang boleh menyelip di perbatasan huruf-angka nama brand.
#
# variants() sudah mengurus arah yang satu: nama yang DIBERI berspasi
# ("Abece De") ikut dicari tanpa spasi. Arah sebaliknya yang belum:
# nama yang diberi tanpa spasi ("OSB99") tidak pernah ketemu waktu
# templatenya menulisnya "OSB 99".
#
# Terukur 14 Agustus 2026 pada job 64, template 'lego themes':
# penyapu menurunkan "OSB99" dari 111 jadi 32 - dan yang 32 semuanya
# di dalam URL, yang memang sengaja tidak disentuh. Yang tersisa di
# teks yang dibaca orang tepat SATU, dan bentuknya "OSB 99".
#
# Disisipkan hanya di perbatasan huruf-angka, bukan di tiap posisi.
# Di situlah nama brand terbelah waktu ditulis tangan - "OSB 99",
# "TIMAH 33" - sedangkan menyisipkannya di mana saja akan membuat
# pola yang cocok dengan hampir apa pun.
BRAND_BOUNDARY = r"[\s\-]?"


def loose_form(bentuk: str) -> str:
    """
    Pola satu bentuk nama, berspasi opsional di perbatasan huruf-angka.
    """
    keping: list[str] = []

    for nomor, huruf in enumerate(bentuk):
        if nomor:
            sebelum = bentuk[nomor - 1]

            ganti_jenis = huruf.isdigit() != sebelum.isdigit()

            if ganti_jenis and huruf.isalnum() and sebelum.isalnum():
                keping.append(BRAND_BOUNDARY)

        keping.append(re.escape(huruf))

    return "".join(keping)


def match_case(sumber: str, pengganti: str) -> str:
    """
    Menyesuaikan huruf besar-kecil pengganti dengan yang digantikan.

    Logo yang ditulis ABECEDE harus jadi DEEFGE, bukan Deefge,
    supaya tampilannya tidak berubah bentuk di tengah halaman.
    """
    if sumber.isupper():
        return pengganti.upper()

    if sumber.islower():
        return pengganti.lower()

    if sumber[:1].isupper():
        return pengganti[:1].upper() + pengganti[1:]

    return pengganti


def build_pattern(old_brand: str) -> re.Pattern | None:
    """
    Menyusun pola pencarian nama brand lama.

    Batas kata tidak dipakai. Aksara Thai seluruhnya masuk kategori
    \\w bagi Python, jadi \\b tidak pernah cocok di antara dua aksara
    Thai dan nama brand yang menempel pada teks Thai tidak akan
    pernah ketemu. Yang dipakai batas buatan: karakter di kiri dan
    kanan tidak boleh berupa huruf Latin atau angka.
    """
    bentuk = variants(old_brand)

    if not bentuk:
        return None

    return re.compile(
        r"(?<![0-9A-Za-z])(" + "|".join(loose_form(b) for b in bentuk) + r")"
        r"(?![0-9A-Za-z])",
        re.IGNORECASE,
    )


def swap_brand(text: str, pattern: re.Pattern, new_brand: str) -> str:
    """
    Mengganti seluruh kemunculan brand lama di satu potongan teks.
    """
    return pattern.sub(
        lambda m: match_case(m.group(0), new_brand),
        text,
    )


# Kata depan yang boleh berdiri di antara dua sebutan nama brand
# yang sebenarnya satu sebutan.
BRAND_JOINERS = (
    "di", "ke", "dari", "pada", "untuk", "dengan", "oleh", "adalah",
    "yaitu", "yakni", "in", "at", "on", "of", "for", "is",
)


def collapse_repeats(text: str, new_brand: str) -> str:
    """
    Merapikan nama brand yang tertulis dua kali berturut-turut.

    Sejak model diminta menyebut nama brand di sekitar separuh
    paragraf, sesekali ia menempelkannya dua kali dalam satu napas.
    Terukur di halaman jadi: "ASOKASLOT di ASOKASLOT dirancang khusus
    untuk memudahkan akses" - sebutan keduanya bukan penekanan,
    melainkan tempelan yang membuat kalimatnya berhenti masuk akal.

    Yang dibuang sebutan kedua beserta kata depan yang menyambungnya,
    sehingga kalimatnya kembali utuh: "ASOKASLOT dirancang khusus
    untuk memudahkan akses".
    """
    nama = " ".join((new_brand or "").split())

    if not nama:
        return text

    pola = re.compile(
        r"(?<![0-9A-Za-z])"
        + re.escape(nama)
        + r"(\s+(?:"
        + "|".join(BRAND_JOINERS)
        + r"))?\s+"
        + re.escape(nama)
        + r"(?![0-9A-Za-z])",
        re.IGNORECASE,
    )

    sebelum = None
    hasil = text

    # Diulang karena tiga sebutan berturut-turut menyisakan pasangan
    # baru sesudah pasangan pertamanya dirapikan.
    while hasil != sebelum:
        sebelum = hasil
        hasil = pola.sub(lambda m: m.group(0)[: len(nama)], hasil)

    return hasil


def normalize(text: str) -> str:
    return " ".join((text or "").split()).strip().casefold()


# Panjang minimum sebuah nama supaya boleh dipulihkan dari ejaan yang
# MELESET, bukan cuma dari huruf besar-kecil yang salah.
#
# Nama pendek berhuruf saja terlalu dekat dengan kata biasa. "MEGA"
# berjarak satu huruf dari "MEJA", "MERA", "MEGAH" - dan kalau tiga
# kata itu boleh ditarik jadi nama brand, halaman yang menyebut meja
# akan terbit menyebut nama situs. Nama berangka tidak punya soal itu:
# tidak ada kata Indonesia maupun Thai yang memuat angka, jadi
# "SIAM123" tidak berjarak dekat dari kata apa pun.
FUZZY_MIN_LETTERS = 6


def edit_distance(a: str, b: str, batas: int) -> int:
    """
    Jarak sunting dua kata, berhenti begitu melewati batas.

    Berhenti lebih awal bukan demi kecepatan melainkan demi
    kejelasan: yang ditanyakan pemanggilnya cuma "apakah masih di
    dalam batas", dan angka pasti di luar batas tidak dipakai
    siapa pun.
    """
    if abs(len(a) - len(b)) > batas:
        return batas + 1

    baris = list(range(len(b) + 1))

    for i, huruf_a in enumerate(a, 1):
        baru = [i]

        for j, huruf_b in enumerate(b, 1):
            baru.append(min(
                baris[j] + 1,
                baru[j - 1] + 1,
                baris[j - 1] + (huruf_a != huruf_b),
            ))

        baris = baru

        if min(baris) > batas:
            return batas + 1

    return baris[-1]


# Token yang bisa jadi calon nama situs: huruf dan angka yang
# bersambung. Tanda hubung TIDAK ikut - "slot-gacor" adalah dua kata,
# dan menyatukannya membuat setiap keyword bertanda hubung jadi calon.
BRAND_CANDIDATE = re.compile(r"[^\W_]+", re.UNICODE)


# Tanda yang boleh diselipkan model di tengah nama situs.
#
# Bukan sembarang tanda: yang di sini semuanya tanda yang TIDAK
# memisahkan kata bagi mata pembaca - spasi, hubung, titik, garis
# bawah. Nama yang dipotong koma atau tanda kurung bukan nama yang
# salah ketik melainkan dua hal yang memang berbeda.
# Nolnya penting: pemisah boleh ada di sela mana pun, bukan wajib di
# setiap sela. Model memenggal nama di satu-dua tempat saja
# ("BATARAT-TO-TO"), bukan di antara tiap huruf. Yang menuntut
# sedikitnya satu pemisah adalah pemeriksaan di restore_split_brand,
# jadi nama yang sudah utuh tetap tidak pernah tersentuh.
BRAND_SPLIT_MARKS = r"[\s._\-]{0,2}"


def split_brand_pattern(brand: str):
    """
    Pola yang menemukan nama situs yang diselipi tanda pisah.

    Model 4B rutin memenggal nama yang tidak dikenalnya. Terukur pada
    halaman yang benar-benar terbit 21 Agustus 2026:

        BATARATOTO - Slot Online di BATARAT-TO-TO Akses Cepat

    Pemulih ejaan yang sudah ada tidak pernah melihatnya, dan sebabnya
    di tokenisasi: BRAND_CANDIDATE memotong per deretan huruf-angka,
    jadi "BATARAT-TO-TO" masuk sebagai TIGA kata - "BATARAT", "TO",
    "TO" - dan tidak satu pun berjarak dua sunting dari "BATARATOTO".

    Akibatnya berlipat, bukan satu. Bentuk yang rusak juga tidak
    dikenali strip_brand_mentions, jadi ia lolos dari penyapu sebutan
    kedua - dan judulnya terbit menyebut nama situs dua kali, sekali
    benar sekali rusak.

    Nama pendek TIDAK dilayani, dengan ambang yang sama seperti
    pemulihan ejaan: pola yang membolehkan spasi di antara tiap huruf
    terlalu longgar untuk nama tiga huruf.
    """
    inti = [huruf for huruf in str(brand or "") if huruf.isalnum()]

    if len(inti) < FUZZY_MIN_LETTERS:
        return None

    return re.compile(
        # Tidak boleh menempel huruf lain di kedua ujungnya, supaya
        # nama tidak dicomot dari tengah kata yang lebih panjang.
        r"(?<![^\W_])"
        + BRAND_SPLIT_MARKS.join(re.escape(huruf) for huruf in inti)
        + r"(?![^\W_])",
        re.IGNORECASE,
    )


def restore_split_brand(text: str, brand: str) -> tuple[str, int]:
    """
    Menyatukan kembali nama situs yang diselipi tanda pisah.

    Yang sudah tertulis benar tidak dihitung: polanya menuntut
    sedikitnya satu tanda pisah, jadi nama yang utuh tidak pernah jadi
    calon dan fungsi ini aman dijalankan berkali-kali.
    """
    nama = str(brand or "").strip()
    isi = str(text or "")

    if not nama or not isi:
        return isi, 0

    pola = split_brand_pattern(nama)

    if pola is None:
        return isi, 0

    jumlah = 0

    def ganti(cocok: re.Match) -> str:
        nonlocal jumlah

        kena = cocok.group(0)

        if kena == nama:
            return kena

        # Yang bedanya cuma huruf besar-kecil diurus restore_brand;
        # di sini yang dicari khusus yang KEMASUKAN tanda pisah.
        if not any(not huruf.isalnum() for huruf in kena):
            return kena

        # Nama yang dipisah SPASI dituntut sama persis huruf
        # besar-kecilnya, dan ini bukan kerewelan.
        #
        # Spasi adalah pemisah kata yang sah, jadi nama situs yang
        # kebetulan berupa frasa umum akan menabrak kalimat biasa.
        # Terukur: brand "SITUSSLOT" mengubah "situs slot gacor hari
        # ini" jadi "SITUSSLOT gacor hari ini" - kalimat pembaca
        # dimakan nama situs. Sebutan nama situs yang sungguhan
        # ditulis seperti namanya; frasa biasa tidak.
        #
        # Tanda hubung, titik, dan garis bawah tidak dituntut begitu:
        # ketiganya jarang memisahkan dua kata biasa, dan justru itu
        # bentuk yang dipakai model waktu memenggal nama.
        if any(huruf.isspace() for huruf in kena):
            if re.sub(r"\s+", "", kena) != nama:
                return kena

        jumlah += 1

        return nama

    hasil = pola.sub(ganti, isi)

    # Jalan kedua: nama yang dipenggal SEKALIGUS salah ketik.
    #
    # Pola di atas menuntut hurufnya sama persis, jadi ia tidak pernah
    # melihat "BATARAT-TO-TO" - potongannya menyusun BATARATTOTO,
    # sebelas huruf, satu lebih banyak daripada namanya. Bentuk itu
    # yang benar-benar terbit 21 Agustus 2026, jadi ia bukan
    # kemungkinan teoretis.
    #
    # Di sini yang dicari deretan yang disambung tanda hubung, titik,
    # atau garis bawah - TANPA spasi, dengan alasan yang sama seperti
    # di atas - lalu bentuk sambungnya diadu dengan nama memakai
    # penjaga yang sama persis dengan pemulihan ejaan biasa: jendela
    # panjang, tiga huruf pertama, dan jarak sunting.
    batas = 1 if len(nama) <= 8 else 2

    def ganti_meleset(cocok: re.Match) -> str:
        nonlocal jumlah

        kena = cocok.group(0)
        sambung = re.sub(r"[._\-]+", "", kena)

        if sambung == nama:
            jumlah += 1
            return nama

        if abs(len(sambung) - len(nama)) > batas:
            return kena

        if sambung.casefold()[:3] != nama.casefold()[:3]:
            return kena

        if edit_distance(sambung.casefold(), nama.casefold(), batas) > batas:
            return kena

        jumlah += 1

        return nama

    return (
        re.sub(
            r"(?<![^\W_])[^\W_]+(?:[._\-][^\W_]+)+(?![^\W_])",
            ganti_meleset,
            hasil,
        ),
        jumlah,
    )


def restore_brand(text: str, brand: str, keyword: str = "") -> tuple[str, int]:
    """
    Mengembalikan nama situs ke ejaan persis seperti yang diketik user.

    Nama brand adalah token atomik: pengguna mengetik "SIAM123", jadi
    seluruh halaman harus berbunyi "SIAM123". Model kecil rutin
    meleset satu huruf - terukur, yang benar-benar terbit "SIAM12S" -
    dan satu huruf itu menerbitkan halaman atas nama situs yang tidak
    ada.

    Dua tingkat, dan pemisahannya yang menahan mesin ini dari merusak
    kata biasa:

      1. Ejaannya sudah benar, huruf besar-kecilnya yang salah
         ("Siam123" untuk "SIAM123"). Selalu dipulihkan, berapa pun
         panjang namanya - tidak ada risikonya, karena yang dicocokkan
         seluruh token, bukan potongan.

      2. Ejaannya sendiri meleset ("SIAM12S", "SIAM1234"). Hanya
         dipulihkan kalau namanya cukup khas - lihat
         FUZZY_MIN_LETTERS.

    Yang TIDAK disentuh, dan inilah yang diuji lebih dulu sebelum
    ambangnya dipilih: "Wayang kulit" di halaman WAYANGPLAY, "Siam"
    sebagai nama lama sebuah negara di halaman SIAM123, "megawatt" di
    halaman MEGA, dan "play" di halaman WAYANGPLAY. Keempatnya berada
    di luar jendela panjang, jadi tidak satu pun pernah jadi calon.

    Kata yang merupakan bagian dari keyword juga tidak pernah
    disentuh: keyword datang dari pengguna, sama seperti nama
    brandnya, dan yang keduanya berdekatan itu perkara pengguna -
    bukan salah ketik model.

    Mengembalikan (teks, jumlah yang dipulihkan).
    """
    nama = str(brand or "").strip()
    isi = str(text or "")

    if not nama or not isi:
        return isi, 0

    # Nama yang dipenggal tanda pisah disatukan LEBIH DULU.
    #
    # Urutannya mengikat: sesudah disatukan, hasilnya jadi satu token
    # yang bisa dinilai tingkat 1 dan tingkat 2 di bawah seperti
    # sebutan lainnya. Dijalankan belakangan, potongannya sudah
    # terlanjur lolos sebagai tiga kata yang masing-masing tidak mirip
    # nama apa pun.
    isi, dipenggal = restore_split_brand(isi, nama)

    target = nama.casefold()
    berangka = any(char.isdigit() for char in nama)
    boleh_meleset = berangka or len(nama) >= FUZZY_MIN_LETTERS

    # Jarak yang ditoleransi tumbuh dengan panjang nama, karena
    # peluang menabrak kata biasa mengecil dengan panjang yang sama.
    batas = 1 if len(nama) <= 8 else 2

    aman = {
        satu.casefold()
        for satu in BRAND_CANDIDATE.findall(str(keyword or ""))
    }

    jumlah = dipenggal

    def ganti(cocok: re.Match) -> str:
        nonlocal jumlah

        kata = cocok.group(0)
        kecil = kata.casefold()

        if kata == nama or kecil in aman:
            return kata

        # Tingkat 1: ejaannya sudah benar.
        if kecil == target:
            jumlah += 1
            return nama

        if not boleh_meleset:
            return kata

        # Jendela panjang diperiksa lebih dulu, sebelum jarak sunting
        # dihitung sama sekali. Ia yang membuang "Siam" dari calon
        # "SIAM123" tanpa perlu menghitung apa pun.
        if abs(len(kata) - len(nama)) > batas:
            return kata

        # Tiga huruf pertama harus sama. Tanpa syarat ini, dua kata
        # berjarak dua huruf yang PANGKALNYA berbeda ikut tertarik,
        # dan pangkal kata itulah yang paling dikenali mata pembaca.
        if kecil[:3] != target[:3]:
            return kata

        if edit_distance(kecil, target, batas) <= batas:
            jumlah += 1
            return nama

        return kata

    return BRAND_CANDIDATE.sub(ganti, isi), jumlah


def restore_brand_content(content, brand: str, keyword: str = ""):
    """
    Memulihkan ejaan nama situs di seluruh isi halaman, sedalam apa pun.

    Peran berawalan garis bawah dilewati - isinya penanda untuk
    riwayat, bukan teks yang terbit. Aturan yang sama dengan
    claim_guard.scrub_content, leak_guard.scrub_leaks, dan
    spelling.fix_content_terms.
    """
    if isinstance(content, str):
        return restore_brand(content, brand, keyword)

    if isinstance(content, list):
        hasil, total = [], 0

        for item in content:
            bersih, jumlah = restore_brand_content(item, brand, keyword)
            hasil.append(bersih)
            total += jumlah

        return hasil, total

    if isinstance(content, dict):
        hasil, total = {}, 0

        for kunci, nilai in content.items():
            if isinstance(kunci, str) and kunci.startswith("_"):
                hasil[kunci] = nilai
                continue

            bersih, jumlah = restore_brand_content(nilai, brand, keyword)
            hasil[kunci] = bersih
            total += jumlah

        return hasil, total

    return content, 0


# Blok yang bukan teks yang dibaca orang.
#
# Dua alasan yang berbeda, satu pengecualian yang sama.
#
# <script> berisi kode: nama brand di dalamnya adalah NAMA VARIABEL -
# terukur di template 616, "window.TeePublic = window.TeePublic || {}"
# - dan menggantinya di situ bukan mengganti merek melainkan merusak
# skrip yang berjalan di halaman. <style> sama, dengan nama kelas.
#
# JSON-LD ikut dikecualikan meski isinya bukan kode, dan alasannya
# bukan bahaya melainkan kepemilikan: seluruh blok itu sudah ditulis
# ulang jsonld_filler, sebagai satu rentang utuh, dengan nama brand
# baru yang sudah terpasang di setiap simpulnya. Menyapunya lagi di
# sini menaruh suntingan sepuluh karakter di tengah rentang dua ribu
# karakter milik orang lain, dan apply_edits menolak seluruh
# pengisian dengan "dua penggantian saling bertumpang tindih" - jadi
# halamannya tidak terbit sama sekali.
#
# Ini juga yang membetulkan dugaan awal waktu penyapu ini ditulis.
# Sisa brand lama di dalam JSON-LD memang terlihat di TEMPLATE, dan
# sempat terbaca seolah ia lolos ke halaman jadi. Ia tidak: di
# halaman yang benar-benar terbit 30 Agustus 2026, sepuluh sisa
# brand lama seluruhnya ada di teks bersarang dan atribut, dan tidak
# satu pun di dalam JSON-LD.
CODE_BLOCK = re.compile(
    r"<script[^>]*>.*?</script\s*>"
    r"|<style[^>]*>.*?</style\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Tanda bahwa sebuah potongan teks sebenarnya sebuah alamat.
#
# Alamat tidak pernah disentuh, dan itu aturan tertua di berkas ini.
# Nama brand di dalam URL adalah bagian dari alamat yang harus tetap
# bisa dibuka; menggantinya menghasilkan tautan mati yang kelihatan
# benar.
URL_MARK = re.compile(
    r"://|^//|^/[\w.-]*/|\.(?:com|net|org|id|co|io|xyz|site|store|"
    r"online|jpg|jpeg|png|gif|webp|svg|css|js|ico|woff2?)\b",
    re.IGNORECASE,
)

# Karakter yang membatasi satu "potongan" waktu memutuskan apakah
# sebuah kecocokan berdiri di dalam alamat.
TOKEN_EDGE = set(" \t\r\n\"'<>()")


def inside_url(html: str, awal: int, akhir: int) -> bool:
    """
    Apakah kecocokan di posisi ini berdiri di dalam sebuah alamat.

    Diputuskan dari potongan yang mengelilinginya, bukan dari nama
    atributnya. Alasannya template sungguhan menaruh alamat di
    puluhan atribut yang berbeda - href, src, srcset, data-href,
    content, action, poster - dan daftar nama atribut akan selalu
    ketinggalan satu. Bentuk alamatnya sendiri tidak berubah-ubah.
    """
    kiri = awal

    while kiri > 0 and html[kiri - 1] not in TOKEN_EDGE:
        kiri -= 1

    kanan = akhir

    while kanan < len(html) and html[kanan] not in TOKEN_EDGE:
        kanan += 1

    return bool(URL_MARK.search(html[kiri:kanan]))


# Atribut yang isinya PENANDA, bukan tulisan.
#
# Nama brand di dalamnya dipakai sebagai nama - nama elemen, nama
# kelas, nama medan formulir - dan yang membacanya CSS dan JavaScript,
# bukan manusia. Terukur di template 616, dua bentuk sekaligus:
#
#   id='teepublic'                              <- dicari getElementById
#   class="... teepublic--border-color ..."      <- dicari selektor CSS
#
# Menggantinya di situ bukan mengganti merek melainkan memutus
# sambungan antara HTML dan berkas gayanya. Halamannya tetap terbit,
# tampilannya yang rusak - dan rusaknya tidak kelihatan sampai
# halamannya dibuka.
IDENTIFIER_ATTRS = frozenset(
    {
        "id", "class", "for", "name", "rel", "type", "role", "form",
        "headers", "style", "target", "method", "enctype", "accept",
        "charset", "lang", "dir", "slot", "part", "itemprop",
        "itemtype", "itemid", "property", "http-equiv", "scheme",
        "media", "sizes", "integrity", "crossorigin", "loading",
        "decoding", "autocomplete", "pattern", "list", "form-action",
    }
)

# Sejauh apa dicari ke belakang waktu mencari nama atribut.
#
# Nilai atribut yang lebih panjang dari ini praktis selalu daftar
# kelas atau JSON yang ditempel, dan dua-duanya sudah tertangkap
# pemeriksaan lain. Batasnya ada supaya pencarian tidak menyusuri
# seluruh dokumen untuk satu kecocokan.
ATTR_LOOKBACK = 4000

ATTR_NAME = re.compile(r"([A-Za-z_:][\w:.-]*)\s*=\s*$")


def attribute_name(html: str, awal: int) -> str:
    """
    Nama atribut HTML yang nilainya memuat posisi ini, kalau ada.

    Dicari dengan menyusur balik ke tanda kutik pembuka, lalu menuntut
    tanda "=" tepat sebelumnya. Tuntutan "=" itu yang membuat fungsi
    ini tidak salah membaca JSON: di dalam JSON-LD, pasangan
    "name": "BATARATOTO" juga punya tanda kutip di kiri nilainya, tapi
    yang berdiri sebelum kutipnya titik dua - jadi ia terbaca bukan
    atribut, dan isinya boleh disapu. Itu justru yang paling
    dibutuhkan.

    Menghasilkan "" kalau posisinya ada di teks biasa, bukan di dalam
    nilai atribut.
    """
    batas = max(0, awal - ATTR_LOOKBACK)
    i = awal - 1

    while i >= batas:
        huruf = html[i]

        # Keluar dari tagnya sebelum ketemu kutip: berarti posisinya
        # ada di teks yang dibaca orang.
        if huruf in "><":
            return ""

        if huruf in "\"'":
            cocok = ATTR_NAME.search(html[batas:i])

            return cocok.group(1).lower() if cocok else ""

        i -= 1

    return ""


def brand_sweep_edits(
    html: str,
    slot_map: dict,
    terpakai,
    old_brand: str,
    new_brand: str,
) -> tuple[list[dict], int]:
    """
    Mengganti brand lama yang berdiri DI LUAR slot mana pun.

    brand_edits menyapu slot; ini menyapu sisanya. Keduanya
    dibutuhkan, dan yang kedua ini yang menutup lubang paling mahal.

    Terukur pada halaman yang benar-benar terbit 30 Agustus 2026,
    template 616: dari 64 sebutan brand lama, 54 tersapu dan SEPULUH
    bertahan sampai ke halaman jadi. Ketiganya yang paling terlihat
    adalah teks yang dibaca orang -

        <span>@ BATARATOTO Situs Slot Online Terpercaya</span>
        <strong> LINK BATARATOTO RESMI </strong>
        ... When You Buy <span class="strong">20+ BATARATOTO

    - dan tujuh sisanya di atribut yang memuat tulisan: alt,
    data-link-label, data-filter-option-label. Semuanya bersarang
    terlalu dalam untuk dikenali pemindai sebagai slot, jadi tidak
    satu lapis pun yang ada sebelumnya pernah melihatnya.

    Blok JSON-LD TIDAK ikut disapu di sini. Ia sudah punya
    penulisnya sendiri - lihat CODE_BLOCK.

    Hasilnya suntingan splice biasa, bentuknya sama persis dengan
    yang lain, jadi ia lewat verify_untouched_regions tanpa
    perlakuan khusus: yang di luar rentang suntingan tetap terbukti
    utuh byte per byte.

    Tiga hal tidak pernah disentuh, dan ketiganya diperiksa per
    kecocokan, bukan per wilayah: kode di dalam <script> dan <style>,
    apa pun yang berbentuk alamat, dan nilai atribut yang isinya
    penanda - lihat IDENTIFIER_ATTRS.
    """
    pattern = build_pattern(old_brand)

    if pattern is None or not (new_brand or "").strip():
        return [], 0

    # Wilayah yang sudah punya pemiliknya sendiri: slot mana pun -
    # terisi atau tidak - dan suntingan yang sudah tersusun. Menyentuh
    # salah satunya berarti dua suntingan bertumpang tindih, dan
    # seluruh pengisian gagal.
    milik: list[tuple[int, int]] = [
        (int(slot["start"]), int(slot["end"]))
        for slots in slot_map["roles"].values()
        for slot in slots
    ]

    milik += [
        (int(slot["start"]), int(slot["end"]))
        for slot in slot_map["skipped"]
    ]

    # Suntingan yang sudah tersusun, DARI DAFTARNYA SENDIRI - bukan
    # dari peta "sudah".
    #
    # Bedanya besar dan mahal. Peta itu berkunci letak slot, dan tidak
    # setiap suntingan punya slot: blok JSON-LD ditulis ulang sebagai
    # satu rentang utuh sepanjang dua ribu karakter, dan rentang itu
    # tidak pernah masuk ke sana. Membacanya dari peta membuat penyapu
    # ini menaruh suntingan sepuluh karakter di TENGAH rentang itu,
    # lalu seluruh pengisian gagal dengan "dua penggantian saling
    # bertumpang tindih" - dan halamannya tidak terbit sama sekali.
    #
    # Isi blok JSON-LD itu memang sudah mendapat nama brand yang baru
    # dari penulisnya sendiri, jadi melewatinya bukan kehilangan.
    milik += [
        (int(x["start"]), int(x["end"]))
        for x in (terpakai or [])
        if isinstance(x, dict) and x.get("end") is not None
    ]

    milik.sort()

    kode = [
        (m.start(), m.end()) for m in CODE_BLOCK.finditer(html)
    ]

    def bertabrakan(awal: int, akhir: int, daftar) -> bool:
        return any(a < akhir and awal < b for a, b in daftar)

    edits: list[dict] = []

    for cocok in pattern.finditer(html):
        awal, akhir = cocok.start(), cocok.end()

        if bertabrakan(awal, akhir, milik):
            continue

        if bertabrakan(awal, akhir, kode):
            continue

        if inside_url(html, awal, akhir):
            continue

        if attribute_name(html, awal) in IDENTIFIER_ATTRS:
            continue

        edits.append(
            {
                "start": awal,
                "end": akhir,
                "kind": "raw",
                "role": "brand",
                "text": match_case(cocok.group(0), new_brand),
            }
        )

    return edits, len(edits)


def brand_edits(
    slot_map: dict,
    sudah: dict,
    old_brand: str,
    new_brand: str,
) -> tuple[list[dict], int]:
    """
    Menyusun penggantian brand untuk slot yang belum terisi.

    Slot yang sudah dapat teks baru tidak disentuh lagi di sini;
    teksnya memang sudah ditulis ulang dari nol. Yang dikerjakan
    hanya slot yang tertinggal - termasuk yang tertinggal karena
    isinya tidak cukup untuk semua slot.
    """
    pattern = build_pattern(old_brand)

    if pattern is None or not (new_brand or "").strip():
        return [], 0

    edits: list[dict] = []

    for slots in slot_map["roles"].values():
        for slot in slots:
            if (slot["start"], slot["end"]) in sudah:
                continue

            asli = slot["current"]
            baru = swap_brand(asli, pattern, new_brand)

            if baru != asli:
                edits.append({**slot, "text": baru})

    for slot in slot_map["skipped"]:
        # Slot yang dilewati kebijakan tetap ikut diganti namanya.
        # Alasan melewatinya adalah "belum tentu ini isi artikel",
        # bukan "boleh menyebut brand orang lain". Blok iklan dan
        # atribut tanpa kutip tetap tidak disentuh.
        #
        # Yang sudah terisi dilewati, sama seperti perulangan di atas.
        # Tanpa syarat ini satu teks bisa kebagian dua penggantian
        # sekaligus - terukur pada template pengguna: 34 atribut alt
        # yang isinya judul lama menerima judul baru dari lapis gema
        # DAN nama brand baru dari lapis ini, lalu seluruh pengisian
        # gagal dengan "dua penggantian saling bertumpang tindih".
        # Dulu tidak pernah kelihatan karena slot semacam itu selalu
        # berakhir di roles, bukan di skipped.
        if (slot["start"], slot["end"]) in sudah:
            continue

        if slot.get("in_ad"):
            continue

        if slot["kind"] == "attribute" and not slot.get("quote"):
            continue

        asli = slot["current"]
        baru = swap_brand(asli, pattern, new_brand)

        if baru != asli:
            edits.append({**slot, "text": baru})

    return edits, len(edits)


def echo_edits(
    slot_map: dict,
    sudah: dict,
    diganti: dict[str, str],
    mentah: dict[str, str] | None = None,
) -> tuple[list[dict], int]:
    """
    Menyamakan teks lama yang kembar dengan teks barunya.

    "diganti" berisi teks lama -> teks baru dari slot yang sudah
    terisi. Slot lain yang teks lamanya sama persis ikut memakai
    teks baru yang sama, jadi kalimat yang di template muncul dua
    kali tetap muncul dua kali dengan bunyi yang sama.

    "mentah" berisi pasangan yang sama, tapi kuncinya teks lama APA
    ADANYA - belum dinormalkan. Itu yang dipakai mencari judul lama
    yang berdiri di dalam teks lain; pencarian potongan tidak bisa
    memakai kunci yang sudah dinormalkan, karena yang dicari harus
    ditemukan di teks aslinya supaya potongannya bisa ditukar tanpa
    menyentuh sisa kalimatnya.
    """
    mentah = mentah or {}
    peta = {
        kunci: nilai
        for kunci, nilai in diganti.items()
        if len(kunci) >= MIN_ECHO_CHARS
    }

    if not peta:
        return [], 0

    edits: list[dict] = []

    semua = [
        slot
        for slots in slot_map["roles"].values()
        for slot in slots
    ] + slot_map["skipped"]

    for slot in semua:
        if (slot["start"], slot["end"]) in sudah:
            continue

        if slot.get("in_ad"):
            continue

        # Menu dan footer memakai kata-kata template, jadi teks
        # kembar di dalamnya tidak ikut disamakan dengan kalimat
        # baru. Kalau ikut, judul baru halaman menyalin dirinya ke
        # menu dan bagian yang sengaja dibekukan berubah juga.
        if slot.get("frozen"):
            continue

        if slot["kind"] == "attribute" and not slot.get("quote"):
            continue

        baru = peta.get(normalize(slot["current"]))

        if baru and normalize(baru) != normalize(slot["current"]):
            edits.append({**slot, "text": baru})
            continue

        # Teks lama yang berdiri DI DALAM teks lain ikut diganti.
        #
        # Sampai 21 Agustus 2026 hanya kembar persis yang disamakan,
        # dan itu meninggalkan bentuk yang paling sering dipakai
        # template toko: judul halaman ditempeli keterangan pemilik
        # gambarnya. Terukur pada halaman BATARATOTO yang terbit -
        # dari tujuh kemunculan judul lama, dua bertahan, keduanya
        # berbentuk
        #
        #     alt='BATARATOTO : Situs Slot Eksklusif ... by Hey siriusly'
        #
        # Judulnya sama persis; yang membuatnya lolos cuma empat kata
        # di belakangnya. Pengguna memintanya ditutup: "setiap kalimat
        # tersebut akan diubah oleh kalimat terbaru".
        #
        # Yang ditukar cuma potongan judulnya. Keterangan di sekitarnya
        # - "by Hey siriusly" - tetap berdiri, karena ia menyebut
        # pemilik gambar dan bukan bagian dari judul.
        asli = str(slot["current"])

        panjang = sorted(
            mentah.items(),
            key=lambda pasangan: len(pasangan[0]),
            reverse=True,
        )

        for lama, ganti in panjang:
            if len(lama) < MIN_ECHO_CHARS:
                continue

            if lama not in asli:
                continue

            if normalize(ganti) == normalize(lama):
                break

            edits.append({**slot, "text": asli.replace(lama, ganti)})
            break

    return edits, len(edits)
