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

from . import hub
from .rewriter import match_marketplace

# Our own article/redirect links, so a forwarded link gets re-tagged to the
# new sender instead of being ignored.
OUR_HOSTS = ("beastaffiliates.com", "beastassociate.com")
OUR_LINK_RE = re.compile(r"/(?:p|go)/([A-Za-z0-9]{4,8})(?:/|$)")

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


async def _site_specific(
    client: httpx.AsyncClient, url: str, domain_map: dict[str, object]
) -> str | None:
    """Handlers for the client's own funnel sites, which are JS-rendered SPAs
    (their HTML contains no Amazon link to scan). Each handler calls the
    site's data API directly."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()

    # pointmarketing.shop/prodetail/<mongo-id> -> product JSON with .Link
    if host.endswith("pointmarketing.shop"):
        m = re.search(r"/(?:active)?prodetail/([a-f0-9]{24})", parts.path)
        if m:
            r = await _follow(
                client, f"https://pointmarketing.shop/api/products/{m.group(1)}"
            )
            if r is not None and r.status_code == 200:
                try:
                    link = (r.json().get("product") or {}).get("Link") or ""
                except ValueError:
                    link = ""
                if link and match_marketplace(_host(link), domain_map):
                    return link

    # OUR OWN article pages — beastaffiliates.com/p/<id>/<slug> (and the
    # /go/<id> buy link). A user forwarding another user's article link must
    # get it re-tagged to themselves, so we look up the underlying product via
    # the website's resolve API. That endpoint records NO view/click, so the
    # original creator's stats are untouched.
    if host.endswith(OUR_HOSTS):
        m = OUR_LINK_RE.search(parts.path)
        if m and hub.enabled():
            try:
                r = await client.get(
                    f"{hub.HUB_API_URL}/api/links/{m.group(1)}/resolve",
                    headers={"X-Service-Key": hub.HUB_SERVICE_KEY},
                )
            except httpx.HTTPError:
                return None
            if r.status_code == 200:
                try:
                    link = (r.json() or {}).get("amazon_url") or ""
                except ValueError:
                    link = ""
                if link and match_marketplace(_host(link), domain_map):
                    return link

    # ilearner.dev/link/<id> and ilearner-store.com/p/<id>[/slug]
    # -> api.ilearner.dev/go/<id> 302s straight to the Amazon URL
    if host == "ilearner.dev" or host.endswith((".ilearner.dev", "ilearner-store.com")):
        m = re.search(r"/(?:link|p)/([A-Za-z0-9_-]+)", parts.path)
        if m:
            try:
                r = await client.get(
                    f"https://api.ilearner.dev/go/{m.group(1)}", follow_redirects=False
                )
            except httpx.HTTPError:
                return None
            location = r.headers.get("location", "")
            if location and match_marketplace(_host(location), domain_map):
                return location

    return None


async def resolve_amazon_url(
    client: httpx.AsyncClient, url: str, domain_map: dict[str, object]
) -> str | None:
    """Return the Amazon marketplace URL a non-Amazon link leads to, or None."""
    direct = await _site_specific(client, url, domain_map)
    if direct:
        return direct

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
