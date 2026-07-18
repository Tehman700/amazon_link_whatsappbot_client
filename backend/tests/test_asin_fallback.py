"""Unit tests for the ASIN+Market no-link fallback (no server needed).

Run: uv run python tests/test_asin_fallback.py
"""

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rewriter import build_from_asin, extract_asin  # noqa: E402


@dataclass
class MP:
    id: int
    code: str
    name: str
    domain: str


MARKETPLACES = [
    MP(1, "US", "United States", "amazon.com"),
    MP(2, "UK", "United Kingdom", "amazon.co.uk"),
    MP(4, "DE", "Germany", "amazon.de"),
    MP(9, "AU", "Australia", "amazon.com.au"),
]
DOMAIN_MAP = {m.domain: m for m in MARKETPLACES}
# sender has tags for US, UK, DE — but NOT AU
TAGS = {1: "beast-20", 2: "beast-21", 4: "beast04-21"}

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


# The real screenshot message: Market:UK + labelled ASIN, no link
MSG = (
    "Market:UK\nKey words: boob tape\nshop : Memojoy\nASIN: B0H3ZGX6YQ\n"
    "Price: 8.99(use coupon)\nNeed only order 1\ntext review full refund"
)
text, reps = build_from_asin(MSG, DOMAIN_MAP, TAGS)
check("screenshot msg -> one link built", len(reps) == 1, reps)
check("link is UK domain + ASIN + tag on TOP",
      text.startswith("https://www.amazon.co.uk/dp/B0H3ZGX6YQ?tag=beast-21\n"), text[:80])
check("original text preserved below the link", MSG in text, text)

# ASIN extraction variants
check("labelled ASIN extracted", extract_asin("ASIN: B0H3ZGX6YQ") == "B0H3ZGX6YQ")
check("bare B0 token extracted", extract_asin("check B0H1D3C6YY here") == "B0H1D3C6YY")
check("lowercased asin label works", extract_asin("asin b0h3zgx6yq") == "B0H3ZGX6YQ")
check("no asin -> None", extract_asin("just some text, no product") is None)

# Market variants
for market, domain in [("Market:US", "amazon.com"), ("Market: USA", "amazon.com"),
                       ("Market: United States", "amazon.com"),
                       ("Market:Germany", "amazon.de"), ("market - uk", "amazon.co.uk")]:
    t, r = build_from_asin(f"{market}\nASIN: B0H3ZGX6YQ", DOMAIN_MAP, TAGS)
    check(f"'{market}' -> {domain}", len(r) == 1 and domain in t, (market, t[:60]))

# Silence conditions (decision #2/#3)
t, r = build_from_asin("ASIN: B0H3ZGX6YQ\nnice product", DOMAIN_MAP, TAGS)
check("ASIN but NO market -> silent", r == [], t[:60])

t, r = build_from_asin("Market:UK\nno product id here", DOMAIN_MAP, TAGS)
check("market but NO asin -> silent", r == [], t[:60])

t, r = build_from_asin("Market:AU\nASIN: B0H3ZGX6YQ", DOMAIN_MAP, TAGS)
check("market sender has no tag for (AU) -> silent", r == [], t[:60])

t, r = build_from_asin("Market: Mexico\nASIN: B0H3ZGX6YQ", DOMAIN_MAP, TAGS)
check("unknown market -> silent", r == [], t[:60])

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
