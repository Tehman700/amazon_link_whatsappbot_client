"""Server-to-server endpoints for the Beast Affiliates portal (website).

Guarded by the same shared secret as the hub mint API (HUB_SERVICE_KEY env).
Additive: nothing in the existing pipeline calls or depends on this router,
and with HUB_SERVICE_KEY unset every route here is closed (403).
"""

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/service", tags=["service"])


def require_service_key(x_service_key: str = Header(default="")) -> None:
    expected = os.getenv("HUB_SERVICE_KEY", "")
    if not expected or x_service_key != expected:
        raise HTTPException(status_code=403, detail="Service key required")


class PreferencesIn(BaseModel):
    link_preference: str | None = Field(default=None, pattern="^(direct|hub)$")
    store_name: str | None = Field(default=None, max_length=120)


def _find_user(number: str, db: Session) -> models.User:
    user = (
        db.query(models.User)
        .filter(models.User.whatsapp_number == number.strip())
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Number is not registered")
    return user


@router.get("/users/{number}", dependencies=[Depends(require_service_key)])
def get_user_by_number(number: str, db: Session = Depends(get_db)):
    user = _find_user(number, db)
    return {
        "name": user.name,
        "whatsapp_number": user.whatsapp_number,
        "link_preference": user.link_preference,
        "store_name": user.store_name,
    }


@router.put("/users/{number}/preferences", dependencies=[Depends(require_service_key)])
def update_preferences(number: str, payload: PreferencesIn, db: Session = Depends(get_db)):
    user = _find_user(number, db)
    if payload.link_preference is not None:
        user.link_preference = payload.link_preference
    if payload.store_name is not None:
        user.store_name = payload.store_name.strip()
    db.commit()
    return {
        "name": user.name,
        "whatsapp_number": user.whatsapp_number,
        "link_preference": user.link_preference,
        "store_name": user.store_name,
    }


@router.get("/users/{number}/linked", dependencies=[Depends(require_service_key)])
def list_linked_numbers(number: str, db: Session = Depends(get_db)):
    user = _find_user(number, db)
    linked = (
        db.query(models.LinkedNumber)
        .filter(models.LinkedNumber.user_id == user.id)
        .order_by(models.LinkedNumber.id)
        .all()
    )
    return {"primary": user.whatsapp_number,
            "linked": [ln.whatsapp_number for ln in linked]}


@router.delete(
    "/users/{number}/linked/{linked_number}",
    dependencies=[Depends(require_service_key)],
    status_code=204,
)
def unlink_number(number: str, linked_number: str, db: Session = Depends(get_db)):
    user = _find_user(number, db)
    row = (
        db.query(models.LinkedNumber)
        .filter(
            models.LinkedNumber.user_id == user.id,
            models.LinkedNumber.whatsapp_number == linked_number.strip(),
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Linked number not found")
    db.delete(row)
    db.commit()
