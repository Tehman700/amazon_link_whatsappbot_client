"""Understanding the messages people actually send, and answering them.

The rewrite engine in `rewriter.py` handles links. This handles everything
around them: working out which country a message is about when it is written
five different ways, pulling out the fields of a review task, laying the reply
out the way the client's template does, and saying something useful when the
message cannot be answered.

Deliberately pure — no database, no network, no clock. Every function here can
be exercised offline, which matters because this code decides what 60 people
see on WhatsApp.
"""

import difflib
import os
import re

# ---------------------------------------------------------------- flags

# 🇺🇸 is two "regional indicator" letters, so a flag decodes straight back to
# its ISO country code. GB is the odd one out: the flag says GB, our
# marketplace table says UK.
_FLAG_PAIR_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
_ISO_TO_MARKET = {"GB": "UK"}

CODE_TO_FLAG = {
    "US": "\U0001F1FA\U0001F1F8", "UK": "\U0001F1EC\U0001F1E7",
    "CA": "\U0001F1E8\U0001F1E6", "DE": "\U0001F1E9\U0001F1EA",
    "FR": "\U0001F1EB\U0001F1F7", "IT": "\U0001F1EE\U0001F1F9",
    "ES": "\U0001F1EA\U0001F1F8", "NL": "\U0001F1F3\U0001F1F1",
    "AU": "\U0001F1E6\U0001F1FA",
}


def flags_in(text: str) -> list[str]:
    """Marketplace codes for any flag emoji in the text."""
    out = []
    for pair in _FLAG_PAIR_RE.findall(text):
        iso = "".join(chr(ord(c) - 0x1F1E6 + ord("A")) for c in pair)
        out.append(_ISO_TO_MARKET.get(iso, iso))
    return out


# ------------------------------------------------------------- countries

# Written forms people actually use, beyond the marketplace code and name.
COUNTRY_WORDS = {
    "usa": "US", "us": "US", "u s a": "US", "america": "US",
    "unitedstates": "US", "unitedstatesofamerica": "US", "states": "US",
    "uk": "UK", "unitedkingdom": "UK", "britain": "UK", "greatbritain": "UK",
    "england": "UK", "gb": "UK",
    "germany": "DE", "deutschland": "DE", "german": "DE", "de": "DE",
    "france": "FR", "french": "FR", "fr": "FR",
    "italy": "IT", "italia": "IT", "italian": "IT", "it": "IT",
    "spain": "ES", "espana": "ES", "espanya": "ES", "spanish": "ES", "es": "ES",
    "netherlands": "NL", "holland": "NL", "dutch": "NL", "nl": "NL",
    "australia": "AU", "aussie": "AU", "au": "AU",
    "canada": "CA", "canadian": "CA", "ca": "CA",
}

# Two-letter forms are only trusted when they are labelled ("Country: it"), not
# when they appear loose in a sentence — otherwise the "it" in "is it in stock"
# would silently send someone to amazon.it.
_AMBIGUOUS_BARE = {"us", "it", "de", "es", "ca", "au", "fr", "nl", "gb"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _match_country(raw: str, *, labelled: bool) -> str | None:
    """A written country to a marketplace code, tolerating small misspellings."""
    key = _norm(raw)
    if not key:
        return None
    if key in COUNTRY_WORDS:
        if not labelled and key in _AMBIGUOUS_BARE:
            return None
        return COUNTRY_WORDS[key]
    # "germny", "unted kingdom" — close enough to be unambiguous.
    if len(key) >= 5:
        near = difflib.get_close_matches(key, COUNTRY_WORDS, n=1, cutoff=0.85)
        if near:
            return COUNTRY_WORDS[near[0]]
    return None


# ------------------------------------------------------------- task fields

# The fields the client's template carries. Order matters: it is the order they
# are printed in. Each entry is (key, emoji, printed label, synonyms).
FIELDS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("country", "\U0001F310", "Country", ("country", "market", "marketplace", "region", "store", "site")),
    ("require", "\U0001F4CB", "Require", ("require", "required", "requirement", "task", "type", "need")),
    ("keyword", "\U0001F50D", "Keyword", ("keyword", "keywords", "key word", "kw", "search", "search term", "product", "item")),
    # ️ on these two is what makes them render as emoji rather than as
    # monochrome glyphs — the client's template has it, so we match it exactly.
    ("sold_by", "\U0001F3F7️", "Sold By", ("sold by", "soldby", "sold", "seller", "sold by seller", "brand")),
    ("price", "\U0001F4B2", "Price", ("price", "cost", "rate")),
    ("refund", "♻️", "Refund", ("refund", "refunds", "refund percent", "cashback")),
]

_LABEL_TO_KEY = {syn: key for key, _, _, syns in FIELDS for syn in syns}
_ALL_LABELS = list(_LABEL_TO_KEY)

# A line like "Sold By: Smart Gathering" or "Keyword - Fitness Tracker".
_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z .%_]{1,24}?)\s*[:\-–—]\s*(.*)$")


def _label_key(raw: str) -> str | None:
    """Which field a written label refers to, tolerating small misspellings."""
    key = " ".join(raw.lower().split())
    key = re.sub(r"[^a-z ]", "", key).strip()
    if key in _LABEL_TO_KEY:
        return _LABEL_TO_KEY[key]
    near = difflib.get_close_matches(key, _ALL_LABELS, n=1, cutoff=0.82)
    return _LABEL_TO_KEY[near[0]] if near else None


class Parsed:
    """What could be understood from one message."""

    def __init__(self, country: str | None, keyword: str, fields: dict[str, str],
                 labelled_keys: set[str]):
        self.country = country
        self.keyword = keyword
        self.fields = fields
        self.labelled_keys = labelled_keys

    @property
    def is_task(self) -> bool:
        """A review-task message rather than someone sharing a link.

        Two labelled fields are required, at least one of them a product detail
        — otherwise a normal message that happens to say "USA" would come back
        reformatted, which is not what anyone asked for."""
        product = {"require", "keyword", "sold_by", "price", "refund"}
        return len(self.labelled_keys) >= 2 and bool(self.labelled_keys & product)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Parsed(country={self.country!r}, keyword={self.keyword!r}, fields={self.fields})"


def parse(text: str) -> Parsed:
    """Pull the country, keyword and task fields out of a freeform message."""
    fields: dict[str, str] = {}
    labelled: set[str] = set()
    country: str | None = None

    lines = text.splitlines()
    for line in lines:
        m = _LINE_RE.match(line)
        if not m:
            continue
        key = _label_key(m.group(1))
        if key is None:
            continue
        value = m.group(2).strip()
        labelled.add(key)
        if key == "country":
            country = country or _match_country(value, labelled=True)
            if country:
                fields["country"] = value
        elif value:
            fields.setdefault(key, value)

    # A flag anywhere is as good as writing the country's name.
    if country is None:
        for code in flags_in(text):
            if code in CODE_TO_FLAG:
                country = code
                break

    # Still nothing: a country sitting on its own line, as in "USA\nFitness
    # Tracker". Whole lines only — a country word inside a sentence is far too
    # easy to hit by accident.
    if country is None:
        for line in lines:
            hit = _match_country(line.strip(), labelled=False)
            if hit:
                country = hit
                break

    keyword = fields.get("keyword", "")
    if not keyword:
        keyword = _bare_keyword(lines)
    if keyword:
        fields.setdefault("keyword", keyword)

    return Parsed(country, keyword, fields, labelled)


def _bare_keyword(lines: list[str]) -> str:
    """The "USA\\nFitness Tracker" shape: the line after a country line, when it
    is plain text rather than a label, a URL or an ASIN."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_country_line = bool(_match_country(stripped, labelled=False)) or bool(
            flags_in(stripped) and not re.sub(_FLAG_PAIR_RE.pattern, "", stripped).strip()
        )
        if not is_country_line:
            continue
        for candidate in lines[i + 1:]:
            c = candidate.strip()
            if not c:
                continue
            if _LINE_RE.match(c) and _label_key(_LINE_RE.match(c).group(1)):
                return ""
            if "http" in c.lower() or re.fullmatch(r"[A-Z0-9]{10}", c):
                return ""
            return c[:80]
    return ""


# ------------------------------------------------------------- the reply

BRANDING = "\U0001F43B Beast"


def format_task_reply(parsed: Parsed, link: str, country_code: str | None) -> str:
    """The client's template. Fields the sender did not provide are left out
    entirely rather than printed empty."""
    out: list[str] = []

    if country_code:
        shown = parsed.fields.get("country") or country_code
        flag = CODE_TO_FLAG.get(country_code, "")
        out.append(f"\U0001F310 Country: {shown}{(' ' + flag) if flag else ''}")

    if "require" in parsed.fields:
        out.append(f"\U0001F4CB Require: {parsed.fields['require']}")

    detail_keys = [k for k in ("keyword", "sold_by", "price", "refund") if k in parsed.fields]
    if detail_keys:
        out.append("\U0001F4E6 Product Details")
        for key, emoji, label, _ in FIELDS:
            if key in detail_keys:
                out.append(f"{emoji} {label}: {parsed.fields[key]}")

    if link:
        out.append(f"\U0001F517 Link: {link}")

    out.append(BRANDING)
    return "\n\n".join(out)


# ------------------------------------------------------------- what to say

# Written to read like a person, not a system: no "I", no "Error:", and always
# a next step. English first, then Urdu, in one message.
REPLIES: dict[str, tuple[str, str]] = {
    "no_country": (
        "Country missing. Add the country — for example USA, UK or Germany — and send it again.",
        "ملک درج نہیں ہے۔ براہِ کرم ملک لکھیں — مثلاً USA، UK یا Germany — اور دوبارہ بھیجیں۔",
    ),
    "no_product": (
        "No Amazon link, ASIN or keyword found here. Send the product link, or the country along with a keyword.",
        "اس پیغام میں کوئی ایمازون لنک، ASIN یا کی ورڈ نہیں ملا۔ پروڈکٹ کا لنک بھیجیں، یا ملک کے ساتھ کی ورڈ لکھیں۔",
    ),
    "no_tag": (
        "No tracking ID saved yet for {country}. The team can add one for you.",
        "{country} کے لیے ابھی ٹریکنگ آئی ڈی محفوظ نہیں ہے۔ ٹیم اسے شامل کر سکتی ہے۔",
    ),
    "unsupported_market": (
        "That Amazon country is not available yet. Working countries: {available}.",
        "یہ ایمازون ملک فی الحال دستیاب نہیں ہے۔ دستیاب ممالک: {available}۔",
    ),
    "unreadable_page": (
        "That page could not be opened. Sending the Amazon product link directly works best.",
        "یہ صفحہ کھولا نہیں جا سکا۔ بہتر ہے کہ ایمازون پروڈکٹ کا لنک براہِ راست بھیجا جائے۔",
    ),
    "dead_page": (
        "That page is no longer available. Check the link and send it again.",
        "یہ صفحہ اب دستیاب نہیں ہے۔ لنک دیکھ کر دوبارہ بھیجیں۔",
    ),
}


def say(kind: str, **ctx) -> str:
    """A bilingual reply, both languages in one message, branded like the rest."""
    english, urdu = REPLIES[kind]
    return "\n".join([english.format(**ctx), urdu.format(**ctx), "", BRANDING])


# ------------------------------------------------------------- search links

# Two lines the client will supply, shown under a keyword search link so nobody
# mistakes it for a direct product link. Empty until they do; set the env var
# and they appear with no code change.
KEYWORD_DISCLAIMER = os.getenv("KEYWORD_DISCLAIMER", "").replace("\\n", "\n").strip()


def search_url(domain: str, keyword: str, tag: str) -> str:
    """A tagged Amazon search link for a keyword, when no product is known."""
    from urllib.parse import quote_plus

    return f"https://www.{domain}/s?k={quote_plus(keyword)}&tag={quote_plus(tag)}"
