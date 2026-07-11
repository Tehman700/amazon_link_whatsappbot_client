"""Core link-rewrite engine.

Finds Amazon URLs inside freeform message text, detects the marketplace
from the URL's domain (against the admin-managed marketplaces table, not
a hardcoded list), and swaps in the sender's tracking tag for that
marketplace. Everything else in the text is passed through untouched.
"""

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


def rewrite_url(url: str, tag: str) -> str:
    """Set tag=<tag> on the URL, merging correctly with existing query params.

    Uses proper URL parsing, never string concatenation. An existing tag
    param (someone else's affiliate tag) is replaced.
    """
    parts = urlsplit(url)
    params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() != "tag"
    ]
    params.append(("tag", tag))
    query = urlencode(params, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


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
