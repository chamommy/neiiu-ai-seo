"""
Mengisi template unggahan pengguna dengan konten baru.

Alurnya kebalikan dari generator biasa. Generator biasa menyusun
konten lalu membangun halaman di sekelilingnya. Di sini halamannya
sudah ada dan tidak boleh berubah, jadi templatelah yang menentukan
berapa banyak konten yang dibutuhkan: kalau template punya delapan
kartu FAQ, yang diminta ke AI juga tepat delapan.

Jumlah dari model tidak pernah dipercaya begitu saja. Schema
dinamis dipakai untuk mengarahkan, tapi dukungan minItems di
llama.cpp berbeda-beda antar versi, jadi hasilnya selalu
dicocokkan ulang secara deterministik sesudahnya.
"""

import hashlib
import html as html_module
import re

from datetime import datetime, timedelta

from generators.schema_generator import json_for_html
from generators.brand_swap import (
    brand_edits,
    build_pattern,
    collapse_repeats,
    echo_edits,
    normalize,
    swap_brand,
)
from generators.jsonld_filler import has_reviews, jsonld_edits
from generators.page_numbers import FIGURE_FREE_ROLES, strip_figures
from generators.page_prices import localize_price, price_edits
from generators.script_text import script_edits
from generators.template_assets import asset_edits
from generators.template_guard import verify
from generators.template_scanner import apply_edits, scan
from generators.template_slots import (
    build_slot_map,
    is_city_name,
    length_floor,
)
from utils.region import format_date, get_region, iso_date, person_names
from utils.text import (
    NAME_PARTS,
    author_name,
    content_shingles,
    content_tokens,
    display_width,
    drop_dangling,
    trim_to_sentence,
    trim_to_width,
)


def region_cities(region: str) -> list[str]:
    """
    Nama kota yang pantas ditulis di halaman zona itu.
    """
    return get_region(region)["city_names"]


def rewrite_author_line(current: str, nama: str, kota: list[str]) -> str:
    """
    Menulis ulang satu baris pengulas dengan mempertahankan bentuknya.

    Bentuk baris ini dibangun template dari beberapa bagian sekaligus
    dan tidak satu pun bisa ditebak dari nama perannya: nama, tanda
    pisah, kota, lalu bintang. Yang diganti cuma dua - namanya dan
    kotanya - sedangkan tanda pisah dan bintangnya ditulis kembali di
    tempat yang persis sama.

    Jadi baris "Mikaela Hyakuya — Malang • ★★★★★" berganti jadi
    "Bagus Setiawan — Semarang • ★★★★★", bukan jadi "Bagus Setiawan"
    yang kehilangan kota dan bintangnya sementara empat kartu lain di
    sebelahnya masih punya.
    """
    bagian = NAME_PARTS.split(" ".join(str(current or "").split()))

    if not bagian:
        return nama

    # Ganjil: potongan teks, genap: pemisahnya. Yang pertama selalu
    # namanya, karena baris ini memang dibuka nama orang.
    bagian[0] = nama

    daftar = list(kota)

    for index in range(2, len(bagian), 2):
        if daftar and is_city_name(bagian[index]):
            bagian[index] = daftar[0]
            daftar = daftar[1:] + daftar[:1]

    return "".join(bagian)


# Nilai rating yang dipasang di schema. Ditetapkan di sini, bukan
# diminta ke AI, supaya angkanya tidak berubah tiap run dan tidak
# ada model yang mengarang 4.9 dari 12.483 ulasan.
REVIEW_RATING = 4.6


# Peran yang isinya berupa daftar. Sisanya tunggal.
LIST_ROLES = (
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "review_author",
    "review_tag",
    "card_title",
    "caption",
    "nav_label",
    "list_item",
    "table_cell",
    "label",
    # Berupa daftar dan URUTANNYA bermakna: tingkat pertama beranda,
    # tingkat terakhir halaman ini. published_content menyusunnya
    # menurut urutan dokumen, yang untuk remah navigasi memang sama
    # dengan urutan jalurnya.
    "breadcrumb",
)

# Peran yang jumlah isiannya dibatasi oleh pasangannya, DAN ARAHNYA
# hanya satu.
#
# Yang terbaca sebagai halaman rusak adalah pertanyaan baru yang
# berdiri di atas jawaban lama. Kebalikannya tidak: jawaban baru di
# bawah pertanyaan yang tidak dikenali sebagai slot tetap wajar,
# karena pertanyaan itu tertulis ulang lewat perannya sendiri.
#
# Dulu batas ini dipasang dua arah, dan itu merugikan dua kali.
# Template dengan 8 tempat pertanyaan tapi 17 tempat jawaban membuat
# 9 jawaban dibiarkan memakai kalimat asli template. Lebih parah,
# template yang menaruh nama pengulas di dalam kalimat ulasannya -
# jadi tidak punya slot review_author sama sekali - membuat SELURUH
# ulasannya tidak terisi, karena batasnya jadi nol.
CAPPED_BY_PAIR = {
    "faq_question": "faq_answer",
    "review_author": "review_text",
}

# Peran yang isinya dihitung sendiri di Python, tidak diminta ke AI.
# Tanggal yang dikarang model sering tidak masuk akal (bulan ke-13,
# tahun di masa depan) dan bentuk kalendernya tidak bisa dijamin.
GENERATED_ROLES = (
    "date",
    "review_date",
    "lang",
    "city",
    "brand",
    # Nama pengulas ikut ditulis di Python sejak baris ini pernah
    # terbit tanpa berubah sama sekali. Alasannya di PERSON_NAMES
    # (utils/region.py): yang diminta ke model adalah padanan dari
    # teks lama, dan padanan sebuah nama adalah nama itu juga.
    "review_author",
    # Harga dihitung, bukan dikarang. Model kecil yang diminta
    # menuliskan harga dalam rupiah menjawab nominal yang tidak ada
    # hubungannya dengan angka aslinya, dan tabel harga yang isinya
    # acak lebih buruk daripada tabel harga berbahasa asing.
    # Perhitungannya di generators/page_prices.py.
    "price",
)


# Judul blok yang ditulis di sini, bukan diminta ke model.
#
# Blok tanya-jawab dan blok ulasan sudah ketahuan jenisnya dari isi
# yang berdiri di bawahnya, jadi judulnya adalah satu-satunya bagian
# halaman yang jawabannya sudah pasti sebelum model dipanggil.
# Memintanya tetap ke model terbukti gagal dua kali berturut-turut
# dengan dua cara berbeda: sekali blok FAQ dinamai "Fitur Utama
# Aplikasi", sekali model menyalin balik "FAQ OSB99" apa adanya.
#
# Ditulis di sini, keduanya tidak mungkin terjadi lagi.
BLOCK_HEADINGS = {
    "id": {
        "faq": "FAQ {brand}",
        "review": "Review Pengguna {brand}",
    },
    "th": {
        "faq": "คำถามที่พบบ่อย {brand}",
        "review": "รีวิวจากผู้ใช้ {brand}",
    },
}

# Dipakai kalau brand kosong: judulnya jatuh ke keyword supaya tetap
# menamai sesuatu, bukan menggantung dengan spasi di ujung.
BLOCK_HEADINGS_NO_BRAND = {
    "id": {
        "faq": "FAQ Seputar {keyword}",
        "review": "Review Pengguna",
    },
    "th": {
        "faq": "คำถามที่พบบ่อยเกี่ยวกับ {keyword}",
        "review": "รีวิวจากผู้ใช้",
    },
}


def block_heading_text(
    block: str,
    brand: dict,
    keyword: str = "",
) -> str:
    """
    Judul untuk satu blok yang jenisnya sudah dikenali.
    """
    region = brand.get("region", "id")
    nama = str(brand.get("site_name", "")).strip()

    sumber = BLOCK_HEADINGS if nama else BLOCK_HEADINGS_NO_BRAND
    pola = sumber.get(region, sumber["id"]).get(block, "")

    if not pola:
        return ""

    return pola.format(brand=nama, keyword=keyword).strip()


# Tanya-jawab cadangan, ditulis Python, untuk kartu FAQ yang tidak
# kebagian jawaban model.
#
# Ini keluhan pengguna, dan kalimatnya persis: "untuk bagian FAQ
# terdapat banyak bug, terdapat banyak 'What Sets ASG Apart?', ini
# bukanlah FAQ perihal slot yang aku inginkan".
#
# Kartu yang tidak terisi memang sengaja jatuh ke teks asli template -
# lihat drop_broken_pairs. Untuk template yang sebelumnya milik situs
# sekolah dan toko jersey, "yang asli" itu berarti "What Sets ASG
# Apart?" dan "Need help finding something?" berdiri di halaman slot,
# dalam bahasa Inggris, menyebut brand yang bukan milik pengguna.
# Jatuh ke teks lama lebih baik daripada pasangan yang tidak nyambung,
# tapi keduanya kalah dari pertanyaan yang memang tentang slot.
#
# Ditulis di sini, bukan diminta ke model, dengan alasan yang sama
# seperti BLOCK_HEADINGS di atas: yang dibutuhkan adalah jawaban yang
# PASTI ada. Kartu cadangan yang gagal dijawab akan kembali jadi
# kartu berbahasa Inggris milik orang lain.
#
# Urutan daftarnya sengaja tidak dipakai apa adanya; pemilihnya
# menggilir dari benih nama brand, supaya dua halaman tidak menambal
# lubangnya dengan pertanyaan yang sama.
FAQ_BANK = {
    "id": (
        (
            "Apa itu slot gacor di {brand}?",
            "Slot gacor adalah permainan yang sedang sering "
            "mengeluarkan kombinasi menang. Di {brand} kamu bisa "
            "melihat permainan mana yang lagi ramai lewat data yang "
            "diperbarui berkala, jadi tidak perlu menebak sendiri.",
        ),
        (
            "Bagaimana cara mulai main slot online di {brand}?",
            "Daftar dulu dengan nomor aktif, lalu masuk ke daftar "
            "permainan. Pilih satu slot, atur nilai taruhan per putaran, "
            "baru mulai spin. Semua langkahnya bisa dikerjakan dari HP.",
        ),
        (
            "Apakah bisa main slot lewat HP tanpa aplikasi?",
            "Bisa. Halaman {brand} berjalan langsung di browser HP, jadi "
            "kamu tidak perlu memasang apa pun. Kalau sinyal sedang pelan, "
            "tutup tab lain supaya putarannya tidak tersendat.",
        ),
        (
            "Berapa modal awal untuk main slot di {brand}?",
            "Tidak ada patokan yang wajib. Kebanyakan pemain mulai dari "
            "nominal kecil dulu untuk mengenali pola permainannya, baru "
            "menaikkan taruhan kalau sudah paham iramanya.",
        ),
        (
            "Jam berapa slot paling ramai dimainkan?",
            "Ramainya berpindah-pindah tiap hari. Yang bisa kamu pegang "
            "bukan jam tetap, melainkan data yang tampil di halaman "
            "{brand} - lihat dulu permainan mana yang sedang aktif "
            "sebelum menentukan waktu main.",
        ),
        (
            "Apa bedanya slot online dengan mesin slot biasa?",
            "Mesin lama memakai gulungan fisik, slot online memakai "
            "putaran acak yang dihitung server. Karena itu di {brand} "
            "kamu bisa melihat riwayat dan data tiap permainan, hal yang "
            "tidak ada di mesin lama.",
        ),
        (
            "Bagaimana cara deposit di {brand}?",
            "Pilih menu deposit, tentukan cara bayarnya - transfer bank, "
            "e-wallet, atau QRIS - lalu ikuti nominal yang tertera. "
            "Saldonya masuk sendiri begitu pembayaran terbaca.",
        ),
        (
            "Berapa lama proses penarikan dana?",
            "Sebagian besar penarikan selesai dalam hitungan menit selama "
            "nama rekening sama dengan nama akun. Kalau lewat dari itu, "
            "biasanya karena bank tujuan sedang dalam jam pemeliharaan.",
        ),
        (
            "Apakah pemain baru dapat bonus?",
            "Ada promo untuk pemain baru, dan syaratnya ditulis di "
            "halaman promo {brand}. Baca dulu ketentuan putarannya "
            "sebelum diambil, karena tiap promo punya aturan sendiri.",
        ),
        (
            "Apa arti RTP di daftar permainan slot?",
            "RTP adalah ukuran seberapa besar taruhan yang kembali ke "
            "pemain dalam jangka panjang. Angkanya bukan janji menang, "
            "tapi berguna untuk membandingkan satu permainan dengan "
            "permainan lain.",
        ),
        (
            "Apakah pola slot benar-benar bisa dibaca?",
            "Yang bisa dibaca adalah kecenderungannya, bukan hasil tiap "
            "putaran. Hasil satu spin tetap acak, jadi pola apa pun "
            "sebaiknya dipakai sebagai bahan pertimbangan, bukan patokan "
            "mati.",
        ),
        (
            "Apa yang harus dilakukan kalau permainan tidak mau terbuka?",
            "Coba muat ulang halamannya dulu, lalu bersihkan cache "
            "browser. Kalau masih sama, hubungi layanan bantuan {brand} "
            "dan sebutkan nama permainannya supaya bisa dicek langsung.",
        ),
        (
            "Apakah akun dan data saya aman?",
            "Data akun disimpan terenkripsi dan tidak dipakai untuk "
            "keperluan lain. Yang tetap jadi tanggung jawab kamu adalah "
            "menjaga kata sandi dan tidak membagikan kode masuk ke siapa "
            "pun.",
        ),
        (
            "Bisakah main slot sambil coba permainan lain?",
            "Bisa. Selain slot, {brand} juga memuat permainan lain di "
            "menu yang sama, dan saldonya dipakai bersama - jadi kamu "
            "tidak perlu pindah akun untuk mencoba.",
        ),
    ),
    "th": (
        (
            "สล็อตแตกง่ายที่ {brand} คืออะไร",
            "คือเกมที่กำลังออกรางวัลบ่อยในช่วงนั้น ที่ {brand} "
            "คุณดูได้จากข้อมูลที่อัปเดตเป็นระยะว่าเกมไหนกำลังมาแรง "
            "จึงไม่ต้องเดาเอง",
        ),
        (
            "เริ่มเล่นสล็อตออนไลน์ที่ {brand} อย่างไร",
            "สมัครด้วยเบอร์ที่ใช้งานจริง จากนั้นเข้าไปที่รายการเกม "
            "เลือกเกมที่ต้องการ ตั้งค่าเดิมพันต่อรอบ แล้วเริ่มหมุนได้เลย "
            "ทุกขั้นตอนทำผ่านมือถือได้",
        ),
        (
            "เล่นผ่านมือถือโดยไม่ติดตั้งแอปได้ไหม",
            "ได้ หน้าเว็บ {brand} เปิดผ่านเบราว์เซอร์บนมือถือได้ทันที "
            "ไม่ต้องติดตั้งอะไรเพิ่ม หากสัญญาณช้าให้ปิดแท็บอื่นก่อน",
        ),
        (
            "เริ่มเล่นสล็อตต้องใช้เงินเท่าไร",
            "ไม่มีจำนวนตายตัว ผู้เล่นส่วนใหญ่เริ่มจากจำนวนน้อยก่อน "
            "เพื่อทำความรู้จักจังหวะของเกม แล้วค่อยปรับเพิ่มทีหลัง",
        ),
        (
            "ฝากเงินที่ {brand} ทำอย่างไร",
            "เลือกเมนูฝากเงิน เลือกช่องทางที่สะดวก ทั้งโอนผ่านธนาคาร "
            "วอลเล็ต หรือคิวอาร์โค้ด แล้วทำตามยอดที่ระบุ "
            "ยอดจะเข้าอัตโนมัติเมื่อระบบอ่านรายการเจอ",
        ),
        (
            "ถอนเงินใช้เวลานานไหม",
            "ส่วนใหญ่เสร็จภายในไม่กี่นาที หากชื่อบัญชีตรงกับชื่อผู้ใช้ "
            "ถ้านานกว่านั้นมักเป็นช่วงที่ธนาคารปลายทางปิดปรับปรุง",
        ),
        (
            "ผู้เล่นใหม่ได้รับโบนัสหรือไม่",
            "มีโปรโมชันสำหรับผู้เล่นใหม่ เงื่อนไขระบุไว้ที่หน้าโปรโมชัน "
            "ของ {brand} ควรอ่านเงื่อนไขการหมุนก่อนรับทุกครั้ง",
        ),
        (
            "RTP ในรายการเกมสล็อตหมายถึงอะไร",
            "คือสัดส่วนเงินเดิมพันที่คืนสู่ผู้เล่นในระยะยาว "
            "ไม่ใช่คำรับประกันว่าจะชนะ แต่ใช้เปรียบเทียบระหว่างเกมได้",
        ),
        (
            "เปิดเกมไม่ได้ต้องทำอย่างไร",
            "ลองรีเฟรชหน้าเว็บก่อน จากนั้นล้างแคชเบราว์เซอร์ "
            "หากยังเหมือนเดิมให้ติดต่อฝ่ายช่วยเหลือของ {brand} "
            "พร้อมแจ้งชื่อเกมที่มีปัญหา",
        ),
        (
            "ข้อมูลบัญชีปลอดภัยหรือไม่",
            "ข้อมูลบัญชีถูกเข้ารหัสและไม่ถูกนำไปใช้กับเรื่องอื่น "
            "สิ่งที่ผู้ใช้ต้องดูแลเองคือรหัสผ่าน "
            "และอย่าบอกรหัสเข้าใช้งานกับใคร",
        ),
    ),
}


def faq_bank_cards(brand: dict, keyword: str = "") -> list[tuple[str, str]]:
    """
    Tanya-jawab cadangan untuk zona ini, sudah diisi nama brand.

    Urutannya digilir dari nama brand supaya dua halaman yang
    lubangnya sama tidak menambalnya dengan pertanyaan yang sama.
    """
    region = brand.get("region", "id")
    kartu = FAQ_BANK.get(region) or FAQ_BANK["id"]

    nama = str(brand.get("site_name", "")).strip() or str(keyword or "").strip()

    benih = int.from_bytes(
        hashlib.sha1(
            "{}|{}|faq".format(
                brand.get("site_name", ""),
                brand.get("variation", ""),
            ).encode("utf-8")
        ).digest()[:4],
        "big",
    )

    mulai = benih % len(kartu)

    return [
        (
            tanya.format(brand=nama).strip(),
            jawab.format(brand=nama).strip(),
        )
        for tanya, jawab in (
            kartu[(mulai + urutan) % len(kartu)]
            for urutan in range(len(kartu))
        )
    ]


# Peran yang teks barunya harus berarti sama dengan teks lamanya,
# bukan tulisan baru yang bebas. Menu, tombol, dan sel tabel menunjuk
# ke sesuatu yang nyata di situs itu; menggantinya dengan kata lain
# membuat tautannya menyesatkan meskipun alamatnya tidak berubah.
KEEP_MEANING_ROLES = ("nav_label", "table_cell", "label")

# Tingkat pertama breadcrumb SELALU beranda, dalam bahasa apa pun.
#
# Jadi "Beranda" yang dijawab "Beranda" adalah jawaban yang benar,
# bukan salinan malas - satu-satunya jawaban yang benar, malah.
# Menolaknya membuang satu giliran model untuk meminta sesuatu yang
# sudah betul, lalu melaporkannya sebagai "1 belum dijawab model"
# padahal Python tetap memasang berandanya sendiri di
# normalize_breadcrumb. Terukur di uji 12 Agustus: 16 dari 17 jawaban
# lolos, dan satu-satunya yang ditolak adalah kata "Beranda".
HOME_LABELS = frozenset(
    {"beranda", "home", "หน้าแรก", "halaman utama", "utama"}
)

# Peran yang teks lamanya dikirim bukan untuk dipertahankan artinya,
# melainkan untuk memberi tahu bagian apa yang dikepalainya.
#
# Judul dibagikan urut dokumen, dan urutan saja tidak memberi tahu
# model bahwa judul ketiga itu judul blok FAQ. Hasilnya terbaca di
# halaman jadi: blok FAQ berjudul "Fitur Utama Aplikasi" dan blok
# ulasan berjudul "Dukungan Teknis" - strukturnya utuh, penamaannya
# tidak menunjuk apa pun yang ada di bawahnya.
KEEP_FUNCTION_ROLES = ("heading",)

# Peran yang teks lamanya ikut dikirim demi BENTUKNYA, bukan demi
# arti maupun fungsinya.
#
# Judul kartu keunggulan dibangun dari dua bagian - nomor urut lalu
# judulnya - dan nomor itu memang tertulis di halaman, bukan
# penunjuk posisi. "1. Deposit QRIS 1 Detik" dijawab "Spin Tanpa
# Jeda" akan terbit sebagai satu-satunya kartu tanpa nomor di antara
# lima kartu bernomor. Baris tag di kartu ulasan sama: awalan
# "Tag: " bagian dari bentuknya.
#
# Sengaja tidak masuk KEEP_MEANING_ROLES: isinya justru harus
# berganti, jadi jawaban yang menyalin balik contohnya tetap ditolak
# dan diminta ulang.
#
# Judul dan deskripsi halaman ikut, dan itu permintaan pengguna
# persisnya - "contoh gayanya pakai dari template, tapi kata-katanya
# generate sendiri". Sebelum ini keduanya tidak pernah diperlihatkan
# ke model sama sekali, jadi satu-satunya patokan bentuk yang
# tersisa adalah berkas contoh gaya, dan model menyalin frame yang
# paling sering muncul di situ alih-alih meniru susunan judul yang
# memang sudah berdiri di template ini.
KEEP_SHAPE_ROLES = ("card_title", "review_tag")

# Peran bertekstunggal yang teks lamanya dikirim sebagai cetakan
# bentuk. Dipisah dari yang di atas karena keduanya tidak berupa
# daftar dan bagian promptnya sendiri.
HEAD_SHAPE_ROLES = ("title", "meta_description")

# Peran yang teks lamanya ikut dikirim ke AI, apa pun alasannya.
SAMPLE_ROLES = (
    KEEP_MEANING_ROLES
    + KEEP_FUNCTION_ROLES
    + KEEP_SHAPE_ROLES
    + HEAD_SHAPE_ROLES
)

# Panjang contoh teks lama yang dikirim ke AI. Cukup untuk mengenali
# maksudnya tanpa menghabiskan prompt untuk paragraf penuh.
SAMPLE_LIMIT = 80

# Batas khusus untuk cetakan bentuk judul dan deskripsi.
#
# Delapan puluh karakter cukup untuk mengenali maksud sebuah label,
# dan itu memang gunanya di peran lain. Untuk deskripsi 200 karakter
# ia memotong tepat di tengah kalimat kedua - dan kalimat kedua
# itulah bagian bentuk yang paling perlu dilihat model, karena di
# situ contohnya menutup dengan ajakan. Yang terkirim sebelum ini
# "Nikmati kemudahan deposit QRIS 1 detik di OSB99. Transaksi
# instan, aman, praktis" - cetakan yang berhenti sebelum bentuknya
# selesai.
#
# Batas yang lebih longgar juga yang membuat penolakan salinan
# bekerja: yang dibandingkan teks lama seutuhnya, bukan 80 huruf
# pertamanya.
HEAD_SAMPLE_LIMIT = 240


def sample_limit(role: str = "") -> int:
    """
    Sepanjang apa teks lama satu peran dikirim sebagai contoh.
    """
    return HEAD_SAMPLE_LIMIT if role in HEAD_SHAPE_ROLES else SAMPLE_LIMIT


def sample_text(current: str, role: str = "") -> str:
    """
    Bentuk baku satu teks lama, dipakai sebagai contoh dan kunci peta.

    Dipakai di kedua sisi - waktu contoh disusun dan waktu hasilnya
    dicocokkan kembali ke slot - supaya keduanya memotong di tempat
    yang sama. Kalau hanya satu sisi yang memotong, teks lama yang
    lebih panjang dari batas tidak akan pernah ketemu padanannya.
    """
    return " ".join(str(current or "").split())[: sample_limit(role)]


def dedupe_samples(
    slots: list[dict],
    role: str = "",
) -> tuple[list[str], list[int]]:
    """
    Menggabungkan slot yang teks lamanya sama jadi satu permintaan.

    Menu template sungguhan mengulang teks yang sama berkali-kali:
    "Mens", "Womens", "View All" muncul di menu utama, di mega menu,
    dan lagi di footer. Diminta satu per satu, 490 label menu di
    template yang dipakai menguji cuma punya 235 bunyi berbeda - dan
    karena permintaannya dipecah beberapa giliran, tiap giliran
    menulis tanpa melihat yang sudah ditulis giliran sebelumnya.
    Hasilnya "Slot Terdepan", "Slot Terbaik", "Slot Terlaris"
    berulang ratusan kali di satu halaman, dan keyword density
    melonjak ke 3,25% dari sana saja.

    Diminta sekali per bunyi, dua hal beres sekaligus: yang diminta
    tinggal separuhnya, dan setiap menu yang tulisannya sama di
    template terbit dengan tulisan yang sama pula - yang memang
    seperti itulah bentuk menu yang benar.

    Jatah panjang diambil yang tersempit di antara slot yang berbagi
    teks, karena satu teks itu harus muat di semuanya.
    """
    urut: list[str] = []
    jatah: dict[str, int] = {}

    for slot in slots:
        teks = sample_text(slot["current"], role)
        kunci = normalize(teks)

        if not kunci:
            continue

        if kunci in jatah:
            jatah[kunci] = min(jatah[kunci], slot["budget"])
            continue

        urut.append(teks)
        jatah[kunci] = slot["budget"]

    return urut, [jatah[normalize(teks)] for teks in urut]


# Peran yang tiap teksnya menerangkan satu teks milik peran lain,
# beserta peran yang diterangkannya.
#
# Judul kartu menamai keterangan yang berdiri di bawahnya; tag ulasan
# menandai ulasan yang berdiri di atasnya. Keduanya ditulis di giliran
# terpisah, sesudah pasangannya jadi, dan kalau pasangan itu tidak
# ikut diperlihatkan yang keluar adalah judul dan tag yang setopik
# halaman tapi tidak menerangkan apa-apa tentang kartunya sendiri.
PARTNER_ROLES = {
    "card_title": "paragraph",
    "review_tag": "review_text",
}


def partner_index(slot_map: dict, role: str) -> list[int]:
    """
    Nomor urut pasangan tiap slot, di dalam daftar peran pasangannya.

    Yang dicatat di slot cuma letak pasangannya di dalam dokumen,
    karena waktu peran diangkat daftar peran lain belum tentu sudah
    lengkap. Nomor urutnya diturunkan di sini, dan nomor itulah yang
    dipakai prompt untuk menunjuk teks yang sudah tertulis.
    """
    pasangan = PARTNER_ROLES.get(role)

    if not pasangan:
        return []

    urut = {
        slot["start"]: nomor
        for nomor, slot in enumerate(
            sorted(
                slot_map["roles"].get(pasangan, []),
                key=lambda item: item["start"],
            )
        )
    }

    return [
        urut.get(slot.get("partner"), -1)
        for slot in sorted(
            slot_map["roles"].get(role, []),
            key=lambda item: item["start"],
        )
    ]


def derive_spec(slot_map: dict) -> dict:
    """
    Menurunkan kebutuhan konten dari template.

    Yang keluar dari sini yang menentukan bentuk permintaan ke AI,
    bukan sebaliknya.
    """
    roles = slot_map["roles"]

    spec: dict[str, dict] = {}

    for role, slots in roles.items():
        if role in GENERATED_ROLES:
            continue

        # Judul yang blocknya sudah dikenali tidak ikut diminta ke
        # model; teksnya ditulis di build_edits. Dikeluarkan di sini
        # supaya jumlah yang diminta benar-benar sama dengan jumlah
        # yang dibutuhkan - kalau ikut dihitung, model diminta 9 judul
        # padahal cuma 7 yang dipakai, dan dua jawaban terakhir
        # terbuang tanpa ada yang tahu.
        slots = [slot for slot in slots if not slot.get("block")]

        if not slots:
            continue

        # Semua slot ikut, tanpa dibatasi.
        #
        # Dulu ada batas per peran di sini, karena satu permintaan ke
        # model tidak muat menampung 658 teks sekaligus. Batas itu
        # menyelesaikan masalah yang salah: yang tidak muat bukan
        # templatenya, melainkan cara memintanya. Sejak permintaannya
        # dipecah beberapa giliran di content_batches, seluruh slot
        # kebagian dan tidak ada lagi kalimat asli template yang
        # tertinggal di halaman terbit.
        #
        # Peran yang teks lamanya ikut dikirim dihitung per BUNYI,
        # bukan per slot: slot yang teks lamanya sama dijawab sekali
        # lalu dipasang di semua tempat yang memakainya.
        samples: list[str] = []

        if role in PARTNER_ROLES:
            # Peran berpasangan TIDAK digabung per bunyi. Nomor urut
            # tiap teks di sini menunjuk pasangannya - judul kartu
            # ke-3 menamai keterangan kartu ke-3 - dan penggabungan
            # menggeser seluruh nomor sesudah teks kembar pertama,
            # sehingga judul kartu terpasang di kartu orang lain.
            samples = [sample_text(slot["current"]) for slot in slots]

            # Jatahnya dikurangi awalan yang ditulis Python.
            #
            # Model tidak lagi menuliskan nomor kartu maupun "Tag:",
            # jadi jatah yang disebut ke model harus jatah untuk
            # SISANYA. Dikirim utuh, model menulis pas di batasnya,
            # lalu awalannya dipasang dan ujungnya kena potong -
            # terukur di halaman jadi sebagai "4. RTP Terupdate
            # Setiap 15", judul yang berhenti di sebuah angka.
            budgets = [
                max(
                    MIN_LEAD_BUDGET,
                    slot["budget"]
                    - display_width(lead_of(slot["current"])),
                )
                for slot in slots
            ]
        elif role in SAMPLE_ROLES:
            samples, budgets = dedupe_samples(slots, role)

        if not samples:
            budgets = [slot["budget"] for slot in slots]

        if not budgets:
            continue

        spec[role] = {
            "count": len(budgets),
            # Batas terkecil di kelompoknya. Hanya untuk dilaporkan;
            # BUKAN batas yang dikirim ke model. Memakai yang
            # terkecil untuk seluruh kelompok membuat satu slot
            # sempit mencekik semuanya: tombol "Daftar Sekarang" yang
            # sebenarnya punya ruang 20 kolom ikut dipotong jadi 8
            # cuma karena ada tautan "Promo" di menu yang sama.
            "max_length": min(budgets),
            # Batas yang dipakai sebagai plafon ke model. Tiap slot
            # tetap dirapikan ke jatahnya sendiri di build_edits.
            "max_length_any": max(budgets),
            # Jatah tiap slot, urut dokumen, supaya model bisa
            # menakar panjang per teks alih-alih menulis semuanya
            # sepanjang slot terlebar.
            "budgets": budgets,
        }

        # Lantai panjang. Dua bentuk, karena dua kebutuhan.
        #
        # min_length satu angka untuk seluruh peran, dipakai title dan
        # meta description - keduanya cuma punya satu teks, dan
        # lantainya ditegakkan grammar.
        #
        # floors satu angka per slot, dipakai teks di badan halaman.
        # Di situ lantainya tidak bisa satu angka: lima belas slot
        # paragraf di template pengguna berjatah 542 sampai 79
        # karakter, dan angka yang pas untuk yang terlebar akan
        # meledakkan yang tersempit keluar dari kotaknya.
        lantai = [length_floor(role, jatah) for jatah in budgets]

        if any(lantai):
            spec[role]["floors"] = lantai

            if role not in LIST_ROLES:
                spec[role]["min_length"] = min(
                    nilai for nilai in lantai if nilai
                )

        if samples:
            # Teks lamanya ikut dikirim ke AI. Untuk menu dan tombol
            # supaya artinya dipertahankan: tanpa ini label ditulis
            # sebagai daftar bebas lalu dibagikan urut dokumen, dan
            # tautan menuju /syarat bisa berakhir bertuliskan "Kota"
            # - menunya jadi berbohong soal tujuannya sendiri. Untuk
            # judul bagian supaya fungsinya dipertahankan: judul blok
            # FAQ tetap menamai FAQ, bukan tertukar dengan judul blok
            # ulasan yang kebetulan berdiri di dekatnya.
            spec[role]["samples"] = samples

        if role in PARTNER_ROLES:
            spec[role]["partners"] = partner_index(slot_map, role)

    return spec


def merge_specs(*specs: dict) -> dict:
    """
    Menggabungkan kebutuhan beberapa berkas template jadi satu.

    Landing page dan AMP hampir tidak pernah punya jumlah slot yang
    sama persis; versi AMP biasanya lebih ringkas. Kalau isi hanya
    dipesan sebanyak slot landing, slot AMP yang lebih banyak tidak
    kebagian dan kartu sisanya terbit dengan teks lama milik pemilik
    template - teks tentang keyword yang sama sekali berbeda.

    Jumlah diambil yang terbanyak supaya semua slot kebagian, dan
    panjang diambil yang paling sempit supaya teksnya tetap muat di
    berkas yang tata letaknya paling ketat.

    Peran yang teks lamanya ikut dikirim digabung sebagai himpunan
    bunyi, bukan dihitung jumlahnya. Yang menentukan jumlah minta di
    peran itu bukan berapa slot yang ada, melainkan berapa bunyi
    berbeda yang perlu dijawab.
    """
    merged: dict[str, dict] = {}

    # Contoh teks lama digabung sebagai HIMPUNAN, bukan diambil dari
    # berkas yang slotnya terbanyak. Landing dan AMP hampir selalu
    # memuat menu yang tidak sepenuhnya sama; memilih salah satu
    # daftar berarti label yang cuma ada di berkas satunya tidak
    # pernah diminta, lalu terbit dengan teks pemilik template.
    gabungan: dict[str, dict[str, tuple[str, int]]] = {}

    def kumpulkan(role: str, rule: dict) -> None:
        ruang = gabungan.setdefault(role, {})

        for teks, jatah in zip(rule["samples"], rule["budgets"]):
            kunci = normalize(teks)

            if kunci in ruang:
                ruang[kunci] = (ruang[kunci][0], min(ruang[kunci][1], jatah))
            else:
                ruang[kunci] = (teks, jatah)

    # Jumlah terbesar yang datang dari berkas yang perannya TIDAK
    # bercontoh. Dipakai sebagai lantai supaya berkas seperti itu
    # tidak kehilangan jatah hanya karena berkas lain menghitung
    # peran yang sama per bunyi.
    lantai: dict[str, int] = {}

    for spec in specs:
        for role, rule in (spec or {}).items():
            # Peran berpasangan sengaja TIDAK digabung per bunyi.
            # Penggabungan itu menyusun ulang daftarnya menurut bunyi
            # teks lama, sementara nomor urut di "partners" menunjuk
            # posisi di daftar semula - dan daftar yang tersusun ulang
            # membuat judul kartu ke-3 menerangkan kartu ke-5.
            bercontoh = (
                role not in PARTNER_ROLES
                and bool(rule.get("samples"))
                and bool(rule.get("budgets"))
            )

            if not bercontoh:
                lantai[role] = max(lantai.get(role, 0), rule["count"])

            if role not in merged:
                merged[role] = dict(rule)

                if bercontoh:
                    kumpulkan(role, rule)

                continue

            current = merged[role]

            if bercontoh:
                # Jumlah, jatah, dan batas panjangnya dihitung ulang
                # dari himpunan gabungan di bawah.
                kumpulkan(role, rule)
                continue

            current["count"] = max(current["count"], rule["count"])
            current["max_length"] = min(
                current["max_length"],
                rule["max_length"],
            )
            current["max_length_any"] = max(
                current["max_length_any"],
                rule["max_length_any"],
            )

            # Lantai diambil yang tertinggi. Berkas yang tidak punya
            # slotnya sama sekali - AMP tanpa meta description - tidak
            # boleh menurunkan lantai yang sudah dipatok berkas lain.
            if rule.get("min_length"):
                current["min_length"] = max(
                    current.get("min_length", 0),
                    rule["min_length"],
                )

            # Jatah per slot diambil dari berkas yang slotnya paling
            # banyak, supaya jumlahnya selalu cukup untuk dipasangkan
            # dengan jumlah yang diminta.
            if len(rule.get("budgets", [])) > len(current.get("budgets", [])):
                current["budgets"] = rule["budgets"]

                if rule.get("floors"):
                    current["floors"] = rule["floors"]

                # Contoh dan nomor pasangan ikut pindah bersama
                # jatahnya. Ketiganya satu daftar yang dibaca menurut
                # nomor urut yang sama; membawa salah satunya saja
                # membuat teks lama milik berkas ini dipasangkan
                # dengan jatah milik berkas satunya.
                for kunci in ("samples", "partners"):
                    if rule.get(kunci):
                        current[kunci] = rule[kunci]

    for role, ruang in gabungan.items():
        teks = [nilai[0] for nilai in ruang.values()]
        jatah = [nilai[1] for nilai in ruang.values()]

        merged[role].update(
            {
                "count": max(len(teks), lantai.get(role, 0)),
                "samples": teks,
                "budgets": jatah,
                "max_length": min(jatah),
                "max_length_any": max(jatah),
            }
        )

        # Lantai dihitung ulang dari jatah gabungan, bukan dibawa dari
        # salah satu berkas. Daftarnya harus sepanjang budgets yang
        # baru; yang lama panjangnya mengikuti berkas asalnya, dan
        # daftar yang panjangnya tidak cocok akan memasangkan lantai
        # milik slot lain ke slot ini.
        batas = [length_floor(role, nilai) for nilai in jatah]

        if any(batas):
            merged[role]["floors"] = batas
        else:
            merged[role].pop("floors", None)

    return merged


def scale_spec(spec: dict, chars_per_column: float) -> dict:
    """
    Mengubah jatah panjang dari kolom tampilan jadi jumlah karakter.

    Semua jatah dihitung dalam kolom, karena kolomlah yang
    menentukan apakah sebuah label masih muat di tata letaknya. Tapi
    yang bisa dihitung model dan dipaksakan JSON Schema adalah
    karakter, dan untuk aksara bertumpuk seperti Thai dua satuan itu
    berbeda jauh. Mengirim angka kolom apa adanya berarti menyuruh
    model menulis dalam separuh ruang yang sebenarnya tersedia.
    """
    if chars_per_column <= 1:
        return spec

    diperbesar: dict[str, dict] = {}

    for role, rule in spec.items():
        salinan = dict(rule)

        for kunci in ("max_length", "max_length_any", "min_length"):
            if kunci in salinan:
                salinan[kunci] = int(salinan[kunci] * chars_per_column)

        for kunci in ("budgets", "floors"):
            if salinan.get(kunci):
                salinan[kunci] = [
                    int(nilai * chars_per_column) for nilai in salinan[kunci]
                ]

        diperbesar[role] = salinan

    return diperbesar


# Kelonggaran plafon schema terhadap batas yang diminta di prompt.
# Grammar harus jadi jaring pengaman, bukan yang pertama kena:
# potongannya mentah dan tidak bisa diperbaiki lagi.
SCHEMA_HEADROOM = 1.3


# Plafon tertinggi yang masih sanggup dijadikan grammar oleh Ollama.
#
# Bukan angka pilihan, melainkan batas yang diukur. maxLength diubah
# llama.cpp jadi aturan pengulangan karakter, dan di atas sekitar dua
# ribu ia menyerah - permintaannya ditolak sebelum satu token pun
# ditulis:
#
#     400 Bad Request
#     Failed to initialize samplers: failed to parse grammar
#
# Dibisect di mesin ini: 1998 lolos, 2012 gagal. Jumlah item di
# dalam array tidak berpengaruh - 1 item dan 15 item sama-sama lolos
# di 1600 - jadi yang dibatasi memang panjang satu teks.
#
# Angka di bawah dipasang jauh di bawah ambangnya, karena ambang itu
# milik satu versi llama.cpp di satu mesin dan bisa berbeda di
# tempat lain. Satu run gagal berarti belasan menit hangus.
#
# Yang menabraknya ada dua jalan, dan dua-duanya nyata:
#   1. Jatah paragraf yang dilebarkan kolom "Panjang artikel" -
#      terukur 1626 karakter, dikali kelonggaran jadi 2113.
#   2. Zona beraksara bertumpuk: scale_spec menggandakan seluruh
#      jatah untuk Thai, jadi slot 1200 karakter jadi 2400 bahkan
#      tanpa target panjang sama sekali.
SCHEMA_MAX_LENGTH = 1800


def build_dynamic_schema(spec: dict) -> dict:
    """
    Menyusun JSON Schema yang jumlahnya persis mengikuti template.
    """
    properties: dict[str, dict] = {}
    required: list[str] = []

    def text_field(role: str) -> dict:
        # Plafon diambil dari slot TERLEBAR di kelompoknya, bukan
        # tersempit, lalu dilonggarkan lagi.
        #
        # maxLength di schema dipaksakan grammar llama.cpp dengan cara
        # memutus string begitu batasnya kena. Pemutusan itu tidak tahu
        # apa-apa soal kata maupun tanda yang menempel, jadi kalau
        # grammar yang lebih dulu kena, hasilnya potongan mentah yang
        # tidak bisa diperbaiki lagi di tahap mana pun. Batas yang
        # sungguhan ditegakkan belakangan per slot, di tempat yang
        # tahu cara memotong tanpa merusak huruf.
        plafon = int(spec[role]["max_length_any"])

        # Lantai dipasang PERSIS di angkanya, bukan dilonggarkan
        # seperti plafon.
        #
        # Alasannya berkebalikan. Teks yang kepanjangan masih bisa
        # diperbaiki belakangan - dipotong di batas kalimat, di tempat
        # yang tahu di mana kata berakhir. Teks yang kependekan tidak
        # bisa diperbaiki oleh siapa pun: tidak ada di Python ini yang
        # sanggup menyambung title 41 karakter jadi 68 karakter yang
        # masih berbunyi seperti kalimat manusia. Jadi untuk lantai,
        # grammar memang harus jadi yang menegakkan - ia menahan tanda
        # kutip penutup sampai jatahnya terpenuhi, dan model meneruskan
        # kalimatnya alih-alih berhenti.
        lantai = int(spec[role].get("min_length") or 0)

        # Plafon SELALU dilonggarkan, termasuk untuk peran yang punya
        # lantai.
        #
        # Sempat dipatok pas di angkanya, dengan alasan yang kedengaran
        # masuk akal: kalau lantai dan plafon dua-duanya dipatok, model
        # menulis di dalam rentangnya dan tidak ada yang perlu
        # dipotong. Yang terjadi justru sebaliknya, dan terbaca di
        # halaman jadi - title terbit sebagai
        #
        #     "TIMAH33 menyediakan slot gacor dengan RTP live dan
        #      deposit QRIS instan untuk sel"
        #
        # Grammar menutup stringnya persis di karakter ke-80, di tengah
        # kata "seluruh", dan tidak ada satu tahap pun sesudahnya yang
        # bisa mengembalikan huruf yang hilang. Lantai membuat model
        # menulis sampai penuh, dan menulis sampai penuh membuat
        # tabrakan dengan plafon jadi keadaan biasa, bukan kekecualian.
        #
        # Jadi kelonggarannya justru lebih dibutuhkan di sini daripada
        # di peran tanpa lantai. Kelebihannya dirapikan belakangan oleh
        # clean_line, yang tahu di mana kata dan kalimat berakhir.
        field = {
            "type": "string",
            "maxLength": min(
                SCHEMA_MAX_LENGTH,
                int(plafon * SCHEMA_HEADROOM),
            ),
        }

        if lantai and lantai < field["maxLength"]:
            field["minLength"] = lantai

        return field

    def list_field(role: str) -> dict:
        count = spec[role]["count"]

        return {
            "type": "array",
            "minItems": count,
            "maxItems": count,
            "items": text_field(role),
        }

    for role in ("title", "meta_description", "meta_keywords", "h1"):
        if role in spec:
            properties[role] = text_field(role)
            required.append(role)

    for role in LIST_ROLES:
        if role in spec and spec[role]["count"] > 0:
            properties[role] = list_field(role)
            required.append(role)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# Kelebihan lebar yang dibiarkan lewat kalau teksnya tidak punya
# batas kata untuk dipotong. Jatah tiap slot sudah memuat toleransi
# 35% terhadap teks aslinya, jadi tambahan ini hanya menyangkut teks
# yang sedikit melewati jatah itu - bukan jawaban yang kepanjangan.
OVERFLOW_TOLERANCE = 1.3


# Peran yang isinya kalimat utuh, jadi potongannya digeser ke akhir
# kalimat. Label menu dan sel tabel tidak ikut: isinya memang bukan
# kalimat, dan menggeser ke titik terdekat akan menghabiskannya.
SENTENCE_ROLES = {
    "paragraph",
    "faq_answer",
    "review_text",
    "list_item",
    "caption",
    # Deskripsi ikut sejak jatahnya dinaikkan ke 160-200 karakter.
    #
    # Di 160 sebuah deskripsi muat satu kalimat, dan potongan di batas
    # kata praktis tidak pernah kelihatan. Di 200 ia memuat dua sampai
    # tiga, dan potongan yang jatuh di tengah kalimat kedua terbaca
    # persis di tempat yang paling banyak dibaca orang - di bawah
    # judul, di hasil pencarian.
    "meta_description",
}

# Urutan siapa yang menang saat beberapa slot punya teks lama yang
# bunyinya sama persis. Yang di depan lebih dulu mengklaim bunyinya.
#
# Judul halaman paling depan karena bunyi itulah yang paling sering
# diulang di seluruh dokumen - di <meta>, di alt gambar, di kartu
# berbagi. Peran yang tidak disebut di sini tetap ikut, di belakang,
# urut dokumen.
ECHO_PRIORITY = (
    "title",
    "h1",
    "meta_description",
    "heading",
)


# Peran yang isinya tidak boleh kembar di satu halaman.
#
# nav_label dan label sengaja TIDAK ikut: menu memang mengulang
# tulisan yang sama di beberapa tempat, dan justru itu bentuk menu
# yang benar. Yang dilarang kembar adalah teks yang masing-masing
# seharusnya membawa isi berbeda.
UNIQUE_ROLES = {
    "heading",
    "paragraph",
    "faq_question",
    "faq_answer",
    "review_text",
    "list_item",
    # Enam kartu keunggulan yang dua di antaranya berjudul sama
    # terbaca sebagai daftar yang diisi asal-asalan, dan tag ulasan
    # yang berulang membuat lima ulasan tampak menyoroti satu hal.
    "card_title",
    "review_tag",
}

# Seberapa besar irisan kata isi yang sudah dianggap mengulang.
#
# Menolak yang sama persis saja tidak cukup, dan itu terukur di
# halaman jadi: tujuh pertanyaan FAQ semuanya berbeda hurufnya, tapi
# isinya cuma empat topik -
#
#   Apakah slot online sama dengan slot fisik?
#   Apa perbedaan slot online dan slot fisik?              tiga
#   Apa perbedaan utama antara slot online dan slot fisik? pertanyaan,
#                                                          satu topik
#
# Angka 0,5 diambil dari jarak yang terukur di halaman itu sendiri.
# Pasangan yang mengulang berada di 0,5 sampai 0,8, sementara
# pasangan yang benar-benar menanyakan hal berbeda tidak lewat dari
# 0,29 - jadi ambangnya duduk di ruang kosong di antara keduanya,
# bukan di tengah sebaran.
NEAR_DUPLICATE_RATIO = 0.5


# Peran yang dibandingkan lewat potongan frasa, bukan irisan kata.
#
# Keduanya paragraf artikel, dan untuk paragraf irisan kata tidak
# bisa dipakai sama sekali. Terukur pada tiga kumpulan teks:
#
#                                    irisan kata   frasa 3 kata
#   tulisan asli pengguna, 16 par         0,396          0,101
#   kerangka kalimat sama, 20 par         1,000          0,829
#   beragam tapi sekosakata, 42 par       0,880          0,500
#
# Baris kedua harus dibatalkan, baris ketiga harus lolos, dan dengan
# irisan kata tidak ada ambang yang memisahkan 0,880 dari 1,000.
# Akibatnya terukur di halaman jadi: artikel 42 paragraf terbit
# tinggal 26 - pengguna melaporkannya sebagai "artikel masih kurang
# panjang", dan sebabnya bukan bentuknya melainkan penyaring ini.
#
# Peran lain tetap memakai irisan kata. Ambang 0,5 di sana diukur
# dari pertanyaan FAQ yang panjangnya sepuluhan kata, dan teks
# sependek itu tidak punya cukup frasa untuk dibandingkan.
PHRASE_ROLES = {"paragraph"}

# Ambang untuk perbandingan frasa. Duduk di ruang kosong antara
# 0,500 (beragam, harus lolos) dan 0,829 (mengulang, harus batal).
PHRASE_DUPLICATE_RATIO = 0.65


# Kata tanya pembuka, dipakai memisahkan dua pertanyaan yang
# kosakatanya sama tapi menanyakan hal yang berbeda.
#
# Ini koreksi untuk penyaring yang memakan pertanyaan yang benar.
# Tujuh pertanyaan tentang satu topik sempit - deposit QRIS di satu
# situs - terpaksa berbagi hampir seluruh kosakatanya, dan irisan
# katanya terukur sampai 0,43 padahal ketujuhnya menanyakan hal yang
# berbeda. Ambang 0,5 cuma menyisakan jarak 0,07, dan gilirannya
# tinggal soal keberuntungan: pada dua run yang diamati, dua dari
# tujuh pertanyaan dibuang lalu diminta ulang dua kali tanpa pernah
# terisi, dan slotnya terbit dengan pertanyaan lama.
#
# Kata tanyanya yang memisahkan dengan bersih. "Bagaimana cara
# deposit QRIS di JUHI88?" dan "Berapa lama deposit QRIS di JUHI88?"
# berbagi hampir semua katanya dan sama sekali bukan pertanyaan yang
# sama; yang menentukan bukan kosakatanya melainkan apa yang diminta.
# Yang panjang didahulukan: tanpa itu "apakah" tercocokkan sebagai
# "apa", dan dua kata tanya yang berbeda terbaca jadi satu. Batas
# kata di ujungnya menutup celah yang sama dari sisi lain.
QUESTION_OPENERS = re.compile(
    r"^(?:apakah|apa|bagaimana|gimana|berapa|kapan|di\s?mana|"
    r"ke\s?mana|mengapa|kenapa|siapa|bolehkah|adakah|amankah|"
    r"benarkah|what|how|why|when|where|who|which|is|are|does|"
    r"did|do|can|could|should|will|would)\b",
    re.IGNORECASE,
)

# Peran yang identitasnya ikut ditentukan kata tanya pembukanya.
OPENER_ROLES = {"faq_question"}


def question_opener(teks: str) -> str:
    """
    Kata tanya yang membuka sebuah pertanyaan, atau kosong.
    """
    cocok = QUESTION_OPENERS.match(str(teks or "").strip())

    return cocok.group(0).lower().replace(" ", "") if cocok else ""


def sidik_isi(teks: str, role: str = "") -> set:
    """
    Sidik jari isi sebuah teks, sesuai cara banding perannya.
    """
    if role in PHRASE_ROLES:
        return content_shingles(teks)

    return content_tokens(teks)


def mirip_isinya(
    teks: str,
    kumpulan: list[set],
    role: str = "",
    pembuka: str = "",
    daftar_pembuka: list[str] | None = None,
) -> bool:
    """
    Apakah teks ini mengulang isi salah satu yang sudah tertulis.

    Untuk pertanyaan, dua teks yang kata tanyanya berbeda tidak
    pernah dihitung mengulang - berapa pun irisan kosakatanya.
    """
    milik = sidik_isi(teks, role)

    if not milik:
        return False

    ambang = (
        PHRASE_DUPLICATE_RATIO
        if role in PHRASE_ROLES
        else NEAR_DUPLICATE_RATIO
    )

    pakai_pembuka = role in OPENER_ROLES and bool(pembuka)
    lawan = list(daftar_pembuka or [])

    for urut, lain in enumerate(kumpulan):
        if not lain:
            continue

        if pakai_pembuka:
            milik_lawan = lawan[urut] if urut < len(lawan) else ""

            if milik_lawan and milik_lawan != pembuka:
                continue

        gabungan = milik | lain

        if len(milik & lain) / len(gabungan) >= ambang:
            return True

    return False


# Nomor urut di awal teks: "26. ", "7) ", "(3) ".
#
# Angka desimal dan angka ribuan tidak ikut tertangkap karena
# polanya menuntut spasi sesudah titik, sedangkan "0.5" dan
# "12.000" diikuti angka.
LIST_NUMBER = re.compile(r"^\s*\(?\d{1,3}\s*[.)]\s+")


def drop_stray_number(value, sample: str = ""):
    """
    Membuang nomor daftar yang ikut tersalin ke dalam jawaban model.

    Daftar teks lama dikirim ke model bernomor supaya jawaban ke-N
    bisa dipasangkan ke slot ke-N. Sebagian model membaca nomor itu
    sebagai bagian dari teksnya lalu menuliskannya kembali. Terukur
    di halaman jadi: 92 teks terbit berawalan nomor, termasuk
    hampir seluruh menu footer - "26. Cara Pesan", "38. Inggris",
    "9. Harga Minimum".

    Yang menentukan boleh dibuang atau tidak adalah teks lamanya,
    bukan bentuk nomornya. Template ini benar-benar punya daftar
    fitur bernomor - "1. Deposit QRIS 1 Detik" sampai "6. Dukungan
    Layanan Responsif" - dan di enam slot itu nomornya memang isi,
    bukan sisa daftar. Aturan yang cuma melihat bentuk akan
    menghapus penomoran yang dipasang pemilik template.

    Dibuang di sini, sebelum panjangnya dihitung, karena nomornya
    ikut memakan jatah: "33. Terminos y Condiciones" terbit
    terpotong jadi "33. Terminos y".
    """
    if not isinstance(value, str):
        return value

    cocok = LIST_NUMBER.match(value)

    if not cocok:
        return value

    if LIST_NUMBER.match(sample_text(sample)):
        return value

    # Kalau nomor itu seluruh isinya, yang tersisa kosong - dan slot
    # kosong diminta ulang, sedangkan slot berisi "26." tidak.
    return value[cocok.end():]


# Awalan yang bagian dari teksnya sendiri, bukan penunjuk posisi.
#
# Dua bentuk, keduanya ada di template pengguna: nomor urut kartu
# keunggulan ("1. Deposit QRIS 1 Detik") dan penanda baris tag di
# kartu ulasan ("Tag: Cepat & Praktis").
LEAD_MARK = re.compile(r"^\s*(?:\d{1,2}\s*[.)]\s*|[^\s:]{2,12}:\s*)")

# Peran yang awalan teks lamanya ditulis ulang di Python.
#
# Diminta lewat kalimat prompt saja tidak cukup, dan bekasnya terbaca
# di halaman: dari enam kartu bernomor, model menulis nomornya di
# sebagian dan melewatkannya di sebagian lain - dan satu kartu tanpa
# nomor di antara lima kartu bernomor lebih kelihatan daripada enam
# kartu yang semuanya tidak bernomor.
LEAD_ROLES = {"card_title", "review_tag"}

# Jatah paling sempit yang masih disisakan sesudah awalannya dipotong.
# Dua kata pendek; di bawah ini yang diminta bukan judul lagi.
MIN_LEAD_BUDGET = 14


def lead_of(text: str) -> str:
    """
    Awalan sebuah teks, kalau ada.
    """
    cocok = LEAD_MARK.match(" ".join(str(text or "").split()))

    return cocok.group(0) if cocok else ""


def bare_text(value: str, role: str = "") -> str:
    """
    Bentuk satu teks untuk DIBANDINGKAN, bukan untuk ditulis.

    Dua hal dibuang, dan keduanya lubang yang benar-benar dipakai
    model untuk menyelinapkan salinan lewat saringan:

    1. Awalan yang ditulis ulang Python. Contoh "1. Deposit QRIS 1
       Detik" dijawab "Deposit QRIS 1 Detik" - beda satu awalan, jadi
       lolos sebagai jawaban baru - lalu restore_lead memasang
       nomornya kembali dan yang terbit teks lama PERSIS. Terukur di
       halaman jadi: kartu 1 sampai 3 dan tag 1 sampai 4 masih milik
       template, sementara log job melaporkan semuanya terisi.

    2. Entity HTML. Contoh dikirim apa adanya dari template, jadi
       yang dibaca model "Tag: Cepat &amp; Praktis". Dijawab "Cepat
       & Praktis" ia beda huruf tapi sama teks.
    """
    badan = html_module.unescape(" ".join(str(value or "").split()))

    if role in LEAD_ROLES:
        badan = badan[len(lead_of(badan)):]

    return normalize(badan)


def copies_sample(teks: str, contoh: str, role: str = "") -> bool:
    """
    Apakah jawaban ini cuma menyalin balik contohnya sendiri.
    """
    bersih = bare_text(teks, role)

    return bool(bersih) and bersih == bare_text(contoh, role)


def restore_lead(new: str, old: str) -> str:
    """
    Mengembalikan awalan teks lama ke teks penggantinya.

    Yang dikembalikan awalan LAMA, bukan awalan yang ditulis model.
    Nomor kartu ditentukan letaknya di halaman, bukan pilihan model:
    kartu ketiga bernomor tiga meskipun model menuliskannya "1.".
    """
    badan = " ".join(str(new or "").split())
    awalan = lead_of(old)

    if not badan or not awalan:
        return badan

    return awalan + badan[len(lead_of(badan)):]


def clean_line(value, limit: int, role: str = "", floor: int = 0) -> str:
    """
    Merapikan satu teks dan memastikan panjangnya masuk akal.

    Pemotongannya diserahkan ke utils.text supaya potongan tidak
    pernah jatuh di tengah huruf. Memotong dengan iris biasa
    menyisakan tanda vokal tanpa huruf induknya, dan itu tampil
    sebagai karakter menggantung yang tidak terbaca.

    Untuk peran yang isinya kalimat, potongannya digeser lagi ke
    akhir kalimat terakhir yang masih muat.

    Peran lain tidak diberi titik - judul dan label memang tidak
    diakhiri titik - tapi tetap dibersihkan dari kata sambung yang
    menggantung di ujung.

    Pertanyaan FAQ tidak dipotong sama sekali. Kalau tidak muat,
    yang dikembalikan kosong, dan posisinya diminta ulang.
    """
    if role == "faq_question":
        # Pertanyaan itu satu kesatuan; memotongnya tidak
        # menghasilkan pertanyaan yang lebih pendek melainkan
        # pertanyaan yang rusak. Terukur di halaman jadi: "Apakah
        # deposit QRIS di ASOKASLOT?" - kata kerjanya hilang di
        # potongan, tanda tanyanya dipasang balik sesudahnya, dan
        # hasilnya terbit sebagai pertanyaan yang tampak utuh
        # sekilas padahal tidak menanyakan apa pun.
        #
        # Paragraf boleh dipotong karena kalimat sebelumnya tetap
        # berdiri sendiri. Pertanyaan tidak punya kalimat sebelumnya.
        badan = " ".join(str(value or "").split())

        if not badan:
            return ""

        if display_width(badan) > limit * OVERFLOW_TOLERANCE:
            return ""

    if role in SENTENCE_ROLES:
        teks = trim_to_sentence(value, limit, OVERFLOW_TOLERANCE, floor)
    else:
        # Apakah teksnya benar-benar dipotong ikut diberitahukan,
        # bukan ditebak dari hasilnya. Itu yang membedakan judul yang
        # kebetulan berakhir "dan Praktis" - utuh, jangan disentuh -
        # dari sisa potongan "dan Transaksi" yang menjanjikan
        # kelanjutan yang tidak pernah datang.
        badan = " ".join(str(value or "").split())
        potongan = trim_to_width(badan, limit, OVERFLOW_TOLERANCE)

        teks = drop_dangling(potongan, dipotong=potongan != badan)

    if role == "faq_question" and teks and teks[-1] not in "?？":
        # Pertanyaan yang kehilangan tanda tanyanya waktu dipotong
        # berhenti terbaca sebagai pertanyaan - "Apa yang perlu
        # diperhatikan saat memilih" berdiri di atas jawaban seolah
        # judul yang salah tulis. Tanda tanyanya dipasang balik, dan
        # kalau jadi kelewat lebar teksnya digeser mundur dulu.
        teks = teks.rstrip(" ,.;:-")

        if display_width(teks) + 1 > limit * OVERFLOW_TOLERANCE:
            teks = trim_to_width(teks, max(1, limit - 1), OVERFLOW_TOLERANCE)

        # Digeser mundur bisa memunculkan kata gantung yang baru, jadi
        # pembersihannya diulang tepat sebelum tanda tanya dipasang.
        teks = drop_dangling(teks)

        teks = f"{teks}?"

    return teks


def fit_content_to_spec(
    content: dict,
    spec: dict,
    fallbacks: dict | None = None,
    seen: dict | None = None,
) -> tuple[dict, list[str]]:
    """
    Mencocokkan jumlah isi dengan jumlah slot, apa pun jawaban model.

    Kelebihan dipotong. Kekurangan ditambal dari bahan yang sudah
    ada di blueprint. Kalau tetap kurang, slot sisanya dibiarkan
    memakai teks asli template: kartu yang isinya teks lama masih
    jauh lebih baik daripada kartu kosong.
    """
    filled: dict = {}
    warnings: list[str] = []
    spare = fallbacks or {}

    for role, rule in spec.items():
        # Plafon terlebar, bukan tersempit. Penyesuaian ke jatah tiap
        # slot dikerjakan belakangan di build_edits, di mana slot yang
        # dimaksud sudah diketahui - dan di situ pula setiap berkas
        # dirapikan menurut tata letaknya sendiri, bukan menurut
        # berkas paling sempit di antara landing dan AMP.
        limit = rule.get("max_length_any") or rule["max_length"]

        if role not in LIST_ROLES:
            nilai = content.get(role, "")

            # Peran tunggal yang dijawab sebagai daftar atau objek
            # akan tertulis di halaman sebagai repr Python kalau
            # dibiarkan, misalnya "['Judul']".
            if isinstance(nilai, (list, tuple)):
                nilai = nilai[0] if nilai else ""
            elif not isinstance(nilai, (str, int, float)):
                nilai = ""

            lantai = int(rule.get("min_length") or 0)

            # Lantai diteruskan hanya untuk peran bertekstunggal,
            # yaitu title dan meta description. Peran daftar di bawah
            # tidak diberi lantai di tahap ini: di situ kalimat utuh
            # yang pendek selalu lebih baik daripada potongan panjang
            # yang berhenti di tengah pikiran.
            filled[role] = clean_line(
                nilai,
                limit,
                role,
                int(rule.get("min_length") or 0),
            )

            # Judul dan deskripsi lama ikut dikirim sebagai cetakan
            # bentuk, dan cetakan yang diperlihatkan ke model kecil
            # kadang disalin bulat-bulat. Yang disalin dikosongkan di
            # sini supaya posisinya diminta ulang; dibiarkan lewat, ia
            # terbit sebagai kalimat pemilik template dengan nama
            # brand baru ditempel di depannya.
            contoh = {
                normalize(sample_text(teks, role))
                for teks in (rule.get("samples") or [])
            }

            if filled[role] and normalize(filled[role]) in contoh:
                warnings.append(
                    f"AI menyalin balik {role} milik template, "
                    "diminta ulang."
                )

                filled[role] = ""

            if not filled[role]:
                warnings.append(
                    f"AI tidak mengisi {role}, slotnya dilewati."
                )

                continue

            # Kekurangan panjang dilaporkan, bukan ditambal.
            #
            # Lantainya sudah ditegakkan grammar waktu jawabannya
            # ditulis, jadi sampai di sini hampir selalu terpenuhi.
            # Yang bisa menjatuhkannya cuma perapian di atas, dan itu
            # berarti jawabannya memang bermasalah - satu kata
            # kepanjangan, atau tanda baca yang membuat potongannya
            # jatuh jauh. Menambalnya di Python berarti mengarang
            # kalimat; yang benar adalah mengatakannya apa adanya.
            if lantai and len(filled[role]) < lantai:
                warnings.append(
                    f"{role} cuma {len(filled[role])} karakter, "
                    f"di bawah lantai {lantai}."
                )

            continue

        wanted = rule["count"]

        raw_items = content.get(role, [])

        # Model kadang mengembalikan satu string untuk peran yang
        # seharusnya daftar. Kalau string itu langsung diiterasi,
        # yang masuk ke slot adalah huruf per huruf: kartu FAQ
        # pertama berisi "J", kedua berisi "u". Halamannya terbit
        # dan tidak ada pemeriksa struktur yang bisa melihatnya,
        # karena strukturnya memang tidak rusak.
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        elif not isinstance(raw_items, (list, tuple)):
            raw_items = []

        # Yang tidak terpakai dikosongkan di tempat, bukan dibuang.
        #
        # Membuangnya menggeser seluruh sisa daftar naik satu posisi,
        # dan posisi itulah yang memasangkan jawaban ke slotnya -
        # jawaban FAQ ke-3 pindah ke pertanyaan ke-2, dan seterusnya
        # sampai ujung. Dikosongkan di tempat, posisinya tercatat
        # kosong dan giliran ulang yang mengisinya.
        # Teks lama dipegang terpisah dari "contoh" di bawah, yang
        # dikosongkan untuk peran yang artinya harus bertahan. Yang
        # dibutuhkan di sini bukan bahan pembanding gema, melainkan
        # bentuk teks lamanya: bernomor atau tidak.
        semula = list(rule.get("samples") or [])

        items = [
            clean_line(
                drop_stray_number(
                    item,
                    semula[index] if index < len(semula) else "",
                ),
                limit,
                role,
            )
            if isinstance(item, (str, int, float))
            else ""
            for index, item in enumerate(raw_items)
        ]

        # Jawaban yang menyalin balik contohnya sendiri dibuang di
        # sini, bukan diterima lalu ditolak belakangan.
        #
        # Bedanya menentukan: kalau salinan diterima, jumlahnya
        # terlihat lengkap dan permintaan ulang tidak pernah jalan,
        # sehingga slotnya terbit dengan teks pemilik template.
        # Dibuang di sini, posisinya tercatat kosong dan giliran ulang
        # yang meminta ganti - itulah yang dulu membuat "FAQ OSB99"
        # bertahan di halaman yang seluruh isinya sudah berganti.
        #
        # Label menu dan sel tabel dikecualikan, dan pengecualiannya
        # bukan kelonggaran melainkan koreksi. Peran itu diminta
        # MEMPERTAHANKAN artinya, jadi "Kontak" yang dijawab "Kontak"
        # adalah jawaban yang benar, bukan salinan malas. Menolaknya
        # membuang seluruh giliran ulang untuk meminta sesuatu yang
        # sudah betul, lalu berakhir memakai teks lama juga - terukur
        # di run terakhir: 74 label diminta ulang dua kali dan
        # jumlahnya tidak bergeser satu pun.
        #
        # Nama brand lama yang ikut terbawa di dalamnya tetap bersih,
        # karena seluruh teks disapu sekali lagi di build_edits.
        contoh = (
            []
            if role in KEEP_MEANING_ROLES
            else (rule.get("samples") or [])
        )

        if contoh:
            items = [
                ""
                if index < len(contoh)
                and normalize(teks) not in HOME_LABELS
                and copies_sample(teks, contoh[index], role)
                else teks
                for index, teks in enumerate(items)
            ]

        # Teks kembar juga dianggap belum terisi. Dua kartu FAQ yang
        # bertanya hal yang sama persis terbaca sebagai halaman yang
        # digenerate asal-asalan, dan itu terukur di halaman jadi:
        # "Bagaimana cara memulai bermain slot online?" muncul dua
        # kali berjejer.
        if role in UNIQUE_ROLES:
            # Yang sudah tertulis di giliran LAIN ikut dihitung.
            #
            # Memeriksa satu giliran saja tidak cukup: permintaannya
            # dipecah, dan tiap giliran menulis tanpa melihat giliran
            # sebelumnya, jadi kalimat yang sama muncul lagi di
            # giliran berikutnya tanpa ada yang menghalangi.
            terlihat = set((seen or {}).get(role) or set())
            urut_terlihat = list(terlihat)
            isi_terlihat = [sidik_isi(t, role) for t in urut_terlihat]
            pembuka_terlihat = [question_opener(t) for t in urut_terlihat]

            for index, teks in enumerate(items):
                kunci = normalize(teks)

                if not kunci:
                    continue

                pembuka = question_opener(teks)

                if kunci in terlihat or mirip_isinya(
                    kunci,
                    isi_terlihat,
                    role,
                    pembuka,
                    pembuka_terlihat,
                ):
                    items[index] = ""
                    continue

                terlihat.add(kunci)
                isi_terlihat.append(sidik_isi(kunci, role))
                pembuka_terlihat.append(pembuka)

        if len(items) > wanted:
            warnings.append(
                f"AI menulis {len(items)} {role} padahal template "
                f"punya {wanted} slot, kelebihannya dibuang."
            )
            items = items[:wanted]

        # Lubang diisi dari bahan cadangan lebih dulu, baru sisanya
        # dibiarkan kosong. Panjang daftar dijaga tepat sebanyak slot
        # supaya nomor urutnya tetap menunjuk slot yang sama - itu
        # yang dipakai giliran ulang untuk tahu posisi mana yang
        # masih perlu diisi.
        items = items + [""] * (wanted - len(items))

        cadangan = [
            teks
            for teks in (
                clean_line(item, limit, role) for item in spare.get(role, [])
            )
            if teks
        ]

        dari_cadangan = 0

        for index, teks in enumerate(items):
            if teks or not cadangan:
                continue

            isi = cadangan.pop(0)

            if normalize(isi) not in {normalize(x) for x in items if x}:
                items[index] = isi
                dari_cadangan += 1

        kosong = sum(1 for teks in items if not teks)

        if kosong:
            warnings.append(
                f"{wanted - kosong} dari {wanted} {role} terisi; "
                f"{kosong} belum dijawab model."
            )

        # Slot yang ditambal dari bahan kompetitor disebut terpisah.
        #
        # Teks ini tidak lewat model sama sekali - Python menyalinnya
        # apa adanya dari hasil crawl ke halaman. Sebelumnya ia ikut
        # terhitung "terisi" dan tidak meninggalkan jejak apa pun,
        # dan itu yang membuat pertanyaan FAQ "Seberapa Pancasila
        # Dirimu?" di halaman slot sempat dikira model mengarang.
        # Yang terjadi sebaliknya: model menulis 6 pertanyaan yang
        # benar, slot ke-7 dibiarkannya kosong, lalu baris di atas
        # menambalnya dengan satu-satunya pertanyaan yang terpanen
        # dari SERP hari itu - milik situs lembaga negara yang
        # dibajak. Sumbernya sudah dibereskan di build_blueprint;
        # catatan ini supaya kejadian sejenis kelihatan dari log,
        # bukan baru ketahuan setelah halamannya dibaca orang.
        if dari_cadangan:
            warnings.append(
                f"{dari_cadangan} {role} tidak ditulis model dan "
                "ditambal dari pertanyaan yang dipakai kompetitor. "
                "Periksa teksnya - itu salinan mentah dari hasil "
                "crawl."
            )

        filled[role] = items

    filled["_by_old"] = pair_by_old_text(spec, filled)

    return filled, warnings


def balance_paired_roles(content: dict) -> list[str]:
    """
    Menyamakan jumlah pertanyaan dengan jumlah jawaban yang tersedia.

    Dijalankan SESUDAH semua giliran disatukan, bukan di dalam tiap
    giliran. Pertanyaan dan jawabannya sering jatuh di giliran yang
    berbeda, dan menyeimbangkan per giliran berarti memangkas satu
    sisi hanya karena pasangannya belum dikerjakan - giliran yang
    isinya pertanyaan saja akan dipotong habis jadi nol.

    Arahnya satu, sama seperti CAPPED_BY_PAIR: yang dipangkas
    pertanyaannya, bukan jawabannya. Pertanyaan baru di atas jawaban
    lama terbaca sebagai halaman rusak; jawaban yang lebih banyak
    dari pertanyaannya tidak.
    """
    catatan: list[str] = []

    for dibatasi, pembatas in CAPPED_BY_PAIR.items():
        a = content.get(dibatasi)
        b = content.get(pembatas)

        if not a or b is None or len(a) <= len(b):
            continue

        catatan.append(
            f"{len(a)} {dibatasi} dan {len(b)} {pembatas} tidak sejajar; "
            f"dipakai {len(b)} supaya tidak ada pertanyaan baru yang "
            "berdiri di atas jawaban lama."
        )

        content[dibatasi] = a[: len(b)]

    catatan.extend(drop_broken_pairs(content))

    return catatan


# Pasangan yang harus terbit bersama atau tidak sama sekali.
#
# Bedanya dengan CAPPED_BY_PAIR: yang itu soal JUMLAH, yang ini soal
# POSISI. Jumlah boleh sama persis - tujuh pertanyaan, tujuh jawaban -
# sementara yang ke-4 di salah satu sisi kosong.
PAIRED_ROLES = (("faq_question", "faq_answer"),)


def drop_broken_pairs(content: dict) -> list[str]:
    """
    Mengosongkan pasangan yang salah satu sisinya tidak terisi.

    Ini penutup terakhir untuk cacat yang paling kelihatan di halaman
    jadi: pertanyaan lama milik brand lama berdiri di atas jawaban
    baru yang membicarakan hal lain.

    Jalan masuknya lewat posisi, bukan jumlah. Satu pertanyaan yang
    tidak terisi - karena jawabannya dari model kepanjangan untuk
    slotnya, lalu dua kali diminta ulang dan tetap kepanjangan -
    membuat slot itu terbit dengan kalimat asli template. Jumlah
    pertanyaan dan jawaban tetap sama, jadi penyeimbang di atas tidak
    melihat apa-apa; yang berubah cuma bahwa jawaban ke-4 sekarang
    menjawab pertanyaan yang tidak pernah ditulis.

    Yang benar di situ adalah membiarkan SATU kartu memakai teks asli
    template seutuhnya - pertanyaan lama dengan jawaban lama, nyambung
    meski bukan tentang brand baru - daripada menerbitkan pasangan
    yang saling tidak kenal.
    """
    catatan: list[str] = []

    for kiri, kanan in PAIRED_ROLES:
        a = content.get(kiri)
        b = content.get(kanan)

        if not isinstance(a, list) or not isinstance(b, list):
            continue

        rusak = [
            index
            for index in range(min(len(a), len(b)))
            if bool(str(a[index]).strip()) != bool(str(b[index]).strip())
        ]

        if not rusak:
            continue

        for index in rusak:
            a[index] = ""
            b[index] = ""

        catatan.append(
            f"{len(rusak)} pasang {kiri} dan {kanan} cuma terisi "
            "sebelah, jadi keduanya dilepas - pertanyaan baru di atas "
            "jawaban lama terbaca sebagai halaman rusak. Kartunya "
            "diisi ulang sebagai satu kesatuan di faq_card_edits."
        )

    return catatan


def pair_by_old_text(spec: dict, filled: dict) -> dict:
    """
    Memetakan teks lama ke penggantinya untuk peran yang berarti.

    Label menu dibagikan urut dokumen, dan itu benar selama slotnya
    berasal dari berkas yang sama dengan contoh yang dikirim ke AI.
    Landing page dan AMP tidak begitu: AMP biasanya cuma punya satu
    tautan di footer, sementara contohnya diambil dari landing yang
    punya enam. Slot pertama AMP lalu kebagian teks pertama landing,
    sehingga tautan menuju /syarat terbit bertuliskan "Promo" -
    alamatnya benar, tulisannya berbohong.

    Dengan peta ini pencocokannya lewat teks lamanya sendiri, jadi
    setiap berkas mendapat padanan yang memang untuk teks itu, tidak
    peduli urutan atau jumlah slotnya. Peta yang sama juga yang
    membagikan satu jawaban ke semua slot yang teks lamanya sama,
    sejak permintaannya dihitung per bunyi di derive_spec.
    """
    peta: dict[str, dict[str, str]] = {}

    for role, rule in spec.items():
        contoh = rule.get("samples") or []
        baru = filled.get(role) or []

        if not contoh or not baru:
            continue

        pasangan = {
            normalize(sample_text(lama)): teks
            for lama, teks in zip(contoh, baru)
            if normalize(lama) and str(teks).strip()
        }

        if pasangan:
            peta[role] = pasangan

    return peta


def generated_dates(count: int, brand: dict) -> list[dict]:
    """
    Membuat tanggal yang menurun dari hari ini.

    Tanggal yang tampil memakai kalender zona, sedangkan nilai untuk
    atribut datetime tetap masehi ISO. Menuliskan tahun Buddha di
    atribut mesin akan membuat tanggalnya terbaca 543 tahun di masa
    depan oleh mesin pencari.
    """
    region = brand.get("region", "id")
    today = datetime.now()

    return [
        {
            "text": format_date(today - timedelta(days=index * 3), region),
            "iso": iso_date(today - timedelta(days=index * 3)),
        }
        for index in range(count)
    ]


def drop_repeats(content: dict, roles=None) -> tuple[dict, int]:
    """
    Membatalkan teks yang mengulang teks lain, tepat sebelum ditulis.

    Penyaring yang sama sudah berjalan waktu jawaban model diterima,
    per giliran dan lintas giliran. Yang ini penjaga terakhir di
    titik penulisan, dan alasannya bukan kehati-hatian berlebihan
    melainkan kejadian: satu halaman terbit dengan dua kartu FAQ
    berpertanyaan sama persis - "Seberapa Pancasila Dirimu?" dua kali
    berjejer, dengan jawaban berbeda - padahal penyaring per giliran
    terbukti menolak pasangan itu waktu diuji terpisah.

    Jalur masuknya sekarang sudah ketahuan, dan bukan dari model:
    pertanyaan itu dipanen dari situs lembaga negara yang dibajak,
    lolos karena build_blueprint dulu jatuh balik memakai halaman
    kotor begitu tidak ada halaman bersih tersisa, lalu ditempelkan
    apa adanya oleh fit_content_to_spec ke slot FAQ yang dibiarkan
    kosong model. Keduanya sudah dibereskan di tempatnya
    masing-masing.

    Penyaring ini tetap dipasang. Ia menjaga hal lain - teks yang
    mengulang teks lain, dari sumber mana pun - dan titik ini tetap
    satu-satunya tempat yang pasti dilewati seluruh isi. Yang
    mengulang dikosongkan, dan slotnya jatuh ke teks asli template -
    pertanyaan lama yang tidak nyambung masih jauh lebih baik
    daripada pertanyaan yang sama dicetak dua kali.

    "roles" membatasi peran mana yang diperiksa. Dipakai supaya
    angka yang dilaporkan benar-benar tentang teks yang akan ditulis
    di tempat itu: teks blok artikel tidak pernah masuk ke slot
    template, jadi menghitungnya bersama slot membuat catatan
    "15 teks dibatalkan, slotnya memakai teks asli template" muncul
    untuk teks yang tidak punya slot sama sekali.
    """
    hasil = dict(content)
    dibatalkan = 0

    for role in roles if roles is not None else UNIQUE_ROLES:
        daftar = hasil.get(role)

        if not isinstance(daftar, list):
            continue

        terlihat: set[str] = set()
        isi_terlihat: list[set] = []
        pembuka_terlihat: list[str] = []
        bersih: list[str] = []

        for teks in daftar:
            kunci = normalize(str(teks))

            if not kunci:
                bersih.append(teks)
                continue

            pembuka = question_opener(str(teks))

            if kunci in terlihat or mirip_isinya(
                kunci,
                isi_terlihat,
                role,
                pembuka,
                pembuka_terlihat,
            ):
                bersih.append("")
                dibatalkan += 1
                continue

            terlihat.add(kunci)
            isi_terlihat.append(sidik_isi(kunci, role))
            pembuka_terlihat.append(pembuka)
            bersih.append(teks)

        hasil[role] = bersih

    return hasil, dibatalkan


# Pertanyaan sependek ini bukan pertanyaan.
#
# Bukan aturan gaya melainkan penjaga: slot pertanyaan yang sempit
# meloloskan jawaban model sependek "Aman?" atau bahkan satu huruf,
# dan kartu FAQ yang pertanyaannya satu kata tidak menanyakan apa pun.
# Kalau kena, kartunya diambil dari FAQ_BANK - yang di situ sudah
# pasti berupa pertanyaan utuh.
MIN_QUESTION_WORDS = 3
MIN_QUESTION_WIDTH = 14


def is_real_question(teks: str) -> bool:
    """
    Apakah teks ini masih terbaca sebagai pertanyaan yang utuh.

    Jumlah katanya dihitung HANYA untuk aksara yang memakai spasi.
    Bahasa Thai ditulis tanpa spasi antar kata, jadi setiap pertanyaan
    Thai - sepanjang apa pun - terhitung satu kata; dihitung dengan
    cara yang sama, seluruh pertanyaan zona Thailand akan ditolak dan
    diganti kartu cadangan, termasuk yang ditulis model dengan benar.
    """
    bersih = str(teks or "").strip()

    if display_width(bersih) < MIN_QUESTION_WIDTH:
        return False

    kata = bersih.rstrip("?？").split()

    if len(kata) < 2:
        # Satu potong tanpa spasi. Lebarnya yang menentukan, karena di
        # aksara tanpa spasi itulah satu-satunya ukuran yang ada - dan
        # ambangnya sudah lewat di baris atas. Terukur pada pertanyaan
        # Thai yang benar: "ถอนเงินใช้เวลานานไหม" 18 kolom,
        # "ฝากเงินทำอย่างไร" 14 kolom, sedangkan "สล็อต" - satu kata
        # yang bukan pertanyaan - cuma 4.
        return True

    return len(kata) >= MIN_QUESTION_WORDS


def fitting_bank_card(
    cadangan: list[tuple[str, str]],
    slot_t: dict,
    slot_j: dict,
    urutan: int,
    terpakai: set,
) -> tuple[str, str]:
    """
    Kartu cadangan pertama yang muat di slotnya TANPA dipotong.

    Dicari, bukan diambil yang nomor urutnya kebetulan sama, karena
    pertanyaan yang dipotong berhenti menanyakan apa pun. Terukur:
    "Apakah akun dan data saya aman?" yang dipaksa masuk slot 30 kolom
    terbit sebagai "Apakah akun dan data saya?" - kata kerjanya hilang,
    tanda tanyanya dipasang balik, dan hasilnya tampak utuh sekilas
    padahal tidak menanyakan apa-apa.

    "terpakai" berisi pertanyaan yang SUDAH berdiri di halaman ini,
    baik dari model maupun dari kartu cadangan sebelumnya. Tanpa itu,
    kartu cadangan bisa mengulang pertanyaan yang barusan ditulis
    model - terukur di zona Thailand: model menulis "ฝากเงินที่ NEONWIN
    ทำอย่างไร" di kartu pertama, dan kartu ketiga menambal lubangnya
    dengan kalimat yang sama persis dari bank.

    Jawabannya boleh dipotong; ia kalimat, dan kalimat sebelumnya
    tetap berdiri sendiri.
    """
    sidik = [sidik_isi(x, "faq_question") for x in terpakai]

    for langkah in range(len(cadangan)):
        tanya_bank, jawab_bank = cadangan[(urutan + langkah) % len(cadangan)]

        # Dibandingkan ISINYA, bukan hurufnya - ambang yang sama dengan
        # yang dipakai drop_repeats untuk seluruh halaman.
        #
        # Kecocokan persis tidak cukup, dan itu sudah terbukti di
        # tempat lain di berkas ini: "Bagaimana cara deposit di X?" dan
        # "Bagaimana cara melakukan deposit di X?" adalah satu
        # pertanyaan yang ditulis dua kali, dan keduanya lolos kalau
        # yang dibandingkan cuma hurufnya.
        if mirip_isinya(
            normalize(tanya_bank.rstrip("?？")),
            sidik,
            "faq_question",
        ):
            continue

        tanya = clean_line(tanya_bank, slot_t["budget"], "faq_question")

        # Tanda tanya di ujung tidak ikut dibandingkan. clean_line
        # memasangnya sendiri untuk peran ini, dan kalimat tanya bahasa
        # Thai memang ditulis tanpa tanda tanya - dibandingkan apa
        # adanya, SELURUH kartu cadangan zona Thailand tertolak sebagai
        # "berubah waktu dirapikan", dan halamannya terbit dengan
        # pertanyaan berbahasa Inggris milik template.
        if not tanya or normalize(tanya.rstrip("?？")) != normalize(
            tanya_bank.rstrip("?？")
        ):
            continue

        jawab = clean_line(jawab_bank, slot_j["budget"], "faq_answer")

        if jawab:
            return tanya, jawab

    return "", ""


def faq_windows(tanya_slot: list, jawab_slot: list) -> list:
    """
    Slot jawaban milik tiap pertanyaan, ditentukan LETAKNYA di dokumen.

    Bukan nomor urut. Nomor urut benar selama satu pertanyaan punya
    tepat satu slot jawaban, dan itu tidak selalu benar: jawaban
    panjang lazim ditulis dua paragraf, sehingga template punya lebih
    banyak slot jawaban daripada slot pertanyaan. Dipasangkan per
    nomor urut, jawaban kedua milik kartu pertama terbit di kartu
    kedua, dan seluruh sisa daftarnya bergeser - persis cacat yang
    faq_card_edits ada untuk mencegahnya.

    Yang dipakai di sini satu-satunya hubungan yang selalu benar:
    jawaban sebuah pertanyaan berdiri SESUDAH pertanyaan itu dan
    SEBELUM pertanyaan berikutnya.
    """
    hasil = []

    for urutan, slot_t in enumerate(tanya_slot):
        batas = (
            tanya_slot[urutan + 1]["start"]
            if urutan + 1 < len(tanya_slot)
            else None
        )

        milik = [
            slot
            for slot in jawab_slot
            if slot["start"] > slot_t["start"]
            and (batas is None or slot["start"] < batas)
        ]

        hasil.append((slot_t, milik))

    return hasil


def faq_card_edits(
    roles: dict,
    content: dict,
    brand: dict,
) -> tuple[list[dict], list[str]]:
    """
    Mengisi kartu FAQ sebagai satu kesatuan, bukan dua daftar terpisah.

    Ini perbaikan untuk cacat yang dilaporkan pengguna sebagai "FAQ
    banyak bug", dan sebabnya ada di cara membagikan teksnya. Selama
    pertanyaan dan jawaban dibagikan sebagai dua daftar yang berdiri
    sendiri, kartu ke-N bisa mendapat pertanyaan ke-N dari satu daftar
    dan jawaban ke-M dari daftar lain - dan tidak ada satu pun tahap
    sesudahnya yang bisa melihat bahwa keduanya tidak saling kenal.

    Dua jalan yang terukur di halaman terbit:

    1. Pertanyaan yang tidak muat di slotnya dikembalikan kosong -
       memotong pertanyaan menghasilkan pertanyaan yang rusak, jadi
       itu memang disengaja. Slot itu lalu dilewati, TAPI teks
       berikutnya di antrean maju mengisi slot berikutnya, sementara
       daftar jawaban tidak ikut bergeser.
    2. Pertanyaan kembar dikosongkan drop_repeats di titik penulisan,
       sesudah penjaga pasangan lewat.

    Keduanya menerbitkan gejala yang sama: "What Sets ASG Apart?" -
    pertanyaan milik pemilik template - berdiri di atas jawaban baru
    berbahasa Indonesia tentang slot.

    Di sini kartunya diisi berpasangan. Satu kartu mendapat pertanyaan
    dan jawaban dari nomor urut yang sama, dan kalau salah satunya
    tidak bisa dipasang, KEDUANYA diambil dari FAQ_BANK - bukan
    dibiarkan jatuh ke teks asli template, karena teks asli template
    di halaman slot berbunyi tentang sekolah dan kaus bola.
    """
    edits: list[dict] = []
    notes: list[str] = []

    tanya_slot = roles.get("faq_question") or []
    jawab_slot = roles.get("faq_answer") or []

    if not tanya_slot or not jawab_slot:
        return edits, notes

    tanya_slot = sorted(tanya_slot, key=lambda slot: slot["start"])
    jawab_slot = sorted(jawab_slot, key=lambda slot: slot["start"])

    tanya_isi = [str(x) for x in (content.get("faq_question") or [])]
    jawab_isi = [str(x) for x in (content.get("faq_answer") or [])]

    cadangan = faq_bank_cards(brand, content.get("_keyword", ""))

    # Pertanyaan yang sudah berdiri di halaman ini, supaya kartu
    # cadangan tidak mengulang salah satunya. Diisi duluan dengan
    # SELURUH pertanyaan dari model - termasuk yang berdiri di kartu
    # yang belum dilewati - karena lubang di kartu kedua bisa saja
    # ditambal dengan kalimat yang baru akan dipakai kartu kelima.
    terpakai = {
        normalize(str(teks).rstrip("?？"))
        for teks in tanya_isi
        if str(teks).strip()
    }

    # Pertanyaan yang sudah terbit di HALAMAN LAIN ikut dihitung
    # terpakai.
    #
    # Bank pertanyaannya digilir dari nama brand, dan nama brand tidak
    # berubah antar halaman - jadi tanpa daftar ini halaman kedua untuk
    # brand yang sama menambal lubang FAQ-nya dengan pertanyaan yang
    # sama persis, di urutan yang sama pula. Pengguna menyebutnya
    # "topik yang udah dipakai jangan dipakai lagi".
    terpakai.update(
        normalize(str(teks).rstrip("?？"))
        for teks in (content.get("_faq_lama") or [])
        if str(teks).strip()
    )

    ditambal = 0

    # Nomor slot jawaban yang sudah terpakai, karena satu kartu bisa
    # punya lebih dari satu slot jawaban dan daftarnya dibagikan urut.
    ambil_jawab = 0

    for urutan, (slot_t, milik) in enumerate(
        faq_windows(tanya_slot, jawab_slot)
    ):
        if not milik:
            # Pertanyaan tanpa slot jawaban di bawahnya. Tidak ada
            # kartu yang bisa dijaga keutuhannya di sini, jadi
            # dilewati - slotnya memakai teks asli template.
            continue

        slot_j = milik[0]

        tanya = clean_line(
            tanya_isi[urutan] if urutan < len(tanya_isi) else "",
            slot_t["budget"],
            "faq_question",
        )

        jawab = clean_line(
            jawab_isi[ambil_jawab] if ambil_jawab < len(jawab_isi) else "",
            slot_j["budget"],
            "faq_answer",
        )

        if copies_sample(tanya, slot_t["current"], "faq_question"):
            tanya = ""

        if copies_sample(jawab, slot_j["current"], "faq_answer"):
            jawab = ""

        if not is_real_question(tanya):
            tanya = ""

        # Satu sisi kosong berarti kartu ini tidak punya pasangan yang
        # saling menjawab. Yang dipakai kartu cadangan UTUH - dua sisi
        # sekaligus - supaya yang terbaca tetap tanya-jawab, bukan
        # pertanyaan baru di atas jawaban lama.
        if not tanya or not jawab:
            tanya, jawab = fitting_bank_card(
                cadangan,
                slot_t,
                slot_j,
                urutan,
                terpakai,
            )

            if not tanya or not jawab:
                # Slot yang bahkan kartu cadangannya tidak muat
                # dibiarkan apa adanya, dua-duanya, supaya tidak ada
                # sisi yang berganti sendirian.
                continue

            ditambal += 1

        terpakai.add(normalize(tanya.rstrip("?？")))
        ambil_jawab += 1

        edits.append({**slot_t, "text": tanya})
        edits.append({**slot_j, "text": jawab})

        # Slot jawaban tambahan di kartu yang sama - paragraf kedua
        # dari satu jawaban - kebagian teks berikutnya di antrean.
        # Kartunya tetap utuh: yang menentukan pasangannya adalah slot
        # jawaban PERTAMA di jendela ini, dan itu sudah terisi.
        for lanjutan in milik[1:]:
            teks = clean_line(
                jawab_isi[ambil_jawab] if ambil_jawab < len(jawab_isi) else "",
                lanjutan["budget"],
                "faq_answer",
            )

            if not teks or copies_sample(
                teks, lanjutan["current"], "faq_answer"
            ):
                continue

            ambil_jawab += 1
            edits.append({**lanjutan, "text": teks})

    if ditambal:
        notes.append(
            f"{ditambal} kartu FAQ tidak terjawab model dan diisi "
            "tanya-jawab seputar slot yang ditulis NEIIU, supaya "
            "pertanyaan milik pemilik template tidak ikut terbit."
        )

    if len(jawab_slot) != len(tanya_slot):
        notes.append(
            f"Template punya {len(tanya_slot)} tempat pertanyaan dan "
            f"{len(jawab_slot)} tempat jawaban; pasangannya ditentukan "
            "letak di dokumen, bukan nomor urut."
        )

    return edits, notes


def build_edits(
    slot_map: dict,
    content: dict,
    brand: dict,
) -> tuple[list[dict], list[str]]:
    """
    Memasangkan isi baru ke slot yang sesuai.
    """
    edits: list[dict] = []
    notes: list[str] = []

    content, kembar = drop_repeats(
        content,
        [role for role in UNIQUE_ROLES if role in slot_map["roles"]],
    )

    if kembar:
        notes.append(
            f"{kembar} teks yang mengulang isi teks lain di halaman ini "
            "dibatalkan, slotnya memakai teks asli template."
        )

    # Pasangan diperiksa LAGI di sini, sesudah drop_repeats.
    #
    # Ini bug yang dilaporkan pengguna sebagai "FAQ banyak bug", dan
    # inilah jalan masuknya. drop_broken_pairs sudah berjalan waktu
    # jawaban model diterima, jadi waktu itu pasangannya memang utuh.
    # Yang memutuskannya justru baris di ATAS: pertanyaan kembar
    # dikosongkan di sini, di titik penulisan, sesudah penjaga pasangan
    # lewat - dan jawabannya, yang tidak kembar, tetap ditulis.
    #
    # Yang terbit persis seperti yang dilaporkan. Halaman WAYANGPLAY
    # menerbitkan tujuh kartu FAQ, tiga di antaranya masih berbunyi
    # "What Sets ASG Apart?" dan "Why Study at ASG??" - pertanyaan
    # milik template - dengan jawaban baru berbahasa Indonesia tentang
    # RTP di bawahnya. Lebih buruk lagi, karena yang kosong cuma sisi
    # pertanyaan, SELURUH sisa daftarnya bergeser: pertanyaan tentang
    # pembaruan tiap jam terbit di atas jawaban tentang cara memilih
    # slot.
    #
    # Diperiksa ulang di sini, kartu yang pertanyaannya batal ikut
    # mengosongkan jawabannya, dan kartu itu ditambal utuh oleh
    # faq_card_edits di bawah.
    for catatan in drop_broken_pairs(content):
        notes.append(catatan)

    roles = slot_map["roles"]

    # Kartu FAQ diisi berpasangan, di luar antrean per peran di bawah.
    # Alasannya di faq_card_edits.
    faq_edits, faq_notes = faq_card_edits(roles, content, brand)

    edits.extend(faq_edits)
    notes.extend(faq_notes)

    # Hanya template yang punya KEDUA sisinya yang dikeluarkan dari
    # antrean biasa. Template yang cuma punya sisi pertanyaan - blok
    # tanya-jawab yang jawabannya dimuat lewat skrip, misalnya - tidak
    # punya pasangan yang bisa dijaga, dan mengeluarkannya dari antrean
    # berarti slotnya tidak diisi siapa pun.
    berpasangan = bool(roles.get("faq_question")) and bool(
        roles.get("faq_answer")
    )

    for role, slots in roles.items():
        if berpasangan and role in ("faq_question", "faq_answer"):
            continue

        if role == "lang":
            for slot in slots:
                edits.append(
                    {**slot, "text": brand.get("html_lang", "id")}
                )

            continue

        if role == "brand":
            # Tulisan logo dan nama situs: diisi nama brand baru apa
            # adanya, tidak diminta ke AI dan tidak dipotong batas
            # panjang. Nama brand yang terpotong lebih buruk daripada
            # header yang sedikit lebih lebar.
            nama = str(brand.get("site_name", "")).strip()

            if nama:
                for slot in slots:
                    edits.append({**slot, "text": nama})

            continue

        if role == "review_author":
            # Nama pengulas diambil dari daftar zona, sama seperti
            # nama kota, dan alasannya sama: yang diminta ke model
            # tidak pernah benar-benar berganti. Penjelasannya di
            # PERSON_NAMES (utils/region.py).
            #
            # Titik awalnya diturunkan dari nama brand supaya dua
            # halaman berbeda tidak terbit dengan lima pengulas yang
            # sama persis, dan tetap sama tiap kali halaman yang sama
            # dibuat ulang.
            nama = person_names(brand.get("region", "id"))
            kota = region_cities(brand.get("region", "id"))

            benih = int.from_bytes(
                hashlib.sha1(
                    "{}|{}".format(
                        brand.get("site_name", ""),
                        brand.get("variation", ""),
                    ).encode("utf-8")
                ).digest()[:4],
                "big",
            )

            for index, slot in enumerate(slots):
                baris = rewrite_author_line(
                    slot["current"],
                    nama[(benih + index) % len(nama)],
                    kota[(benih + index) % len(kota):]
                    + kota[: (benih + index) % len(kota)],
                )

                edits.append(
                    {
                        **slot,
                        # Jatah panjangnya dilewati dengan sengaja.
                        # Nama orang yang terpotong di tengah lebih
                        # buruk daripada baris yang beberapa kolom
                        # lebih lebar, dan panjangnya sudah dijaga
                        # dari sisi lain - bentuknya diambil dari
                        # baris lama, jadi selisihnya cuma sepanjang
                        # selisih nama.
                        "text": baris,
                    }
                )

            continue

        if role == "price":
            # Harga template ditukar ke mata uang zona, angkanya
            # dikonversi dari nilai yang memang tertulis di situ.
            # Yang tidak bisa ditukar - mata uangnya sudah benar, atau
            # angkanya tidak terbaca - dilewati, dan slotnya terbit
            # apa adanya.
            ditukar = 0

            for slot in slots:
                teks = localize_price(
                    slot["current"],
                    brand.get("region", "id"),
                )

                if teks:
                    edits.append({**slot, "text": teks})
                    ditukar += 1

            if ditukar:
                notes.append(
                    f"{ditukar} harga ditukar ke mata uang "
                    f"{brand.get('region_label', 'Indonesia')}."
                )

            continue

        if role == "city":
            # Nama kota diambil dari daftar zona, bukan dari AI.
            # Model kecil rutin mengarang kota yang tidak ada, dan
            # kota palsu di halaman yang menargetkan satu negara
            # justru merusak sinyal lokalnya.
            kota = region_cities(brand.get("region", "id"))

            for index, slot in enumerate(slots):
                edits.append(
                    {**slot, "text": kota[index % len(kota)]}
                )

            continue

        if role in GENERATED_ROLES:
            # Dikelompokkan per elemen, bukan per urutan slot. Satu
            # <time> punya dua slot sekaligus: nilai atribut datetime
            # dan teks yang terbaca di layar. Kalau dibagikan
            # berurutan, keduanya dapat tanggal berbeda, sehingga
            # mesin pencari dan pembaca melihat hari yang tidak sama
            # untuk ulasan yang sama.
            groups: dict[int, list[dict]] = {}

            for slot in slots:
                groups.setdefault(slot.get("element_index", -1), []).append(
                    slot
                )

            dates = generated_dates(len(groups), brand)

            for moment, members in zip(dates, groups.values()):
                for slot in members:
                    edits.append(
                        {
                            **slot,
                            "text": (
                                moment["iso"]
                                if slot["kind"] == "attribute"
                                else moment["text"]
                            ),
                        }
                    )

            continue

        if role == "heading":
            # Judul blok yang jenisnya sudah dikenali ditulis di sini,
            # dan slotnya dikeluarkan dari antrean di bawah supaya
            # tidak kebagian dua kali.
            tetap = [slot for slot in slots if slot.get("block")]
            slots = [slot for slot in slots if not slot.get("block")]

            for slot in tetap:
                teks = block_heading_text(
                    slot["block"],
                    brand,
                    content.get("_keyword", ""),
                )

                if teks:
                    edits.append(
                        {
                            **slot,
                            "text": clean_line(
                                teks,
                                slot["budget"],
                                role,
                            ),
                        }
                    )

        if role in LIST_ROLES:
            items = list(content.get(role, []))

            # Peran berpasangan dipotong sampai sejumlah slot
            # pasangannya. Kalau template punya 4 tempat pertanyaan
            # tapi cuma 3 tempat jawaban, mengisi keempatnya membuat
            # kartu terakhir terbit dengan pertanyaan baru di atas
            # jawaban lama - persis kesalahan yang paling sulit
            # dilihat, karena strukturnya sama sekali tidak rusak.
            pasangan = CAPPED_BY_PAIR.get(role)
            slot_pasangan = roles.get(pasangan, []) if pasangan else []

            # Batas hanya berlaku kalau pasangannya memang ada di
            # template ini. Template yang tidak punya slot pasangan
            # sama sekali bukan template yang setengah berganti; ia
            # cuma menaruh keterangan itu di tempat lain.
            if pasangan and slot_pasangan:
                muat = min(len(slots), len(slot_pasangan))

                if muat < len(slots):
                    notes.append(
                        f"Template punya {len(slots)} tempat {role} tapi "
                        f"{len(slot_pasangan)} tempat {pasangan}; diisi "
                        f"{muat} supaya tidak ada pertanyaan baru yang "
                        "berdiri di atas jawaban lama."
                    )

                slots = slots[:muat]

            # Peran yang artinya harus dipertahankan dicocokkan lewat
            # teks lamanya sendiri. Sisanya - dan slot yang teks
            # lamanya tidak ada di peta - tetap dibagikan urut
            # dokumen seperti biasa.
            peta = (content.get("_by_old") or {}).get(role, {})
            terpakai = set(peta.values())

            # Lubang kosong tidak ikut antre. Daftar isi sengaja
            # dipanjangkan sampai sejumlah slot supaya nomor urutnya
            # tetap menunjuk slot yang sama; kalau lubangnya ikut
            # dibagikan, slot yang seharusnya memakai teks aslinya
            # justru ditimpa teks kosong dan kartunya terbit hampa.
            antre = [
                teks
                for teks in items
                if str(teks).strip() and teks not in terpakai
            ]

            for slot in slots:
                # Kuncinya dipotong sama persis seperti waktu contoh
                # disusun. Tanpa itu, teks lama yang lebih panjang
                # dari batas contoh tidak pernah ketemu padanannya
                # dan jatuh ke antrean sisa - dibagikan urut dokumen,
                # persis yang mau dihindari peta ini.
                text = peta.get(normalize(sample_text(slot["current"])))

                if text is None:
                    if not antre:
                        continue

                    text = antre.pop(0)

                # Jawaban yang isinya teks lama itu sendiri dianggap
                # TIDAK menjawab.
                #
                # Peran yang teks lamanya ikut dikirim sebagai contoh
                # membuat model kecil kadang menyalinnya bulat-bulat.
                # Kalau salinan itu diterima sebagai isi, slotnya
                # tercatat "sudah terisi", dan penggantian nama brand
                # yang berjalan sesudahnya melewatinya - sehingga nama
                # pemilik template justru bertahan di tempat yang
                # tadinya pasti tertukar. Terukur di halaman jadi:
                # "FAQ OSB99" terbit utuh, dan jumlah "OSB99" di
                # halaman naik dua kali lipat dibanding run sebelumnya.
                # Awalan teks lama - nomor kartu, penanda "Tag:" -
                # ditulis kembali di sini, dan jatah panjangnya
                # disisihkan lebih dulu supaya awalannya tidak
                # mendorong ujung teksnya keluar dari kotak.
                awalan = lead_of(slot["current"]) if role in LEAD_ROLES else ""

                teks = clean_line(
                    text,
                    max(4, slot["budget"] - display_width(awalan)),
                    role,
                )

                if awalan:
                    teks = restore_lead(teks, slot["current"])

                # Diperiksa SESUDAH awalannya dipasang, bukan sebelum.
                #
                # Sebelum awalan dipasang, "Deposit QRIS 1 Detik" dan
                # "1. Deposit QRIS 1 Detik" adalah dua teks berbeda
                # dan pemeriksaan ini meloloskannya; sesudah dipasang
                # keduanya satu teks yang sama, dan itulah yang
                # benar-benar terbit di halaman.
                if not teks or copies_sample(teks, slot["current"], role):
                    continue

                edits.append({**slot, "text": teks})

            continue

        text = content.get(role, "")

        if not text:
            continue

        # Angka persen dibuang dari judul di titik penulisan juga,
        # bukan cuma waktu isinya disusun.
        #
        # Ia sudah dibuang enforce_title_shape dan
        # enforce_content_numbers, dan tetap diulang di sini dengan
        # alasan yang sama seperti drop_repeats: ini satu-satunya titik
        # yang PASTI dilewati setiap teks yang terbit, dari jalur mana
        # pun ia datang. Pengguna memintanya dengan jelas - "rtp 96,4%
        # bisa diganti rtp saja" - dan judul adalah satu-satunya teks
        # halaman yang dibaca orang sebelum memutuskan mengklik.
        if role in FIGURE_FREE_ROLES:
            text = strip_figures(text)

        for slot in slots:
            edits.append(
                {
                    **slot,
                    "text": clean_line(
                        text,
                        slot["budget"],
                        role,
                    ),
                }
            )

    used = len(edits)
    total = sum(len(items) for items in roles.values())

    if used < total:
        notes.append(
            f"{total - used} slot dibiarkan memakai teks asli template."
        )

    return edits, notes


def brand_left_in_ads(scanned: dict, html: str, old_brand: str) -> int:
    """
    Berapa kali nama brand lama muncul di dalam blok iklan.

    Yang di dalam alamat tidak dihitung, karena di situ namanya
    bagian dari URL dan memang harus tetap - mengubahnya mematikan
    tautan iklannya.
    """
    nama = str(old_brand or "").strip()

    if not nama:
        return 0

    pola = build_pattern(nama)
    jumlah = 0

    for awal, akhir in scanned.get("ads", []):
        badan = re.sub(
            r'(?i)(href|src|srcset|content|action)\s*=\s*'
            r'(["\'])[^"\']*\2',
            "",
            html[awal:akhir],
        )

        jumlah += len(pola.findall(badan))

    return jumlah


def published_content(edits: list[dict], content: dict) -> dict:
    """
    Isi seperti yang BENAR-BENAR terbit, bukan seperti yang diminta.

    Teks dari AI dipotong menyesuaikan lebar slotnya, jadi kalimat
    yang tampak di halaman bisa lebih pendek daripada kalimat yang
    dikirim. Data terstruktur harus memakai versi yang tampak itu.

    Terukur pada halaman jadi: JSON-LD memuat jawaban FAQ "...tidak
    memerlukan verifikasi tambahan untuk dimainkan." sementara yang
    terbaca di halaman berhenti di "...verifikasi tambahan". Google
    mensyaratkan teks FAQ di schema sama persis dengan teks di
    halaman; yang tidak sama diabaikan, atau lebih buruk, dianggap
    schema yang menjanjikan sesuatu yang tidak ada.

    Urutan dokumen dipakai apa adanya. Untuk peran berdaftar itu
    sama dengan urutan isi aslinya, karena slot dibagikan berurutan
    dari antrean yang sama.
    """
    urut = sorted(
        (
            item
            for item in edits
            if item.get("role") and str(item.get("text", "")).strip()
        ),
        key=lambda item: item["start"],
    )

    per_peran: dict[str, list[str]] = {}

    for item in urut:
        per_peran.setdefault(item["role"], []).append(str(item["text"]))

    hasil = dict(content)

    for peran, daftar in per_peran.items():
        if peran in LIST_ROLES:
            hasil[peran] = daftar
        else:
            # Satu kalimat bisa terbit di beberapa tempat dengan
            # lebar berbeda - judul di <title> utuh, di og:title
            # terpotong. Yang terpanjang tetap ada di halaman, jadi
            # itu yang paling aman dipakai.
            hasil[peran] = max(daftar, key=len)

    align_faq_pairs(urut, hasil)

    return hasil


def align_faq_pairs(urut: list[dict], hasil: dict) -> None:
    """
    Menyamakan pasangan FAQ di data terstruktur dengan yang di halaman.

    rewrite_faq memasang questions[N] dan answers[N] ke kartu schema
    ke-N, jadi kedua daftar itu harus sejajar satu-satu. Diratakan per
    peran seperti di atas, kesejajarannya putus begitu satu pertanyaan
    punya lebih dari satu slot jawaban - jawaban paragraf kedua milik
    kartu pertama masuk ke kartu kedua, dan seluruh sisanya bergeser.

    Google membandingkan teks FAQ di schema dengan teks yang terbaca di
    halaman; yang tidak sama diabaikan, atau lebih buruk, dianggap
    schema yang menjanjikan sesuatu yang tidak ada di halaman.

    Jawaban paragraf kedua ikut disambung ke jawaban kartunya, bukan
    dibuang: yang dibaca pembaca di kartu itu memang kedua paragrafnya.
    """
    tanya = [x for x in urut if x.get("role") == "faq_question"]
    jawab = [x for x in urut if x.get("role") == "faq_answer"]

    if not tanya or not jawab:
        return

    pasangan_tanya: list[str] = []
    pasangan_jawab: list[str] = []

    for slot_t, milik in faq_windows(tanya, jawab):
        if not milik:
            continue

        pasangan_tanya.append(str(slot_t["text"]))
        pasangan_jawab.append(
            " ".join(str(x["text"]).strip() for x in milik).strip()
        )

    if pasangan_tanya:
        hasil["faq_question"] = pasangan_tanya
        hasil["faq_answer"] = pasangan_jawab


def build_review_block(
    content: dict,
    brand: dict,
    dates: list[dict],
) -> str:
    """
    Menyusun JSON-LD Review dan AggregateRating dari isi ulasan.

    Rating tidak diminta ke AI melainkan ditetapkan di sini, supaya
    angka yang muncul di schema selalu sama dengan yang bisa
    dipertanggungjawabkan dan tidak berubah-ubah tiap run.
    """
    texts = content.get("review_text", [])
    authors = content.get("review_author", [])

    if not texts:
        return ""

    reviews = []

    for index, text in enumerate(texts):
        author = author_name(
            authors[index]
            if index < len(authors)
            else brand.get("site_name", "")
        )

        moment = dates[index] if index < len(dates) else dates[-1]

        reviews.append(
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": author},
                "datePublished": moment["iso"],
                "reviewBody": text,
                "reviewRating": {
                    "@type": "Rating",
                    "ratingValue": REVIEW_RATING,
                    "bestRating": 5,
                    "worstRating": 1,
                },
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": content.get("h1") or brand.get("site_name", ""),
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": REVIEW_RATING,
            "reviewCount": len(reviews),
            "bestRating": 5,
            "worstRating": 1,
        },
        "review": reviews,
    }

    return (
        '<script type="application/ld+json">'
        + json_for_html(payload)
        + "</script>"
    )


def review_insert_point(html: str, scanned: dict | None = None) -> int:
    """
    Mencari tempat menyisipkan blok schema.

    Ditaruh tepat sebelum </head> karena di situlah blok JSON-LD
    lazim berada, dan penyisipan di satu titik tetap membuat
    perbandingan struktur mudah dibuktikan.

    Letaknya diambil dari hasil pengurai, bukan dari mencari teks
    "</head>" di dalam dokumen. Deretan huruf itu bisa muncul di
    dalam komentar atau di dalam string milik <script> - pola yang
    justru lazim di skrip penulis widget - dan menyisipkan di situ
    menaruh JSON-LD di tempat yang tidak pernah dibaca mesin pencari
    sekaligus merusak skrip yang tidak ada hubungannya.
    """
    for marker in ("head", "body"):
        for item in (scanned or {}).get("end_tags", []):
            if item["tag"] == marker:
                return item["start"]

    return len(html)


def fill_template(
    html: str,
    content: dict,
    brand: dict,
    add_review_schema: bool = True,
    old_brand: str = "",
    is_amp: bool = False,
    assets: dict | None = None,
) -> dict:
    """
    Mengisi satu berkas template dan membuktikan strukturnya utuh.

    Melempar ValueError kalau hasilnya melanggar struktur. Template
    itu milik pengguna; menerbitkan versi yang rusak jauh lebih
    merugikan daripada gagal dengan pesan yang jelas.

    Tiga lapis, berurutan:
      1. Slot diisi teks baru dari AI.
      2. Slot yang tertinggal dibersihkan dari nama brand lama.
      3. Teks lama yang kembar disamakan dengan teks barunya.

    Lapis 2 dan 3 tidak pernah menyentuh slot yang sudah terisi di
    lapis sebelumnya, jadi tidak ada rentang yang ditulis dua kali.

    Tidak ada lapis keempat. Panjang artikel diatur jauh sebelum
    fungsi ini dipanggil, dengan melebarkan jatah slot paragraf yang
    sudah ada, jadi jumlah paragraf di halaman terbit selalu sama
    dengan jumlah paragraf di template unggahan.
    """
    scanned = scan(html)
    slot_map = build_slot_map(scanned, old_brand)

    edits, notes = build_edits(slot_map, content, brand)

    # Disalin sebelum lapis berikutnya menambah apa pun. Edit gema
    # dan edit nama brand ikut membawa "role" karena disusun dari
    # slot yang sama, dan kalau ikut terhitung, satu kalimat yang
    # kebetulan muncul dua kali di halaman akan tercatat dua kali -
    # menggeser pasangan tanya-jawab di data terstruktur satu langkah.
    edits_isi = list(edits)

    # Slot yang sudah kebagian teks baru, dikenali dari letaknya.
    sudah = {(item["start"], item["end"]): item for item in edits}

    # Gambar diganti SEBELUM lapis gema dan lapis nama brand.
    #
    # Urutannya penting. Alamat gambar sering memuat nama brand lama -
    # "assets/img/logo-osb99.png" - dan lapis nama brand menyentuh
    # setiap slot yang belum kebagian isi. Kalau gambar dikerjakan
    # belakangan, dua lapis menulis ke rentang yang sama dan seluruh
    # pengisian dibatalkan karena penggantiannya bertumpang tindih.
    gambar, tukar_gambar, catatan_gambar = asset_edits(
        scanned,
        assets or {},
        sudah,
    )

    if gambar:
        edits.extend(gambar)
        sudah.update({(x["start"], x["end"]): x for x in gambar})

    notes.extend(catatan_gambar)

    # Peta teks lama -> teks baru, dengan urutan siapa yang menang.
    #
    # Satu bunyi lama bisa dipakai beberapa slot berperan berbeda. Di
    # template pengguna, <title>, dua <meta>, dan <h1> semuanya
    # berbunyi "OSB99 - Solusi Deposit QRIS 1 Detik yang Cepat dan
    # Praktis" - dan 34 atribut alt gambar ikut berbunyi sama. Kamus
    # biasa membuat yang terakhir dibaca yang menang, dan itu jatuh
    # ke h1: seluruh gambar terbit beralt "TIMAH33 QRIS" sementara
    # judul barunya kalimat yang lain sama sekali.
    #
    # Urutannya dipatok di sini: teks yang bunyinya sama dengan judul
    # halaman mengikuti JUDUL, bukan heading yang kebetulan berbunyi
    # sama. Itu yang diminta pengguna, dan itu juga yang benar -
    # yang diulang di seluruh halaman memang judul halamannya.
    diganti: dict[str, str] = {}

    for peran in ECHO_PRIORITY:
        for item in edits:
            if item.get("role") != peran:
                continue

            if item.get("kind") == "attribute":
                continue

            teks = str(item.get("text", ""))

            if teks.strip():
                diganti.setdefault(normalize(item["current"]), teks)

    for item in edits:
        if item.get("kind") == "attribute":
            continue

        teks = str(item.get("text", ""))

        if teks.strip():
            diganti.setdefault(normalize(item["current"]), teks)

    # Teks kembar didahulukan atas penggantian nama. Kalimat lama
    # yang muncul dua kali - judul yang diulang di footer, misalnya -
    # harus memakai KALIMAT BARU yang sama, bukan sekadar kalimat
    # lama dengan nama brand yang ditukar. Kalau urutannya dibalik,
    # footer terbit berbunyi "DEEFGE Situs Slot Terpercaya" padahal
    # judul barunya "DEEFGE Situs Slot Resmi".
    gema, jumlah_gema = echo_edits(slot_map, sudah, diganti)

    if gema:
        edits.extend(gema)
        sudah.update({(x["start"], x["end"]): x for x in gema})

        notes.append(
            f"{jumlah_gema} teks lama yang kembar disamakan dengan "
            "teks barunya."
        )

    tambahan, jumlah_brand = brand_edits(
        slot_map,
        sudah,
        old_brand,
        brand.get("site_name", ""),
    )

    if tambahan:
        edits.extend(tambahan)
        sudah.update({(x["start"], x["end"]): x for x in tambahan})

        notes.append(
            f"Nama brand lama '{old_brand}' diganti di "
            f"{jumlah_brand} tempat yang tidak kebagian teks baru."
        )

    # Harga yang tertinggal ikut pindah zona, dengan alasan yang sama
    # seperti nama brand di atas: slot yang dilewati dilewati karena
    # "belum tentu ini isi artikel", bukan karena isinya boleh tetap
    # milik toko asal template. Halaman berbahasa Indonesia yang
    # tabelnya berharga euro terbaca sebagai halaman yang tulisannya
    # ditimpa, dan pengguna sudah menyatakan harga boleh diubah.
    harga, jumlah_harga = price_edits(
        slot_map,
        sudah,
        brand.get("region", "id"),
    )

    if harga:
        edits.extend(harga)
        sudah.update({(x["start"], x["end"]): x for x in harga})

        notes.append(
            f"{jumlah_harga} harga yang tertinggal ditukar ke mata uang "
            f"{brand.get('region_label', 'Indonesia')}."
        )

    # Data terstruktur ditulis ulang dari isi yang sama dengan yang
    # terbit di halaman. Tanpa ini, rich result di Google menampilkan
    # pertanyaan, ulasan, dan nama brand milik template lama meskipun
    # seluruh teks yang tampak sudah berganti.
    tanggal = generated_dates(
        max(len(content.get("review_text", [])), 8),
        brand,
    )

    terbit = published_content(edits_isi, content)

    schema, jumlah_schema = jsonld_edits(
        scanned,
        html,
        terbit,
        brand,
        tanggal,
        old_brand,
        assets or {},
    )

    if schema:
        edits.extend(schema)
        sudah.update({(x["start"], x["end"]): x for x in schema})

        notes.append(
            f"Data terstruktur diperbarui: {jumlah_schema} nilai di "
            "JSON-LD ikut memakai isi baru."
        )

    # Teks yang tertanam di dalam skrip. Blok konfigurasi milik
    # template menimpakan judulnya sendiri ke halaman saat dibuka,
    # jadi judul yang sudah diganti akan kembali ke judul lama di
    # layar pengunjung kalau blok itu dibiarkan.
    tertanam, jumlah_tertanam = script_edits(
        scanned,
        html,
        diganti,
        old_brand,
        brand.get("site_name", ""),
        content,
    )

    if tertanam:
        edits.extend(tertanam)
        sudah.update({(x["start"], x["end"]): x for x in tertanam})

        notes.append(
            f"{jumlah_tertanam} teks yang tertanam di dalam skrip ikut "
            "diperbarui, termasuk judul yang ditimpakan saat halaman "
            "dibuka."
        )

    # Nama brand lama yang ikut tertulis di dalam teks BARU.
    #
    # Lapis penggantian nama di atas hanya menyentuh slot yang tidak
    # kebagian teks baru. Tapi nama lama juga bisa masuk lewat pintu
    # lain: model melihat teks lama sebagai contoh, lalu menyalin
    # namanya ke kalimat yang ditulisnya. Teks seperti itu lolos dari
    # seluruh lapis - dia terhitung "sudah terisi", jadi tidak pernah
    # diperiksa lagi.
    #
    # Terukur di halaman jadi: "Tentang OSB99" terbit di atas judul
    # SEO, satu-satunya sisa nama lama yang terlihat pembaca di
    # halaman yang selebihnya sudah berganti nama seluruhnya.
    pola_brand = build_pattern(old_brand)
    nama_baru = str(brand.get("site_name", "")).strip()
    ditimpa = 0

    dirapikan = 0

    if pola_brand and nama_baru:
        for item in edits:
            teks = str(item.get("text", ""))
            ganti = swap_brand(teks, pola_brand, nama_baru)

            if ganti != teks:
                item["text"] = ganti
                ditimpa += 1

    if nama_baru:
        for item in edits:
            teks = str(item.get("text", ""))
            rapi = collapse_repeats(teks, nama_baru)

            if rapi != teks:
                item["text"] = rapi
                dirapikan += 1

    if dirapikan:
        notes.append(
            f"Nama '{nama_baru}' tertulis dua kali berturut-turut di "
            f"{dirapikan} teks dan dirapikan."
        )

    if ditimpa:
        notes.append(
            f"Nama '{old_brand}' ikut tertulis di {ditimpa} teks baru "
            "dan diganti."
        )

    # Nama brand lama yang tertinggal di dalam blok iklan. Isi iklan
    # sengaja tidak pernah disentuh, jadi ini bukan sesuatu yang bisa
    # diperbaiki sendiri - tapi mendiamkannya membuat halaman terbit
    # dengan alt="Banner OSB99" di tengah halaman yang seluruhnya
    # sudah bernama lain, tanpa ada yang tahu.
    sisa_iklan = brand_left_in_ads(scanned, html, old_brand)

    if sisa_iklan:
        notes.append(
            f"Nama '{old_brand}' masih ada di {sisa_iklan} tempat di "
            "dalam blok iklan. Isi iklan tidak pernah diubah, jadi "
            "kalau itu bukan iklan pihak lain, gantilah sendiri di "
            "templatenya."
        )

    if slot_map["unquoted"]:
        notes.append(
            f"{len(slot_map['unquoted'])} atribut ditulis tanpa tanda "
            "kutip di template, jadi dibiarkan apa adanya: "
            + ", ".join(sorted(set(slot_map["unquoted"]))[:5])
        )

    # Diperiksa dari edits_isi, bukan edits. Penggantian gambar tidak
    # membuktikan apa pun tentang AI: template yang logonya berhasil
    # ditukar tapi seluruh teksnya gagal terisi harus tetap berhenti
    # di sini, bukan terbit dengan kalimat template lama.
    if not edits_isi:
        # Dua sebab yang sangat berbeda, dan menyebut sebab yang
        # salah membuat pengguna memperbaiki template yang sebenarnya
        # tidak ada masalahnya.
        if not slot_map["roles"]:
            raise ValueError(
                "Tidak ada satu pun slot isi yang dikenali di template "
                "ini. Pastikan templatenya memuat judul, heading, dan "
                "paragraf, atau tandai bagian yang mau diisi dengan "
                "data-neiiu."
            )

        raise ValueError(
            f"Template ini punya {sum(len(v) for v in slot_map['roles'].values())} "
            "slot yang bisa diisi, tapi AI tidak menghasilkan teks satu "
            "pun untuk mengisinya. Templatenya tidak bermasalah. "
            "Periksa apakah Ollama masih berjalan dan modelnya sanggup "
            "menjawab dalam bahasa yang diminta, lalu ulangi."
        )

    allowance: dict[str, int] = {}

    # Tidak ada satu byte pun yang disisipkan untuk artikel di sini,
    # dan itu bukan kelalaian melainkan bentuk yang diminta.
    #
    # Artikelnya terisi seluruhnya di atas, lewat slot paragraf milik
    # template, di tempat yang memang disediakan untuk itu. Panjangnya
    # diatur dengan melebarkan JATAH slot-slot itu sebelum permintaan
    # dikirim ke model - lihat generators/article_block.py - sehingga
    # jumlah paragraf di halaman terbit persis sama dengan jumlah
    # paragraf di template unggahan, berapa pun targetnya.
    #
    # Dua bentuk sebelumnya ditolak pengguna: satu <section> utuh
    # sebelum </main> ("artikelnya 1 aja"), lalu lanjutan <h2> dan <p>
    # polos di dalam blok yang sama ("bukan menambah paragraf baru
    # tetapi memperpanjang isi paragraf yang sudah ada").

    # Blok ulasan sendiri hanya ditambahkan kalau template belum punya.
    # Template yang sudah membawa Product beserta aggregateRating akan
    # berakhir dengan DUA klaim rating yang berbeda di satu halaman,
    # dan mesin pencari melihatnya sebagai data yang bertentangan -
    # lebih buruk daripada tidak menambahkan apa pun. Yang sudah ada
    # tetap terisi ulasan baru lewat jsonld_edits di atas.
    sudah_punya = has_reviews(scanned, html)

    if sudah_punya:
        notes.append(
            "Template sudah punya data ulasan sendiri, jadi isinya "
            "diperbarui di tempat - bukan ditambah blok kedua."
        )

    # Ulasan hanya boleh diklaim di schema kalau ulasannya memang
    # terbaca di halaman. Terukur pada AMP milik pengguna: berkasnya
    # tidak punya satu pun tempat ulasan - tidak ada kata "ulasan",
    # "review", atau "testimoni" di seluruh teksnya - tapi tetap
    # kebagian blok schema berisi lima ulasan. Itu persis yang
    # dilarang Google: rich result bintang untuk ulasan yang tidak
    # ada di halaman, dan hukumannya tindakan manual untuk seluruh
    # situs, bukan cuma halaman itu.
    tampil_ulasan = bool(slot_map["roles"].get("review_text"))

    boleh_tambah = (
        add_review_schema
        and bool(content.get("review_text"))
        and not sudah_punya
    )

    if boleh_tambah and not tampil_ulasan:
        notes.append(
            "Blok schema Review tidak ditambahkan: halaman ini tidak "
            "menampilkan ulasan, dan schema ulasan untuk teks yang "
            "tidak terlihat melanggar aturan Google."
        )

    if boleh_tambah and tampil_ulasan:
        block = build_review_block(
            terbit,
            brand,
            generated_dates(len(content["review_text"]), brand),
        )

        if block:
            position = review_insert_point(html, scanned)

            # Rentang kosong: tidak ada teks lama yang dibuang,
            # hanya disisipkan di satu titik.
            edits.append(
                {
                    "kind": "raw",
                    "start": position,
                    "end": position,
                    "text": block,
                }
            )

            allowance["script"] = 1
            notes.append(
                f"Blok schema Review ditambahkan untuk "
                f"{len(terbit.get('review_text', []))} ulasan yang "
                "terbaca di halaman."
            )

    filled = apply_edits(html, edits)

    check = verify(html, filled, edits, allowance, tukar_gambar)

    if not check["ok"]:
        raise ValueError(
            "Hasil pengisian mengubah struktur template: "
            + "; ".join(check["violations"][:3])
        )

    return {
        "html": filled,
        "edits": len(edits),
        "slot_counts": slot_map["counts"],
        "skipped": len(slot_map["skipped"]),
        "notes": notes,
        "stats": check["stats"],
    }
