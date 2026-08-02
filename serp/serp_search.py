"""
Pencarian SERP dengan cache lokal.

Hasil SERP disimpan supaya percobaan berulang untuk keyword yang
sama tidak menghabiskan kuota API dan pipeline bisa diulang
dengan data yang persis sama.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    SERP_CACHE_DIR,
    SERP_CACHE_TTL_HOURS,
    SERP_PROVIDER,
    SERP_REGION,
    SERP_TOP_N,
)
from serp.providers import SerpProviderError, run_provider
from utils.region import get_region, slug_for_filename


def slugify(value: str) -> str:
    """
    Mengubah teks jadi nama file yang aman.

    Sengaja hanya menghasilkan ASCII: ini dipakai untuk nama file
    cache dan nama folder hasil, bukan untuk slug URL. Slug URL
    boleh memuat aksara Thai dan diurus terpisah oleh
    utils.region.slug_for_url.
    """
    return slug_for_filename(value)


def cache_path(
    keyword: str,
    provider: str,
    region: str = SERP_REGION,
) -> str:
    """
    Menentukan nama file cache untuk satu pencarian.

    Zona wajib ikut jadi bahan sidik jari. Kalau tidak, hasil
    pencarian Indonesia dan Thailand untuk keyword yang sama akan
    saling menimpa di file yang sama, dan job kedua akan menerima
    SERP negara lain tanpa tanda apa pun bahwa itu keliru.
    """
    code = get_region(region)["code"]

    fingerprint = hashlib.sha1(
        f"{provider}|{code}|{keyword}".encode("utf-8")
    ).hexdigest()[:10]

    filename = f"{code}-{slugify(keyword)}-{fingerprint}.json"

    return str(SERP_CACHE_DIR / filename)


def read_cache(
    path: str,
    ttl_hours: int,
) -> dict | None:
    cache_file = Path(path)

    if not cache_file.exists():
        return None

    try:
        with cache_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return None

    fetched_at = payload.get("fetched_at", "")

    try:
        fetched_time = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None

    if datetime.now() - fetched_time > timedelta(hours=ttl_hours):
        return None

    return payload


def write_cache(
    path: str,
    payload: dict,
) -> None:
    SERP_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with Path(path).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def search_keyword(
    keyword: str,
    limit: int = SERP_TOP_N,
    provider: str = SERP_PROVIDER,
    use_cache: bool = True,
    region: str = SERP_REGION,
) -> dict:
    """
    Mengambil hasil pencarian Google untuk satu keyword.

    Mengembalikan:
        {
            "keyword": str,
            "provider": str,
            "fetched_at": str,
            "from_cache": bool,
            "results": [...],
            "people_also_ask": [...],
            "related_searches": [...],
        }
    """
    clean_keyword = keyword.strip()

    if not clean_keyword:
        raise ValueError("Keyword tidak boleh kosong.")

    spec = get_region(region)

    path = cache_path(clean_keyword, provider, region)

    if use_cache:
        cached = read_cache(path, SERP_CACHE_TTL_HOURS)

        if cached is not None:
            cached["from_cache"] = True

            return cached

    results = run_provider(
        provider=provider,
        keyword=clean_keyword,
        limit=limit,
        region=region,
    )

    if not results:
        raise SerpProviderError(
            f"Provider '{provider}' tidak mengembalikan hasil "
            f"untuk keyword '{clean_keyword}'."
        )

    extras = results[0].pop("_extras", {})

    payload = {
        "keyword": clean_keyword,
        "provider": provider,
        "region": spec["code"],
        "region_label": spec["label"],
        "country": spec["gl"],
        "language": spec["hl"],
        "location": spec["location"],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "from_cache": False,
        "results": results,
        "people_also_ask": extras.get("people_also_ask", []),
        "related_searches": extras.get("related_searches", []),
    }

    write_cache(path, payload)

    return payload
