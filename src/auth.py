"""Local RBAC authentication with scrypt password hashes and signed sessions."""
import base64
import binascii
import hashlib
import hmac
import os
import time

COOKIE_NAME = "nexus_session"
SESSION_TTL_SECONDS = 8 * 60 * 60


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Create a Docker Compose-safe scrypt password hash."""
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return ":".join(
        (
            "scrypt",
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(digest).decode(),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password without ever storing or logging its plaintext."""
    try:
        scheme, salt, digest = encoded.split(":", 2)
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=2**14,
            r=8,
            p=1,
        )
        return hmac.compare_digest(candidate, base64.urlsafe_b64decode(digest))
    except (ValueError, TypeError, binascii.Error):
        return False


def make_session(role: str, secret: str) -> str:
    expires = str(int(time.time()) + SESSION_TTL_SECONDS)
    payload = f"{role}.{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode()


def read_session(value: str | None, secret: str) -> str | None:
    try:
        role, expires, signature = base64.urlsafe_b64decode(value or "").decode().split(".", 2)
        payload = f"{role}.{expires}"
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        is_valid = (
            role in {"admin", "viewer"}
            and int(expires) >= time.time()
            and hmac.compare_digest(signature, expected)
        )
        return role if is_valid else None
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
