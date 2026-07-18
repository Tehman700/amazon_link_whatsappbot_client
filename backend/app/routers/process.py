import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import hub, models, schemas
from ..database import get_db
from ..resolver import resolve_all
from ..rewriter import find_urls, process_text

router = APIRouter(tags=["process"])

# Linking codes use an unambiguous alphabet (no 0/O/1/I) — see the website's
# code generator. A message must be EXACTLY one code to trigger a claim.
LINK_CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")
MAX_NUMBERS_PER_USER = 3  # primary + 2 linked


async def _try_link_code(text: str, sender: str, db: Session) -> str | None:
    """If `text` is a valid linking code, link `sender` to its account and
    return the confirmation reply. None = not a code / invalid -> stay silent."""
    code = text.strip().upper()
    if not LINK_CODE_RE.match(code):
        return None
    primary_number = await hub.claim_link_code(code, sender)
    if not primary_number:
        return None
    primary = (
        db.query(models.User)
        .filter(models.User.whatsapp_number == primary_number)
        .first()
    )
    if primary is None:
        return None
    existing = (
        db.query(models.LinkedNumber)
        .filter(models.LinkedNumber.whatsapp_number == sender)
        .first()
    )
    if existing is not None:
        if existing.user_id == primary.id:
            return "✅ This number is already linked. Send any Amazon link to get started!"
        return None  # linked to a different account — silent
    linked_count = (
        db.query(models.LinkedNumber)
        .filter(models.LinkedNumber.user_id == primary.id)
        .count()
    )
    if 1 + linked_count >= MAX_NUMBERS_PER_USER:
        return ("You already have the maximum of 3 linked WhatsApp numbers. "
                "Unlink one in your dashboard first.")
    db.add(models.LinkedNumber(user_id=primary.id, whatsapp_number=sender))
    db.commit()
    return ("✅ Linked! This number is now connected to your Beast Affiliates "
            "account. Send any Amazon link to get your affiliate link.")


@router.post("/process-message", response_model=schemas.ProcessResponse)
async def process_message(payload: schemas.ProcessRequest, db: Session = Depends(get_db)):
    sender = payload.sender.strip()
    user = (
        db.query(models.User)
        .filter(models.User.whatsapp_number == sender)
        .first()
    )
    if user is None:
        # Secondary numbers linked via the portal behave exactly like the
        # primary (same tags/preference/attribution).
        linked = (
            db.query(models.LinkedNumber)
            .filter(models.LinkedNumber.whatsapp_number == sender)
            .first()
        )
        if linked is not None:
            user = linked.user
    if user is None:
        # Unregistered sender. One narrow carve-out from silence: a message
        # that is EXACTLY a 6-char linking code gets validated against the
        # website; anything else keeps the current silent-404 behavior.
        reply = await _try_link_code(payload.text, sender, db)
        if reply is not None:
            # links_replaced=1 with no replacements is deliberate: the adapter
            # only sends a reply when links_replaced > 0.
            return schemas.ProcessResponse(
                text=reply, links_replaced=1, replacements=[], skipped=[]
            )
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
