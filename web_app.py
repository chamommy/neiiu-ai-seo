import html
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartException
from starlette.middleware.sessions import (
    SessionMiddleware,
)

from ai.chat_service import (
    generate_chat_response,
)
from auth.security import (
    hash_password,
    verify_password,
)
from config import (
    CRAWL_TOP_N,
    OUTPUT_DIR,
    SERP_PROVIDER,
    SERP_REGION,
    SERP_TOP_N,
)
from database.ip_allowlist_db import (
    add_ip,
    delete_ip,
    init_ip_db,
    is_allowed,
    is_enabled,
    list_ips,
    set_enabled,
)
from database.neiiu_jobs_db import (
    create_job,
    delete_job,
    get_job,
    init_jobs_db,
    list_jobs,
    reset_stuck_jobs,
)
from database.neiiu_templates_db import (
    MAX_TEMPLATE_BYTES,
    MAX_TEMPLATES_PER_USER,
    TemplateError,
    create_template,
    delete_template,
    init_templates_db,
    list_templates,
    read_template_files,
)
from generators.template_scanner import TemplateTooDeep, scan
from generators.template_slots import build_slot_map
from serp.serp_search import slugify
from utils.region import REGIONS
from services.neiiu_runner import (
    active_job_id,
    submit_job,
)
from database.app_db import (
    add_message,
    consume_one_token,
    create_chat,
    create_user,
    delete_chat,
    get_chat,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_chats,
    list_messages,
    list_users,
    refund_one_token,
    update_user_active,
    update_user_password,
    update_user_tokens,
    update_chat_pinned,
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

def resolve_session_secret() -> str:
    """
    Mengambil kunci penanda tangan cookie sesi.

    Sebelumnya nilai bawaannya berupa teks tetap di dalam file ini.
    Selama server hanya mendengarkan di 127.0.0.1 hal itu tidak
    berbahaya, tapi begitu dibuka ke jaringan, siapa pun yang bisa
    membaca kode ini dapat menandatangani cookie sesi sendiri dan
    masuk sebagai admin tanpa password.

    Sekarang kalau NEIIU_SESSION_SECRET tidak diisi, kuncinya dibuat
    acak setiap kali server dinyalakan. Aman secara bawaan, dengan
    konsekuensi semua sesi berakhir tiap restart. Isi kuncinya di
    .env supaya sesi bertahan; serve.py melakukannya otomatis.
    """
    secret = os.environ.get("NEIIU_SESSION_SECRET", "").strip()

    if secret:
        return secret

    print(
        "[NEIIU] NEIIU_SESSION_SECRET belum diisi. "
        "Memakai kunci acak sementara, jadi semua sesi login akan "
        "berakhir saat server dimatikan.\n"
        "        Jalankan lewat 'python serve.py' untuk membuatkan "
        "kunci tetap di .env."
    )

    return secrets.token_urlsafe(48)


SESSION_SECRET = resolve_session_secret()

app = FastAPI(
    title="NEIIU AI",
    version="1.0.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="neiiu_session",
    max_age=60 * 60 * 24 * 7,
    same_site="lax",
    https_only=False,
)

app.mount(
    "/static",
    StaticFiles(
        directory=STATIC_DIR
    ),
    name="static",
)


LOGIN_MAX_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 300
LOGIN_LOCKOUT_SECONDS = 300

_login_attempts: dict[str, list] = {}
_login_lock = threading.Lock()


def login_throttle_check(address: str) -> int:
    """
    Mengembalikan sisa detik penguncian, 0 kalau boleh mencoba.

    Selama server hanya mendengarkan di 127.0.0.1, tidak adanya
    pembatasan percobaan login tidak jadi soal. Setelah dibuka ke
    jaringan, siapa pun di Wi-Fi yang sama bisa menembaki halaman
    login tanpa henti. Selain menebak password, tiap percobaan juga
    memaksa satu hitungan PBKDF2 yang berat, sehingga percobaan
    beruntun bisa menghabiskan CPU dan mengganggu job yang jalan.
    """
    now = time.monotonic()

    with _login_lock:
        record = _login_attempts.get(address)

        if not record:
            return 0

        locked_until, stamps = record

        if locked_until > now:
            return int(locked_until - now)

        fresh = [
            stamp
            for stamp in stamps
            if now - stamp < LOGIN_WINDOW_SECONDS
        ]

        _login_attempts[address] = (0.0, fresh)

        return 0


def login_record_failure(address: str) -> None:
    now = time.monotonic()

    with _login_lock:
        locked_until, stamps = _login_attempts.get(address, (0.0, []))

        stamps = [
            stamp
            for stamp in stamps
            if now - stamp < LOGIN_WINDOW_SECONDS
        ]

        stamps.append(now)

        if len(stamps) >= LOGIN_MAX_ATTEMPTS:
            locked_until = now + LOGIN_LOCKOUT_SECONDS
            stamps = []

        _login_attempts[address] = (locked_until, stamps)


def login_clear(address: str) -> None:
    with _login_lock:
        _login_attempts.pop(address, None)


def client_ip(request: Request) -> str:
    """
    Mengambil alamat IP pengunjung.

    Sengaja memakai alamat sambungan langsung, bukan header
    X-Forwarded-For. Header itu diisi oleh pengirim request dan
    bisa dikarang siapa saja, jadi memakainya di sini akan membuat
    penyaringan IP bisa dilewati hanya dengan menambahkan satu
    header. Kalau nanti aplikasi ini ditaruh di belakang proxy,
    barulah header itu boleh dipercaya, itu pun hanya dari proxy
    yang alamatnya sudah dipastikan.
    """
    return request.client.host if request.client else ""


@app.middleware("http")
async def ip_allowlist_guard(request: Request, call_next):
    """
    Menolak perangkat yang tidak ada di daftar IP.

    Berjalan sebelum halaman login, jadi perangkat asing bahkan
    tidak melihat formulir loginnya. Alamat loopback selalu lolos
    supaya admin tidak pernah terkunci dari komputernya sendiri.
    """
    address = client_ip(request)

    if not is_allowed(address):
        return HTMLResponse(
            "<h1>Akses ditolak</h1>"
            f"<p>Alamat <code>{html.escape(address)}</code> tidak ada "
            "di daftar IP yang diizinkan.</p>"
            "<p>Minta admin menambahkannya lewat halaman Admin.</p>",
            status_code=403,
        )

    return await call_next(request)

templates = Jinja2Templates(
    directory=TEMPLATES_DIR
)


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=12_000,
    )
    mode: Literal["normal", "seo"] = "normal"
    chat_id: int | None = None

class PinRequest(BaseModel):
    is_pinned: bool


class NeiiuJobRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(default="", max_length=60)
    base_url: str = Field(default="", max_length=200)
    provider: Literal["serper", "google_cse", "manual"] = (
        SERP_PROVIDER
        if SERP_PROVIDER in {"serper", "google_cse", "manual"}
        else "serper"
    )
    limit: int = Field(default=SERP_TOP_N, ge=3, le=20)
    crawl: int = Field(default=CRAWL_TOP_N, ge=1, le=20)
    reference: str = Field(default="", max_length=500)
    use_cache: bool = True
    analyze_only: bool = False
    # Zona dibatasi ke daftar yang dikenal di sini juga, bukan cuma
    # di registry. Zona yang salah berarti seluruh halaman ditulis
    # dalam bahasa yang keliru, dan itu terlalu mahal untuk ditebak.
    region: Literal["id", "th"] = (
        SERP_REGION if SERP_REGION in {"id", "th"} else "id"
    )
    # 0 berarti tidak memakai template unggahan, jadi jalur lama
    # yang meniru struktur kompetitor tetap dipakai.
    template_id: int = Field(default=0, ge=0)


@app.on_event("startup")
def startup() -> None:
    init_db()
    init_jobs_db()
    init_ip_db()
    init_templates_db()

    # Job runner hidup di dalam proses ini. Kalau server sebelumnya
    # mati di tengah run, jobnya tertinggal di status running tanpa
    # ada yang mengerjakan, jadi ditutup di sini.
    stuck = reset_stuck_jobs()

    if stuck:
        print(
            f"[NEIIU] {stuck} job tertinggal dari sesi sebelumnya "
            "ditandai gagal."
        )


def session_user(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        return None

    user = get_user_by_id(int(user_id))

    if not user or not user["is_active"]:
        request.session.clear()
        return None

    return user


def require_user(request: Request):
    user = session_user(request)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Silakan login.",
        )

    return user


def require_admin(request: Request):
    user = require_user(request)

    if user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Akses admin diperlukan.",
        )

    return user


def chat_title(message: str) -> str:
    clean = " ".join(message.split())

    if len(clean) <= 42:
        return clean

    return clean[:42].rstrip() + "..."


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = session_user(request)

    if not user:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    return RedirectResponse(
        "/chat",
        status_code=303,
    )


@app.get(
    "/login",
    response_class=HTMLResponse,
)
def login_page(request: Request):
    if session_user(request):
        return RedirectResponse(
            "/chat",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
        },
    )


@app.post(
    "/login",
    response_class=HTMLResponse,
)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    address = client_ip(request)

    remaining = login_throttle_check(address)

    if remaining:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": (
                    "Terlalu banyak percobaan login. "
                    f"Coba lagi dalam {remaining // 60 + 1} menit."
                ),
            },
            status_code=429,
        )

    user = get_user_by_username(
        username
    )

    if (
        not user
        or not user["is_active"]
        or not verify_password(
            password,
            user["password_hash"],
        )
    ):
        login_record_failure(address)

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": (
                    "Username atau password salah."
                ),
            },
            status_code=400,
        )

    login_clear(address)

    request.session.clear()
    request.session["user_id"] = int(
        user["id"]
    )

    return RedirectResponse(
        "/chat",
        status_code=303,
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()

    return RedirectResponse(
        "/login",
        status_code=303,
    )


@app.get(
    "/chat",
    response_class=HTMLResponse,
)
def chat_page(request: Request):
    user = session_user(request)

    if not user:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    chats = list_chats(
        int(user["id"])
    )

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "user": dict(user),
            "chats": [
                dict(item)
                for item in chats
            ],
        },
    )


@app.get("/api/me")
def api_me(request: Request):
    user = require_user(request)

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "token_balance": (
            user["token_balance"]
        ),
    }


@app.get("/api/chats")
def api_chats(request: Request):
    user = require_user(request)

    return {
        "chats": [
            dict(item)
            for item in list_chats(
                int(user["id"])
            )
        ]
    }


@app.get("/api/chats/{chat_id}")
def api_chat_detail(
    chat_id: int,
    request: Request,
):
    user = require_user(request)

    chat = get_chat(
        chat_id,
        int(user["id"]),
    )

    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Chat tidak ditemukan.",
        )

    return {
        "chat": dict(chat),
        "messages": [
            dict(item)
            for item in list_messages(
                chat_id
            )
        ],
    }

@app.patch("/api/chats/{chat_id}/pin")
def api_pin_chat(
    chat_id: int,
    payload: PinRequest,
    request: Request,
):
    user = require_user(request)

    try:
        update_chat_pinned(
            chat_id=chat_id,
            user_id=int(user["id"]),
            is_pinned=payload.is_pinned,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return {
        "status": "success",
        "is_pinned": payload.is_pinned,
    }

@app.delete("/api/chats/{chat_id}")
def api_delete_chat(
    chat_id: int,
    request: Request,
):
    user = require_user(request)

    try:
        delete_chat(
            chat_id,
            int(user["id"]),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return {"status": "success"}


@app.post("/api/chat")
def api_chat(
    payload: ChatRequest,
    request: Request,
):
    user = require_user(request)
    user_id = int(user["id"])

    clean_message = payload.message.strip()

    if not clean_message:
        raise HTTPException(
            status_code=400,
            detail="Pesan tidak boleh kosong.",
        )

    chat_id = payload.chat_id

    if chat_id is None:
        chat_id = create_chat(
            user_id=user_id,
            title=chat_title(
                clean_message
            ),
            mode=payload.mode,
        )
    else:
        chat = get_chat(
            chat_id,
            user_id,
        )

        if not chat:
            raise HTTPException(
                status_code=404,
                detail="Chat tidak ditemukan.",
            )

    history_rows = list_messages(
        chat_id
    )

    history = [
        {
            "role": row["role"],
            "content": row["content"],
        }
        for row in history_rows[-12:]
    ]

    try:
        remaining_tokens = consume_one_token(
            user_id
        )

    except ValueError as error:
        raise HTTPException(
            status_code=402,
            detail=str(error),
        ) from error

    add_message(
        chat_id=chat_id,
        role="user",
        content=clean_message,
        token_cost=1,
    )

    try:
        result = generate_chat_response(
            message=clean_message,
            mode=payload.mode,
            history=history,
        )

        answer = result["answer"]

    except Exception as error:
        refund_one_token(
            user_id
        )

        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    add_message(
        chat_id=chat_id,
        role="assistant",
        content=answer,
        token_cost=0,
    )

    return {
        "status": "success",
        "chat_id": chat_id,
        "answer": answer,
        "remaining_tokens": (
            remaining_tokens
        ),
    }


@app.get(
    "/admin",
    response_class=HTMLResponse,
)
def admin_page(request: Request):
    user = session_user(request)

    if not user:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    if user["role"] != "admin":
        return RedirectResponse(
            "/chat",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": dict(user),
            "users": [
                dict(item)
                for item in list_users()
            ],
            "allowed_ips": list_ips(),
            "ip_enabled": is_enabled(),
            "client_ip": client_ip(request),
            "message": (
                request.query_params.get(
                    "message"
                )
            ),
        },
    )


def admin_redirect(message: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(
        f"/admin?message={quote(message)}#ip",
        status_code=303,
    )


@app.post("/admin/ip")
def admin_add_ip(
    request: Request,
    value: str = Form(...),
    label: str = Form(""),
):
    admin = require_admin(request)

    try:
        entry = add_ip(
            value=value,
            label=label,
            created_by=str(admin["username"]),
        )

    except ValueError as error:
        return admin_redirect(str(error))

    return admin_redirect(f"{entry} ditambahkan ke daftar IP")


@app.post("/admin/ip/{ip_id}/delete")
def admin_delete_ip(
    ip_id: int,
    request: Request,
):
    require_admin(request)

    try:
        delete_ip(ip_id)

    except ValueError as error:
        return admin_redirect(str(error))

    return admin_redirect("Alamat dihapus dari daftar IP")


@app.post("/admin/ip/toggle")
def admin_toggle_ip(
    request: Request,
    enabled: int = Form(...),
):
    require_admin(request)

    try:
        set_enabled(bool(enabled))

    except ValueError as error:
        return admin_redirect(str(error))

    return admin_redirect(
        "Penyaringan IP dinyalakan"
        if enabled
        else "Penyaringan IP dimatikan"
    )


@app.post("/admin/users")
def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    token_balance: int = Form(0),
):
    require_admin(request)

    try:
        create_user(
            username=username,
            password_hash=hash_password(
                password
            ),
            role=role,
            token_balance=token_balance,
        )

    except (
        ValueError,
        sqlite3.IntegrityError,
    ) as error:
        return RedirectResponse(
            "/admin?message="
            + str(error).replace(" ", "%20"),
            status_code=303,
        )

    return RedirectResponse(
        "/admin?message=User%20berhasil%20dibuat",
        status_code=303,
    )


@app.post(
    "/admin/users/{user_id}/tokens"
)
def admin_update_tokens(
    user_id: int,
    request: Request,
    token_balance: int = Form(...),
):
    require_admin(request)

    update_user_tokens(
        user_id,
        token_balance,
    )

    return RedirectResponse(
        "/admin?message=Token%20diperbarui",
        status_code=303,
    )


@app.post(
    "/admin/users/{user_id}/active"
)
def admin_update_active(
    user_id: int,
    request: Request,
    is_active: int = Form(...),
):
    admin = require_admin(request)

    if user_id == int(admin["id"]):
        return RedirectResponse(
            "/admin?message=Admin%20tidak%20boleh%20menonaktifkan%20dirinya",
            status_code=303,
        )

    update_user_active(
        user_id,
        bool(is_active),
    )

    return RedirectResponse(
        "/admin?message=Status%20user%20diperbarui",
        status_code=303,
    )


@app.post(
    "/admin/users/{user_id}/password"
)
def admin_reset_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
):
    require_admin(request)

    update_user_password(
        user_id,
        hash_password(password),
    )

    return RedirectResponse(
        "/admin?message=Password%20diperbarui",
        status_code=303,
    )


# ==========================================================
# NEIIU — GENERATOR LANDING PAGE
# ==========================================================

# Nama file yang boleh diambil dari folder hasil. Daftar putih
# ini yang mencegah folder output dipakai untuk membaca file lain
# di disk lewat nama yang dikarang.
DOWNLOADABLE = {
    "index.html": ("index.html", "text/html"),
    "amp.html": ("amp/index.html", "text/html"),
    "sitemap.xml": ("sitemap.xml", "application/xml"),
    "analisis.md": ("ANALISIS.md", "text/markdown"),
    "report.json": ("report.json", "application/json"),
    "analysis.json": ("analysis.json", "application/json"),
}


def job_output_file(job, name: str) -> Path:
    """
    Menyelesaikan path file hasil milik satu job dengan aman.
    """
    entry = DOWNLOADABLE.get(name.lower())

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="File tidak dikenal.",
        )

    if not job["output_dir"]:
        raise HTTPException(
            status_code=404,
            detail="Job ini belum menghasilkan file.",
        )

    output_root = OUTPUT_DIR.resolve()
    path = (Path(job["output_dir"]) / entry[0]).resolve()

    # Folder hasil disimpan sebagai teks di database. Kalau isinya
    # pernah diubah, path bisa menunjuk ke luar folder output, jadi
    # hasil akhirnya tetap harus diperiksa.
    if not path.is_relative_to(output_root):
        raise HTTPException(
            status_code=403,
            detail="Path di luar folder output.",
        )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File {name} belum ada.",
        )

    return path


def job_to_dict(row) -> dict:
    data = dict(row)

    for field in ("summary", "log"):
        if field in data:
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                data[field] = {} if field == "summary" else []

    return data


@app.get("/neiiu", response_class=HTMLResponse)
def neiiu_page(request: Request):
    user = session_user(request)

    if not user:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="neiiu.html",
        context={
            "user": dict(user),
            "default_provider": SERP_PROVIDER,
            "default_crawl": CRAWL_TOP_N,
            "default_region": SERP_REGION,
            "regions": [
                {"code": spec["code"], "label": spec["label"]}
                for spec in REGIONS.values()
            ],
            "max_template_mb": MAX_TEMPLATE_BYTES // (1024 * 1024),
        },
    )


@app.post("/api/neiiu/jobs")
def api_neiiu_create_job(
    payload: NeiiuJobRequest,
    request: Request,
):
    user = require_user(request)
    user_id = int(user["id"])

    keyword = payload.keyword.strip()

    if not keyword:
        raise HTTPException(
            status_code=400,
            detail="Keyword tidak boleh kosong.",
        )

    # Kepemilikan template diperiksa sebelum job dibuat. Tanpa ini,
    # siapa pun bisa memakai template pengguna lain hanya dengan
    # menebak nomornya, dan isinya akan ikut terbaca lewat hasil
    # generate.
    #
    # Diperiksa SEBELUM token dipotong. Kalau urutannya dibalik,
    # pengguna yang salah pilih template - atau yang templatenya baru
    # saja dihapus di tab lain - kehilangan satu token untuk job yang
    # tidak pernah dibuat, dan tidak ada jalur pengembalian sama
    # sekali: refund hanya jalan lewat fail_job, yang butuh job yang
    # sudah ada di database.
    if payload.template_id:
        try:
            read_template_files(payload.template_id, user_id)
        except TemplateError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error

    try:
        remaining_tokens = consume_one_token(user_id)

    except ValueError as error:
        raise HTTPException(
            status_code=402,
            detail=str(error),
        ) from error

    job_id = create_job(
        user_id=user_id,
        keyword=keyword,
        brand_name=payload.brand_name.strip(),
        base_url=payload.base_url.strip(),
        provider=payload.provider,
        crawl_limit=payload.crawl,
        serp_limit=payload.limit,
        reference_url=payload.reference.strip(),
        use_cache=payload.use_cache,
        analyze_only=payload.analyze_only,
        region=payload.region,
        template_id=payload.template_id,
    )

    submit_job(job_id)

    return {
        "status": "success",
        "job_id": job_id,
        "remaining_tokens": remaining_tokens,
        "queued_behind": (
            0 if active_job_id() is None else 1
        ),
    }


async def read_upload(
    upload: UploadFile | None,
    label: str,
) -> str:
    """
    Membaca satu berkas unggahan dengan batas ukuran yang ditegakkan.

    Dibaca bertahap sambil dihitung, bukan sekaligus. Membaca
    seluruhnya lebih dulu berarti berkas 500 MB sudah terlanjur
    masuk memori sebelum sempat ditolak, dan job runner berjalan di
    dalam proses server yang sama sehingga kehabisan memori di sini
    mematikan layanan untuk semua pengguna.
    """
    if upload is None or not upload.filename:
        return ""

    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await upload.read(64 * 1024)

        if not chunk:
            break

        total += len(chunk)

        if total > MAX_TEMPLATE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Berkas {label} melebihi "
                    f"{MAX_TEMPLATE_BYTES // (1024 * 1024)} MB."
                ),
            )

        chunks.append(chunk)

    raw = b"".join(chunks)

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Berkas {label} bukan teks UTF-8. "
                    "Simpan ulang templatenya dengan encoding UTF-8."
                ),
            ) from error


def summarize_template(html_text: str) -> dict:
    """
    Menghitung slot yang bisa diisi di satu template.
    """
    slot_map = build_slot_map(scan(html_text))

    return {
        "counts": slot_map["counts"],
        "total": sum(
            len(items) for items in slot_map["roles"].values()
        ),
        "skipped": len(slot_map["skipped"]),
    }


@app.get("/api/neiiu/templates")
def api_neiiu_list_templates(request: Request):
    user = require_user(request)

    return {
        "templates": [
            {
                **dict(row),
                "slot_summary": json.loads(row["slot_summary"] or "{}"),
            }
            for row in list_templates(int(user["id"]))
        ],
        "max_templates": MAX_TEMPLATES_PER_USER,
        "max_bytes": MAX_TEMPLATE_BYTES,
    }


# Batas seluruh badan permintaan unggah: dua berkas sebesar batas
# per berkas, plus ruang untuk pembatas multipart dan nama berkas.
MAX_UPLOAD_BODY = MAX_TEMPLATE_BYTES * 2 + 64 * 1024


@app.post("/api/neiiu/templates")
async def api_neiiu_upload_template(request: Request):
    """
    Menerima template landing page dan AMP milik pengguna.

    Berkasnya sengaja TIDAK diambil lewat parameter UploadFile.
    FastAPI mengurai seluruh badan permintaan untuk mengisi parameter
    itu sebelum satu baris pun isi fungsi ini berjalan, jadi
    pemeriksaan login di bawah datang terlambat: siapa saja tanpa
    login bisa mengirim badan permintaan 200 MB, dan Starlette sudah
    menuliskannya ke berkas sementara di disk sebelum jawabannya 401.
    Dengan mengurai sendiri, urutannya jadi benar: login dulu, ukuran
    dulu, baru badan permintaannya disentuh.
    """
    user = require_user(request)

    declared = request.headers.get("content-length")

    if declared is None:
        raise HTTPException(
            status_code=411,
            detail=(
                "Permintaan unggah harus menyertakan Content-Length. "
                "Kirim ulang lewat formulir unggah di halaman NEIIU."
            ),
        )

    try:
        declared_size = int(declared)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Content-Length tidak sah.",
        ) from error

    if declared_size > MAX_UPLOAD_BODY:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Total unggahan melebihi "
                f"{MAX_UPLOAD_BODY // (1024 * 1024)} MB."
            ),
        )

    try:
        form = await request.form(
            max_files=4,
            max_fields=8,
            max_part_size=MAX_TEMPLATE_BYTES,
        )
    except MultiPartException as error:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Berkas melebihi "
                f"{MAX_TEMPLATE_BYTES // (1024 * 1024)} MB."
            ),
        ) from error

    try:
        name = str(form.get("name") or "")
        landing = form.get("landing")
        amp = form.get("amp")

        # Diperiksa terhadap kelas milik Starlette, bukan milik
        # FastAPI. request.form() menghasilkan objek Starlette, dan
        # UploadFile milik FastAPI adalah turunannya - jadi memeriksa
        # dengan yang FastAPI selalu bernilai salah dan setiap
        # unggahan yang sah ikut ditolak.
        if not isinstance(landing, StarletteUploadFile):
            raise HTTPException(
                status_code=400,
                detail="Berkas landing page belum dipilih.",
            )

        if not isinstance(amp, StarletteUploadFile):
            amp = None

        landing_html = await read_upload(landing, "landing page")

        if not landing_html.strip():
            raise HTTPException(
                status_code=400,
                detail="Berkas landing page kosong.",
            )

        amp_html = await read_upload(amp, "AMP")
        landing_filename = landing.filename
    finally:
        await form.close()

    # Pemindaian dijalankan di thread terpisah. Ia murni CPU dan bisa
    # memakan waktu lama untuk berkas besar; dijalankan langsung di
    # sini ia menahan event loop, sehingga satu unggahan membekukan
    # seluruh server untuk semua pengguna, bukan cuma permintaannya
    # sendiri.
    try:
        summary = await run_in_threadpool(summarize_template, landing_html)
    except TemplateTooDeep as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    notes: list[str] = []

    if summary["total"] == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tidak ada satu pun bagian isi yang dikenali di "
                "template ini. Pastikan ada judul, heading, dan "
                "paragraf, atau tandai sendiri dengan atribut "
                'data-neiiu="title" dan seterusnya.'
            ),
        )

    if amp_html:
        try:
            amp_summary = await run_in_threadpool(
                summarize_template,
                amp_html,
            )
        except TemplateTooDeep as error:
            raise HTTPException(
                status_code=400,
                detail=f"Berkas AMP: {error}",
            ) from error

        if amp_summary["total"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Berkas AMP tidak punya satu pun bagian isi yang "
                    "bisa dikenali. Kalau dibiarkan, AMP-nya akan "
                    "terbit dengan teks lama sementara landing page "
                    "sudah berganti isi."
                ),
            )

        # Halaman AMP yang isinya berbeda dari halaman kanoniknya
        # dianggap pelanggaran oleh Google, jadi selisih jumlah slot
        # perlu diketahui pengguna sejak awal, bukan setelah
        # halamannya terbit.
        for role, count in summary["counts"].items():
            other = amp_summary["counts"].get(role, 0)

            if other != count:
                notes.append(
                    f"Jumlah {role} berbeda antara landing ({count}) "
                    f"dan AMP ({other})."
                )

    try:
        template_id = create_template(
            user_id=int(user["id"]),
            name=name or landing_filename or "Template",
            landing_html=landing_html,
            amp_html=amp_html,
            slot_summary=json.dumps(
                summary["counts"],
                ensure_ascii=False,
            ),
            notes=" ".join(notes),
        )
    except TemplateError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    return {
        "status": "success",
        "template_id": template_id,
        "slots": summary["counts"],
        "total_slots": summary["total"],
        "notes": notes,
    }


@app.delete("/api/neiiu/templates/{template_id}")
def api_neiiu_delete_template(
    template_id: int,
    request: Request,
):
    user = require_user(request)

    try:
        delete_template(template_id, int(user["id"]))
    except TemplateError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return {"status": "success"}


@app.get("/api/neiiu/jobs")
def api_neiiu_list_jobs(request: Request):
    user = require_user(request)

    return {
        "jobs": [
            job_to_dict(row)
            for row in list_jobs(int(user["id"]))
        ],
        "active_job_id": active_job_id(),
    }


@app.get("/api/neiiu/jobs/{job_id}")
def api_neiiu_job_detail(
    job_id: int,
    request: Request,
):
    user = require_user(request)

    job = get_job(job_id, int(user["id"]))

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job tidak ditemukan.",
        )

    return {"job": job_to_dict(job)}


@app.delete("/api/neiiu/jobs/{job_id}")
def api_neiiu_delete_job(
    job_id: int,
    request: Request,
):
    user = require_user(request)

    if job_id == active_job_id():
        raise HTTPException(
            status_code=409,
            detail=(
                "Job ini sedang berjalan dan tidak bisa dihapus. "
                "Tunggu sampai selesai."
            ),
        )

    try:
        delete_job(job_id, int(user["id"]))

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return {"status": "success"}


@app.get("/neiiu/jobs/{job_id}/preview/{name}")
def neiiu_preview(
    job_id: int,
    name: str,
    request: Request,
):
    """
    Menampilkan halaman hasil apa adanya di browser.
    """
    user = require_user(request)

    job = get_job(job_id, int(user["id"]))

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job tidak ditemukan.",
        )

    path = job_output_file(job, name)
    media_type = DOWNLOADABLE[name.lower()][1]

    # Hanya halaman yang memang dibuat generator yang boleh
    # dirender sebagai HTML. Berkas lain seperti report.json memuat
    # judul dan cuplikan mentah dari situs kompetitor. Menyajikannya
    # sebagai text/html berarti menjalankan apa pun yang mereka
    # tulis di judul halamannya, di origin ini, dengan cookie sesi
    # pemiliknya ikut terbawa.
    if media_type != "text/html":
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            media_type=f"{media_type}; charset=utf-8",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers=preview_headers(),
    )


def preview_headers() -> dict:
    """
    Header untuk menampilkan halaman hasil dengan aman.

    Sejak template bisa diunggah pengguna, halaman hasil memuat
    skrip milik orang lain: pemasang iklan, penghitung kunjungan,
    dan apa pun yang ada di template. Tanpa pengaman, skrip itu
    berjalan di origin aplikasi ini, dengan cookie sesi ikut
    terkirim, dan bisa memanggil endpoint admin atas nama siapa pun
    yang sedang membuka pratinjaunya.

    "sandbox allow-scripts" membuat halamannya diperlakukan sebagai
    origin tersendiri yang tidak dikenal: skripnya tetap jalan
    sehingga halaman AMP tetap tampil benar, tapi tidak punya jalan
    ke cookie, penyimpanan, maupun endpoint aplikasi ini.
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox allow-scripts allow-popups",
        "Referrer-Policy": "no-referrer",
    }


@app.get("/neiiu/jobs/{job_id}/download/{name}")
def neiiu_download(
    job_id: int,
    name: str,
    request: Request,
):
    user = require_user(request)

    job = get_job(job_id, int(user["id"]))

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job tidak ditemukan.",
        )

    path = job_output_file(job, name)
    media_type = DOWNLOADABLE[name.lower()][1]

    # Nama berkas dibersihkan lewat slugify, bukan dipakai apa
    # adanya, supaya keyword yang memuat tanda kutip atau baris baru
    # tidak bisa menyisipkan header tambahan ke respons.
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"{slugify(job['keyword'])}-{name}",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.get("/neiiu/jobs/{job_id}/download-all")
def neiiu_download_all(
    job_id: int,
    request: Request,
):
    """
    Mengemas seluruh hasil satu job jadi satu berkas ZIP.

    Berkas dikirim ke browser yang meminta, jadi hasilnya tersimpan
    di folder unduhan komputer yang membukanya, bukan di komputer
    yang menjalankan server.
    """
    user = require_user(request)

    job = get_job(job_id, int(user["id"]))

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job tidak ditemukan.",
        )

    if not job["output_dir"]:
        raise HTTPException(
            status_code=404,
            detail="Job ini belum menghasilkan file.",
        )

    output_root = OUTPUT_DIR.resolve()
    folder = Path(job["output_dir"]).resolve()

    if not folder.is_relative_to(output_root) or not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Folder hasil tidak ditemukan.",
        )

    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue

            # Symlink diabaikan supaya isi ZIP tidak pernah
            # menunjuk ke berkas di luar folder hasil.
            if path.is_symlink():
                continue

            archive.write(path, path.relative_to(folder))

    buffer.seek(0)

    label = slugify(job["keyword"])
    brand = (job["brand_name"] or "").strip()

    if brand:
        label = f"{slugify(brand)}-{label}"

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="neiiu-{label}.zip"'
            )
        },
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "NEIIU AI",
    }
