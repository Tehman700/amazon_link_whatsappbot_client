from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


def _normalize(payload: schemas.MarketplaceCreate) -> dict:
    data = payload.model_dump()
    data["code"] = data["code"].strip().upper()
    data["domain"] = data["domain"].strip().lower().removeprefix("www.")
    return data


@router.get("", response_model=list[schemas.MarketplaceOut])
def list_marketplaces(db: Session = Depends(get_db)):
    return db.query(models.Marketplace).order_by(models.Marketplace.id).all()


@router.post("", response_model=schemas.MarketplaceOut, status_code=201)
def create_marketplace(payload: schemas.MarketplaceCreate, db: Session = Depends(get_db)):
    marketplace = models.Marketplace(**_normalize(payload))
    db.add(marketplace)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Code or domain already exists")
    db.refresh(marketplace)
    return marketplace


@router.put("/{marketplace_id}", response_model=schemas.MarketplaceOut)
def update_marketplace(
    marketplace_id: int, payload: schemas.MarketplaceCreate, db: Session = Depends(get_db)
):
    marketplace = db.get(models.Marketplace, marketplace_id)
    if marketplace is None:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    for key, value in _normalize(payload).items():
        setattr(marketplace, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Code or domain already exists")
    db.refresh(marketplace)
    return marketplace


@router.delete("/{marketplace_id}", status_code=204)
def delete_marketplace(marketplace_id: int, db: Session = Depends(get_db)):
    marketplace = db.get(models.Marketplace, marketplace_id)
    if marketplace is None:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    db.delete(marketplace)
    db.commit()
