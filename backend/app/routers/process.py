import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import hub, message, models, schemas
from ..database import get_db
from ..resolver import resolve_all
from ..rewriter import (
    Replacement,
    build_from_asin,
    extract_asin,
    find_urls,
    process_text,
    tagged_product_link,
)

router = APIRouter(tags=["process"])


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off")


# Both new behaviours can be switched off from the environment without a code
# change, the way MUST_LINK_FEATURE was — if either one misreads a real message
# in production, it can be stopped in the time it takes to redeploy.
STRUCTURED_REPLY = _flag("STRUCTURED_REPLY")
ALWAYS_REPLY = _flag("ALWAYS_REPLY")

# Linking codes use an unambiguous alphabet (no 0/O/1/I) — see the website's
# code generator. A message must be EXACTLY one code to trigger a claim.
LINK_CODE_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")
# primary + 5 linked. MUST match MAX_WA_NUMBERS in the website's portal.py —
# the portal shows the allowance and hands out codes, this enforces it on claim.
MAX_NUMBERS_PER_USER = 6


def _keyword_reply(parsed, marketplace, tag: str) -> str:
    """A tagged search link, plus the client's disclaimer lines when they have
    supplied them, so nobody mistakes a search for a specific product."""
    link = message.search_url(marketplace.domain, parsed.keyword, tag)
    parts = [f"\U0001F50D {parsed.keyword}", link]
    if message.KEYWORD_DISCLAIMER:
        parts.append(message.KEYWORD_DISCLAIMER)
    parts.append(message.BRANDING)
    return "\n\n".join(parts)


def _explain(text: str, parsed, skipped, by_code: dict) -> str | None:
    """What to say when no link could be produced, or None to stay silent.

    Silence is still the right answer to "ok" or a sticker: replying to
    everything would roughly double what this number sends in a day, and
    answering messages nobody asked about is exactly what WhatsApp looks for
    when deciding something is a bot."""
    urls = find_urls(text)
    asin = extract_asin(text)
    trying = bool(urls or asin or parsed.country or parsed.fields)
    if not trying:
        return None

    # The sender has no tracking ID for a marketplace they linked to.
    if skipped:
        code = skipped[0].reason.rsplit(" ", 1)[-1]
        market = by_code.get(code)
        return message.say("no_tag", country=market.name if market else code)

    # A country we do not run, e.g. amazon.co.jp.
    if parsed.country and parsed.country not in by_code:
        return message.say(
            "unsupported_market", available=", ".join(sorted(by_code)),
        )

    # A link was sent but nothing Amazon came back from it.
    if urls:
        return message.say("unreadable_page")

    if not parsed.country:
        return message.say("no_country")
    if not asin and not parsed.keyword:
        return message.say("no_product")

    # Country and a product are both present, so the only thing left is that
    # this user has no tag for that country.
    market = by_code.get(parsed.country)
    return message.say("no_tag", country=market.name if market else parsed.country)


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
        return (f"You already have the maximum of {MAX_NUMBERS_PER_USER} WhatsApp "
                "numbers. Unlink one in your dashboard first.")
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
    resolved = await resolve_all(find_urls(payload.text), domain_map, db)

    new_text, replacements, skipped = process_text(
        payload.text, domain_map, tags, resolved
    )

    # Fallback: message had no link at all, but a labelled ASIN + market —
    # build the tagged link and prepend it. Silent unless everything resolves.
    if not replacements:
        fb_text, fb_replacements = build_from_asin(payload.text, domain_map, tags)
        if fb_replacements:
            new_text, replacements = fb_text, fb_replacements

    # Everything below only runs where the message could NOT be answered by the
    # code above — i.e. exactly where the bot used to say nothing at all. The
    # working path is untouched.
    parsed = message.parse(payload.text)
    by_code = {m.code: m for m in domain_map.values()}
    marketplace = by_code.get(parsed.country or "")

    if not replacements and marketplace is not None:
        tag = tags.get(marketplace.id)
        asin = extract_asin(payload.text)
        if tag and asin:
            # Same as the fallback above, but the country was written as a
            # flag, a bare name or a misspelling rather than "Market: X".
            link = tagged_product_link(marketplace, asin, tag)
            new_text = f"{link}\n{payload.text}"
            replacements = [
                Replacement(original=f"ASIN:{asin}", rewritten=link,
                            marketplace_code=marketplace.code)
            ]
        elif tag and parsed.keyword:
            # No product, but enough to search for one. A search link has no
            # ASIN, so it never becomes an article — it is returned as-is.
            # A task message still gets the client's layout: the forwarded ones
            # carry a seller and a price, and dropping to a bare search link
            # would throw away everything the sender wrote.
            if STRUCTURED_REPLY and parsed.is_task:
                text = message.format_task_reply(
                    parsed,
                    message.search_url(marketplace.domain, parsed.keyword, tag),
                    marketplace.code,
                    note=message.KEYWORD_DISCLAIMER,
                )
            else:
                text = _keyword_reply(parsed, marketplace, tag)
            return schemas.ProcessResponse(
                text=text, links_replaced=1, replacements=[], skipped=[],
            )

    # Always publish an article for every rewritten link so it appears in the
    # user's portal with its own view/click tracking. Only hub users get the
    # article URL in their WhatsApp reply; direct users keep the tagged Amazon
    # link. Fail-safe: any website-side problem leaves new_text as built above.
    # A review-task message gets the client's layout instead of an echo. Built
    # BEFORE the article swap on purpose: the block carries the tagged link, so
    # publish_articles finds and replaces it exactly as it would in any reply.
    if replacements and STRUCTURED_REPLY and parsed.is_task:
        new_text = message.format_task_reply(
            parsed,
            replacements[0].rewritten,
            parsed.country or replacements[0].marketplace_code,
        )

    if replacements:
        swap_reply = getattr(user, "link_preference", "direct") == "hub"
        try:
            new_text = await hub.publish_articles(
                new_text, replacements, user, swap_reply=swap_reply
            )
        except Exception:
            pass

    # Nothing could be produced. Say why, rather than leaving the sender
    # wondering — but only when they were actually trying to get a link.
    if not replacements and ALWAYS_REPLY:
        reply = _explain(payload.text, parsed, skipped, by_code)
        if reply:
            return schemas.ProcessResponse(
                text=reply, links_replaced=1, replacements=[], skipped=[]
            )

    return schemas.ProcessResponse(
        text=new_text,
        links_replaced=len(replacements),
        replacements=[schemas.ReplacementOut(**vars(r)) for r in replacements],
        skipped=[schemas.SkippedOut(**vars(s)) for s in skipped],
    )
