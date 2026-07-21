"""Client for the Beast Affiliates website's link-mint API (hub articles).

An article is published on the website for EVERY rewritten link, regardless
of the user's link_preference (owner decision 2026-07-20) — so it always
shows in their portal with its own view/click tracking. The WhatsApp reply
text is only swapped to the article URL for 'hub' users; 'direct' users keep
the tagged Amazon link in their reply while the article is still published.

Every failure mode — website down, timeout, bad key, product data
unavailable — leaves the reply exactly as the direct tagged Amazon link, so
the live pipeline can never break because of this feature. Unset HUB_API_URL
disables it entirely (safe pre-config deploy state).
"""

import os
import re
import time
from urllib.parse import parse_qs, urlsplit

import httpx

# Matches one of OUR article links in the user's original message, so the
# website can tell "this user forwarded their own article" and return that
# same article instead of duplicating it.
OUR_ARTICLE_RE = re.compile(
    r"https?://(?:www\.)?(?:beastaffiliates|beastassociate)\.com/(?:p|go)/([A-Za-z0-9]{4,8})",
    re.I,
)

HUB_API_URL = os.getenv("HUB_API_URL", "").rstrip("/")
HUB_SERVICE_KEY = os.getenv("HUB_SERVICE_KEY", "")
# The bot API runs inside a ~10s Vercel function. The whole hub swap must
# finish well inside that so a slow first-time scrape on the website side
# degrades to the direct link instead of killing the reply entirely.
# (Cached products mint in <1s; only brand-new products can be slow — the
# website keeps scraping/caching server-side, so the NEXT share is instant.)
HUB_BUDGET_SECONDS = float(os.getenv("HUB_BUDGET_SECONDS", "7.0"))


def enabled() -> bool:
    return bool(HUB_API_URL)


async def claim_link_code(code: str, sender: str) -> str | None:
    """Ask the website whether `code` is a valid, unexpired linking code.
    Returns the primary WhatsApp number it belongs to, or None (invalid code,
    website down, feature unconfigured — all silent no-ops for the caller)."""
    if not enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                f"{HUB_API_URL}/api/wa-codes/claim",
                json={"code": code, "sender": sender},
                headers={"X-Service-Key": HUB_SERVICE_KEY},
            )
        if resp.status_code != 200:
            return None
        return (resp.json() or {}).get("primary_number") or None
    except Exception:
        return None


def _tag_of(url: str) -> str:
    return (parse_qs(urlsplit(url).query).get("tag") or [""])[0]


async def publish_articles(
    text: str, replacements: list, user, swap_reply: bool
) -> str:
    """Publish an article for every rewritten link. When `swap_reply` is True
    (hub users) each tagged URL in the reply is replaced with its article URL;
    when False (direct users) the reply is untouched but the articles are
    still created. Per-link best effort within a time budget so a slow
    first-time scrape never delays a reply past the serverless limit."""
    if not enabled() or not replacements:
        return text

    store_name = (getattr(user, "store_name", "") or "").strip()
    sender = getattr(user, "whatsapp_number", "") or ""
    deadline = time.monotonic() + HUB_BUDGET_SECONDS

    async with httpx.AsyncClient() as client:
        for r in replacements:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                break  # budget spent — remaining articles skipped this send
            source = OUR_ARTICLE_RE.search(getattr(r, "original", "") or "")
            try:
                resp = await client.post(
                    f"{HUB_API_URL}/api/links",
                    json={
                        "url": r.rewritten,
                        "tag": _tag_of(r.rewritten),
                        "store_name": store_name,
                        "sender": sender,
                        "source_link_id": source.group(1) if source else "",
                    },
                    headers={"X-Service-Key": HUB_SERVICE_KEY},
                    timeout=remaining,
                )
                if resp.status_code != 200:
                    continue
                article_url = (resp.json() or {}).get("article_url", "")
                if article_url and swap_reply:
                    text = text.replace(r.rewritten, article_url)
                    r.rewritten = article_url
            except Exception:
                continue  # article not created this send; reply unaffected
    return text
