import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

import bcrypt
import jwt

from app.core.config import settings

_LEGACY_SALT = "sih26034_salt"


def _bcrypt_input(password: str) -> bytes:
    # bcrypt reads at most 72 bytes; pre-hashing keeps long passwords fully significant.
    return hashlib.sha256(password.encode()).hexdigest().encode()


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return verify_and_upgrade(plain_password, hashed_password)[0]


def verify_and_upgrade(plain_password: str, hashed_password: str) -> Tuple[bool, Optional[str]]:
    """Checks a password. Old SHA-256 rows pass once, and a bcrypt replacement is returned for saving."""
    if hashed_password.startswith("$2"):
        try:
            return bcrypt.checkpw(_bcrypt_input(plain_password), hashed_password.encode()), None
        except ValueError:
            return False, None
    legacy = hashlib.sha256((plain_password + _LEGACY_SALT).encode()).hexdigest()
    if hmac.compare_digest(legacy, hashed_password):
        return True, get_password_hash(plain_password)
    return False, None


def create_access_token(subject: str | Any, role: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    return jwt.encode({"exp": expire, "sub": str(subject), "role": role}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
