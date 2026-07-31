import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
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
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

SESSION_SECRET = os.environ.get(
    "NEIIU_SESSION_SECRET",
    "CHANGE-ME-BEFORE-PRODUCTION-NEIIU",
)

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


@app.on_event("startup")
def startup() -> None:
    init_db()


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


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(
    chat_id: int,
    request: Request,
):
    user = require_user(request)

    delete_chat(
        chat_id,
        int(user["id"]),
    )

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
            "message": (
                request.query_params.get(
                    "message"
                )
            ),
        },
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "NEIIU AI",
    }
