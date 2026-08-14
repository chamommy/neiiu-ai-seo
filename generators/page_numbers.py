"""
Satu set angka per halaman, dipilih sekali lalu ditegakkan.

Model kecil mengarang angka untuk terdengar meyakinkan, dan yang
dikarangnya berganti tiap paragraf. Terukur di halaman jadi: RTP
ditulis 94,3% di satu kartu, 95,1% di kartu berikutnya, 93,8% di
ulasan, dan data yang sama disebut "diperbarui setiap 15 menit" di
satu paragraf lalu "setiap 10 detik" di paragraf lain.

Angkanya sendiri bukan masalah - situs seperti ini memang memajang
RTP. Yang membuat halaman ketahuan ditulis mesin adalah angka yang
saling bertabrakan di halaman yang sama, karena tidak ada manusia
yang menulis dua angka berbeda untuk satu hal di satu halaman.

Jadi yang dikerjakan di sini bukan membuang angka, melainkan
menyatukannya: satu set dipilih di awal run, dikirim ke model sebagai
satu-satunya angka yang boleh dipakai, lalu apa pun yang lolos di
luar set itu ditarik kembali ke anggota set yang terdekat.

Penarikannya dipetakan, bukan diacak. Nilai salah yang sama selalu
jatuh ke nilai benar yang sama, jadi kalimat yang menyebut "94,3%"
dua kali tetap menyebut angka yang sama sesudah dirapikan.
"""

import hashlib
import re

# Rentang RTP yang wajar dipajang. Di bawah 94 terbaca seperti
# peringatan, di atas 97 terbaca seperti janji yang tidak masuk akal.
RTP_FLOOR = 940
RTP_CEIL = 970

# Berapa nilai RTP yang boleh berdiri di satu halaman.
#
# Satu terlalu kaku - halaman yang membandingkan beberapa permainan
# memang butuh angka yang berbeda. Lebih dari tiga dan pembaca tidak
# bisa lagi membedakan mana yang disebut ulang dan mana yang baru.
RTP_COUNT = 3

# Seberapa sering data diperbarui. Dipilih satu, lalu itu saja.
CADENCE_CHOICES = (
    "setiap hari",
    "setiap jam",
    "dua kali sehari",
)

# Persen apa pun: "94,3%", "95.1 %", "96%", "96,45%".
#
# Dua angka desimal ikut ditangkap. Dibatasi satu, "96,45%" tidak
# pernah cocok utuh - yang tertangkap justru potongan "45%" di
# belakangnya, angka yang di luar rentang RTP sehingga dibiarkan lewat.
# Halaman lalu terbit dengan angka yang tidak pernah diseragamkan.
PERCENT = re.compile(r"\b(\d{1,3})(?:[.,](\d{1,2}))?\s*%")

# Kekerapan yang dikarang: "setiap 15 menit", "tiap 10 detik".
CADENCE = re.compile(
    r"\b(setiap|tiap)\s+\d+\s*(detik|menit|jam)\b",
    re.IGNORECASE,
)


def build_number_set(
    keyword: str,
    brand_name: str,
    variation: str = "",
) -> dict:
    """
    Memilih angka yang berlaku untuk satu halaman.

    Diturunkan dari benih, bukan diacak, karena alasan yang sama
    dengan pick_style_examples: awalan prompt harus identik di setiap
    giliran supaya cache prompt Ollama tidak batal. Penanda run ikut
    masuk supaya halaman kedua untuk keyword yang sama tidak memajang
    angka yang persis sama dengan halaman pertama.
    """
    benih = hashlib.sha1(
        f"{keyword}|{brand_name}|{variation}|angka".encode("utf-8")
    ).digest()

    rtp: list[str] = []
    lebar = RTP_CEIL - RTP_FLOOR

    for urutan in range(RTP_COUNT):
        nilai = RTP_FLOOR + (benih[urutan] % lebar)

        # Ditulis dengan koma, seperti kelaziman menulis desimal di
        # Indonesia dan Thailand.
        teks = f"{nilai // 10},{nilai % 10}%"

        if teks not in rtp:
            rtp.append(teks)

    rtp.sort()

    return {
        "rtp": rtp,
        "cadence": CADENCE_CHOICES[benih[8] % len(CADENCE_CHOICES)],
    }


# Peran yang tidak boleh memuat angka persen sama sekali.
#
# Ini permintaan pengguna untuk title, dan alasannya kelihatan begitu
# judul yang terbit dijajarkan dengan daftar title miliknya sendiri:
#
#   terbit   : WAYANGPLAY: Slot Gacor 2026 dengan RTP 96,4% Update
#              Harian Live Paling
#   miliknya : [ BRAND ] | Update Harian RTP Slot dengan Pola Gacor
#              Terbaik
#
# Dari 120 contoh title yang dikirim pengguna, TIDAK SATU PUN memuat
# angka desimal. Angka di judul memakan ruang yang seharusnya dipakai
# janjinya, dan pembaca hasil pencarian tidak pernah mencari angka
# persisnya - ia mencari tahu situs ini menawarkan apa.
#
# Judul dan heading aman dibuangi angkanya karena bentuknya frasa
# benda: "RTP 96,4% Update Harian" tetap utuh dibaca jadi "RTP Update
# Harian". Kalimat isi TIDAK ikut - membuang angka dari "angkanya
# 96,4%" menyisakan "angkanya" yang menggantung.
#
# meta_description ikut meskipun bentuknya kalimat, karena pengguna
# menyebutnya bersama title: "jangan bikin title atau description
# seperti itu lagi". Yang menahan kalimatnya jangan sampai cacat
# adalah FIGURE_IN_PHRASE, yang sudah ikut memakan kata takaran di
# depan angkanya - "mencapai 96,4%" hilang seluruhnya, bukan
# menyisakan "mencapai". Aturan promptnya menyusul di
# neiiu_prompts.py supaya angkanya tidak ditulis sejak awal, dan
# penyaring ini cuma jaring terakhir.
FIGURE_FREE_ROLES = (
    "title",
    "meta_description",
    "h1",
    "heading",
    "card_title",
    "faq_question",
    "meta_keywords",
    "review_tag",
    "nav_label",
    "label",
)

# Penanda sementara di tempat angka yang dibuang, supaya pembungkus
# dan pemisah yang jadi yatim bisa dikenali dari bekasnya sendiri.
# Dipilih karakter yang tidak pernah ada di teks halaman.
TANDA_BUANG = "\x00"

# Persen beserta kata takaran yang mendahuluinya, supaya yang tersisa
# tidak berupa "dengan" atau "sebesar" yang menggantung sendirian.
FIGURE_IN_PHRASE = re.compile(
    r"\s*(?:sebesar|sampai|hingga|di\s+angka|di\s+atas|mencapai|"
    r"kisaran|sekitar|up\s+to)?\s*\b(\d{1,3})(?:[.,](\d{1,2}))?\s*%",
    re.IGNORECASE,
)


def strip_figures(text: str) -> str:
    """
    Membuang angka persen dari teks yang bentuknya frasa benda.

    Dipakai judul, heading, dan pertanyaan FAQ. Yang dibuang angkanya
    saja; kata yang diterangkannya tetap berdiri, jadi "RTP 96,4%
    Update Harian" jadi "RTP Update Harian" - masih menyebutkan hal
    yang sama, tanpa angka yang membuat judulnya sesak.

    SEMUA angka persen dibuang, tanpa memandang nilainya.

    Dulu yang dibuang cuma yang berbentuk RTP - berkoma, atau bulat di
    rentang RTP - sehingga "100%" dan "88%" lolos dengan sengaja,
    dengan alasan bahwa "Bonus New Member 100% & Promo Slot Terbesar"
    ada di daftar contoh milik pengguna. Alasan itu tidak berlaku
    lagi: pengguna menghitung sendiri angka yang terbit di judul dan
    deskripsi, dan yang ia sebut justru angka yang lolos rentang -
    100%, 88%. Rentangnya membuat penyaring ini menyaring persis
    setengah dari yang dikeluhkan.

    Kalimat isi TIDAK memakai fungsi ini; lihat FIGURE_FREE_ROLES.
    """
    if not isinstance(text, str) or "%" not in text:
        return text

    bersih = FIGURE_IN_PHRASE.sub(TANDA_BUANG, text)

    # Pembungkus dan pemisah yang isinya cuma angka yang barusan
    # dibuang ikut dibuang.
    #
    # Tanpa ini yang terbit adalah bekasnya: dari 30 judul realistis,
    # 13 terbit cacat - "Slot Gacor ( ) Update Harian", "RTP / Hari
    # Ini", 'Slot " " Terbaru'. Kurung kosong lebih kelihatan daripada
    # angka yang tadinya berdiri di situ, jadi membuang angkanya tanpa
    # membereskan bekasnya cuma menukar satu cacat dengan cacat lain.
    #
    # Dikerjakan lewat penanda, bukan lewat mencocokkan spasi, supaya
    # yang dibereskan benar-benar bekas angka - kurung kosong yang
    # memang sudah ada di teks aslinya tidak ikut tersentuh.
    bersih = re.sub(
        r"[(\[{\"'‘“]\s*" + TANDA_BUANG + r"\s*[)\]}\"'’”]",
        " ",
        bersih,
    )
    # Pemisah dibuang HANYA kalau ia jadi yatim: berdiri di antara dua
    # angka yang sama-sama dibuang, atau menempel di ujung teks.
    # "RTP 96,4% / 95,2% Hari Ini" jadi "RTP Hari Ini", sedangkan
    # "Update RTP 96,4% | Pola Gacor" tetap memakai pemisahnya, karena
    # di situ pemisahnya masih memisahkan dua hal yang benar-benar ada.
    bersih = re.sub(
        TANDA_BUANG + r"\s*[/|·–—]\s*" + TANDA_BUANG,
        TANDA_BUANG,
        bersih,
    )
    bersih = re.sub(
        r"^\s*" + TANDA_BUANG + r"\s*[/|·–—]\s*"
        r"|\s*[/|·–—]\s*" + TANDA_BUANG + r"\s*$",
        " ",
        bersih,
    )
    bersih = bersih.replace(TANDA_BUANG, " ")

    # Tanda baca yang ditinggalkan angka yang dibuang ikut dirapikan:
    # "RTP 96,4%, pola stabil" tanpa ini jadi "RTP , pola stabil".
    bersih = re.sub(r"\s+([,.;:!?])", r"\1", bersih)
    bersih = re.sub(r"\s{2,}", " ", bersih).strip(" ,;:-–—")

    # Kalau yang tersisa cuma serpihan, teks aslinya yang dipakai.
    # Judul yang isinya memang cuma angka lebih baik terbit apa adanya
    # daripada terbit kosong.
    return bersih if len(bersih.split()) >= 2 else text


def enforce_numbers(text: str, angka: dict, benih: str = "") -> str:
    """
    Menarik angka di luar set kembali ke anggota set.

    Yang disentuh cuma persen dan kekerapan pembaruan. Angka lain -
    jam, tanggal, nomor urut, harga, "1 detik" milik nama produknya
    sendiri - dibiarkan, karena tidak ada set kanonik untuk itu dan
    menebak-nebak di situ merusak kalimat yang benar.

    "benih" menyatakan teks ini yang mana - peran dan nomor urutnya.
    Dengan benih, angka yang sama di dua teks BERBEDA jatuh ke anggota
    set yang berbeda; tanpa benih, seluruh halaman memakai pemetaan
    yang sama. Alasannya di ANGKA_SEBAR di bawah.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    boleh = list(angka.get("rtp") or [])

    if boleh:
        def ganti_persen(cocok: re.Match) -> str:
            utuh = cocok.group(0)
            bulat = cocok.group(1)
            pecahan = cocok.group(2)
            tertulis = f"{bulat},{pecahan or '0'}%"

            if tertulis in boleh and not benih:
                return utuh

            # Persen yang jelas bukan RTP dibiarkan. Bonus 100%,
            # "diskon 50%", dan "mobile friendly 100%" adalah angka
            # yang artinya lain, dan menariknya ke 94,6% mengubah
            # kalimat yang benar jadi kalimat yang salah.
            try:
                nilai = int(bulat)
            except ValueError:
                return utuh

            # Yang membedakan bukan besarnya, melainkan ADA TIDAKNYA
            # koma.
            #
            # Sempat dibatasi rentang nilai saja, dan itu meloloskan
            # "88,4%" - angka RTP karangan yang jatuh di bawah rentang
            # wajar justru yang paling perlu dirapikan. Sebaliknya
            # angka bulat hampir tidak pernah RTP: bonus, diskon, dan
            # "mobile friendly 100%" semuanya ditulis bulat.
            #
            # Jadi yang berkoma dirapikan sepanjang masih masuk akal
            # sebagai persentase permainan, sedangkan yang bulat cuma
            # disentuh kalau persis berada di rentang RTP - supaya
            # "RTP 95%" ikut seragam tanpa menyeret "diskon 50%".
            if pecahan:
                if not 80 <= nilai <= 99:
                    return utuh
            elif not 93 <= nilai <= 98:
                return utuh

            # Dipetakan, bukan diambil yang pertama: di dalam SATU
            # teks, nilai yang sama selalu jatuh ke nilai yang sama,
            # supaya kalimat yang menyebut satu angka dua kali tidak
            # jadi menyebut dua angka berbeda.
            #
            # Benih teksnya ikut masuk, jadi yang tetap sama cuma di
            # dalam teks itu. Antar teks sengaja berbeda - lihat
            # ANGKA_SEBAR.
            sidik = hashlib.sha1(
                f"{tertulis}|{benih}".encode("utf-8")
            ).digest()

            return boleh[sidik[0] % len(boleh)]

        text = PERCENT.sub(ganti_persen, text)

    kekerapan = str(angka.get("cadence") or "").strip()

    if kekerapan:
        text = CADENCE.sub(kekerapan, text)

    return text


# Peran yang angkanya BOLEH berbeda antar teks.
#
# Ini keluhan pengguna, dan bentuknya terukur: "96,4%" muncul 18 kali
# di teks yang dibaca orang - di judul, di enam paragraf, di lima
# jawaban FAQ, dan di KELIMA ulasan sekaligus, lengkap dengan koma
# desimalnya. Tidak ada lima orang yang menulis testimoni dan
# kelimanya menyebut angka desimal yang sama persis.
#
# Yang disebar HANYA ulasan, dan pembatasan itu penting. Ulasan
# ditulis lima orang berbeda pada jam yang berbeda, jadi angka yang
# berlainan memang wajar - halaman ini justru berdiri di atas premis
# bahwa datanya berubah tiap jam.
#
# Teks redaksi TIDAK ikut disebar: paragraf, jawaban FAQ, dan judul
# kartu adalah satu suara yang sama, dan menyebar angkanya berarti
# satu permainan yang sama disebut dengan tiga angka berbeda di satu
# halaman. Itu persis cacat yang page_numbers.py ini dibuat untuk
# menutupnya, dan sempat terbuka lagi waktu penyebarannya diberlakukan
# ke semua peran: terukur, "Gates of Olympus" terbit dengan 94,9% di
# paragraf, 96,0% di jawaban FAQ, dan 96,1% di ulasan.
#
# Yang mengurangi pengulangan di teks redaksi bukan penyebaran,
# melainkan dua hal lain: angka dibuang sama sekali dari judul dan
# heading (FIGURE_FREE_ROLES), dan promptnya sendiri sekarang membatasi
# berapa kali angka boleh disebut.
SPREAD_ROLES = ("review_text",)


# Kata pengganti angka persen di KALIMAT.
#
# Peran yang bentuknya frasa benda cukup dibuangi angkanya - "RTP
# 96,4% Update Harian" tetap utuh jadi "RTP Update Harian". Kalimat
# tidak: "angkanya 96,4%." yang dibuang angkanya menyisakan
# "angkanya." yang menggantung, dan "ternyata 96,4% di slot 777"
# menyisakan "ternyata di slot 777".
#
# Jadi di kalimat angkanya DIGANTI, bukan dibuang. Ketiganya dipilih
# supaya masuk di tempat angka berdiri, apa pun kata di depannya:
# "RTP tinggi", "angkanya stabil", "ternyata lagi bagus di slot 777".
#
# Pengguna sudah menyatakan angkanya tidak penting: "gausah di
# detailin, rtp berapa persennya ga penting". Yang tersisa justru
# yang dicari pembaca - sedang bagus atau tidak.
FIGURE_WORDS = ("tinggi", "stabil", "lagi bagus")


def soften_figures(text: str, benih: str = "") -> str:
    """
    Mengganti angka persen di kalimat dengan kata, bukan membuangnya.

    Katanya digilir dari benih supaya enam kalimat di satu halaman
    tidak berbunyi sama - itu pengulangan yang sama kelihatannya
    dengan angka yang diulang.
    """
    if not isinstance(text, str) or "%" not in text:
        return text

    urut = [0]

    def ganti(cocok: re.Match) -> str:
        bulat = cocok.group(1)
        pecahan = cocok.group(2)

        try:
            nilai = int(bulat)
        except ValueError:
            return cocok.group(0)

        # Cuma yang berbentuk RTP yang diganti kata: yang berkoma,
        # atau yang bulat di rentang RTP. Bonus 100% dan diskon 50%
        # tidak disentuh.
        #
        # strip_figures dulu memakai pembeda yang sama dan sekarang
        # TIDAK lagi - di sana semua persen dibuang. Bedanya disengaja:
        # yang di sini mengerjakan kalimat isi, tempat "bonus 100%"
        # memang keterangan yang berguna, sedangkan yang di sana
        # mengerjakan title dan meta description, tempat pengguna
        # tidak mau melihat persen apa pun lagi.
        if pecahan:
            if not 80 <= nilai <= 99:
                return cocok.group(0)
        elif not 93 <= nilai <= 98:
            return cocok.group(0)

        sidik = hashlib.sha1(
            f"{benih}|{urut[0]}".encode("utf-8")
        ).digest()

        urut[0] += 1

        return FIGURE_WORDS[sidik[0] % len(FIGURE_WORDS)]

    bersih = PERCENT.sub(ganti, text)

    return re.sub(r"\s{2,}", " ", bersih).strip()


def enforce_content_numbers(content: dict, angka: dict) -> dict:
    """
    Menjalankan enforce_numbers pada seluruh teks satu halaman.

    Dua hal yang dikerjakan sekaligus, dan keduanya karena halaman
    yang sama angkanya dari atas sampai bawah terbaca sebagai tulisan
    mesin:

    1. Peran yang bentuknya frasa benda - judul, heading, pertanyaan -
       dibuangi angkanya. Ini permintaan pengguna untuk title.
    2. Peran lain dapat benih sendiri-sendiri, jadi angkanya menyebar
       di dalam set yang sudah dipilih halaman ini.

    Kunci berawalan garis bawah dilewati: itu metadata, bukan teks
    yang terbit.
    """
    hasil: dict = {}

    for peran, nilai in content.items():
        if peran.startswith("_"):
            hasil[peran] = nilai
            continue

        def rapikan(teks, urutan: int = 0):
            if not isinstance(teks, str):
                return teks

            if peran in FIGURE_FREE_ROLES:
                return strip_figures(teks)

            # Kekerapan yang dikarang tetap diseragamkan; angkanya
            # sendiri diganti kata. Tidak ada lagi tahap yang menarik
            # angka ke set kanonik, karena tidak ada lagi angka yang
            # terbit - lihat FIGURE_WORDS.
            return soften_figures(
                enforce_numbers(teks, angka),
                f"{peran}|{urutan}",
            )

        if isinstance(nilai, list):
            hasil[peran] = [
                rapikan(teks, urutan) for urutan, teks in enumerate(nilai)
            ]
        else:
            hasil[peran] = rapikan(nilai)

    return hasil
