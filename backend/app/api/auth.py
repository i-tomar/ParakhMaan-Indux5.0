from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_and_upgrade, get_password_hash, create_access_token, decode_access_token
from app.models.all_models import User
from app.schemas.all_schemas import Token, LoginRequest, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
security_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        if not settings.AUTH_REQUIRED:
            return _anonymous_operator(db)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired authentication credentials")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")
    return user


def _anonymous_operator(db: Session) -> User:
    """Only reachable with AUTH_REQUIRED=false (local test runs): gets a user with an unusable password."""
    user = db.query(User).filter(User.email == "operator@local").first()
    if not user:
        user = User(email="operator@local", full_name="Local Operator", hashed_password="!", role="ADMIN")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def require_roles(*roles: str):
    """Route dependency: ADMIN always passes, others must hold one of `roles`."""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != "ADMIN" and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires role: {', '.join(roles)}")
        return user
    return checker


DEMO_ACCOUNTS = [
    ("inspector@gov.in", "Quality Inspector", "INSPECTOR"),
    ("supervisor@gov.in", "Line Supervisor", "SUPERVISOR"),
    ("admin@gov.in", "Plant Administrator", "ADMIN"),
]


def ensure_demo_accounts(db: Session) -> None:
    """Creates the demo logins with DEMO_PASSWORD. Does nothing unless DEMO_MODE is on."""
    if not settings.DEMO_MODE or not settings.DEMO_PASSWORD:
        return
    for email, name, role in DEMO_ACCOUNTS:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, full_name=name, role=role, badge_number="DEMO", hashed_password="!")
            db.add(user)
        user.hashed_password = get_password_hash(settings.DEMO_PASSWORD)
    db.commit()


@router.post("/login", response_model=Token)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    ensure_demo_accounts(db)
    user = db.query(User).filter(User.email == req.email).first()
    # Same reply for unknown user and wrong password, so accounts cannot be enumerated.
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    valid, upgraded = verify_and_upgrade(req.password, user.hashed_password)
    if not valid:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if upgraded:
        user.hashed_password = upgraded
        db.commit()

    token = create_access_token(subject=user.id, role=user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "badge_number": user.badge_number
        }
    }


@router.post("/register", response_model=UserResponse)
def register(req: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    user = User(
        email=req.email,
        full_name=req.full_name,
        hashed_password=get_password_hash(req.password),
        role=req.role,
        badge_number=req.badge_number
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
