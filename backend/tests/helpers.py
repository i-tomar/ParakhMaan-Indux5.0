from functools import lru_cache

from fastapi.testclient import TestClient

from app.core.bootstrap import DEMO_USERS, run_bootstrap
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app

ROLE_EMAILS = {u["role"]: u["email"] for u in DEMO_USERS}


@lru_cache(maxsize=1)
def _bootstrapped() -> bool:
    db = SessionLocal()
    try:
        run_bootstrap(db)
    finally:
        db.close()
    return True


@lru_cache(maxsize=None)
def token_for(role: str) -> str:
    _bootstrapped()
    resp = TestClient(app).post(
        "/api/v1/auth/login", json={"email": ROLE_EMAILS[role], "password": settings.DEMO_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def client_for(role: str = "ADMIN") -> TestClient:
    """A TestClient authenticated as the seeded demo user with the given role."""
    return TestClient(app, headers={"Authorization": f"Bearer {token_for(role)}"})


def anonymous_client() -> TestClient:
    _bootstrapped()
    return TestClient(app)
