import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import bcrypt
import jwt
from app.core.config import settings

_LEGACY_SALT = "sih26034_salt"


def get_password_hash(password: str) -> str:
    # bcrypt only uses the first 72 bytes; longer inputs are pre-hashed so they are not silently truncated.
    data = password.encode()
    if len(data) > 72:
        data = hashlib.sha256(data).hexdigest().encode()
    return bcrypt.hashpw(data, bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        data = plain_password.encode()
        if len(data) > 72:
            data = hashlib.sha256(data).hexdigest().encode()
        try:
            return bcrypt.checkpw(data, hashed_password.encode())
        except ValueError:
            return False
    # Accounts created before bcrypt used salted SHA-256; they are re-hashed on next login.
    legacy = hashlib.sha256((plain_password + _LEGACY_SALT).encode()).hexdigest()
    return hmac.compare_digest(legacy, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    return not hashed_password.startswith(("$2a$", "$2b$", "$2y$"))


def create_access_token(subject: str | Any, role: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"exp": expire, "sub": str(subject), "role": role, "typ": "access"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "access" else None


# --- Edge device API keys ---
def generate_device_key() -> tuple[str, str, str]:
    """Returns (plaintext key shown once, prefix for display/lookup, hash to store)."""
    key = "pmk_" + secrets.token_urlsafe(32)
    return key, key[:12], hash_device_key(key)


def hash_device_key(key: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), key.encode(), hashlib.sha256).hexdigest()
