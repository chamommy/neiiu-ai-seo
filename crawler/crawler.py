import requests

from config import REQUEST_TIMEOUT, USER_AGENT


def fetch_page(
    url: str,
    user_agent: str = USER_AGENT,
) -> dict:
    """
    Mengambil satu halaman HTML.

    user_agent bisa diganti supaya halaman yang melakukan cloaking
    bisa diambil dalam kedua versinya, lihat analyzer/cloak_detector.py
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()

    if "text/html" not in content_type:
        raise ValueError(
            f"URL bukan halaman HTML. Content-Type: {content_type}"
        )

    return {
        "requested_url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "content_type": content_type,
        "html": response.text,
        "user_agent": user_agent,
    }
