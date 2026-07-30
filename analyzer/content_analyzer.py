import re


def count_keyword(text: str, keyword: str) -> int:
    pattern = rf"\b{re.escape(keyword.lower())}\b"

    return len(
        re.findall(
            pattern,
            text.lower(),
        )
    )


def analyze_content(page: dict, keyword: str) -> dict:
    text = page.get("visible_text", "")
    words = text.split()
    word_count = len(words)

    reading_time = round(
        word_count / 200,
        1,
    )

    keyword = keyword.strip().lower()

    keyword_count = count_keyword(
        text,
        keyword,
    )

    keyword_density = (
        round(
            keyword_count / word_count * 100,
            2,
        )
        if word_count
        else 0
    )

    title = page.get(
        "title",
        "",
    ).lower()

    meta = page.get(
        "meta_description",
        "",
    ).lower()

    h1_list = page.get(
        "headings",
        {},
    ).get(
        "h1",
        [],
    )

    keyword_in_h1 = any(
        keyword in h1.lower()
        for h1 in h1_list
    )

    paragraphs = page.get(
        "paragraphs",
        [],
    )

    paragraph_word_counts = [
        len(paragraph.split())
        for paragraph in paragraphs
    ]

    paragraph_count = len(paragraphs)

    average_paragraph = (
        round(
            sum(paragraph_word_counts)
            / paragraph_count,
            1,
        )
        if paragraph_count
        else 0
    )

    longest_paragraph = (
        max(paragraph_word_counts)
        if paragraph_word_counts
        else 0
    )

    return {
        "word_count": word_count,
        "reading_time": reading_time,
        "keyword_count": keyword_count,
        "keyword_density": keyword_density,
        "keyword_in_title": keyword in title,
        "keyword_in_meta": keyword in meta,
        "keyword_in_h1": keyword_in_h1,
        "paragraph_count": paragraph_count,
        "average_paragraph_length": average_paragraph,
        "longest_paragraph_length": longest_paragraph,
    }