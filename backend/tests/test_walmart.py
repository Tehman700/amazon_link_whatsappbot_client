"""Walmart links: recognising them, and turning them into affiliate links.

Offline. The cases that matter most are the ones that would lose money quietly:
appending Amazon's `?tag=` to a Walmart URL produces a link that looks perfect
and earns nothing, and a forwarded affiliate link must be re-attributed to the
sender rather than left earning for whoever generated it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Configured BEFORE the module is imported — the ids are read at import time.
os.environ["WALMART_PUBLISHER_ID"] = "1234567"
os.environ["WALMART_CAMPAIGN_ID"] = "891011"
os.environ["WALMART_AD_ID"] = "9383"

from app import rewriter, walmart  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


class MP:
    def __init__(self, code, domain):
        self.id, self.code, self.domain = 99, code, domain


WM = MP("WM", "walmart.com")
US = MP("US", "amazon.com")

LONG = ("https://www.walmart.com/ip/SGIN-15-6in-Laptop-6GB-DDR4-128GB-SSD/"
        "19839769706?classType=VARIANT&from=/search")
SHORT = "https://www.walmart.com/ip/19839769706"

# ------------------------------------------------------------- reading a URL
check("item id out of a full product URL", walmart.item_id(LONG) == "19839769706")
check("item id out of the short form", walmart.item_id(SHORT) == "19839769706")
check("a non-product Walmart page has no item id",
      walmart.item_id("https://www.walmart.com/browse/electronics") is None)
check("tracking junk is dropped", walmart.product_url(LONG) == SHORT, walmart.product_url(LONG))

# ------------------------------------------------------- building the link
built = walmart.affiliate_url(LONG, "user42")
check("built on the Impact host", built.startswith("https://goto.walmart.com/c/"), built)
check("carries the publisher and campaign", "/c/1234567/891011/9383?" in built, built)
check("carries the sender identifier", "sharedid=user42" in built, built)
check("carries the product, encoded",
      "u=https%3A%2F%2Fwww.walmart.com%2Fip%2F19839769706" in built, built)

# ------------------------------------------------- the money-losing mistakes
viaengine = rewriter.affiliate_link(LONG, "user42", WM)
check("the engine routes Walmart to the wrapper, not to ?tag=",
      viaengine.startswith("https://goto.walmart.com/"), viaengine)
check("...and never appends a tag param", "tag=" not in viaengine.split("?u=")[0], viaengine)

amazon = rewriter.affiliate_link("https://www.amazon.com/dp/B0GS64BBG2", "beast-20", US)
check("Amazon is untouched by any of this",
      amazon == "https://www.amazon.com/dp/B0GS64BBG2?tag=beast-20", amazon)

# a forwarded affiliate link must be re-attributed, exactly as a foreign
# Amazon tag is replaced today
someone_else = ("https://goto.walmart.com/c/9999999/222222/9383?veh=aff"
                "&u=https%3A%2F%2Fwww.walmart.com%2Fip%2F19839769706&subId1=otherguy")
check("an existing affiliate link is unwrapped to its product",
      walmart.unwrap(someone_else).endswith("/ip/19839769706"),
      walmart.unwrap(someone_else))
mine = walmart.affiliate_url(someone_else, "user42")
check("...and rebuilt under our publisher", "/c/1234567/891011/" in mine, mine)
check("...carrying our sender's identifier, not theirs",
      "sharedid=user42" in mine and "otherguy" not in mine, mine)

# The parameter name is not a detail: goto.walmart.com silently drops subId1 on
# the way to the product page, so a link built with it would track the client
# but never tell their users apart. Verified against the live link 2026-08-18.
check("the per-user parameter is sharedid, never subId1",
      "sharedid=" in built and "subId1=" not in built, built)

# ------------------------------------------------- off until it is configured
walmart.PUBLISHER_ID = ""
check("with no Impact ids configured the feature is off", not walmart.enabled())
check("...and a Walmart link is returned untouched rather than broken",
      walmart.affiliate_url(LONG, "user42") == LONG)
walmart.PUBLISHER_ID = "1234567"
check("...and back on once configured", walmart.enabled())

# ------------------------------------------------------------ marketplace routing
check("Walmart is recognised from its domain, not a hardcoded code",
      rewriter.is_walmart(MP("ANYTHING", "walmart.com")))
check("Amazon is not", not rewriter.is_walmart(US))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
