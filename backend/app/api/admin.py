from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.database import get_db
from app.core.permissions import ADMIN, ROLES, normalize_role
from app.core.security import generate_device_key, get_password_hash
from app.models.all_models import EdgeDevice, Station, User
from app.schemas.all_schemas import EdgeDeviceCreate, EdgeDeviceResponse, UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/admin", tags=["Administration"])


def _validate_role(role: str) -> str:
    role = normalize_role(role)
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {', '.join(ROLES)}")
    return role


def _org_user(db: Session, user_id: str, admin: User) -> User:
    user = db.query(User).filter(User.id == user_id, User.organization_id == admin.organization_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------- users
@router.get("/users", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require("user:manage"))):
    return db.query(User).filter(User.organization_id == admin.organization_id).order_by(User.email).all()


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(req: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require("user:manage"))):
    email = req.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = User(email=email, full_name=req.full_name, role=_validate_role(req.role),
                badge_number=req.badge_number, organization_id=admin.organization_id,
                hashed_password=get_password_hash(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: str, req: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require("user:manage"))):
    user = _org_user(db, user_id, admin)
    new_role = _validate_role(req.role) if req.role else user.role
    deactivating = req.is_active is False
    if user.id == admin.id and (deactivating or new_role != ADMIN):
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator access")
    if req.full_name:
        user.full_name = req.full_name
    if req.badge_number is not None:
        user.badge_number = req.badge_number
    if req.password:
        user.hashed_password = get_password_hash(req.password)
    if req.is_active is not None:
        user.is_active = req.is_active
    user.role = new_role
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------- edge devices
def _org_device(db: Session, device_id: str, admin: User) -> EdgeDevice:
    device = db.query(EdgeDevice).filter(EdgeDevice.id == device_id, EdgeDevice.organization_id == admin.organization_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/devices", response_model=List[EdgeDeviceResponse])
def list_devices(db: Session = Depends(get_db), admin: User = Depends(require("org:manage"))):
    return db.query(EdgeDevice).filter(EdgeDevice.organization_id == admin.organization_id).order_by(EdgeDevice.name).all()


@router.post("/devices", status_code=201)
def create_device(req: EdgeDeviceCreate, db: Session = Depends(get_db), admin: User = Depends(require("org:manage"))):
    if req.station_id:
        station = db.get(Station, req.station_id)
        if not station or station.line.plant.organization_id != admin.organization_id:
            raise HTTPException(status_code=400, detail="Unknown station")
    key, prefix, key_hash = generate_device_key()
    device = EdgeDevice(organization_id=admin.organization_id, station_id=req.station_id, name=req.name,
                        key_prefix=prefix, key_hash=key_hash)
    db.add(device)
    db.commit()
    db.refresh(device)
    # The plaintext key is returned once; only its hash is stored.
    return {"device": EdgeDeviceResponse.model_validate(device), "device_key": key}


@router.post("/devices/{device_id}/rotate-key")
def rotate_device_key(device_id: str, db: Session = Depends(get_db), admin: User = Depends(require("org:manage"))):
    device = _org_device(db, device_id, admin)
    key, prefix, key_hash = generate_device_key()
    device.key_prefix, device.key_hash = prefix, key_hash
    db.commit()
    db.refresh(device)
    return {"device": EdgeDeviceResponse.model_validate(device), "device_key": key}


@router.patch("/devices/{device_id}", response_model=EdgeDeviceResponse)
def update_device(device_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require("org:manage"))):
    device = _org_device(db, device_id, admin)
    if "is_active" in payload:
        device.is_active = bool(payload["is_active"])
    if "name" in payload and str(payload["name"]).strip():
        device.name = str(payload["name"]).strip()[:255]
    db.commit()
    db.refresh(device)
    return device
