from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import has_permission
from app.core.security import decode_access_token
from app.models.all_models import DefectDetection, Inspection, User

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise unauthorized
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise unauthorized
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise unauthorized
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def require(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {permission}")
        return user
    return dependency


def get_org_inspection(db: Session, inspection_id: str, user: User, mode: Optional[str] = None) -> Inspection:
    """Object-level authorisation: an inspection outside the caller's organisation does not exist for them."""
    query = db.query(Inspection).filter(Inspection.id == inspection_id, Inspection.organization_id == user.organization_id)
    if mode:
        query = query.filter(Inspection.inspection_mode == mode)
    insp = query.first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return insp


def get_org_detection(db: Session, detection_id: str, user: User) -> DefectDetection:
    det = (
        db.query(DefectDetection)
        .join(Inspection, Inspection.id == DefectDetection.inspection_id)
        .filter(DefectDetection.id == detection_id, Inspection.organization_id == user.organization_id)
        .first()
    )
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")
    return det
