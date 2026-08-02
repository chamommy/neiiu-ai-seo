"""
Provider SERP untuk NEIIU.

Setiap provider menerima keyword dan mengembalikan daftar
hasil organik dengan bentuk yang seragam:

    {
        "position": int,
        "url": str,
        "title": str,
        "snippet": str,
        "domain": str,
    }

Provider sengaja dipisah supaya sumber data SERP bisa diganti
tanpa mengubah pipeline analisis di lapisan atas.
"""

import json
from urllib.parse import urlparse

import requests

from config import (
    GOOGLE_CSE_CX,
    GOOGLE_CSE_KEY,
    REQUEST_TIMEOUT,
    SERP_COUNTRY,
    SERP_LANGUAGE,
    SERP_MANUAL_FILE,
    SERPER_API_KEY,
)


class SerpProviderError(RuntimeError):
    """
    Error yang berasal dari provider SERP.
    """


def get_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()

    return netloc[4:] if netloc.startswith("www.") else netloc


def normalize_results(
    raw_items: list[dict],
    limit: int,
) -> list[dict]:
    """
    Menyeragamkan hasil provider dan membuang duplikat domain.

    Satu domain hanya diambil sekali karena sitelink dan halaman
    turunan dari domain yang sama tidak menambah informasi baru
    untuk analisis struktur SERP.
    """
    results: list[dict] = []
    seen_domains: set[str] = set()

    for item in raw_items:
        url = str(item.get("url", "")).strip()

        if not url.startswith(("http://", "https://")):
            continue

        domain = get_domain(url)

        if not domain or domain in seen_domains:
            continue

        seen_domains.add(domain)

        results.append(
            {
                "position": len(results) + 1,
                "url": url,
                "title": str(item.get("title", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
                "domain": domain,
            }
        )

        if len(results) >= limit:
            break

    return results


def search_serper(
    keyword: str,
    limit: int,
) -> list[dict]:
    """
    Provider Serper.dev (butuh SERPER_API_KEY).
    """
    if not SERPER_API_KEY:
        raise SerpProviderError(
            "SERPER_API_KEY belum diisi di file .env."
        )

    response = requests.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "q": keyword,
            "gl": SERP_COUNTRY,
            "hl": SERP_LANGUAGE,
            "num": max(limit, 10),
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 401:
        raise SerpProviderError(
            "SERPER_API_KEY ditolak (401). Cek kembali API key."
        )

    if response.status_code == 429:
        raise SerpProviderError(
            "Kuota Serper.dev habis atau terlalu banyak request (429)."
        )

    response.raise_for_status()

    payload = response.json()

    raw_items = [
        {
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in payload.get("organic", [])
    ]

    extras = {
        "people_also_ask": [
            str(item.get("question", "")).strip()
            for item in payload.get("peopleAlsoAsk", [])
            if str(item.get("question", "")).strip()
        ],
        "related_searches": [
            str(item.get("query", "")).strip()
            for item in payload.get("relatedSearches", [])
            if str(item.get("query", "")).strip()
        ],
    }

    results = normalize_results(raw_items, limit)

    if results:
        results[0]["_extras"] = extras

    return results


def search_google_cse(
    keyword: str,
    limit: int,
) -> list[dict]:
    """
    Provider Google Custom Search JSON API.

    Catatan: CSE membatasi 10 hasil per request.
    """
    if not GOOGLE_CSE_KEY or not GOOGLE_CSE_CX:
        raise SerpProviderError(
            "GOOGLE_CSE_KEY / GOOGLE_CSE_CX belum diisi di file .env."
        )

    response = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": GOOGLE_CSE_KEY,
            "cx": GOOGLE_CSE_CX,
            "q": keyword,
            "gl": SERP_COUNTRY,
            "hl": SERP_LANGUAGE,
            "num": min(limit, 10),
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 403:
        raise SerpProviderError(
            "Google CSE menolak request (403). "
            "Kuota harian habis atau API belum diaktifkan."
        )

    response.raise_for_status()

    payload = response.json()

    raw_items = [
        {
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in payload.get("items", [])
    ]

    return normalize_results(raw_items, limit)


def search_manual(
    keyword: str,
    limit: int,
) -> list[dict]:
    """
    Provider manual, tanpa API.

    Membaca daftar URL hasil pencarian yang disalin sendiri
    dari halaman Google ke file JSON.

    Format file yang diterima:
        {"slot gacor": ["https://a.com", "https://b.com"]}
    atau:
        ["https://a.com", "https://b.com"]
    """
    if not SERP_MANUAL_FILE.exists():
        raise SerpProviderError(
            f"File SERP manual tidak ditemukan: {SERP_MANUAL_FILE}\n"
            "Buat file itu dan isi daftar URL hasil pencarian."
        )

    with SERP_MANUAL_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if isinstance(data, dict):
        urls = data.get(keyword.strip().lower(), [])

        if not urls:
            available = ", ".join(data.keys()) or "kosong"

            raise SerpProviderError(
                f"Keyword '{keyword}' tidak ada di {SERP_MANUAL_FILE.name}. "
                f"Keyword tersedia: {available}"
            )
    else:
        urls = data

    raw_items = [
        {
            "url": str(url),
            "title": "",
            "snippet": "",
        }
        for url in urls
    ]

    return normalize_results(raw_items, limit)


PROVIDERS = {
    "serper": search_serper,
    "google_cse": search_google_cse,
    "manual": search_manual,
}


def run_provider(
    provider: str,
    keyword: str,
    limit: int,
) -> list[dict]:
    """
    Menjalankan provider berdasarkan namanya.
    """
    handler = PROVIDERS.get(provider)

    if handler is None:
        available = ", ".join(sorted(PROVIDERS))

        raise SerpProviderError(
            f"Provider SERP '{provider}' tidak dikenal. "
            f"Pilihan: {available}"
        )

    return handler(keyword, limit)
