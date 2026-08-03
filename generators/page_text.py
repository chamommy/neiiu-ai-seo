"""
Teks tetap yang muncul di halaman hasil.

Isi halaman ditulis AI, tapi kerangkanya punya kata-kata sendiri:
menu, judul daftar isi, judul blok FAQ, dan catatan hak cipta.
Kalau ini dibiarkan berbahasa Indonesia sementara isinya berbahasa
Thai, halamannya jadi campur dua bahasa, dan Google membaca
campuran itu sebagai halaman yang bahasanya tidak jelas.

Terjemahan Thai di sini adalah istilah baku yang lazim dipakai di
situs Thailand. Kalau nanti ada penutur asli yang bisa memeriksa,
bagian ini yang perlu dilihat lebih dulu.
"""

from utils.region import DEFAULT_REGION, get_region


PAGE_TEXT: dict[str, dict[str, str]] = {
    "id": {
        "home": "Beranda",
        "faq_nav": "FAQ",
        "toc_title": "Daftar Isi",
        "toc_label": "Daftar isi",
        "faq_heading": "Pertanyaan Yang Sering Diajukan",
        "related_topics": "Topik terkait",
        "rights_reserved": "Seluruh hak cipta dilindungi.",
        "table_number": "#",
        "table_point": "Poin",
        "table_detail": "Keterangan",
        "reviews_heading": "Ulasan Pengguna",
        "rating_label": "Penilaian",
        # Label blok baru (blocks.py). Semuanya netral dan tidak
        # mengaku-ngaku apa pun soal brand, karena datanya memang
        # tidak ada di pipeline ini.
        "cta_login": "LOGIN",
        "cta_register": "DAFTAR",
        "cta_promo": "PROMO BONUS",
        "cta_alt": "LINK ALTERNATIF",
        "cta_chat": "LIVE CHAT",
        "popup_close": "Tutup",
        "menu_label": "Menu utama",
        "quick_menu_label": "Menu cepat",
        "testimoni_heading": "Testimoni Member",
        "ratings_heading": "Penilaian Layanan",
        "tags_heading": "Topik Populer",
        "out_of_5": "dari 5",
        "footer_explore": "Jelajahi",
        "footer_topics": "Topik",
        "footer_page": "Halaman Ini",
    },
    "th": {
        "home": "หน้าแรก",
        "faq_nav": "คำถามที่พบบ่อย",
        "toc_title": "สารบัญ",
        "toc_label": "สารบัญ",
        "faq_heading": "คำถามที่พบบ่อย",
        "related_topics": "หัวข้อที่เกี่ยวข้อง",
        "rights_reserved": "สงวนลิขสิทธิ์",
        "table_number": "ลำดับ",
        "table_point": "หัวข้อ",
        "table_detail": "รายละเอียด",
        "reviews_heading": "รีวิวจากผู้ใช้งาน",
        "rating_label": "คะแนน",
        "cta_login": "เข้าสู่ระบบ",
        "cta_register": "สมัครสมาชิก",
        "cta_promo": "โปรโมชั่นโบนัส",
        "cta_alt": "ลิงก์สำรอง",
        "cta_chat": "แชทสด",
        "popup_close": "ปิด",
        "menu_label": "เมนูหลัก",
        "quick_menu_label": "เมนูด่วน",
        "testimoni_heading": "รีวิวจากสมาชิก",
        "ratings_heading": "คะแนนการให้บริการ",
        "tags_heading": "หัวข้อยอดนิยม",
        "out_of_5": "จาก 5",
        "footer_explore": "สำรวจ",
        "footer_topics": "หัวข้อ",
        "footer_page": "หน้านี้",
    },
}


def page_text(region: str = DEFAULT_REGION) -> dict[str, str]:
    """
    Mengambil kamus teks tetap untuk satu zona.
    """
    code = get_region(region)["code"]

    return PAGE_TEXT.get(code, PAGE_TEXT[DEFAULT_REGION])


def text_of(brand: dict) -> dict[str, str]:
    """
    Mengambil teks tetap dari dict brand yang sudah dibawa pipeline.

    Semua generator sudah menerima brand, jadi zona ikut lewat di
    sana dan tidak perlu ditambahkan sebagai parameter baru ke
    setiap fungsi render.
    """
    return page_text(brand.get("region", DEFAULT_REGION))
