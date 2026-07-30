import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def get_meta_content(
    soup: BeautifulSoup,
    name: str,
) -> str:
    tag = soup.find(
        "meta",
        attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)},
    )

    if not tag:
        return ""

    return clean_text(tag.get("content", ""))


def get_canonical(
    soup: BeautifulSoup,
    base_url: str,
) -> str:
    tag = soup.find(
        "link",
        rel=lambda value: value and "canonical" in value,
    )

    if not tag:
        return ""

    href = tag.get("href", "").strip()

    return urljoin(base_url, href) if href else ""


def get_visible_text(soup: BeautifulSoup) -> str:
    copied_soup = BeautifulSoup(str(soup), "html.parser")

    for tag in copied_soup(
        ["script", "style", "noscript", "svg", "template"]
    ):
        tag.decompose()

    return clean_text(copied_soup.get_text(" ", strip=True))


def extract_links(
    soup: BeautifulSoup,
    base_url: str,
) -> tuple[list[str], list[str]]:
    internal_links = set()
    external_links = set()

    base_domain = urlparse(base_url).netloc.lower()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        if href.startswith(
            ("#", "mailto:", "tel:", "javascript:")
        ):
            continue

        absolute_url = urljoin(base_url, href)
        parsed_url = urlparse(absolute_url)

        if parsed_url.scheme not in {"http", "https"}:
            continue

        normalized_url = parsed_url._replace(fragment="").geturl()

        if parsed_url.netloc.lower() == base_domain:
            internal_links.add(normalized_url)
        else:
            external_links.add(normalized_url)

    return sorted(internal_links), sorted(external_links)


def parse_html(
    html: str,
    final_url: str,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = (
        clean_text(soup.title.get_text(" ", strip=True))
        if soup.title
        else ""
    )

    meta_description = get_meta_content(
        soup,
        "description",
    )

    robots_meta = get_meta_content(
        soup,
        "robots",
    )

    canonical = get_canonical(
        soup,
        final_url,
    )

    h1_tags = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all("h1")
    ]

    h2_tags = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in soup.find_all("h2")
    ]

    h3_tags = [
    clean_text(tag.get_text(" ", strip=True))
    for tag in soup.find_all("h3")
    ]

    visible_text = get_visible_text(soup)
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

    paragraphs = [
    clean_text(tag.get_text(" ", strip=True))
    for tag in soup.find_all("p")
    if clean_text(tag.get_text(" ", strip=True))
    ]

    return {
    "title": title,
    "visible_text": visible_text,
        "paragraphs": paragraphs,
        "title_length": len(title),
        "meta_description": meta_description,
        "meta_description_length": len(meta_description),
        "robots_meta": robots_meta,
        "canonical": canonical,
        "word_count": word_count,
        "headings": {
            "h1": h1_tags,
            "h1_count": len(h1_tags),
            "h2": h2_tags,
            "h2_count": len(h2_tags),
            "h3": h3_tags,
            "h3_count": len(h3_tags),
     },
        "images": {
            "total": len(images),
            "without_alt": images_without_alt,
            "without_alt_count": len(images_without_alt),
        },
        "links": {
            "internal": internal_links,
            "internal_count": len(internal_links),
            "external": external_links,
            "external_count": len(external_links),
        },
    }