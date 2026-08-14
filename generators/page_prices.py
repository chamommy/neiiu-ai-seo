"""
Harga dan mata uang milik template, ditulis ulang ke mata uang zona.

Sebelumnya seluruh teks yang bentuknya angka dilewati begitu saja -
lihat NOT_PROSE di generators/template_slots.py - dengan alasan yang
benar untuk sebagian besarnya: jam operasional, nomor urut, dan ukuran
badan di tabel ukuran memang tidak jadi lebih baik kalau ditimpa
tulisan.

Harga bukan salah satunya, dan pengguna sudah menegaskannya: "untuk
angka yang dapat kamu ubah adalah currency dan harga barang, itu tidak
apa-apa diubah".

Alasannya kelihatan di halaman yang terbit. Template yang dipakai
aslinya toko jersey Eropa, dan sesudah seluruh tulisannya berganti jadi
halaman slot berbahasa Indonesia, dua belas harga di dalamnya masih
berbunyi "€15,00" sampai "€130,00". Halaman yang isinya Indonesia tapi
harganya euro tidak terbaca sebagai halaman Indonesia; ia terbaca
sebagai halaman orang lain yang tulisannya ditimpa.

Yang dikerjakan di sini cuma memindahkan mata uangnya, bukan mengarang
harga: angka yang tertulis dikonversi memakai kurs kasar yang ditulis
di bawah, lalu dibulatkan ke kelipatan yang wajar dibaca. Kursnya
memang tidak presisi dan tidak perlu presisi - yang dibeli di sini
bukan ketepatan nilai tukar melainkan halaman yang harganya masuk akal
dibaca orang di zona sasaran.
"""

import html as html_module
import re

# Berapa satuan mata uang ini untuk satu dolar AS.
#
# Angka kasar, dan sengaja bulat. Ia cuma dipakai memindahkan besaran
# ke ordo yang benar - "seratus ribuan" untuk rupiah, "ratusan" untuk
# baht - dan pembulatan di bawah menghapus sisa ketelitiannya.
USD_RATE = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "IDR": 16000.0,
    "THB": 35.0,
    "MYR": 4.7,
    "SGD": 1.35,
    "PHP": 58.0,
    "VND": 25000.0,
}

# Mata uang yang dipakai tiap zona, beserta cara menuliskannya.
#
# "step" adalah kelipatan pembulatan. Harga hasil konversi yang tidak
# dibulatkan terbaca seperti hasil hitungan mesin - "Rp 260.869" bukan
# harga yang ditulis orang - dan justru itu yang mau dihindari.
REGION_CURRENCY = {
    "id": {
        "code": "IDR",
        "symbol": "Rp",
        "space": True,
        "thousands": ".",
        "step": 5000,
        "min": 10000,
    },
    "th": {
        "code": "THB",
        "symbol": "฿",
        "space": False,
        "thousands": ",",
        "step": 10,
        "min": 20,
    },
}

# Lambang dan kode mata uang yang mungkin berdiri di template.
CURRENCY_SIGNS = (
    ("€", "EUR"),
    ("£", "GBP"),
    ("฿", "THB"),
    ("$", "USD"),
    ("rp", "IDR"),
    ("idr", "IDR"),
    ("usd", "USD"),
    ("eur", "EUR"),
    ("gbp", "GBP"),
    ("thb", "THB"),
    ("myr", "MYR"),
    ("sgd", "SGD"),
    ("php", "PHP"),
    ("vnd", "VND"),
)

# Teks yang seluruhnya berupa harga: lambang mata uang dan angka, dalam
# urutan mana pun, boleh berimbuhan ",00" atau ".00".
#
# Dipatok dari ujung ke ujung dengan sengaja. Kalimat yang KEBETULAN
# menyebut harga tidak ikut - itu tulisan, dan tulisan diganti lewat
# jalur biasa. Yang disasar di sini cuma sel tabel dan label harga,
# yang isinya memang tidak lain daripada harganya sendiri.
PRICE_TEXT = re.compile(
    r"""^\s*
    (?:
        (?P<sign_pre>€|£|฿|\$|rp|idr|usd|eur|gbp|thb|myr|sgd|php|vnd)
        \s*(?P<amount_a>\d[\d.,\s]*)
        |
        (?P<amount_b>\d[\d.,\s]*)\s*
        (?P<sign_post>€|£|฿|\$|rp|idr|usd|eur|gbp|thb|myr|sgd|php|vnd)
    )
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def plain(text: str) -> str:
    """
    Teks slot dengan entitas HTML-nya dikembalikan jadi huruf biasa.

    Yang dibaca pemindai adalah sumber HTML apa adanya, dan lambang
    mata uang di template sungguhan lebih sering ditulis sebagai
    entitas daripada sebagai hurufnya: template toko jersey yang
    dipakai menguji menulis "&euro;90,00", bukan "€90,00". Tanpa
    baris ini, semua harga euro di halaman itu lolos dari pemeriksaan
    dan terbit apa adanya - "$1" ikut tertukar, sedangkan yang euro
    tidak, sehingga satu tabel harga terbit dengan dua mata uang.
    """
    return html_module.unescape(str(text or ""))


def looks_like_price(text: str) -> bool:
    """
    Apakah teks ini seluruhnya berupa harga.
    """
    return bool(PRICE_TEXT.match(plain(text)))


def parse_amount(raw: str) -> float:
    """
    Membaca nilai angka dari tulisan harga, apa pun gaya pemisahnya.

    Dua gaya berdiri berdampingan di web - "1,299.00" gaya Inggris dan
    "1.299,00" gaya Eropa - dan keduanya harus terbaca 1299. Yang
    membedakannya bukan tanda mana yang dipakai melainkan tanda mana
    yang muncul TERAKHIR: pemisah desimal selalu paling belakang.
    """
    bersih = re.sub(r"[^\d.,]", "", plain(raw))

    if not bersih:
        return 0.0

    titik = bersih.rfind(".")
    koma = bersih.rfind(",")

    if titik == -1 and koma == -1:
        return angka_aman(bersih)

    if titik > koma:
        desimal, ribuan = ".", ","
    else:
        desimal, ribuan = ",", "."

    ekor = bersih.rsplit(desimal, 1)[-1]

    # Tiga angka di belakang tanda berarti tanda itu pemisah ribuan,
    # bukan desimal: "1,500" adalah seribu lima ratus, bukan satu koma
    # lima. Uang tidak pernah ditulis dengan tiga angka desimal.
    if len(ekor) == 3:
        return angka_aman(re.sub(r"[.,]", "", bersih))

    return angka_aman(
        bersih.replace(ribuan, "").replace(desimal, ".")
    )


def angka_aman(teks: str) -> float:
    """
    float() yang tidak pernah membatalkan pembuatan halaman.

    Ini penutup untuk cacat yang paling mahal di berkas ini: satu sel
    berbunyi "$1.299.00" - gaya penulisan yang benar-benar dipakai
    sebagian toko - membuat float() melempar ValueError, dan karena
    price_edits menyapu SELURUH slot termasuk yang dilewati kebijakan,
    satu sel itu cukup untuk menggagalkan seluruh halaman. Pengguna
    melihatnya sebagai job yang mati, bukan sebagai satu harga yang
    tidak tertukar.

    Yang salah bentuk dikembalikan nol, dan nol berarti "biarkan apa
    adanya" di localize_price.
    """
    try:
        return float(teks)
    except ValueError:
        pass

    # Bentuk yang gagal dibaca selalu punya lebih dari satu tanda
    # pemisah, misalnya "1.299.00". Yang paling masuk akal: kelompok
    # terakhir yang panjangnya DUA angka adalah sen, sisanya ribuan.
    # Dibaca begitu, "1.299.00" jadi 1299,00 - bukan 129.900, yang
    # meleset seratus kali lipat.
    potongan = [x for x in re.split(r"[.,]", teks) if x]

    if not potongan or not all(x.isdigit() for x in potongan):
        angka = re.sub(r"\D", "", teks)

        return float(angka) if angka.isdigit() else 0.0

    if len(potongan) > 1 and len(potongan[-1]) == 2:
        return float("".join(potongan[:-1]) + "." + potongan[-1])

    return float("".join(potongan))


def source_currency(text: str) -> str:
    """
    Mata uang yang tertulis di teks harga ini.
    """
    rendah = plain(text).lower()

    for tanda, kode in CURRENCY_SIGNS:
        if tanda in rendah:
            return kode

    return ""


def format_amount(nilai: float, spec: dict) -> str:
    """
    Menuliskan nilai dengan lambang dan pemisah ribuan zona ini.
    """
    bulat = int(round(nilai))
    angka = f"{bulat:,}".replace(",", spec["thousands"])

    return (
        f"{spec['symbol']} {angka}"
        if spec.get("space")
        else f"{spec['symbol']}{angka}"
    )


# Harga yang berdiri DI DALAM teks lain, bukan sendirian.
#
# Slot yang isinya cuma harga sudah ditangani lewat peran "price".
# Yang ini untuk sisanya, dan sisanya justru mayoritas: di template
# toko jersey yang dipakai menguji, dari dua belas harga euro hanya
# SATU yang berdiri sendirian. Sebelas sisanya menempel pada kata di
# depannya - "From                     €120,00" - sehingga teks
# slotnya bukan harga melainkan kalimat yang memuat harga, dan satu
# tabel terbit dengan dua mata uang sekaligus.
# Batas kiri dan kanan ikut diperiksa, dan itu bukan kehati-hatian
# berlebihan melainkan perbaikan atas tiga kerusakan yang terukur:
#
#   "US$ 25"  -> "USRp 400.000"      huruf negara tertinggal di depan
#   "A$ 30"   -> "ARp 480.000"
#   "$50OFF"  -> "Rp 800.000OFF"     kode promo, bukan harga
#
# Yang pertama karena "$" dipatok tanpa melihat huruf di kirinya, yang
# ketiga karena angkanya dipatok tanpa melihat huruf di kanannya.
PRICE_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"(?P<sign_pre>€|£|฿|\$|Rp|IDR|USD|EUR|GBP|THB)"
    r"\s*(?P<amount_a>\d[\d.,]*\d|\d)"
    r"|"
    r"(?P<amount_b>\d[\d.,]*\d|\d)\s*"
    r"(?P<sign_post>€|£|฿|\$|IDR|USD|EUR|GBP|THB)"
    r")"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def localize_prices_in_text(text: str, region: str = "id") -> str:
    """
    Menukar setiap harga yang muncul di dalam sebuah teks.

    Yang di luar harga tidak disentuh sama sekali, jadi "From €120,00"
    jadi "From Rp 2.085.000" - katanya tetap milik template, angkanya
    yang pindah zona. Kata itu memang belum berbahasa Indonesia, tapi
    ia diurus jalur lain: kalau slotnya kebagian teks baru dari model,
    sapuan ini tidak menyentuhnya sama sekali.
    """
    spec = REGION_CURRENCY.get(region)

    if not spec:
        return text

    asli = plain(text)

    if not asli:
        return text

    def tukar(cocok: re.Match) -> str:
        potongan = cocok.group(0)
        hasil = localize_price(potongan, region)

        return hasil or potongan

    baru = PRICE_IN_TEXT.sub(tukar, asli)

    return baru if baru != asli else text


def price_edits(
    slot_map: dict,
    sudah: dict,
    region: str = "id",
) -> tuple[list[dict], int]:
    """
    Menukar harga di slot yang TIDAK kebagian teks baru dari model.

    Bentuknya sengaja dibuat sama dengan brand_edits, dan alasannya
    juga sama: slot yang sudah ditulis ulang dari nol tidak perlu
    disentuh - teks barunya memang tidak memuat harga euro - sedangkan
    slot yang tertinggal justru yang paling perlu, karena isinya masih
    milik pemilik template seutuhnya.
    """
    edits: list[dict] = []

    def sapu(slot: dict) -> None:
        if (slot["start"], slot["end"]) in sudah:
            return

        if slot.get("in_ad"):
            return

        if slot["kind"] == "attribute" and not slot.get("quote"):
            return

        asli = slot["current"]
        baru = localize_prices_in_text(asli, region)

        if baru != asli:
            edits.append({**slot, "text": baru})

    for slots in slot_map["roles"].values():
        for slot in slots:
            sapu(slot)

    for slot in slot_map["skipped"]:
        sapu(slot)

    return edits, len(edits)


def localize_price(text: str, region: str = "id") -> str:
    """
    Menukar satu harga template ke mata uang zona sasaran.

    Mengembalikan teks kosong kalau tidak ada yang perlu ditukar -
    bukan harga, mata uangnya sudah benar, atau angkanya tidak
    terbaca - supaya pemanggilnya membiarkan slot itu apa adanya.
    """
    spec = REGION_CURRENCY.get(region)

    if not spec or not looks_like_price(text):
        return ""

    asal = source_currency(text)

    if not asal or asal == spec["code"]:
        return ""

    nilai = parse_amount(plain(text))

    if nilai <= 0:
        return ""

    if asal not in USD_RATE:
        return ""

    hasil = nilai / USD_RATE[asal] * USD_RATE[spec["code"]]

    # Dibulatkan ke kelipatan yang wajar, lalu ditahan di lantainya.
    # Tanpa lantai, harga kecil seperti "$1" jatuh jadi "Rp 15.000"
    # yang masih wajar, tapi "€0,50" jatuh ke nol dan terbit sebagai
    # "Rp 0".
    langkah = spec["step"]
    hasil = round(hasil / langkah) * langkah

    return format_amount(max(hasil, spec["min"]), spec)
