"""
Penjalan job NEIIU di belakang layar.

Hanya satu job yang benar-benar berjalan pada satu waktu. Model
lokal dijalankan lewat Ollama di mesin yang sama, dan menjalankan
dua pipeline sekaligus justru membuat keduanya berebut CPU dan
jadi lebih lambat daripada dijalankan berurutan.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

from database.app_db import refund_one_token
from database.neiiu_jobs_db import (
    finish_job,
    get_job,
    set_status,
    update_progress,
)
from serp.providers import SerpProviderError
from services.neiiu_pipeline import PipelineError, run_neiiu


# max_workers=1 adalah antriannya: job berikutnya menunggu giliran.
_executor = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="neiiu-job",
)

_lock = threading.Lock()
_active_job_id: int | None = None


def active_job_id() -> int | None:
    with _lock:
        return _active_job_id


def build_summary(result: dict) -> dict:
    """
    Merangkum hasil pipeline seperlunya untuk ditampilkan di daftar.
    """
    blueprint = result["analysis"]["blueprint"]

    brand = result.get("brand", {})

    hijack_info = {
        "brand_name": brand.get("site_name", ""),
        "base_url": brand.get("base_url", ""),
        "hijacked_count": blueprint.get("hijacked_count", 0),
        "hijacked_pages": blueprint.get("hijacked_pages", []),
        "unreadable_count": blueprint.get("unreadable_count", 0),
        "unreadable_pages": blueprint.get("unreadable_pages", []),
        "hijack_fallback": blueprint.get("hijack_fallback", False),
    }

    if result.get("analyze_only"):
        return {
            "analyze_only": True,
            "analyzed_pages": blueprint["analyzed_pages"],
            "failed_pages": blueprint["failed_pages"],
            "reference_domain": result["template"]["source_domain"],
            **hijack_info,
        }

    plan = result["plan"]
    seo = result["seo_result"]

    return {
        **hijack_info,
        "analyze_only": False,
        "title": plan["title"],
        "meta_description": plan["meta_description"],
        "slug": plan["slug"],
        "sections": len(plan["sections"]),
        "faq": len(plan["faq"]),
        "amp_valid": result["amp_valid"],
        "amp_errors": result["amp_result"]["errors"],
        "seo_score": seo["score"],
        "word_count": seo["word_count"],
        "word_target": seo["word_target"],
        "keyword_density": seo["keyword_density"],
        "problems": seo["problems"],
        "reference_domain": result["template"]["source_domain"],
        "page_url": result["page_url"],
        "amp_url": result["amp_url"],
    }


def fail_job(job, message: str) -> None:
    """
    Menandai job gagal dan mengembalikan token penggunanya.

    Token dipotong saat job dibuat supaya pengguna langsung tahu
    kalau saldonya habis. Kalau jobnya kemudian gagal, potongan itu
    tidak adil, jadi dikembalikan di sini.
    """
    set_status(int(job["id"]), "error", message)

    try:
        refund_one_token(int(job["user_id"]))
    except Exception:
        # Kegagalan refund tidak boleh menutupi error aslinya.
        pass


def run_job(job_id: int) -> None:
    """
    Menjalankan satu job sampai selesai.

    Fungsi ini jalan di thread terpisah, jadi setiap error harus
    ditangkap di sini. Kalau lolos, thread mati diam-diam dan job
    akan tersangkut di status running selamanya.
    """
    global _active_job_id

    job = get_job(job_id)

    if job is None:
        return

    if job["status"] == "cancelled":
        return

    with _lock:
        _active_job_id = job_id

    try:
        set_status(job_id, "running")

        def on_event(event: dict) -> None:
            if event["status"] == "start":
                line = f"Mulai: {event['label']}"
            elif event["status"] == "info":
                line = event["message"]
            else:
                line = (
                    f"Selesai: {event['label']}"
                    + (f" — {event['message']}" if event["message"] else "")
                )

            update_progress(
                job_id=job_id,
                step=event["step"],
                step_label=event["label"],
                line=line,
            )

        result = run_neiiu(
            keyword=job["keyword"],
            brand_name=job["brand_name"],
            base_url=job["base_url"],
            limit=int(job["serp_limit"]),
            crawl=int(job["crawl_limit"]),
            provider=job["provider"],
            reference=job["reference_url"],
            use_cache=bool(job["use_cache"]),
            analyze_only=bool(job["analyze_only"]),
            on_event=on_event,
        )

        finish_job(
            job_id=job_id,
            output_dir=result["output_dir"],
            summary=build_summary(result),
        )

    except SerpProviderError as error:
        fail_job(job, f"SERP: {error}")

    except PipelineError as error:
        fail_job(job, str(error))

    except Exception as error:
        fail_job(job, f"{type(error).__name__}: {error}")

    finally:
        with _lock:
            if _active_job_id == job_id:
                _active_job_id = None


def submit_job(job_id: int) -> None:
    """
    Memasukkan job ke antrian.
    """
    _executor.submit(run_job, job_id)
