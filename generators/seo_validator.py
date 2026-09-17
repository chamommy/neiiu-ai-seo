"""
Pemeriksa kualitas SEO halaman hasil generate.

Halaman baru diukur terhadap blueprint SERP, bukan terhadap
patokan umum. Standar "cukup panjang" untuk satu keyword bisa
jauh berbeda dari keyword lain, jadi acuannya diambil dari
halaman yang sedang menang di keyword itu sendiri.
"""

import json
import re

from ai.schemas import META_MAX, META_MIN, TITLE_MAX, TITLE_MIN
from parser.html_parser import parse_html


# Blok data terstruktur beserta isinya, dipetik apa adanya dari HTML.
JSONLD_BLOCK = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>'
    r"(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Perintah yang menahan halaman ini keluar dari indeks.
BLOCKING_ROBOTS = re.compile(r"\bno(?:index|follow)\b", re.IGNORECASE)


def check_crawl(html: str, page: dict, problems: list, passed: list) -> None:
    """
    Pemeriksaan yang menentukan halaman ini terbaca mesin atau tidak.

    Dipisah dari pemeriksaan isi karena beda akibatnya. Title yang
    kependekan membuat halaman kalah bersaing; noindex membuatnya
    tidak ikut bersaing sama sekali, dan satu kata itu membatalkan
    seluruh isi yang ditulis di atasnya.
    """
    robots = page.get("robots_meta", "")

    if BLOCKING_ROBOTS.search(robots):
        problems.append(
            f'Meta robots berisi "{robots}", jadi halaman ini tidak '
            "akan diindeks. Hapus noindex/nofollow sebelum diunggah."
        )
    else:
        passed.append("Meta robots tidak menahan halaman dari indeks.")

    # Bahasa halaman. Tanpa lang, mesin pencari menebaknya sendiri,
    # dan halaman berbahasa Indonesia rutin ditebak Melayu - cukup
    # untuk membuatnya disajikan ke negara yang salah.
    if re.search(r"<html[^>]+\blang\s*=\s*[\"'][^\"']+", html, re.I):
        passed.append("Atribut lang terpasang di <html>.")
    else:
        problems.append("Atribut lang belum ada di <html>.")

    # Data terstruktur yang tidak bisa diurai sama saja dengan tidak
    # ada. Diperiksa dengan mengurai sungguhan, bukan dengan mencari
    # kata "ld+json" di HTML: blok yang koma penutupnya berlebih tetap
    # lolos pencarian kata, dan tetap dibuang Google tanpa pesan
    # apa pun.
    blok = JSONLD_BLOCK.findall(html)
    rusak = 0

    for isi in blok:
        try:
            json.loads(isi)
        except (ValueError, TypeError):
            rusak += 1

    if not blok:
        problems.append("Structured data belum terpasang.")
    elif rusak:
        problems.append(
            f"{rusak} dari {len(blok)} blok structured data tidak bisa "
            "diurai, jadi tidak akan dibaca mesin pencari."
        )
    else:
        passed.append(
            f"{len(blok)} blok structured data terpasang dan sah."
        )


def check_length(
    label: str,
    value: int,
    minimum: int,
    maximum: int,
    problems: list[str],
) -> None:
    if value < minimum:
        problems.append(
            f"{label} terlalu pendek ({value}, minimal {minimum})."
        )
    elif value > maximum:
        problems.append(
            f"{label} terlalu panjang ({value}, maksimal {maximum})."
        )


def check_head_pair(
    page: dict,
    amp_html: str,
    amp_url: str,
    brand_name: str,
    problems: list[str],
    passed: list[str],
) -> None:
    """
    Memeriksa dua hal yang cuma kelihatan kalau kedua berkas diadu.

    Pertama, nama situs di title. Bentuk judul yang diminta pengguna
    menaruhnya paling depan, dan itu ditegakkan enforce_title_shape -
    tapi penegak itu punya jalan keluar (judul yang jatahnya hampir
    habis dipakai nama situsnya sendiri terbit apa adanya), dan tidak
    ada satu pun lapisan sesudahnya yang mengatakan kalau itu terjadi.

    Kedua, title dan deskripsi halaman AMP. Keduanya diisi dari isi
    yang sama dengan halaman landing, jadi dua teks yang berbeda
    berarti salah satunya tidak kebagian - dan yang terbit di
    tempatnya kalimat pemilik template.

    Terukur pada halaman yang benar-benar terbit 16 Agustus 2026:

      landing : Cara Akses Slot Gacor di HP dengan Link Resmi
      AMP     : WAYANGPLAY - Solusi Deposit QRIS yang Cepat dan Praktis

    Yang pertama 44 karakter dan tidak menyebut nama situs sama
    sekali; yang kedua judul milik template dengan nama brandnya saja
    yang tertukar - "Solusi Deposit QRIS ... yang Cepat dan Praktis"
    adalah kalimat pemilik template, dan keywordnya tidak ada di
    situ. Dua halaman yang seharusnya satu maksud terbit dengan dua
    judul yang tidak berhubungan, dan tidak satu pun pemeriksaan yang
    berjalan waktu itu keberatan.
    """
    judul = str(page.get("title") or "")

    nama = str(brand_name or "").strip()

    if nama:
        if re.search(re.escape(nama), judul, re.IGNORECASE):
            passed.append("Nama situs ada di title.")
        else:
            problems.append(
                f'Title tidak menyebut nama situs "{nama}". Bentuk '
                "judul yang dipakai NEIIU menaruhnya paling depan, "
                "jadi judul tanpa nama berarti penegak bentuknya "
                "menyerah - biasanya karena jatah lebar slot title "
                "di template hampir habis dipakai namanya sendiri."
            )

    if not amp_html:
        return

    amp = parse_html(amp_html, amp_url or page_url_of(page))

    pasangan = (
        ("Title", judul, str(amp.get("title") or "")),
        (
            "Meta description",
            str(page.get("meta_description") or ""),
            str(amp.get("meta_description") or ""),
        ),
    )

    for label, landing, versi_amp in pasangan:
        satu = " ".join(landing.split())
        dua = " ".join(versi_amp.split())

        if not satu or not dua:
            problems.append(
                f"{label} kosong di salah satu berkas "
                f"(landing: {len(satu)} karakter, AMP: {len(dua)})."
            )
        elif satu == dua:
            passed.append(f"{label} halaman AMP sama dengan landing.")
        else:
            problems.append(
                f"{label} halaman AMP berbeda dari halaman landing, "
                "padahal keduanya diisi dari isi yang sama. Berarti "
                "salah satu slotnya tidak kebagian teks baru dan "
                f"terbit dengan kalimat pemilik template. "
                f"Landing: \"{satu[:60]}\". AMP: \"{dua[:60]}\"."
            )


def page_url_of(page: dict) -> str:
    """
    Alamat halaman yang sudah terbaca, untuk dipakai ulang menguraikan
    berkas AMP saat alamatnya sendiri belum diketahui.
    """
    return str(page.get("canonical") or "") or "https://localhost/"


def validate_page(
    html: str,
    keyword: str,
    blueprint: dict,
    page_url: str,
    amp_html: str = "",
    amp_url: str = "",
    brand_name: str = "",
) -> dict:
    """
    Membandingkan halaman hasil generate dengan target SERP.

    Berkas AMP dan nama brand boleh tidak diberikan, dan kalau tidak
    diberikan pemeriksaannya dilewati begitu saja - pemanggil lama
    tetap mendapat laporan yang sama persis seperti sebelumnya.
    """
    page = parse_html(html, page_url)
    target = blueprint["target"]

    problems: list[str] = []
    passed: list[str] = []

    keyword_lower = keyword.lower()

    # Rentangnya diambil dari sumber yang sama dengan yang diminta ke
    # AI. Angka sendiri di sini pernah membuat pemeriksa menolak
    # halaman yang panjangnya persis seperti yang diperintahkan -
    # laporan yang menghitung keberhasilan sebagai kegagalan.
    check_length(
        "Title",
        page["title_length"],
        TITLE_MIN,
        TITLE_MAX,
        problems,
    )

    check_length(
        "Meta description",
        page["meta_description_length"],
        META_MIN,
        META_MAX,
        problems,
    )

    if keyword_lower in page["title"].lower():
        passed.append("Keyword ada di title.")
    else:
        problems.append("Keyword tidak ada di title.")

    if keyword_lower in page["meta_description"].lower():
        passed.append("Keyword ada di meta description.")
    else:
        problems.append("Keyword tidak ada di meta description.")

    h1_count = page["headings"]["h1_count"]

    if h1_count == 1:
        passed.append("Jumlah H1 tepat satu.")
    else:
        problems.append(
            f"Jumlah H1 harus satu, saat ini {h1_count}."
        )

    h1_text = " ".join(page["headings"]["h1"]).lower()

    if keyword_lower in h1_text:
        passed.append("Keyword ada di H1.")
    else:
        problems.append("Keyword tidak ada di H1.")

    word_target = int(
        max(
            target["word_count_top5_median"],
            target["word_count_median"],
        )
    )

    word_count = page["word_count"]

    if word_target and word_count < word_target * 0.8:
        problems.append(
            f"Konten {word_count} kata, target halaman pertama "
            f"sekitar {word_target} kata."
        )
    else:
        passed.append(
            f"Panjang konten {word_count} kata, "
            f"sesuai target {word_target} kata."
        )

    h2_target = int(target["h2_median"])
    h2_count = page["headings"]["h2_count"]

    if h2_target and h2_count < h2_target:
        problems.append(
            f"Jumlah H2 {h2_count}, kompetitor rata-rata {h2_target}."
        )
    else:
        passed.append(f"Jumlah H2 {h2_count}, sudah memadai.")

    text_lower = page["visible_text"].lower()
    keyword_count = text_lower.count(keyword_lower)

    density = (
        round(
            keyword_count
            * len(keyword_lower.split())
            / max(word_count, 1)
            * 100,
            2,
        )
    )

    if density > 3:
        problems.append(
            f"Keyword density {density}%, terlalu padat."
        )
    elif density < 0.5:
        problems.append(
            f"Keyword density {density}%, terlalu tipis."
        )
    else:
        passed.append(f"Keyword density {density}%, wajar.")

    if page["canonical"]:
        passed.append("Canonical terpasang.")
    else:
        problems.append("Canonical belum terpasang.")

    if re.search(
        r'<link[^>]+rel=["\']amphtml["\']',
        html,
        re.IGNORECASE,
    ):
        passed.append("Link ke versi AMP terpasang.")
    else:
        problems.append("Link rel=amphtml belum terpasang.")

    check_crawl(html, page, problems, passed)

    check_head_pair(
        page,
        amp_html,
        amp_url,
        brand_name,
        problems,
        passed,
    )

    if '"FAQPage"' in html:
        passed.append("Schema FAQPage terpasang.")
    else:
        problems.append("Schema FAQPage belum terpasang.")

    score = round(
        len(passed) / max(len(passed) + len(problems), 1) * 100
    )

    return {
        "score": score,
        "word_count": word_count,
        "word_target": word_target,
        "keyword_density": density,
        "title_length": page["title_length"],
        "meta_length": page["meta_description_length"],
        "h2_count": h2_count,
        "passed": passed,
        "problems": problems,
    }
