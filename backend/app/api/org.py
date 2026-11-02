from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.database import get_db
from app.models.all_models import Inspection, Plant, Product, ProductionLine, Station, User
from app.schemas.all_schemas import (
    LineCreate, LineResponse, PlantCreate, PlantResponse, ProductCreate, ProductResponse, StationCreate,
    StationResponse
)

router = APIRouter(prefix="/org", tags=["Organisation Structure"])


def _plant(db: Session, plant_id: str, user: User) -> Plant:
    plant = db.query(Plant).filter(Plant.id == plant_id, Plant.organization_id == user.organization_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


def _line(db: Session, line_id: str, user: User) -> ProductionLine:
    line = db.get(ProductionLine, line_id)
    if not line or line.plant.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Line not found")
    return line


def _station(db: Session, station_id: str, user: User) -> Station:
    station = db.get(Station, station_id)
    if not station or station.line.plant.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


def _commit(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{what} with this name already exists")


@router.get("/tree", response_model=List[PlantResponse])
def get_org_tree(db: Session = Depends(get_db), user: User = Depends(require("org:read"))):
    """Plants -> lines -> stations, for selectors and the admin console."""
    return db.query(Plant).filter(Plant.organization_id == user.organization_id).order_by(Plant.name).all()


@router.post("/plants", response_model=PlantResponse, status_code=201)
def create_plant(req: PlantCreate, db: Session = Depends(get_db), user: User = Depends(require("org:manage"))):
    plant = Plant(organization_id=user.organization_id, name=req.name.strip(), location=req.location)
    db.add(plant)
    _commit(db, "Plant")
    db.refresh(plant)
    return plant


@router.post("/lines", response_model=LineResponse, status_code=201)
def create_line(req: LineCreate, db: Session = Depends(get_db), user: User = Depends(require("org:manage"))):
    plant = _plant(db, req.plant_id, user)
    line = ProductionLine(plant_id=plant.id, name=req.name.strip())
    db.add(line)
    _commit(db, "Line")
    db.refresh(line)
    return line


@router.post("/stations", response_model=StationResponse, status_code=201)
def create_station(req: StationCreate, db: Session = Depends(get_db), user: User = Depends(require("org:manage"))):
    line = _line(db, req.line_id, user)
    station = Station(line_id=line.id, name=req.name.strip(), camera_info=req.camera_info)
    db.add(station)
    _commit(db, "Station")
    db.refresh(station)
    return station


@router.patch("/stations/{station_id}", response_model=StationResponse)
def update_station(station_id: str, payload: dict = Body(...), db: Session = Depends(get_db),
                   user: User = Depends(require("org:manage"))):
    station = _station(db, station_id, user)
    if "name" in payload and str(payload["name"]).strip():
        station.name = str(payload["name"]).strip()[:255]
    if "camera_info" in payload:
        station.camera_info = payload["camera_info"]
    if "is_active" in payload:
        station.is_active = bool(payload["is_active"])
    _commit(db, "Station")
    db.refresh(station)
    return station


@router.delete("/stations/{station_id}", status_code=204)
def delete_station(station_id: str, db: Session = Depends(get_db), user: User = Depends(require("org:manage"))):
    station = _station(db, station_id, user)
    if db.query(Inspection).filter(Inspection.station_id == station.id).first():
        raise HTTPException(status_code=409, detail="Station has inspections; deactivate it instead")
    db.delete(station)
    db.commit()


@router.get("/products", response_model=List[ProductResponse])
def list_products(include_inactive: bool = False, db: Session = Depends(get_db), user: User = Depends(require("org:read"))):
    query = db.query(Product).filter(Product.organization_id == user.organization_id)
    if not include_inactive:
        query = query.filter(Product.is_active.is_(True))
    return query.order_by(Product.name).all()


@router.post("/products", response_model=ProductResponse, status_code=201)
def create_product(req: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require("org:manage"))):
    product = Product(organization_id=user.organization_id, sku=req.sku.strip(), name=req.name.strip(),
                      family=req.family, material=req.material)
    db.add(product)
    _commit(db, "Product SKU")
    db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: str, payload: dict = Body(...), db: Session = Depends(get_db),
                   user: User = Depends(require("org:manage"))):
    product = db.query(Product).filter(Product.id == product_id, Product.organization_id == user.organization_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field in ("name", "family", "material"):
        if field in payload:
            setattr(product, field, payload[field])
    if "is_active" in payload:
        product.is_active = bool(payload["is_active"])
    _commit(db, "Product")
    db.refresh(product)
    return product
