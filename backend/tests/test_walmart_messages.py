"""Messages that name Walmart.

The client's Walmart tasks label the item id as "ASIN" even though it is an
eleven-digit Walmart item number, so the word "Walmart" in the message is the
only reliable signal. Before this, those messages came back as an Amazon
keyword search — a link that works, looks right, and earns nothing.

Offline: detection and link building only, no server.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["WALMART_PUBLISHER_ID"] = "7486129"
os.environ["WALMART_CAMPAIGN_ID"] = "1398372"

from app import message, walmart  # noqa: E402

passed = failed = 0

REAL = ("3. Walmart computers.\nASIN:  19839769706\nKeywords: Laptop\n"
        "Price: $359.99\nStore: SGIN Official Store\n"
        "There are 2 orders in total, 1 per day, image review orders.\n8.16\n\nUS")


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


# ------------------------------------------------------------- recognising it
check("the real message is recognised as Walmart", message.mentions_walmart(REAL))
check("its item id is read despite the 'ASIN' label",
      message.walmart_item_id(REAL) == "19839769706", message.walmart_item_id(REAL))
check("'wal-mart' is recognised too", message.mentions_walmart("wal-mart deal"))
check("an Amazon message is not", not message.mentions_walmart("Country: USA\nASIN: B0GS64BBG2"))

# the shape of the number is what identifies it, not the label
check("a real Amazon ASIN is not read as a Walmart item",
      message.walmart_item_id("Walmart\nASIN: B0GS64BBG2") == "")
check("a price is not read as an item id",
      message.walmart_item_id("Walmart\nPrice: 359.99") == "")
check("a short number is not read as an item id",
      message.walmart_item_id("Walmart\nQty: 12345") == "")

# ------------------------------------------------------------- building links
prod = walmart.affiliate_url(walmart.product_url_for_item("19839769706"), "khan")
check("product link points at the item", "%2Fip%2F19839769706" in prod, prod)
check("product link carries the client's publisher", "/c/7486129/1398372/16662" in prod, prod)
check("product link carries the user", "sharedid=khan" in prod, prod)
check("product link matches the client's own format",
      "sourceid=imp_000011112222333344" in prod and "veh=aff" in prod, prod)

search = walmart.affiliate_url(walmart.search_url("Yoga Mat"), "khan")
check("a search link keeps its query",
      "q%3DYoga" in search or "q=Yoga" in search,
      "stripping the query would send people to a blank search page")
check("a search link still carries the user", "sharedid=khan" in search, search)

# tracking junk on a product page is still dropped
messy = walmart.affiliate_url(
    "https://www.walmart.com/ip/SGIN-Laptop/19839769706?from=/search&classType=VARIANT", "khan")
check("tracking junk is dropped from a product URL",
      "classType" not in messy and "%2Fip%2F19839769706" in messy, messy)

# a forwarded affiliate link is re-attributed to this sender
theirs = ("https://goto.walmart.com/c/9999999/222222/9383?veh=aff"
          "&u=https%3A%2F%2Fwww.walmart.com%2Fip%2F19839769706&sharedid=someoneelse")
mine = walmart.affiliate_url(theirs, "khan")
check("a forwarded link is rebuilt under our publisher", "/c/7486129/1398372/" in mine, mine)
check("...and carries our sender, not theirs",
      "sharedid=khan" in mine and "someoneelse" not in mine, mine)

# ------------------------------------------------------- the refusal wording
check("a non-US country for Walmart has its own message",
      "walmart_country" in message.REPLIES)
msg = message.say("walmart_country")
check("that message is bilingual", "US store" in msg and "والمارٹ" in msg, msg)
check("...and branded", msg.rstrip().endswith("Beast"), msg)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
