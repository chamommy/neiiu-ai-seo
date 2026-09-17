"""
Bidang halaman: menentukan hal apa yang boleh dijanjikan dan
tanya-jawab apa yang wajar, tanpa mematok satu bidang untuk semua
halaman.

Sebelum berkas ini ada, tiga tempat memaksa setiap halaman jadi
halaman slot, apa pun keywordnya:

  1. Prompt template menyuruh "ISI FAQ SEPUTAR SLOT, dan cuma itu",
     lalu menyebutkan cara main, deposit, bonus, dan spin.
  2. brand_confidence_rules menyebut kesanggupan brand dalam kalimat
     yang cuma masuk akal untuk situs judi - "yang menang dibayar",
     "deposit dan withdraw diproses cepat".
  3. FAQ_BANK, tanya-jawab cadangan yang ditulis Python, seluruhnya
     tentang slot.

Ketiganya lahir dari bug yang benar-benar terjadi dan tidak boleh
dibatalkan: template sekolah yang diisi jadi halaman slot terbit
dengan FAQ "What Sets ASG Apart?" - pertanyaan milik pemilik
template, tentang sebuah sekolah, di halaman yang topiknya sudah lain
sama sekali. Yang dituju aturan itu sebenarnya "FAQ harus tentang
TOPIK HALAMAN INI", dan itu pernyataan yang berlaku untuk bidang apa
pun. Yang dipatok waktu itu bidangnya, bukan sifatnya.

Sekarang bidangnya dikenali dari keyword. Bidang "gambling"
menghasilkan teks yang sama persis seperti sebelum berkas ini ada -
itu yang dipakai pengguna sehari-hari dan tidak boleh bergeser.
Bidang lain mendapat aturan yang menyebut topiknya sendiri, dan
daftar kesanggupan yang tidak mengarang apa pun tentang bidang yang
NEIIU tidak tahu apa-apa tentangnya.
"""

import re


# Kata yang menandai halaman judi.
#
# Dicocokkan sebagai kata utuh, bukan potongan. "bet" sebagai potongan
# ikut menandai "beton" dan "sebet"; "slot" sebagai potongan ikut
# menandai "slotted". Batas kata di sini yang memisahkan pengenalan
# dari tebakan.
#
# Aksara Thai tidak punya batas kata, jadi kata Thai dicocokkan
# sebagai potongan - dan itu aman, karena rangkaian aksara seperti
# สล็อต tidak muncul di dalam kata lain.
GAMBLING_WORDS = (
    "slot",
    "gacor",
    "judi",
    "casino",
    "kasino",
    "togel",
    "poker",
    "taruhan",
    "betting",
    "jackpot",
    "maxwin",
    "spin",
    "rtp",
    "bandar",
    "baccarat",
    "bakarat",
    "roulette",
    "rolet",
    "sportsbook",
    "parlay",
    "gambling",
)

GAMBLING_THAI = (
    "สล็อต",
    "คาสิโน",
    "บาคาร่า",
    "หวย",
    "พนัน",
    "เดิมพัน",
    "ยิงปลา",
    "แทงบอล",
    "เว็บตรง",
)

GAMBLING_PATTERN = re.compile(
    r"\b(" + "|".join(GAMBLING_WORDS) + r")\b",
    re.IGNORECASE,
)


def detect_niche(
    keyword: str = "",
    brand_name: str = "",
    extra_text: str = "",
) -> str:
    """
    Mengenali bidang halaman dari kata-kata yang sudah diketahui.

    Nama brand ikut diperiksa karena sebagian brand menamai bidangnya
    di dalam namanya sendiri. extra_text disediakan untuk pemanggil
    yang punya bahan lain - misalnya judul template - dan boleh
    dikosongkan.

    Yang dikembalikan cuma dua nilai untuk saat ini. Menambah bidang
    ketiga berarti menambah daftar kesanggupan dan tanya-jawabnya di
    NICHES; menebak bidang tanpa menyiapkan keduanya menghasilkan
    halaman yang berbicara seperti bidang yang salah, dan itu lebih
    buruk daripada berbicara netral.
    """
    bahan = " ".join(
        str(x or "") for x in (keyword, brand_name, extra_text)
    )

    if GAMBLING_PATTERN.search(bahan):
        return "gambling"

    if any(kata in bahan for kata in GAMBLING_THAI):
        return "gambling"

    return "generic"


# Aturan tiap bidang.
#
# "capabilities" adalah hal yang BOLEH ditulis sebagai kemampuan yang
# memang ada. Isinya berbeda per bidang karena kesanggupan yang wajar
# untuk situs judi tidak wajar untuk toko atau sekolah - dan menulis
# "yang menang dibayar" di halaman kursus bukan cuma janggal, ia
# kalimat yang tidak menunjuk apa pun.
#
# "faq_topics" menggantikan daftar "cara main, deposit, bonus" yang
# dulu dipatok. Untuk bidang generic, isinya ditulis relatif terhadap
# topik halaman, bukan terhadap sebuah bidang.
NICHES: dict[str, dict] = {
    "gambling": {
        "label": "situs permainan",
        "capabilities": {
            "id": (
                "  dana dan data pemain aman, deposit dan withdraw "
                "diproses cepat,\n"
                "  yang menang dibayar, layanan bisa dihubungi kapan "
                "saja,\n"
                "  pilihan permainannya lengkap, situsnya bisa dibuka "
                "dari mana saja."
            ),
            "th": (
                "  เงินและข้อมูลของผู้เล่นปลอดภัย ฝากถอนรวดเร็ว\n"
                "  จ่ายจริงเมื่อชนะ ติดต่อทีมงานได้ตลอดเวลา\n"
                "  เกมให้เลือกครบ เข้าเล่นได้จากทุกที่"
            ),
        },
        "faq_topics": {
            "id": (
                "- ISI FAQ SEPUTAR SLOT, dan cuma itu: cara mainnya, cara "
                "daftar,\n"
                "  deposit dan penarikan, bonus, main dari HP, keamanan "
                "akun, arti\n"
                "  istilah yang dipakai pemain."
            ),
            "th": (
                "- คำถามต้องเกี่ยวกับสล็อตเท่านั้น เช่น วิธีเล่น วิธีสมัคร\n"
                "  ฝากถอน โบนัส เล่นผ่านมือถือ ความปลอดภัยของบัญชี\n"
                "  และความหมายของศัพท์ที่ผู้เล่นใช้"
            ),
        },
    },
    "generic": {
        "label": "situs ini",
        "capabilities": {
            "id": (
                "  data pemakainya aman, permintaan dan pesanan diurus "
                "sampai\n"
                "  selesai, layanan bisa dihubungi, dan apa yang "
                "ditawarkan di\n"
                "  halaman ini memang tersedia."
            ),
            "th": (
                "  ข้อมูลของผู้ใช้ปลอดภัย คำขอและคำสั่งซื้อได้รับการดูแล\n"
                "  จนเสร็จ ติดต่อทีมงานได้ และสิ่งที่หน้านี้เสนอมีอยู่จริง"
            ),
        },
        "faq_topics": {
            "id": (
                "- ISI FAQ SEPUTAR {bidang}, dan cuma itu: hal yang "
                "wajar\n"
                "  ditanyakan orang yang baru menemukan halaman ini dan "
                "sedang\n"
                "  menimbang memakainya - apa yang ditawarkan, cara "
                "memulainya,\n"
                "  syaratnya, biayanya kalau ada, dan apa yang terjadi "
                "kalau ada\n"
                "  yang tidak sesuai."
            ),
            "th": (
                "- คำถามต้องเกี่ยวกับ{bidang} เท่านั้น คือเรื่องที่\n"
                "  คนเพิ่งเจอหน้านี้และกำลังตัดสินใจจะถาม เช่น มีอะไรให้บ้าง\n"
                "  เริ่มต้นอย่างไร มีเงื่อนไขอะไร มีค่าใช้จ่ายไหม\n"
                "  และถ้ามีอะไรไม่ตรงต้องทำอย่างไร"
            ),
        },
    },
}


# Batas panjang nama bidang yang ikut ke prompt.
#
# Kolom Niche menerima 120 karakter, dan yang mengetik kalimat penuh
# di situ akan menyisipkan kalimat itu ke tengah aturan FAQ. Yang
# dipakai bidang, bukan kalimat.
FIELD_MAX = 60

# Karakter yang dibuang dari nama bidang sebelum masuk prompt.
#
# Kurung kurawal yang paling menentukan: aturan ini disusun dengan
# str.format, dan satu kurawal di dalam nama bidang mengubah teks
# yang diketik pengguna jadi lubang substitusi. Sisanya tanda kutip
# dan baris baru, yang cuma merusak bentuk daftar.
FIELD_STRIP = re.compile(r"[{}\r\n\t\"']+")


def field_label(niche_text: str = "", fallback: str = "topik halaman ini") -> str:
    """
    Nama bidang yang dibaca model, diambil dari yang diketik pengguna.

    Ini yang membuat kolom Niche benar-benar menentukan ISI halaman,
    bukan cuma jadi kata pencarian.

    Sebelum ini, bidang di luar judi selalu jatuh ke aturan yang
    berbunyi "SEPUTAR TOPIK HALAMAN INI" - benar, tapi tidak menunjuk
    apa pun. Model 4B yang diberi aturan tanpa rujukan mengisi
    rujukannya sendiri dari bahan terdekat yang ada di prompt, dan
    bahan terdekat itu contoh gaya dan teks template. Hasilnya FAQ
    yang membahas bidang milik pemilik template.

    Sekarang bidangnya disebut namanya: "ISI FAQ SEPUTAR toko sepatu".
    """
    bersih = FIELD_STRIP.sub(" ", str(niche_text or ""))
    bersih = " ".join(bersih.split()).strip(" -–—:|,.")

    if not bersih:
        return fallback

    if len(bersih) > FIELD_MAX:
        # Dipotong di batas kata, bukan di tengah kata. Nama bidang
        # yang terpotong jadi "toko sepatu olahra" membaca seperti
        # salah ketik, dan model menirunya.
        potong = bersih[:FIELD_MAX].rsplit(" ", 1)[0]
        bersih = potong or bersih[:FIELD_MAX]

    return bersih


def niche_profile(niche: str = "generic") -> dict:
    """
    Aturan satu bidang, jatuh ke generic kalau tidak dikenal.
    """
    return NICHES.get(str(niche or "").strip().lower(), NICHES["generic"])


def fill_field(teks: str, niche_text: str = "") -> str:
    """
    Mengisi lubang {bidang} kalau ada, dan membiarkan yang tidak punya.

    Teks bidang "gambling" tidak punya satu lubang pun, jadi ia
    melewati fungsi ini tanpa berubah sehuruf pun. Itu yang dijaga:
    halaman judi adalah yang dipakai pengguna sehari-hari dan sudah
    disetel berkali-kali, jadi ia tidak boleh bergeser gara-gara
    bidang lain dibuat lebih pintar.
    """
    if "{bidang}" not in teks:
        return teks

    return teks.replace("{bidang}", field_label(niche_text))


def capability_lines(
    niche: str,
    language_code: str = "id",
    niche_text: str = "",
) -> str:
    """
    Daftar kesanggupan yang boleh ditulis sebagai fakta.
    """
    profile = niche_profile(niche)
    isi = profile["capabilities"]

    return fill_field(isi.get(language_code) or isi["id"], niche_text)


def faq_topic_rules(
    niche: str,
    language_code: str = "id",
    niche_text: str = "",
) -> str:
    """
    Aturan isi FAQ untuk satu bidang.

    niche_text adalah yang DIKETIK pengguna di kolom Niche, sedangkan
    niche adalah bidang yang dikenali dari situ ("gambling" atau
    "generic"). Keduanya dibutuhkan: yang pertama menyebut bidangnya
    dengan nama, yang kedua memilih aturan mana yang dipakai.
    """
    profile = niche_profile(niche)
    isi = profile["faq_topics"]

    return fill_field(isi.get(language_code) or isi["id"], niche_text)


# Tanya-jawab cadangan untuk bidang yang bukan judi.
#
# Ditulis dengan lubang {topik} dan {brand}, bukan dengan isi yang
# sudah jadi, karena satu-satunya hal yang benar-benar diketahui
# pipeline tentang bidang ini adalah keyword dan nama brandnya.
# Pertanyaan yang menyebut kedua hal itu saja tetap benar untuk
# bidang apa pun; pertanyaan yang menebak isinya tidak.
#
# Jawabannya sengaja tidak menjanjikan angka, tenggat, atau harga -
# lihat generators/claim_guard.py untuk alasan yang sama ditegakkan
# di sisi keluaran.
GENERIC_FAQ_BANK = {
    "id": (
        (
            "Apa yang bisa didapat dari {topik} di {brand}?",
            "Halaman ini memuat {topik} beserta keterangan yang "
            "dibutuhkan sebelum memilih. Yang tercantum di sini yang "
            "memang tersedia di {brand}, jadi tidak perlu mencari "
            "keterangannya di tempat lain.",
        ),
        (
            "Bagaimana cara mulai di {brand}?",
            "Buka halamannya, baca bagian yang paling dekat dengan "
            "kebutuhanmu, lalu ikuti langkah yang tertulis di situ. "
            "Kalau ada yang belum jelas, tim {brand} bisa dihubungi "
            "lebih dulu sebelum kamu memutuskan.",
        ),
        (
            "Apakah {topik} bisa diakses dari HP?",
            "Bisa. Halaman {brand} berjalan langsung di browser HP, "
            "jadi tidak ada yang perlu dipasang lebih dulu.",
        ),
        (
            "Apa yang perlu disiapkan sebelum mulai?",
            "Tidak banyak. Yang paling menentukan justru mengetahui "
            "dulu apa yang kamu cari, karena {topik} di {brand} "
            "punya beberapa pilihan yang tidak sama peruntukannya.",
        ),
        (
            "Kalau ada yang tidak sesuai, harus bagaimana?",
            "Hubungi {brand} dan sebutkan bagian mana yang tidak "
            "sesuai. Keterangan yang lebih tepat membuat urusannya "
            "selesai lebih cepat daripada keluhan yang umum.",
        ),
        (
            "Apakah keterangan di halaman ini diperbarui?",
            "Diperbarui mengikuti apa yang berlaku di {brand}. Kalau "
            "ada bagian yang terlihat sudah lama, tanyakan langsung "
            "supaya kamu tidak berangkat dari keterangan lama.",
        ),
    ),
    "th": (
        (
            "{topik} ที่ {brand} มีอะไรบ้าง",
            "หน้านี้รวม {topik} พร้อมรายละเอียดที่ต้องรู้ก่อนตัดสินใจ "
            "สิ่งที่เขียนไว้ตรงนี้คือสิ่งที่ {brand} มีจริง "
            "จึงไม่ต้องไปหาข้อมูลจากที่อื่น",
        ),
        (
            "เริ่มต้นกับ {brand} อย่างไร",
            "เปิดหน้าเว็บ อ่านส่วนที่ใกล้กับสิ่งที่ต้องการที่สุด "
            "แล้วทำตามขั้นตอนที่เขียนไว้ ถ้ายังไม่ชัดเจน "
            "ติดต่อทีมงาน {brand} ก่อนตัดสินใจได้",
        ),
        (
            "ใช้งานผ่านมือถือได้ไหม",
            "ได้ หน้าเว็บ {brand} เปิดผ่านเบราว์เซอร์บนมือถือได้เลย "
            "ไม่ต้องติดตั้งอะไรก่อน",
        ),
        (
            "ต้องเตรียมอะไรก่อนเริ่ม",
            "ไม่มากนัก สิ่งที่สำคัญกว่าคือรู้ก่อนว่าตัวเองต้องการอะไร "
            "เพราะ {topik} ที่ {brand} มีหลายแบบและใช้ต่างกัน",
        ),
        (
            "ถ้ามีอะไรไม่ตรงต้องทำอย่างไร",
            "ติดต่อ {brand} แล้วระบุว่าส่วนไหนไม่ตรง "
            "รายละเอียดที่ชัดเจนช่วยให้เรื่องจบเร็วกว่าการแจ้งแบบกว้าง ๆ",
        ),
        (
            "ข้อมูลในหน้านี้อัปเดตหรือไม่",
            "อัปเดตตามที่ใช้จริงที่ {brand} หากเห็นส่วนไหนดูเก่า "
            "สอบถามได้โดยตรง จะได้ไม่เริ่มจากข้อมูลเดิม",
        ),
    ),
}
