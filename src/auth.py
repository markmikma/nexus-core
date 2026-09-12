"""Local RBAC authentication with scrypt password hashes and signed sessions."""
import base64, hashlib, hmac, os, time

COOKIE_NAME = "nexus_session"

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, digest = encoded.split("$", 2)
        if scheme != "scrypt": return False
        candidate = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(candidate, base64.urlsafe_b64decode(digest))
    except (ValueError, TypeError): return False

def make_session(role: str, secret: str) -> str:
    expires = str(int(time.time()) + 8*3600)
    payload = f"{role}.{expires}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()

def read_session(value: str | None, secret: str) -> str | None:
    try:
        role, expires, signature = base64.urlsafe_b64decode(value or "").decode().split(".", 2)
        payload=f"{role}.{expires}"; expected=hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return role if role in {"admin","viewer"} and int(expires) >= time.time() and hmac.compare_digest(signature, expected) else None
    except (ValueError, UnicodeDecodeError): return None
