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

# Words safe to spot INSIDE a line of other words, as in "Usa review". The
# two-letter codes and the adjectives ("german", "italian") are left out on
# purpose: those turn up inside ordinary sentences and product titles, and
# picking the wrong country here sends someone to the wrong marketplace with
# the wrong tag, which costs real money.
_STRONG_COUNTRY_WORDS = {
    w: c for w, c in COUNTRY_WORDS.items()
    if w not in _AMBIGUOUS_BARE
    and w not in {"states", "german", "french", "italian", "spanish", "dutch",
                  "canadian", "aussie"}
}

# How a country is named in the reply when the sender did not spell it out.
COUNTRY_DISPLAY = {
    "US": "USA", "UK": "UK", "CA": "Canada", "DE": "Germany", "FR": "France",
    "IT": "Italy", "ES": "Spain", "NL": "Netherlands", "AU": "Australia",
}


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

# A line like "Sold By: Smart Gathering", "Keyword - Fitness Tracker", or
# "Price...67.99". The run of dots is not a stylistic detail: it is what the
# client's own forwarded messages actually use, and only accepting colons meant
# every one of those fields was invisible to us.
_LINE_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z .%_]{1,24}?)\s*(?::|[-–—]|\.{2,}|…)\s*(.*)$"
)


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
                 labelled_keys: set[str], extra: list[str] | None = None):
        self.country = country
        self.keyword = keyword
        self.fields = fields
        self.labelled_keys = labelled_keys
        # Everything the sender wrote that did not become a field. Carried into
        # the reply verbatim rather than dropped: a line like "Must order
        # through link otherwise not accept cancel" is the whole point of the
        # message, and there is no chance of recognising every way people write.
        self.extra = extra or []

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
    # Line numbers whose content already appears in the formatted reply. What is
    # left over is carried through untouched, so nothing the sender wrote is
    # thrown away just because it was not recognised.
    consumed: set[int] = set()

    for i, line in enumerate(lines):
        m = _LINE_RE.match(line)
        if not m:
            continue
        key = _label_key(m.group(1))
        if key is None:
            continue  # unknown label — carried over verbatim, not dropped
        consumed.add(i)
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

    # Still nothing: a country written among other words, as in "USA\nFitness
    # Tracker" or "Usa review".
    if country is None:
        for i, line in enumerate(lines):
            hit = _country_in_line(line)
            if hit:
                country = hit
                # Only swallow the line when it is nothing BUT the country;
                # "Usa review" keeps its other word rather than losing it.
                if _match_country(line.strip(), labelled=False):
                    consumed.add(i)
                break

    keyword = fields.get("keyword", "")
    if not keyword:
        keyword = _bare_keyword(lines)
        if keyword:
            for i, line in enumerate(lines):
                if line.strip() == keyword:
                    consumed.add(i)
                    break
    if keyword:
        fields.setdefault("keyword", keyword)

    # "need text review" on its own line is the requirement, just without a label.
    if "require" not in fields:
        m = _REQUIRE_RE.search(text)
        if m:
            fields["require"] = m.group(1).title()
            for i, line in enumerate(lines):
                if _REQUIRE_RE.search(line):
                    consumed.add(i)
                    break

    return Parsed(country, keyword, fields, labelled,
                  extra=_carry_over(lines, consumed))


# Generous ceilings. They exist only to stop a pasted essay turning one reply
# into a wall of text; real messages are nowhere near them.
MAX_CARRY_LINES = 20
MAX_CARRY_CHARS = 300

_URL_IN_LINE_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _carry_over(lines: list[str], consumed: set[int]) -> list[str]:
    """Whatever the sender wrote that is not already in the formatted reply.

    URLs are stripped out. Echoing the original link back would hand the buyer
    a route to the product that carries no affiliate tag — which is exactly
    what the "must order through link" instruction in these messages exists to
    prevent, so repeating it would defeat the sender's own purpose.
    """
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in consumed:
            continue
        cleaned = _URL_IN_LINE_RE.sub("", line).strip()
        # A line that was only a link leaves nothing worth carrying.
        if not cleaned:
            continue
        out.append(cleaned[:MAX_CARRY_CHARS])
        if len(out) >= MAX_CARRY_LINES:
            break
    return out


def _country_in_line(line: str) -> str | None:
    """A country named anywhere in one line.

    The whole line is tried first, so "united kingdom" still works. Failing
    that, individual words are checked against the strong list only — "Usa
    review" resolves, "is it in stock" does not.
    """
    stripped = line.strip()
    whole = _match_country(stripped, labelled=False)
    if whole:
        return whole

    words = [w.lower() for w in re.findall(r"[A-Za-z]+", stripped)]
    for word in words:
        if word in _STRONG_COUNTRY_WORDS:
            return _STRONG_COUNTRY_WORDS[word]
    # "United States" / "Great Britain" arrive as two words.
    for a, b in zip(words, words[1:]):
        pair = a + b
        if pair in _STRONG_COUNTRY_WORDS:
            return _STRONG_COUNTRY_WORDS[pair]
    return None


# "need text review", "video review" — the requirement written without a label.
# Anchored on the kind of review so an unrelated line saying "review" is not
# mistaken for one.
_REQUIRE_RE = re.compile(
    r"\b((?:text|video|photo|image|picture|written)\s+review)\b", re.IGNORECASE
)


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

# Signed at the end of everything the bot composes. Defined once: the layout,
# the search replies and the bilingual explanations all use this, so the mark
# changes everywhere at once. (Was a bear; the client moved to sparkles.)
BRANDING = "✨ Beast"


def format_task_reply(parsed: Parsed, link: str, country_code: str | None,
                      note: str = "") -> str:
    """The client's template. Fields the sender did not provide are left out
    entirely rather than printed empty.

    `note` goes between the link and the branding — it carries the search-link
    disclaimer, which is needed just as much when a task message resolves to a
    search as when a bare keyword does."""
    out: list[str] = []

    if country_code:
        shown = (parsed.fields.get("country")
                 or COUNTRY_DISPLAY.get(country_code, country_code))
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
    if note:
        out.append(note)
    if parsed.extra:
        # Last, just above the sign-off: anything the sender wrote that did not
        # map to a field — their own instructions, a store name written a way
        # we do not recognise, a note for the buyer.
        out.append("\n".join(parsed.extra))

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
