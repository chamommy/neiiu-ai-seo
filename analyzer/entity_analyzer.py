import re


def normalize_text(text: str) -> str:
    """
    Membersihkan text agar mudah dibandingkan.
    """
    return re.sub(
        r"\s+",
        " ",
        text.lower(),
    ).strip()


def find_matching_topic(
    keyword: str,
    entity_database: dict,
) -> str | None:
    """
    Mencari topik entity yang paling sesuai dengan keyword.
    """

    keyword = normalize_text(keyword)

    if keyword in entity_database:
        return keyword

    for topic in entity_database.keys():
        topic_normalized = normalize_text(topic)

        if (
            topic_normalized in keyword
            or keyword in topic_normalized
        ):
            return topic

    return None


def analyze_entities(
    text: str,
    keyword: str,
    entity_database: dict,
) -> dict:
    """
    Menghitung coverage entity berdasarkan keyword.
    """

    normalized_text = normalize_text(text)

    topic = find_matching_topic(
        keyword,
        entity_database,
    )

    if topic is None:
        return {
            "topic_found": False,
            "topic": None,
            "coverage_percentage": 0,
            "total_entities": 0,
            "found_count": 0,
            "missing_count": 0,
            "found_entities": [],
            "missing_entities": [],
            "message": "Topik belum tersedia di database entity."
        }

    entities = entity_database[topic]

    found_entities = []
    missing_entities = []

    for entity in entities:

        entity_normalized = normalize_text(entity)

        if entity_normalized in normalized_text:
            found_entities.append(entity)
        else:
            missing_entities.append(entity)

    total_entities = len(entities)
    found_count = len(found_entities)
    missing_count = len(missing_entities)

    if total_entities > 0:
        coverage = round(
            (found_count / total_entities) * 100,
            2
        )
    else:
        coverage = 0

    return {
        "topic_found": True,
        "topic": topic,
        "coverage_percentage": coverage,
        "total_entities": total_entities,
        "found_count": found_count,
        "missing_count": missing_count,
        "found_entities": found_entities,
        "missing_entities": missing_entities,
        "message": "Entity analysis berhasil."
    }