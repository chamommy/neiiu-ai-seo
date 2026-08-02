"""
Deteksi cloaking dan domain bajakan di hasil pencarian.

Banyak halaman spam menumpang di domain institusi yang sudah
dipercaya Google — kampus, kementerian, jurnal, yayasan. Halaman
itu melakukan cloaking: pengunjung biasa dilayani halaman asli
milik institusinya, sedangkan Googlebot dilayani halaman spam yang
kemudian diindeks dan ngerank.

Akibatnya untuk pipeline ini ada dua:

1. Crawler dengan User-Agent biasa membaca halaman institusinya,
   bukan halaman yang benar-benar ngerank. Blueprint jadi tersusun
   dari konten yang salah.
2. Halaman itu ngerank karena otoritas domain curian, bukan karena
   struktur halamannya. Menirunya tidak ada gunanya.

Modul ini mengambil kedua versi halaman, membandingkannya, lalu
menilai apakah halaman itu layak dijadikan acuan.
"""

import re
from urllib.parse import urlparse

from config import (
    GOOGLEBOT_USER_AGENT,
    HIJACK_MIN_CONFIDENCE,
    USER_AGENT,
)
from crawler.crawler import fetch_page
from parser.html_parser import parse_html


# Domain institusi yang otoritasnya sering dibajak.
INSTITUTIONAL_SUFFIXES = (
    ".go.id", ".ac.id", ".sch.id", ".mil.id", ".desa.id",
    ".kab.go.id", ".kota.go.id", ".or.id", ".ponpes.id",
    ".gov", ".edu", ".mil", ".int",
    ".gov.uk", ".ac.uk", ".edu.au", ".gov.au", ".edu.my",
    ".go.th", ".ac.th", ".edu.ph", ".gov.ph", ".edu.sg",
)

# Domain organisasi yang juga sering jadi sasaran.
NGO_SUFFIXES = (".org", ".ngo", ".foundation")


def registrable_parts(host: str) -> tuple[str, str]:
    """
    Memisahkan subdomain dari nama domain utamanya.

    Pemisahan ini disederhanakan: cukup untuk membedakan
    "slot" dari "gasrestaurant" pada slot.gasrestaurant.com,
    bukan implementasi public suffix list yang lengkap.
    """
    host = host.lower().strip(".")
    labels = host.split(".")

    if len(labels) <= 2:
        return "", host

    # Domain bertingkat seperti co.id, ac.id, go.id, co.uk.
    if len(labels[-2]) <= 3 and len(labels[-1]) <= 3:
        root = ".".join(labels[-3:])
        subdomain = ".".join(labels[:-3])
    else:
        root = ".".join(labels[-2:])
        subdomain = ".".join(labels[:-2])

    return subdomain, root


def is_institutional(host: str) -> bool:
    host = host.lower()

    return any(
        host.endswith(suffix) for suffix in INSTITUTIONAL_SUFFIXES
    )


def keyword_tokens(keyword: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", keyword.lower())
        if len(token) >= 3
    ]


def count_keyword(text: str, keyword: str) -> int:
    return text.lower().count(keyword.lower())


def word_set(text: str, limit: int = 4000) -> set[str]:
    return set(
        re.findall(r"[a-z]{4,}", text.lower())[:limit]
    )


def similarity(text_a: str, text_b: str) -> float:
    """
    Kemiripan dua halaman berdasarkan irisan kosakatanya.

    Dipakai Jaccard, bukan diff karakter, supaya perbedaan kecil
    seperti tanggal atau nomor sesi tidak dianggap perubahan besar,
    sementara pergantian topik total tetap terbaca jelas.
    """
    set_a = word_set(text_a)
    set_b = word_set(text_b)

    if not set_a and not set_b:
        return 1.0

    union = set_a | set_b

    if not union:
        return 1.0

    return len(set_a & set_b) / len(union)


def fetch_both_versions(url: str) -> dict:
    """
    Mengambil satu URL dua kali: sebagai browser dan sebagai Googlebot.
    """
    result = {
        "normal": None,
        "googlebot": None,
        "normal_error": "",
        "googlebot_error": "",
    }

    try:
        result["normal"] = fetch_page(url, user_agent=USER_AGENT)
    except Exception as error:
        result["normal_error"] = f"{type(error).__name__}: {error}"

    try:
        result["googlebot"] = fetch_page(
            url,
            user_agent=GOOGLEBOT_USER_AGENT,
        )
    except Exception as error:
        result["googlebot_error"] = f"{type(error).__name__}: {error}"

    return result


def compare_versions(
    normal_page: dict | None,
    bot_page: dict | None,
    keyword: str,
) -> dict:
    """
    Membandingkan versi browser dan versi Googlebot dari satu halaman.
    """
    if normal_page is None or bot_page is None:
        # Sebagian situs menolak salah satu User-Agent. Perbandingan
        # jadi mustahil, tapi ini dicatat supaya tidak terbaca sebagai
        # "sudah diperiksa dan bersih".
        return {
            "checked": False,
            "reason_unchecked": (
                "versi Googlebot gagal diambil"
                if bot_page is None
                else "versi pengunjung biasa gagal diambil"
            ),
            "normal_ok": normal_page is not None,
            "googlebot_ok": bot_page is not None,
            "cloaking": False,
            "similarity": None,
            "title_changed": False,
            "keyword_normal": 0,
            "keyword_googlebot": 0,
            "words_normal": (
                normal_page["word_count"] if normal_page else 0
            ),
            "words_googlebot": (
                bot_page["word_count"] if bot_page else 0
            ),
        }

    text_normal = normal_page["visible_text"]
    text_bot = bot_page["visible_text"]

    ratio = similarity(text_normal, text_bot)

    keyword_normal = count_keyword(text_normal, keyword)
    keyword_bot = count_keyword(text_bot, keyword)

    title_changed = (
        normal_page["title"].strip().lower()
        != bot_page["title"].strip().lower()
    )

    # Cloaking disimpulkan kalau isinya berbeda jauh, atau kalau
    # keyword hanya muncul di versi yang dilihat Googlebot.
    keyword_only_for_bot = (
        keyword_bot >= 3 and keyword_normal == 0
    )

    cloaking = (
        ratio < 0.45
        or keyword_only_for_bot
        or (title_changed and ratio < 0.7)
    )

    return {
        "checked": True,
        "normal_ok": True,
        "googlebot_ok": True,
        "cloaking": bool(cloaking),
        "similarity": round(ratio, 3),
        "title_changed": title_changed,
        "keyword_normal": keyword_normal,
        "keyword_googlebot": keyword_bot,
        "keyword_only_for_bot": keyword_only_for_bot,
        "words_normal": normal_page["word_count"],
        "words_googlebot": bot_page["word_count"],
        "title_normal": normal_page["title"][:120],
        "title_googlebot": bot_page["title"][:120],
    }


def is_parasite_subdomain(
    host: str,
    keyword: str,
) -> tuple[bool, str, str]:
    """
    Mengecek pola subdomain yang namanya memuat keyword sementara
    domain induknya tidak berkaitan.
    """
    subdomain, root = registrable_parts(host)
    tokens = keyword_tokens(keyword)

    if not subdomain or not tokens:
        return False, subdomain, root

    sub_hit = any(token in subdomain for token in tokens)
    root_hit = any(token in root for token in tokens)

    return (sub_hit and not root_hit), subdomain, root


def check_root_domain(
    root: str,
    keyword: str,
) -> dict:
    """
    Memeriksa halaman depan domain induk.

    Ini yang memisahkan parasit dari subdomain yang sah. Pola
    "slot.gasrestaurant.com" dan "slot.pragmaticplay.com" identik
    kalau dilihat dari namanya saja. Bedanya baru kelihatan di
    domain induknya: yang satu jualan makanan dan tidak tahu-menahu
    soal keyword ini, yang satu memang bergerak di bidangnya.
    """
    result = {
        "checked": False,
        "keyword_hits": 0,
        "words": 0,
        "error": "",
    }

    for scheme in ("https", "http"):
        try:
            crawl = fetch_page(
                f"{scheme}://{root}/",
                user_agent=USER_AGENT,
            )

            page = parse_html(crawl["html"], crawl["final_url"])

            result["checked"] = True
            result["words"] = page["word_count"]
            result["keyword_hits"] = count_keyword(
                page["visible_text"],
                keyword,
            )

            return result

        except Exception as error:
            result["error"] = f"{type(error).__name__}: {error}"

    return result


def detect_hijack(
    url: str,
    keyword: str,
    comparison: dict,
    indexed_page: dict | None,
    root_check: dict | None = None,
) -> dict:
    """
    Menilai apakah satu hasil SERP berdiri di atas domain bajakan.

    Skor dijumlahkan dari beberapa sinyal supaya satu sinyal saja
    tidak langsung menjatuhkan vonis. Halaman kampus yang memang
    membahas topiknya tidak akan lolos ambang hanya karena
    domainnya .ac.id.
    """
    host = urlparse(url).netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    subdomain, root = registrable_parts(host)
    tokens = keyword_tokens(keyword)

    score = 0
    reasons: list[str] = []
    evidence = False

    institutional = is_institutional(host)

    # Density dihitung dari halaman yang benar-benar diindeks, lepas
    # dari berhasil tidaknya pembandingan dua versi. Sebagian situs
    # menolak salah satu User-Agent, dan tanpa ini halaman parasit di
    # domain kampus lolos begitu saja hanya karena gagal dibandingkan.
    density = 0.0

    if indexed_page is not None:
        words = max(indexed_page.get("word_count", 0), 1)

        hits = count_keyword(
            indexed_page.get("visible_text", ""),
            keyword,
        )

        density = hits * max(len(tokens), 1) / words * 100

    if comparison.get("cloaking"):
        score += 50
        evidence = True
        reasons.append(
            "Isi halaman berbeda antara pengunjung biasa dan Googlebot "
            f"(kemiripan {comparison.get('similarity')})."
        )

    if comparison.get("keyword_only_for_bot"):
        score += 25
        evidence = True
        reasons.append(
            f"Keyword hanya muncul di versi Googlebot "
            f"({comparison.get('keyword_googlebot')} kali), "
            "tidak ada di versi pengunjung biasa."
        )

    if institutional:
        score += 35
        reasons.append(
            f"Domain institusi ({root}), otoritasnya sering dibajak."
        )
    elif host.endswith(NGO_SUFFIXES):
        score += 15
        reasons.append(f"Domain organisasi ({root}).")

    # Subdomain yang namanya memuat keyword sementara domain
    # induknya tidak, ciri khas parasit di situs orang lain.
    parasite, _, _ = is_parasite_subdomain(host, keyword)

    if parasite:
        if root_check and root_check.get("checked"):
            root_hits = root_check.get("keyword_hits", 0)
            root_words = max(root_check.get("words", 0), 1)

            root_density = (
                root_hits * max(len(tokens), 1) / root_words * 100
            )

            if root_hits == 0:
                score += 45
                evidence = True
                reasons.append(
                    f"Subdomain '{subdomain}' dipenuhi keyword, tapi "
                    f"halaman depan '{root}' tidak menyebutnya sama "
                    "sekali. Ciri numpang di situs orang."
                )

            elif root_density >= 2.0:
                # Domain induk yang ikut dipenuhi keyword bukan bukti
                # bahwa subdomainnya sah. Justru sebaliknya: seluruh
                # domainnya sudah dikuasai spam, bukan cuma satu
                # subdomain. Bobotnya disamakan dengan kasus induk
                # bersih, karena dua-duanya sama-sama menunjukkan
                # halaman itu bukan milik pemilik domain aslinya.
                score += 45
                evidence = True
                reasons.append(
                    f"Halaman depan '{root}' juga dipenuhi keyword "
                    f"(density {round(root_density, 1)}%). Bukan cuma "
                    "subdomainnya, seluruh domain ini sudah dikuasai spam."
                )

            else:
                reasons.append(
                    f"Subdomain '{subdomain}' memuat keyword, dan "
                    f"domain induk '{root}' membahasnya secara wajar "
                    f"(density {round(root_density, 1)}%), "
                    "jadi kemungkinan besar memang miliknya."
                )
        else:
            # Domain induk tidak bisa diperiksa. Polanya tetap
            # mencurigakan, tapi bobotnya ditahan karena belum ada
            # bukti pemisah antara parasit dan subdomain yang sah.
            score += 30
            evidence = True
            reasons.append(
                f"Subdomain '{subdomain}' memuat keyword sedangkan "
                f"domain induk '{root}' tidak. Halaman depan '{root}' "
                "tidak bisa diperiksa untuk memastikan."
            )

    # Halaman institusi yang isinya dipenuhi keyword komersial adalah
    # ciri parasit, entah lewat cloaking atau lewat konten yang
    # diunggah pengguna. Ambangnya dipasang di 2.5% karena artikel
    # yang ditulis wajar jarang melewati 2%.
    if institutional and density >= 2.5:
        score += 25
        evidence = True
        reasons.append(
            f"Domain institusi dengan keyword density "
            f"{round(density, 1)}%, ciri halaman parasit."
        )

    if density > 6:
        score += 15
        reasons.append(
            f"Keyword density {round(density, 1)}%, "
            "jauh di atas wajar."
        )

    # Sinyal domain saja tidak cukup untuk memvonis. Tanpa bukti dari
    # isi halamannya, skor ditahan di bawah ambang supaya situs
    # kampus atau pemerintah yang memang membahas topiknya tidak
    # ikut tervonis hanya karena alamat domainnya.
    if not evidence:
        score = min(score, 45)

    score = min(score, 100)

    return {
        "is_hijacked": score >= HIJACK_MIN_CONFIDENCE,
        "confidence": score,
        "reasons": reasons,
        "host": host,
        "root_domain": root,
        "institutional": institutional,
    }


def inspect_url(
    url: str,
    keyword: str,
) -> dict:
    """
    Pemeriksaan lengkap satu URL: ambil dua versi, banding, nilai.

    Mengembalikan juga halaman versi Googlebot, karena versi itulah
    yang diindeks dan diberi peringkat oleh Google.
    """
    fetched = fetch_both_versions(url)

    normal_parsed = None
    bot_parsed = None

    if fetched["normal"] is not None:
        normal_parsed = parse_html(
            fetched["normal"]["html"],
            fetched["normal"]["final_url"],
        )

    if fetched["googlebot"] is not None:
        bot_parsed = parse_html(
            fetched["googlebot"]["html"],
            fetched["googlebot"]["final_url"],
        )

    comparison = compare_versions(
        normal_parsed,
        bot_parsed,
        keyword,
    )

    # Yang dianalisis adalah versi Googlebot, karena itu yang
    # diindeks. Kalau gagal diambil, pakai versi biasa.
    indexed = fetched["googlebot"] or fetched["normal"]
    indexed_parsed = bot_parsed or normal_parsed

    # Domain induk hanya diperiksa kalau polanya memang mencurigakan,
    # supaya tidak ada request tambahan untuk halaman biasa.
    host = urlparse(url).netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    parasite, _, root = is_parasite_subdomain(host, keyword)

    root_check = (
        check_root_domain(root, keyword) if parasite else None
    )

    hijack = detect_hijack(
        url=url,
        keyword=keyword,
        comparison=comparison,
        indexed_page=indexed_parsed,
        root_check=root_check,
    )

    return {
        "fetched": fetched,
        "indexed_crawl": indexed,
        "indexed_page": indexed_parsed,
        "comparison": comparison,
        "root_check": root_check,
        "hijack": hijack,
    }
