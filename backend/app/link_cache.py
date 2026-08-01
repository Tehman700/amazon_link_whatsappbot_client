"""Remembered page -> Amazon URL resolutions.

Reading a blog/landing page is the one step in the pipeline that depends on a
third party being willing to answer us, and from a serverless datacenter IP
they often are not. Caching turns that coin-flip into a one-time cost: the
first send of a link pays for the fetch, every later send of the same link
costs nothing and cannot fail.

Entries expire so an edited post can start pointing somewhere new — but a
failed refresh falls back to the stored answer rather than dropping the link,
keeping the pipeline's fail-safe habit of never making things worse.
"""

import hashlib
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from . import models

CACHE_TTL = timedelta(days=int(os.getenv("RESOLVE_CACHE_TTL_DAYS", "30")))


def _key(url: str) -> str:
    """Hash of the URL, ignoring only the parts that cannot change which
    product a page shows: case in the host, the fragment, a trailing slash.
    The query string is kept — some funnel sites identify the product there."""
    parts = urlsplit(url.strip())
    normalized = urlunsplit(
        (
            parts.scheme.lower(),
            (parts.netloc or "").lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def get(db: Session, url: str) -> tuple[str | None, bool]:
    """Return (amazon_url, is_fresh); (None, False) when the link is unknown.
    A stale hit is still returned so the caller can fall back to it."""
    try:
        row = (
            db.query(models.ResolvedLink)
            .filter(models.ResolvedLink.source_hash == _key(url))
            .first()
        )
    except Exception:
        return None, False  # cache is an optimization, never a hard dependency
    if row is None:
        return None, False
    return row.amazon_url, (datetime.utcnow() - row.resolved_at) < CACHE_TTL


def put(db: Session, url: str, amazon_url: str) -> None:
    """Remember a successful resolution. Silently gives up on any DB problem,
    including two concurrent sends of the same link racing to insert it."""
    key = _key(url)
    try:
        row = (
            db.query(models.ResolvedLink)
            .filter(models.ResolvedLink.source_hash == key)
            .first()
        )
        if row is None:
            db.add(
                models.ResolvedLink(
                    source_hash=key,
                    source_url=url[:2048],
                    amazon_url=amazon_url[:2048],
                )
            )
        else:
            row.amazon_url = amazon_url[:2048]
            row.resolved_at = datetime.utcnow()
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
