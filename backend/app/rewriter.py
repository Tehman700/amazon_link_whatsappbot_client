"""Core link-rewrite engine.

Finds Amazon URLs inside freeform message text, detects the marketplace
from the URL's domain (against the admin-managed marketplaces table, not
a hardcoded list), and swaps in the sender's tracking tag for that
marketplace. Everything else in the text is passed through untouched.
"""

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Characters that are commonly sentence punctuation rather than part of a URL
# when they appear at the very end of a match.
_TRAILING_PUNCT = ".,;:!?)]}>'\""


@dataclass
class Replacement:
    original: str
    rewritten: str
    marketplace_code: str


@dataclass
class SkippedLink:
    url: str
    reason: str


def _clean_url_match(raw: str) -> str:
    return raw.rstrip(_TRAILING_PUNCT)


def match_marketplace(host: str | None, domain_map: dict[str, object]):
    """Match a hostname against marketplace domains.

    Accepts the exact domain or any subdomain of it (www.amazon.de,
    smile.amazon.com). Longest domain wins so amazon.com.au is never
    mistaken for amazon.com.
    """
    if not host:
        return None
    host = host.lower().split(":")[0]
    for domain in sorted(domain_map, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return domain_map[domain]
    return None


def find_urls(text: str) -> list[str]:
    """All URLs present in the text, trailing punctuation stripped."""
    return [_clean_url_match(m.group(0)) for m in URL_RE.finditer(text)]


# Amazon product id (ASIN) in a URL path: /dp/<ASIN>, /gp/product/<ASIN>, ...
ASIN_PATH_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?=[/?]|$)")

# Query params that change what the customer sees/buys — everything else
# (ref, social_share, rsd, edk, linkCode, ...) is share-tracking residue.
KEEP_PARAMS = {"th", "psc", "smid", "m"}


def rewrite_url(url: str, tag: str) -> str:
    """Set tag=<tag> on the URL, merging correctly with existing query params.

    When the URL contains a recognizable product id (ASIN), it is rebuilt in
    canonical short form — https://<host>/dp/<ASIN>?tag=... — keeping only
    params that affect the product shown (KEEP_PARAMS). Share links carry
    hundreds of chars of tracking junk that does nothing for attribution;
    the tag param is all Amazon's affiliate system reads.

    Without a confident ASIN match, falls back to the original URL with the
    tag merged in (previous behavior). An existing tag param (someone else's
    affiliate tag) is replaced in both paths. Proper URL parsing throughout,
    never string concatenation.
    """
    parts = urlsplit(url)
    asin = ASIN_PATH_RE.search(parts.path)

    if asin:
        params = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() in KEEP_PARAMS
        ]
        params.append(("tag", tag))
        query = urlencode(params, quote_via=quote)
        return urlunsplit((parts.scheme, parts.netloc, f"/dp/{asin.group(1)}", query, ""))

    params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() != "tag"
    ]
    params.append(("tag", tag))
    query = urlencode(params, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


# ---- ASIN + Market fallback (messages with no link at all) ----
#
# Some senders forward a product with NO url, but a labelled ASIN and market,
# e.g.  "Market:UK ... ASIN: B0H3ZGX6YQ ...". When the normal pipeline finds
# no link to rewrite, we reconstruct the Amazon link from (marketplace, ASIN)
# and prepend it. Requires BOTH a confident ASIN and a resolvable market AND
# the sender having a tag for it — otherwise stay silent (no guessing).

ASIN_LABELED_RE = re.compile(r"\bASIN\b\s*[:#\-]?\s*([A-Za-z0-9]{10})\b", re.IGNORECASE)
ASIN_BARE_RE = re.compile(r"\bB0[A-Z0-9]{8}\b")
MARKET_RE = re.compile(r"\bmarket\b\s*[:#\-]?\s*([A-Za-z][A-Za-z .]{0,30})", re.IGNORECASE)

# Common ways senders name a marketplace that aren't the DB code or full name.
MARKET_ALIASES = {
    "usa": "US", "america": "US", "unitedstates": "US", "us": "US",
    "uk": "UK", "unitedkingdom": "UK", "britain": "UK", "england": "UK",
    "germany": "DE", "deutschland": "DE",
    "france": "FR", "italy": "IT", "italia": "IT", "spain": "ES", "espana": "ES",
    "netherlands": "NL", "holland": "NL", "australia": "AU", "canada": "CA",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def extract_asin(text: str) -> str | None:
    """First labelled ASIN (uppercased), else a bare B0######## token."""
    m = ASIN_LABELED_RE.search(text)
    if m:
        return m.group(1).upper()
    m = ASIN_BARE_RE.search(text)
    return m.group(0).upper() if m else None


def _resolve_market(text: str, market_index: dict[str, object]):
    """Match the 'Market: X' line against marketplaces by code / name / alias."""
    m = MARKET_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    for key in (_norm(raw), _norm(raw.split()[0]) if raw.split() else ""):
        if not key:
            continue
        if key in market_index:
            return market_index[key]
        alias = MARKET_ALIASES.get(key)
        if alias and alias.lower() in market_index:
            return market_index[alias.lower()]
    return None


def build_from_asin(
    text: str,
    domain_map: dict[str, object],
    tags_by_marketplace_id: dict[int, str],
) -> tuple[str, list[Replacement]]:
    """When the message has no link: build a tagged Amazon link from a
    labelled ASIN + market and prepend it. Returns ("", []) to stay silent
    unless ASIN, market, and the sender's tag for that market all resolve."""
    asin = extract_asin(text)
    if not asin:
        return "", []

    market_index: dict[str, object] = {}
    for mp in domain_map.values():
        market_index[_norm(mp.code)] = mp
        market_index[_norm(mp.name)] = mp
    marketplace = _resolve_market(text, market_index)
    if marketplace is None:
        return "", []

    tag = tags_by_marketplace_id.get(marketplace.id)
    if tag is None:
        return "", []

    link = urlunsplit(
        ("https", f"www.{marketplace.domain}", f"/dp/{asin}",
         urlencode([("tag", tag)], quote_via=quote), "")
    )
    new_text = f"{link}\n{text}"
    replacement = Replacement(
        original=f"ASIN:{asin}", rewritten=link, marketplace_code=marketplace.code
    )
    return new_text, [replacement]


def process_text(
    text: str,
    domain_map: dict[str, object],
    tags_by_marketplace_id: dict[int, str],
    resolved: dict[str, str] | None = None,
) -> tuple[str, list[Replacement], list[SkippedLink]]:
    """Replace every Amazon link in the text with its tagged version.

    domain_map: marketplace domain -> Marketplace row (or any object with
    .id and .code), built from the marketplaces table.
    tags_by_marketplace_id: the sender's tags, keyed by marketplace id.
    resolved: optional map of non-Amazon URL found in the text -> the Amazon
    URL it leads to (from the resolver: amzn.to redirects, blog/landing pages
    with a "View on Amazon" link). The original URL in the message is replaced
    by the tagged Amazon URL.

    Non-Amazon URLs that resolve to nothing, and URLs on marketplaces the
    sender has no tag for, are left untouched (the latter is reported in
    skipped).
    """
    resolved = resolved or {}
    replacements: list[Replacement] = []
    skipped: list[SkippedLink] = []
    out: list[str] = []
    last_end = 0

    for match in URL_RE.finditer(text):
        url = _clean_url_match(match.group(0))
        end = match.start() + len(url)

        target = url
        marketplace = match_marketplace(urlsplit(url).hostname, domain_map)
        if marketplace is None and url in resolved:
            target = resolved[url]
            marketplace = match_marketplace(urlsplit(target).hostname, domain_map)
        if marketplace is None:
            continue  # not an Amazon marketplace URL — leave as-is

        tag = tags_by_marketplace_id.get(marketplace.id)
        if tag is None:
            skipped.append(
                SkippedLink(
                    url=url,
                    reason=f"sender has no tracking ID for marketplace {marketplace.code}",
                )
            )
            continue

        new_url = rewrite_url(target, tag)
        out.append(text[last_end : match.start()])
        out.append(new_url)
        last_end = end
        replacements.append(
            Replacement(
                original=url, rewritten=new_url, marketplace_code=marketplace.code
            )
        )

    out.append(text[last_end:])
    return "".join(out), replacements, skipped


# --------------------------------------------------------- MUST_LINK_FEATURE
#
# Appends a call-to-action line to every reply that contains a rewritten link,
# for both reply styles (tagged Amazon link and hub article link).
#
# Controlled by the MUST_LINK_FEATURE env var. Set it to any of
# 0 / false / no / off to switch the feature off — replies then go out exactly
# as they did before the feature existed. Read per call, so flipping the env
# var and redeploying is the whole off switch; no other code changes needed.

MUST_LINK_TEXT = "*Order Through above Link 🔗 otherwise Order not accepted❌❌❌❌*"

# Wordings we've used before. Kept so a forwarded copy of an older reply is
# recognized as already carrying the line instead of collecting a second one.
_PAST_MUST_LINK_TEXTS = (
    MUST_LINK_TEXT,
    "*MUST BUY USING THIS ABOVE LINK*",
)

_OUR_ARTICLE_HOSTS = ("beastaffiliates.com", "beastassociate.com")


def must_link_enabled() -> bool:
    return os.getenv("MUST_LINK_FEATURE", "true").strip().lower() not in (
        "0", "false", "no", "off", "",
    )


def _is_our_link(url: str, domain_map: dict[str, object]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in _OUR_ARTICLE_HOSTS):
        return True
    return match_marketplace(host, domain_map) is not None


def append_must_link(
    text: str, link_count: int, domain_map: dict[str, object] | None = None
) -> str:
    """Add the call-to-action line to a reply that carries link_count links.

    One link  -> at the end of the line the link sits on, so a sentence that
                 continues below the link is never split in half.
    Several   -> once at the very end of the whole reply.
    """
    if not must_link_enabled() or link_count < 1:
        return text
    if any(t in text for t in _PAST_MUST_LINK_TEXTS):
        return text  # forwarded copy of one of our own replies

    if link_count == 1:
        domain_map = domain_map or {}
        ours = [m for m in URL_RE.finditer(text)
                if _is_our_link(_clean_url_match(m.group(0)), domain_map)]
        if ours:
            line_end = text.find("\n", ours[-1].end())
            if line_end != -1:
                return f"{text[:line_end]}\n\n{MUST_LINK_TEXT}{text[line_end:]}"

    return f"{text.rstrip()}\n\n{MUST_LINK_TEXT}"
