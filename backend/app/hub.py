"""Client for the Beast Affiliates website's link-mint API (hub articles).

Used only for users whose link_preference is 'hub'. Every failure mode —
website down, timeout, bad key, product data unavailable — leaves the reply
exactly as the direct tagged Amazon link, so the live pipeline can never
break because of this feature. Unset HUB_API_URL disables the feature
entirely (safe pre-config deploy state).
"""

import os
from urllib.parse import parse_qs, urlsplit

import httpx

HUB_API_URL = os.getenv("HUB_API_URL", "").rstrip("/")
HUB_SERVICE_KEY = os.getenv("HUB_SERVICE_KEY", "")
# Mint can include a first-time scrape on the website side; keep headroom.
HUB_TIMEOUT_SECONDS = float(os.getenv("HUB_TIMEOUT_SECONDS", "25"))


def enabled() -> bool:
    return bool(HUB_API_URL)


def _tag_of(url: str) -> str:
    return (parse_qs(urlsplit(url).query).get("tag") or [""])[0]


async def swap_links_for_articles(text: str, replacements: list, user) -> str:
    """Replace each direct tagged Amazon URL in the reply with a hub article
    URL. Per-link best effort: a link whose mint fails stays direct."""
    if not enabled() or not replacements:
        return text

    store_name = (getattr(user, "store_name", "") or "").strip()
    sender = getattr(user, "whatsapp_number", "") or ""

    async with httpx.AsyncClient(timeout=HUB_TIMEOUT_SECONDS) as client:
        for r in replacements:
            try:
                resp = await client.post(
                    f"{HUB_API_URL}/api/links",
                    json={
                        "url": r.rewritten,
                        "tag": _tag_of(r.rewritten),
                        "store_name": store_name,
                        "sender": sender,
                    },
                    headers={"X-Service-Key": HUB_SERVICE_KEY},
                )
                if resp.status_code != 200:
                    continue
                article_url = (resp.json() or {}).get("article_url", "")
                if article_url:
                    text = text.replace(r.rewritten, article_url)
                    r.rewritten = article_url
            except Exception:
                continue  # this link stays as the direct tagged URL
    return text
