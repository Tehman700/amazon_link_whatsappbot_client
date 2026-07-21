from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/users", tags=["users"])


def _get_user_or_404(user_id: int, db: Session) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    apply_defaults = data.pop("apply_default_tags", False)
    user = models.User(**data)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="WhatsApp number already registered")
    db.refresh(user)

    # Pre-fill tracking IDs from each marketplace's built-in default so the
    # admin only has to edit the ones that differ.
    if apply_defaults:
        for m in db.query(models.Marketplace).all():
            if (m.default_tag or "").strip():
                db.add(models.TrackingID(
                    user_id=user.id, marketplace_id=m.id, tag=m.default_tag.strip()
                ))
        db.commit()
        db.refresh(user)
    return user


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _get_user_or_404(user_id, db)


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, payload: schemas.UserCreate, db: Session = Depends(get_db)):
    user = _get_user_or_404(user_id, db)
    data = payload.model_dump()
    data.pop("apply_default_tags", None)  # create-only flag
    for key, value in data.items():
        setattr(user, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="WhatsApp number already registered")
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = _get_user_or_404(user_id, db)
    db.delete(user)
    db.commit()


@router.put("/{user_id}/tracking-ids", response_model=schemas.UserOut)
def set_tracking_ids(
    user_id: int, payload: list[schemas.TrackingIDSet], db: Session = Depends(get_db)
):
    """Upsert the user's tracking IDs. Sending an empty tag is not allowed;
    omit a marketplace to leave it unset, existing entries not present in the
    payload are kept as-is."""
    user = _get_user_or_404(user_id, db)
    existing = {t.marketplace_id: t for t in user.tracking_ids}

    for item in payload:
        if db.get(models.Marketplace, item.marketplace_id) is None:
            raise HTTPException(
                status_code=404, detail=f"Marketplace {item.marketplace_id} not found"
            )
        if item.marketplace_id in existing:
            existing[item.marketplace_id].tag = item.tag.strip()
        else:
            db.add(
                models.TrackingID(
                    user_id=user.id,
                    marketplace_id=item.marketplace_id,
                    tag=item.tag.strip(),
                )
            )

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}/tracking-ids/{marketplace_id}", status_code=204)
def delete_tracking_id(user_id: int, marketplace_id: int, db: Session = Depends(get_db)):
    user = _get_user_or_404(user_id, db)
    entry = next(
        (t for t in user.tracking_ids if t.marketplace_id == marketplace_id), None
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Tracking ID not found")
    db.delete(entry)
    db.commit()
