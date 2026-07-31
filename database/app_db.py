import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "neiiu_ai.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
                    CHECK(role IN ('admin', 'user')),
                token_balance INTEGER NOT NULL DEFAULT 0
                    CHECK(token_balance >= 0),
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'normal'
                    CHECK(mode IN ('normal', 'seo')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL
                    CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                token_cost INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id)
                    REFERENCES chats(id)
                    ON DELETE CASCADE
            );
            """
        )

        chat_columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(chats)"
            ).fetchall()
        }

        if "is_pinned" not in chat_columns:
            db.execute(
                """
                ALTER TABLE chats
                ADD COLUMN is_pinned
                INTEGER NOT NULL DEFAULT 0
                """
            )

        db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_chats_user_updated
            ON chats(
                user_id,
                is_pinned DESC,
                updated_at DESC
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat
            ON messages(chat_id, id);
            """
        )


def get_user_by_username(username: str):
    with db_connection() as db:
        return db.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()


def get_user_by_id(user_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()


def create_user(
    username: str,
    password_hash: str,
    role: str = "user",
    token_balance: int = 0,
) -> int:
    clean_username = username.strip()

    if not clean_username:
        raise ValueError("Username tidak boleh kosong.")

    if role not in {"admin", "user"}:
        raise ValueError("Role tidak valid.")

    if token_balance < 0:
        raise ValueError("Token tidak boleh negatif.")

    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                role,
                token_balance,
                is_active,
                created_at
            )
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (
                clean_username,
                password_hash,
                role,
                token_balance,
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def list_users():
    with db_connection() as db:
        return db.execute(
            """
            SELECT
                id,
                username,
                role,
                token_balance,
                is_active,
                created_at
            FROM users
            ORDER BY id DESC
            """
        ).fetchall()


def update_user_tokens(user_id: int, token_balance: int) -> None:
    if token_balance < 0:
        raise ValueError("Token tidak boleh negatif.")

    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE users
            SET token_balance = ?
            WHERE id = ?
            """,
            (token_balance, user_id),
        )

        if cursor.rowcount == 0:
            raise ValueError("User tidak ditemukan.")


def update_user_active(user_id: int, is_active: bool) -> None:
    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE users
            SET is_active = ?
            WHERE id = ?
            """,
            (1 if is_active else 0, user_id),
        )

        if cursor.rowcount == 0:
            raise ValueError("User tidak ditemukan.")


def update_user_password(user_id: int, password_hash: str) -> None:
    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            (password_hash, user_id),
        )

        if cursor.rowcount == 0:
            raise ValueError("User tidak ditemukan.")


def create_chat(
    user_id: int,
    title: str,
    mode: str,
) -> int:
    if mode not in {"normal", "seo"}:
        raise ValueError("Mode chat tidak valid.")

    now = utc_now()

    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO chats (
                user_id,
                title,
                mode,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title.strip() or "Chat baru",
                mode,
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def list_chats(user_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT
                id,
                title,
                mode,
                is_pinned,
                created_at,
                updated_at
            FROM chats
            WHERE user_id = ?
            ORDER BY
                is_pinned DESC,
                updated_at DESC,
                id DESC
            """,
            (user_id,),
        ).fetchall()


def get_chat(chat_id: int, user_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT id, user_id, title, mode, created_at, updated_at
            FROM chats
            WHERE id = ? AND user_id = ?
            """,
            (chat_id, user_id),
        ).fetchone()

def update_chat_pinned(
    chat_id: int,
    user_id: int,
    is_pinned: bool,
) -> None:
    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE chats
            SET
                is_pinned = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                1 if is_pinned else 0,
                utc_now(),
                chat_id,
                user_id,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "Chat tidak ditemukan."
            )

def delete_chat(chat_id: int, user_id: int) -> None:
    with db_connection() as db:
        db.execute(
            """
            DELETE FROM chats
            WHERE id = ? AND user_id = ?
            """,
            (chat_id, user_id),
        )


def list_messages(chat_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT id, role, content, token_cost, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,),
        ).fetchall()


def add_message(
    chat_id: int,
    role: str,
    content: str,
    token_cost: int = 0,
) -> int:
    if role not in {"user", "assistant"}:
        raise ValueError("Role pesan tidak valid.")

    with db_connection() as db:
        cursor = db.execute(
            """
            INSERT INTO messages (
                chat_id,
                role,
                content,
                token_cost,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                role,
                content,
                token_cost,
                utc_now(),
            ),
        )

        db.execute(
            """
            UPDATE chats
            SET updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), chat_id),
        )

        return int(cursor.lastrowid)


def consume_one_token(user_id: int) -> int:
    with db_connection() as db:
        cursor = db.execute(
            """
            UPDATE users
            SET token_balance = token_balance - 1
            WHERE
                id = ?
                AND is_active = 1
                AND token_balance > 0
            """,
            (user_id,),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                "Token habis atau akun sedang dinonaktifkan."
            )

        row = db.execute(
            """
            SELECT token_balance
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        return int(row["token_balance"])


def refund_one_token(user_id: int) -> None:
    with db_connection() as db:
        db.execute(
            """
            UPDATE users
            SET token_balance = token_balance + 1
            WHERE id = ?
            """,
            (user_id,),
        )
