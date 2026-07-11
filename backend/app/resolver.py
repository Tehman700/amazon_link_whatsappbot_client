"""Resolve non-Amazon links to the Amazon product URL they lead to.

Covers two real cases from the client's messages:
- Short links (amzn.to/...) that HTTP-redirect straight to a marketplace.
- Landing/blog pages (e.g. blogspot product posts) that contain a
  "View on Amazon" link somewhere in their HTML.

Everything is best-effort with tight timeouts: if a page can't be fetched
or holds no Amazon link, the original link is simply left untouched.
"""

import html
import re
from urllib.parse import urlsplit

import httpx

from .rewriter import match_marketplace

URL_IN_HTML_RE = re.compile(r"https?://[^\s\"'<>\\]+")
_TRAILING = ".,;:!?)]}>'\""

# Known Amazon short-link hosts — always worth following their redirect.
SHORT_HOSTS = {"amzn.to", "amzn.eu", "amzn.asia", "a.co"}

MAX_HTML_BYTES = 1_500_000
REQUEST_TIMEOUT = httpx.Timeout(8.0)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


async def _follow(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        return await client.get(url)
    except httpx.HTTPError:
        return None


async def resolve_amazon_url(
    client: httpx.AsyncClient, url: str, domain_map: dict[str, object]
) -> str | None:
    """Return the Amazon marketplace URL a non-Amazon link leads to, or None."""
    response = await _follow(client, url)
    if response is None:
        return None

    # Case 1: redirects landed directly on a marketplace (amzn.to etc.)
    final_url = str(response.url)
    if match_marketplace(_host(final_url), domain_map):
        return final_url

    # Case 2: scan the page HTML for the first Amazon link
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type:
        return None
    page = html.unescape(response.text[:MAX_HTML_BYTES])
    candidates = [c.rstrip(_TRAILING) for c in URL_IN_HTML_RE.findall(page)]

    for candidate in candidates:
        if match_marketplace(_host(candidate), domain_map):
            return candidate

    # Case 3: the page links out via an Amazon short link — follow it
    for candidate in candidates:
        if _host(candidate) in SHORT_HOSTS:
            inner = await _follow(client, candidate)
            if inner is not None and match_marketplace(_host(str(inner.url)), domain_map):
                return str(inner.url)

    return None


async def resolve_all(
    urls: list[str], domain_map: dict[str, object]
) -> dict[str, str]:
    """Resolve every non-Amazon URL in the list; returns {original: amazon_url}."""
    to_resolve = [
        u
        for u in dict.fromkeys(urls)  # de-dupe, keep order
        if match_marketplace(_host(u), domain_map) is None
    ]
    if not to_resolve:
        return {}

    resolved: dict[str, str] = {}
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=HEADERS
    ) as client:
        for url in to_resolve:
            target = await resolve_amazon_url(client, url, domain_map)
            if target:
                resolved[url] = target
    return resolved
