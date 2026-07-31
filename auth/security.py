import base64
import hashlib
import hmac
import os
from typing import Final


PBKDF2_ITERATIONS: Final[int] = 310_000


def hash_password(password: str) -> str:
    if len(password) < 6:
        raise ValueError(
            "Password minimal 6 karakter."
        )

    salt = os.urandom(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return (
        f"pbkdf2_sha256"
        f"${PBKDF2_ITERATIONS}"
        f"${base64.b64encode(salt).decode('ascii')}"
        f"${base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = (
            stored_hash.split("$", 3)
        )

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iteration_text)
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

        return hmac.compare_digest(
            actual,
            expected,
        )

    except (
        ValueError,
        TypeError,
        base64.binascii.Error,
    ):
        return False
