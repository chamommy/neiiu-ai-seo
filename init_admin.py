import getpass
import sqlite3

from auth.security import hash_password
from database.app_db import (
    create_user,
    get_user_by_username,
    init_db,
)


def main() -> None:
    init_db()

    username = input(
        "Username admin [admin]: "
    ).strip() or "admin"

    existing = get_user_by_username(
        username
    )

    if existing:
        print(
            "ERROR: Username tersebut sudah ada."
        )
        return

    password = getpass.getpass(
        "Password admin: "
    )

    confirmation = getpass.getpass(
        "Ulangi password: "
    )

    if password != confirmation:
        print("ERROR: Password tidak sama.")
        return

    try:
        user_id = create_user(
            username=username,
            password_hash=hash_password(
                password
            ),
            role="admin",
            token_balance=999_999,
        )

    except (
        ValueError,
        sqlite3.IntegrityError,
    ) as error:
        print(f"ERROR: {error}")
        return

    print(
        f"Admin berhasil dibuat. ID: {user_id}"
    )


if __name__ == "__main__":
    main()
