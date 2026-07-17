from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import hub, models, schemas
from ..database import get_db
from ..resolver import resolve_all
from ..rewriter import find_urls, process_text

router = APIRouter(tags=["process"])


@router.post("/process-message", response_model=schemas.ProcessResponse)
async def process_message(payload: schemas.ProcessRequest, db: Session = Depends(get_db)):
    user = (
        db.query(models.User)
        .filter(models.User.whatsapp_number == payload.sender.strip())
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Sender is not a registered user")

    domain_map = {m.domain.lower(): m for m in db.query(models.Marketplace).all()}
    tags = {t.marketplace_id: t.tag for t in user.tracking_ids}

    # Non-Amazon links (short links, blog/landing pages) -> the Amazon URL
    # they lead to, so they can be swapped for the tagged product link.
    resolved = await resolve_all(find_urls(payload.text), domain_map)

    new_text, replacements, skipped = process_text(
        payload.text, domain_map, tags, resolved
    )

    # Hub mode (opt-in per user): swap direct tagged links for article-page
    # links on the website. Fail-safe by design — any problem on the website
    # side leaves new_text exactly as built above (direct tagged links).
    if replacements and getattr(user, "link_preference", "direct") == "hub":
        try:
            new_text = await hub.swap_links_for_articles(new_text, replacements, user)
        except Exception:
            pass

    return schemas.ProcessResponse(
        text=new_text,
        links_replaced=len(replacements),
        replacements=[schemas.ReplacementOut(**vars(r)) for r in replacements],
        skipped=[schemas.SkippedOut(**vars(s)) for s in skipped],
    )
