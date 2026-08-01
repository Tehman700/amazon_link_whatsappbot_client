"""Resolve non-Amazon links to the Amazon product URL they lead to.

Covers two real cases from the client's messages:
- Short links (amzn.to/...) that HTTP-redirect straight to a marketplace.
- Landing/blog pages (e.g. blogspot product posts) that contain a
  "View on Amazon" link somewhere in their HTML.

Everything is best-effort with tight timeouts: if a page can't be fetched
or holds no Amazon link, the original link is simply left untouched.
"""

import asyncio
import html
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from . import hub, link_cache
from .rewriter import match_marketplace

# Our own article/redirect links, so a forwarded link gets re-tagged to the
# new sender instead of being ignored.
OUR_HOSTS = ("beastaffiliates.com", "beastassociate.com")
OUR_LINK_RE = re.compile(r"/(?:p|go)/([A-Za-z0-9]{4,8})(?:/|$)")

URL_IN_HTML_RE = re.compile(r"https?://[^\s\"'<>\\]+")
_TRAILING = ".,;:!?)]}>'\""

# Known Amazon short-link hosts — always worth following their redirect.
# `link.amazon` is Amazon's own .amazon-TLD shortener, which affiliate blog
# templates now use instead of a plain marketplace URL: the page then contains
# NO amazon.com link at all, so without this the HTML scan finds nothing.
SHORT_HOSTS = {"amzn.to", "amzn.eu", "amzn.asia", "a.co", "link.amazon"}

MAX_HTML_BYTES = 1_500_000
REQUEST_TIMEOUT = httpx.Timeout(8.0)

# Blogspot and the WooCommerce storefronts throttle traffic from datacenter IP
# ranges, which is all a serverless host has. Measured on production, the same
# page succeeds roughly half the time on any single try, and a refusal comes
# back in about a second rather than timing out — so a couple of extra tries
# cost little and turn a coin flip into near-certainty.
RESOLVE_ATTEMPTS = int(os.getenv("RESOLVE_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RESOLVE_RETRY_DELAY", "0.7"))
# Ceiling on the whole resolve step so a message full of slow links can never
# push the reply past the serverless limit; whatever is left stays untouched.
RESOLVE_BUDGET_SECONDS = float(os.getenv("RESOLVE_BUDGET_SECONDS", "25.0"))
# A bare User-Agent gets refused by some hosts (WooCommerce storefronts return
# 403, Facebook 400). Sending the rest of what a real browser sends makes those
# pages return 200 so their Amazon link can be found.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
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
    client: httpx.AsyncClient,
    url: str,
    domain_map: dict[str, object],
    gone: set[str] | None = None,
) -> str | None:
    """Return the Amazon marketplace URL a non-Amazon link leads to, or None.

    `gone` collects links the host answered about definitively (a deleted blog
    or post), so the caller knows not to bother retrying them."""
    direct = await _site_specific(client, url, domain_map)
    if direct:
        return direct

    response = await _follow(client, url)
    if response is None:
        return None
    if response.status_code in (404, 410) and gone is not None:
        gone.add(url)  # the page is deleted, not throttled — retrying is waste

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
    urls: list[str], domain_map: dict[str, object], db: Session | None = None
) -> dict[str, str]:
    """Resolve every non-Amazon URL in the list; returns {original: amazon_url}.

    `db` enables the resolution cache; without it every link is fetched live,
    which is what the offline tests exercise."""
    to_resolve = [
        u
        for u in dict.fromkeys(urls)  # de-dupe, keep order
        if match_marketplace(_host(u), domain_map) is None
    ]
    if not to_resolve:
        return {}

    resolved: dict[str, str] = {}
    pending: list[str] = []
    stale: dict[str, str] = {}  # expired hits, kept as a fallback
    for url in to_resolve:
        cached, fresh = link_cache.get(db, url) if db is not None else (None, False)
        if cached and fresh:
            resolved[url] = cached
            continue
        if cached:
            stale[url] = cached
        pending.append(url)

    if not pending:
        return resolved  # every link already known — no network at all

    deadline = time.monotonic() + RESOLVE_BUDGET_SECONDS
    gone: set[str] = set()
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=HEADERS
    ) as client:
        for url in pending:
            target = None
            for attempt in range(RESOLVE_ATTEMPTS):
                if time.monotonic() >= deadline:
                    break  # budget spent — remaining links left untouched
                target = await resolve_amazon_url(client, url, domain_map, gone)
                if target or url in gone or attempt + 1 >= RESOLVE_ATTEMPTS:
                    break
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            if target:
                resolved[url] = target
                if db is not None:
                    link_cache.put(db, url, target)
            elif url in stale:
                # Refresh failed; the remembered answer beats no link at all.
                resolved[url] = stale[url]
    return resolved
