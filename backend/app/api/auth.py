import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user  # noqa: F401  (re-exported for existing imports)
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import normalize_role, permissions_for
from app.core.security import create_access_token, get_password_hash, needs_rehash, verify_password
from app.models.all_models import User
from app.schemas.all_schemas import LoginRequest, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])

_attempts: dict[str, deque] = defaultdict(deque)
_attempts_lock = threading.Lock()


def _check_rate_limit(key: str) -> None:
    now = time.monotonic()
    with _attempts_lock:
        window = _attempts[key]
        while window and now - window[0] > settings.LOGIN_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= settings.LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
            )


def _record_failure(key: str) -> None:
    with _attempts_lock:
        _attempts[key].append(time.monotonic())


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": normalize_role(user.role),
        "permissions": permissions_for(user.role),
        "badge_number": user.badge_number,
        "organization_id": user.organization_id,
        "organization_name": user.organization.name if user.organization else None,
    }


@router.post("/login", response_model=Token)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    key = f"{email}|{request.client.host if request.client else 'unknown'}"
    _check_rate_limit(key)

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        _record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    if needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(req.password)
    if user.role != normalize_role(user.role):
        user.role = normalize_role(user.role)
    db.commit()

    token = create_access_token(subject=user.id, role=user.role)
    return {"access_token": token, "token_type": "bearer", "user": user_payload(user)}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return user_payload(current_user)


@router.get("/config")
def get_auth_config():
    """Public login-page configuration. Demo accounts are only advertised in development."""
    demo = []
    if not settings.is_production and settings.SEED_DEMO_DATA:
        from app.core.bootstrap import DEMO_USERS
        demo = [{"email": u["email"], "role": u["role"], "password": settings.DEMO_PASSWORD} for u in DEMO_USERS]
    return {"environment": settings.ENVIRONMENT, "demo_accounts": demo}
