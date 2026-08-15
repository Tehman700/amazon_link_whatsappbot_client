"""Walmart product links, and turning them into affiliate links.

Walmart works nothing like Amazon. There is no tag to append: an affiliate link
is built by *wrapping* the product URL in an Impact tracking URL, and the person
who earns is identified by the publisher/campaign in that wrapper. Individual
users are told apart with a subId parameter, which is what lets the admin split
Walmart earnings the way Amazon's per-user tracking IDs do.

The publisher and campaign ids come from the client's Impact dashboard and live
in the environment, never here. Until they are set, `enabled()` is False and the
bot leaves Walmart links exactly as they arrived — the fail-safe habit used
everywhere else in this pipeline.
"""

import os
import re
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

# From the client's Impact account. A single generated link contains all three:
#   https://goto.walmart.com/c/<publisher>/<campaign>/<ad>?...&u=<product url>
PUBLISHER_ID = os.getenv("WALMART_PUBLISHER_ID", "").strip()
CAMPAIGN_ID = os.getenv("WALMART_CAMPAIGN_ID", "").strip()
AD_ID = os.getenv("WALMART_AD_ID", "9383").strip()
# Which subId slot the client's Impact reporting is grouped by.
SUB_ID_PARAM = os.getenv("WALMART_SUBID_PARAM", "subId1").strip() or "subId1"

IMPACT_HOST = "goto.walmart.com"

# /ip/<seo-slug>/<itemId> and the shorter /ip/<itemId>. Walmart item ids are
# numeric and run to about 11 digits.
ITEM_PATH_RE = re.compile(r"/ip/(?:[^/]+/)?(\d{5,15})(?=[/?#]|$)")

# Params that change which product is shown; everything else is tracking noise.
KEEP_PARAMS = {"variantfieldid", "selected", "athbdg"}


def enabled() -> bool:
    """True once the client's Impact ids are configured."""
    return bool(PUBLISHER_ID and CAMPAIGN_ID)


def is_impact_link(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower().endswith(IMPACT_HOST)


def unwrap(url: str) -> str:
    """The product URL inside an existing affiliate link.

    Someone else's Impact link carries the product in its `u=` parameter, and
    rebuilding from that is how a forwarded link gets re-attributed to the
    sender — the same thing replacing a foreign `tag=` does for Amazon.
    """
    if not is_impact_link(url):
        return url
    target = parse_qs(urlsplit(url).query).get("u", [""])[0]
    return target or url


def item_id(url: str) -> str | None:
    """The Walmart item id in a product URL, or None if it is not one."""
    m = ITEM_PATH_RE.search(urlsplit(unwrap(url)).path or "")
    return m.group(1) if m else None


def product_url(url: str) -> str:
    """The product URL stripped of tracking, ready to be wrapped.

    Rebuilt as /ip/<itemId> when the id is recognisable — Walmart resolves that
    on its own, and it keeps the shared link short and free of whatever
    campaign junk the sender's copy carried.
    """
    inner = unwrap(url)
    parts = urlsplit(inner)
    item = item_id(inner)
    if item:
        return f"https://www.walmart.com/ip/{item}"
    kept = [
        (k, v)
        for k, v in parse_qs(parts.query).items()
        if k.lower() in KEEP_PARAMS
    ]
    query = urlencode({k: v[0] for k, v in kept}, quote_via=quote)
    host = parts.netloc or "www.walmart.com"
    return urlunsplit((parts.scheme or "https", host, parts.path, query, ""))


def affiliate_url(url: str, sub_id: str) -> str:
    """Wrap a Walmart product URL as this user's affiliate link.

    Returns the URL untouched when the Impact ids are not configured: a link
    that earns the client nothing is still better than a broken one, and it
    means switching Walmart on is an environment change rather than a deploy.
    """
    if not enabled():
        return url
    target = product_url(url)
    query = urlencode(
        {"veh": "aff", "u": target, SUB_ID_PARAM: sub_id}, quote_via=quote
    )
    return f"https://{IMPACT_HOST}/c/{PUBLISHER_ID}/{CAMPAIGN_ID}/{AD_ID}?{query}"
