import json


def load_knowledge(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def get_topic(
    knowledge,
    topic,
):
    return knowledge.get(
        topic.lower(),
        {},
    )