"""Unit tests for canonical short-link rewriting (no server/DB needed).

Run:  uv run python tests/test_canonical.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rewriter import replace_urls, rewrite_url  # noqa: E402

passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}\n      got:  {got}\n      want: {want}")


# The real monster share-link from the client's WhatsApp screenshot
monster = (
    "https://www.amazon.com/dp/B0GZV98Z9K?ref=cm_sw_r_cso_cp_apan_dp_DV32QF1W61Z3A8E0ZVP1"
    "&ref_=cm_sw_r_cso_cp_apan_dp_DV32QF1W61Z3A8E0ZVP1"
    "&social_share=cm_sw_r_cso_cp_apan_dp_DV32QF1W61Z3A8E0ZVP1"
    "&rsd=ryGBEOsL1MSUBr5r5V12YkRfsF23kS2zLZreKz20QC2tnUpfXK8irXz8tJRDQdId86oTU95DCDr5WxI"
    "&edk=AQIDAHi1lw"
)
check(
    "monster share link -> canonical /dp/ASIN?tag=",
    rewrite_url(monster, "testabc"),
    "https://www.amazon.com/dp/B0GZV98Z9K?tag=testabc",
)

# Variant-selection params survive canonicalization
check(
    "th & psc kept, junk dropped",
    rewrite_url("https://www.amazon.de/dp/B0D4HWJM99?th=1&linkCode=ll2&psc=1&linkId=abc123", "mytag-21"),
    "https://www.amazon.de/dp/B0D4HWJM99?th=1&psc=1&tag=mytag-21",
)

# Foreign affiliate tag replaced in canonical path
check(
    "foreign tag replaced (canonical)",
    rewrite_url("https://www.amazon.com/dp/B0GZV98Z9K?tag=competitor-20", "mine-20"),
    "https://www.amazon.com/dp/B0GZV98Z9K?tag=mine-20",
)

# Slug paths collapse to /dp/ASIN
check(
    "product slug path collapsed",
    rewrite_url(
        "https://www.amazon.co.uk/Lehwey-External-Universal-Player-Car/dp/B0D4HWJM99?th=1&ref_=xyz",
        "uk-21",
    ),
    "https://www.amazon.co.uk/dp/B0D4HWJM99?th=1&tag=uk-21",
)

# /gp/product/ form
check(
    "gp/product form canonicalized",
    rewrite_url("https://www.amazon.com/gp/product/B0GZV98Z9K?ref=share", "t-20"),
    "https://www.amazon.com/dp/B0GZV98Z9K?tag=t-20",
)

# No confident ASIN -> previous behavior exactly (params preserved, tag merged)
check(
    "short fake id falls back to old behavior",
    rewrite_url("https://www.amazon.com/dp/B0X?th=1", "t-20"),
    "https://www.amazon.com/dp/B0X?th=1&tag=t-20",
)
check(
    "search page falls back to old behavior",
    rewrite_url("https://www.amazon.com/s?k=fingerprint+lock&ref=nb_sb", "t-20"),
    "https://www.amazon.com/s?k=fingerprint%20lock&ref=nb_sb&tag=t-20",
)
check(
    "storefront link falls back, foreign tag replaced",
    rewrite_url("https://www.amazon.com/stores/page/ABC?tag=other-20", "t-20"),
    "https://www.amazon.com/stores/page/ABC?tag=t-20",
)

# replace_urls: the keyword-search fallback echoes the sender's message with
# its dead / unresolvable link swapped for the tagged search link.
check("replace_urls swaps the link in place, keeps the rest",
      replace_urls("before https://sagcart.com/product/-P-x after", "SEARCH"),
      "before SEARCH after")
check("replace_urls preserves the lines around a multi-line message",
      replace_urls("Note" + chr(10) + "https://sagcart.com/x" + chr(10) + "more", "SEARCH"),
      "Note" + chr(10) + "SEARCH" + chr(10) + "more")
check("replace_urls prepends the link when the message has none",
      replace_urls("USA" + chr(10) + "Fitness Tracker", "SEARCH"),
      "SEARCH" + chr(10) + "USA" + chr(10) + "Fitness Tracker")
check("replace_urls keeps only the first link, drops extras",
      replace_urls("x https://a.com/1 y https://b.com/2 z", "S"),
      "x S y  z")
check("replace_urls leaves trailing punctuation out of the link",
      replace_urls("see https://a.com/1, thanks", "S"),
      "see S, thanks")

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
