import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


OUTPUT_FILE = Path("seo_report.json")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_page(url: str) -> tuple[BeautifulSoup, requests.Response]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20,
        allow_redirects=True,
    )

    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()

    if "text/html" not in content_type:
        raise ValueError(
            f"URL bukan halaman HTML. Content-Type: {content_type}"
        )

    soup = BeautifulSoup(response.text, "html.parser")

    return soup, response


def get_meta_description(soup: BeautifulSoup) -> str:
    meta = soup.find(
        "meta",
        attrs={"name": re.compile("^description$", re.I)},
    )

    if not meta:
        return ""

    return clean_text(meta.get("content", ""))


def get_canonical(soup: BeautifulSoup, base_url: str) -> str:
    canonical = soup.find(
        "link",
        attrs={"rel": lambda value: value and "canonical" in value},
    )

    if not canonical:
        return ""

    href = canonical.get("href", "").strip()

    return urljoin(base_url, href) if href else ""


def get_robots_meta(soup: BeautifulSoup) -> str:
    robots = soup.find(
        "meta",
        attrs={"name": re.compile("^robots$", re.I)},
    )

    if not robots:
        return ""

    return clean_text(robots.get("content", ""))


def extract_visible_text(soup: BeautifulSoup) -> str:
    soup_copy = BeautifulSoup(str(soup), "html.parser")

    for tag in soup_copy(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "template",
        ]
    ):
        tag.decompose()

    return clean_text(soup_copy.get_text(" ", strip=True))


def extract_links(
    soup: BeautifulSoup,
    final_url: str,
) -> tuple[list[str], list[str]]:
    internal_links = set()
    external_links = set()

    base_domain = urlparse(final_url).netloc.lower()

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()

        if not href:
            continue

        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        absolute_url = urljoin(final_url, href)
        parsed = urlparse(absolute_url)

        if parsed.scheme not in {"http", "https"}:
            continue

        normalized_url = parsed._replace(fragment="").geturl()
        link_domain = parsed.netloc.lower()

        if link_domain == base_domain:
            internal_links.add(normalized_url)
        else:
            external_links.add(normalized_url)

    return sorted(internal_links), sorted(external_links)


def build_recommendations(
    title: str,
    meta_description: str,
    h1_tags: list[str],
    word_count: int,
    images_without_alt: list[str],
    internal_links: list[str],
    canonical: str,
    robots_meta: str,
) -> tuple[int, list[str], list[str]]:
    score = 100
    problems = []
    recommendations = []

    title_length = len(title)
    meta_length = len(meta_description)

    if not title:
        score -= 15
        problems.append("Title tidak ditemukan")
        recommendations.append(
            "Tambahkan title yang menjelaskan topik utama halaman."
        )
    elif title_length < 30:
        score -= 5
        problems.append("Title terlalu pendek")
        recommendations.append(
            "Perjelas title agar lebih deskriptif."
        )
    elif title_length > 60:
        score -= 5
        problems.append("Title cukup panjang")
        recommendations.append(
            "Pertimbangkan meringkas title agar inti topik muncul lebih awal."
        )

    if not meta_description:
        score -= 10
        problems.append("Meta description tidak ditemukan")
        recommendations.append(
            "Tambahkan meta description yang relevan dengan isi halaman."
        )
    elif meta_length < 70:
        score -= 3
        problems.append("Meta description terlalu pendek")
        recommendations.append(
            "Tambahkan informasi yang menjelaskan manfaat halaman."
        )
    elif meta_length > 170:
        score -= 5
        problems.append("Meta description cukup panjang")
        recommendations.append(
            "Ringkas meta description tanpa menghilangkan pesan utama."
        )

    if len(h1_tags) == 0:
        score -= 15
        problems.append("H1 tidak ditemukan")
        recommendations.append(
            "Tambahkan satu heading utama yang jelas."
        )
    elif len(h1_tags) > 1:
        score -= 5
        problems.append("Terdapat lebih dari satu H1")
        recommendations.append(
            "Pastikan struktur heading mudah dipahami."
        )

    if word_count < 300:
        score -= 10
        problems.append("Konten terlihat cukup tipis")
        recommendations.append(
            "Tambahkan informasi yang benar-benar membantu pengguna."
        )

    if images_without_alt:
        penalty = min(10, len(images_without_alt))
        score -= penalty
        problems.append(
            f"{len(images_without_alt)} gambar tidak memiliki alt text"
        )
        recommendations.append(
            "Tambahkan alt text yang menjelaskan fungsi atau isi gambar."
        )

    if not internal_links:
        score -= 5
        problems.append("Internal link tidak ditemukan")
        recommendations.append(
            "Tambahkan internal link menuju halaman terkait."
        )

    if not canonical:
        score -= 5
        problems.append("Canonical tidak ditemukan")
        recommendations.append(
            "Tambahkan canonical jika halaman berpotensi memiliki URL duplikat."
        )

    if "noindex" in robots_meta.lower():
        score -= 20
        problems.append("Halaman menggunakan noindex")
        recommendations.append(
            "Periksa apakah noindex memang disengaja."
        )

    return max(score, 0), problems, recommendations


def analyze_page(url: str) -> dict:
    soup, response = fetch_page(url)

    final_url = response.url

    title = (
        clean_text(soup.title.get_text())
        if soup.title
        else ""
    )

    meta_description = get_meta_description(soup)

    h1_tags = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all("h1")
    ]

    h2_tags = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all("h2")
    ]

    visible_text = extract_visible_text(soup)
    word_count = len(visible_text.split())

    images = soup.find_all("img")

    images_without_alt = []

    for image in images:
        alt = image.get("alt")

        if alt is None or not alt.strip():
            image_url = urljoin(
                final_url,
                image.get("src", ""),
            )

            images_without_alt.append(image_url)

    internal_links, external_links = extract_links(
        soup,
        final_url,
    )

    canonical = get_canonical(soup, final_url)
    robots_meta = get_robots_meta(soup)

    score, problems, recommendations = build_recommendations(
        title=title,
        meta_description=meta_description,
        h1_tags=h1_tags,
        word_count=word_count,
        images_without_alt=images_without_alt,
        internal_links=internal_links,
        canonical=canonical,
        robots_meta=robots_meta,
    )

    report = {
        "analyzed_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "requested_url": url,
        "final_url": final_url,
        "http_status": response.status_code,
        "seo_score": score,
        "page": {
            "title": title,
            "title_length": len(title),
            "meta_description": meta_description,
            "meta_description_length": len(meta_description),
            "canonical": canonical,
            "robots_meta": robots_meta,
            "word_count": word_count,
        },
        "headings": {
            "h1_count": len(h1_tags),
            "h1": h1_tags,
            "h2_count": len(h2_tags),
            "h2": h2_tags,
        },
        "images": {
            "total": len(images),
            "without_alt_count": len(images_without_alt),
            "without_alt": images_without_alt,
        },
        "links": {
            "internal_count": len(internal_links),
            "external_count": len(external_links),
            "internal": internal_links,
            "external": external_links,
        },
        "problems": problems,
        "recommendations": recommendations,
    }

    return report


def save_report(report: dict, output_file: Path) -> None:
    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )


def print_report(report: dict) -> None:
    page = report["page"]
    headings = report["headings"]
    images = report["images"]
    links = report["links"]

    print("\n" + "=" * 60)
    print("SEO ANALYSIS RESULT")
    print("=" * 60)

    print(f"URL akhir          : {report['final_url']}")
    print(f"HTTP status        : {report['http_status']}")
    print(f"SEO score          : {report['seo_score']}/100")
    print(f"Title              : {page['title'] or 'Tidak ada'}")
    print(f"Panjang title      : {page['title_length']}")
    print(
        f"Meta description   : "
        f"{page['meta_description'] or 'Tidak ada'}"
    )
    print(
        f"Panjang meta       : "
        f"{page['meta_description_length']}"
    )
    print(f"Canonical          : {page['canonical'] or 'Tidak ada'}")
    print(
        f"Robots meta        : "
        f"{page['robots_meta'] or 'Tidak ada'}"
    )
    print(f"Jumlah kata        : {page['word_count']}")
    print(f"Jumlah H1          : {headings['h1_count']}")
    print(f"Jumlah H2          : {headings['h2_count']}")
    print(f"Jumlah gambar      : {images['total']}")
    print(
        f"Gambar tanpa alt   : "
        f"{images['without_alt_count']}"
    )
    print(f"Internal link      : {links['internal_count']}")
    print(f"External link      : {links['external_count']}")

    print("\nMasalah:")

    if report["problems"]:
        for problem in report["problems"]:
            print(f"- {problem}")
    else:
        print("- Tidak ditemukan masalah utama")

    print("\nRekomendasi:")

    if report["recommendations"]:
        for recommendation in report["recommendations"]:
            print(f"- {recommendation}")
    else:
        print("- Tidak ada rekomendasi utama")

    print(f"\nLaporan disimpan di: {OUTPUT_FILE.resolve()}")
    print("=" * 60)


def main() -> None:
    url = input("Masukkan URL website: ").strip()

    if not url:
        print("ERROR: URL tidak boleh kosong.")
        return

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        report = analyze_page(url)
        save_report(report, OUTPUT_FILE)
        print_report(report)

    except requests.exceptions.Timeout:
        print("ERROR: Website terlalu lama merespons.")

    except requests.exceptions.HTTPError as error:
        print(f"ERROR HTTP: {error}")

    except requests.exceptions.SSLError:
        print("ERROR: Sertifikat SSL website bermasalah.")

    except requests.exceptions.RequestException as error:
        print(f"ERROR koneksi: {error}")

    except ValueError as error:
        print(f"ERROR: {error}")

    except Exception as error:
        print(f"ERROR tidak terduga: {error}")


if __name__ == "__main__":
    main()