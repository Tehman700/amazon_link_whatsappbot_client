"""End-to-end behaviour for issues #5 and #6, against a running API.

Two things are being protected here. The new behaviour has to work — a country
written as a flag, a task message coming back in the client's layout, a failure
being explained instead of ignored. And the old behaviour has to be untouched:
a shared link must still come back as the same message with only the link
swapped, because that is what 60 people rely on every day.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
SENDER = os.getenv("SMART_SENDER", "+923005550101")

passed = failed = 0


def post(text, timeout=90):
    req = urllib.request.Request(
        BASE + "/process-message",
        data=json.dumps({"sender": SENDER, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


# ------------------------------------------- the old pipeline is untouched
r = post("https://www.amazon.com/dp/B0GS64BBG2?th=1")
check("a plain link is still just the link, tagged",
      r["links_replaced"] == 1 and r["text"].startswith("https://")
      and "Beast" not in r["text"], r["text"])

r = post("Usa review\nhttps://www.amazon.com/dp/B0GS64BBG2\nthanks")
check("a caption is still passed through untouched",
      r["text"].startswith("Usa review\n") and r["text"].endswith("\nthanks"), r["text"])

r = post("hello, no links here")
check("ordinary chatter is still answered with silence",
      r["links_replaced"] == 0 and r["text"] == "hello, no links here", r)

r = post("ok thanks 👍")
check("a thumbs-up is not worth a reply", r["links_replaced"] == 0, r)

# ------------------------------------------------------- link hygiene (#5)
r = post("*https://www.amazon.com/dp/B0GS64BBG2*")
check("a bold link is tagged correctly, not after the asterisk",
      "B0GS64BBG2?tag=" in r["text"], r["text"])

r = post("_https://www.amazon.com/dp/B0GS64BBG2_")
check("an italic link works too", "B0GS64BBG2?tag=" in r["text"], r["text"])

r = post("https://www.amazon.com/dp/B0GS64BBG2​")
check("an invisible character does not break the link",
      "B0GS64BBG2?tag=" in r["text"], r["text"])

# ------------------------------------------------- country detection (#6)
r = post("Country: USA\nASIN: B0GS64BBG2")
check("'Country:' is understood, not only 'Market:'",
      r["links_replaced"] == 1 and "amazon.com" in r["text"], r["text"])

r = post("\U0001F1E9\U0001F1EA\nASIN: B0GS64BBG2")
check("a flag emoji picks the marketplace",
      r["links_replaced"] == 1 and "amazon.de" in r["text"], r["text"])

r = post("Country: Germny\nASIN: B0GS64BBG2")
check("a misspelt country still resolves",
      r["links_replaced"] == 1 and "amazon.de" in r["text"], r["text"])

# ---------------------------------------------------- keyword search (#6)
r = post("Country: USA\nKeyword: Fitness Tracker")
check("a keyword with no product returns a tagged search link",
      "/s?k=Fitness+Tracker" in r["text"] and "tag=" in r["text"], r["text"])
check("the search reply is branded", r["text"].rstrip().endswith("Beast"), r["text"])

r = post("USA\nFitness Tracker")
check("country and keyword on bare lines work too",
      "/s?k=Fitness+Tracker" in r["text"], r["text"])

# ------------------------------------------------- the task layout (#5)
task = ("Country: USA\nRequire: Text Review\nKeyword: Fitness Tracker\n"
        "Sold By: Smart Gathering\nPrice: $39.99\nASIN: B0GS64BBG2")
r = post(task)
t = r["text"]
check("a review task comes back in the client's layout",
      "Country: USA" in t and "Require: Text Review" in t
      and "Product Details" in t and "Sold By: Smart Gathering" in t, t)
check("the layout carries the tagged link", "tag=" in t, t)
check("the layout is branded", t.rstrip().endswith("Beast"), t)
check("fields the sender never sent are not printed",
      "Refund" not in t, t)

# a task without the fields must NOT be reformatted
r = post("Country: USA\nhttps://www.amazon.com/dp/B0GS64BBG2")
check("a country plus a link is left as a normal reply",
      "Product Details" not in r["text"], r["text"])

# --------------------------------------------------- saying why (#5)
r = post("ASIN: B0GS64BBG2")
check("an ASIN with no country is explained",
      r["links_replaced"] == 1 and "Country missing" in r["text"], r["text"])
check("the explanation is bilingual", "ملک" in r["text"], r["text"])
check("the explanation avoids first person",
      " I " not in f" {r['text']} ", r["text"])

r = post("Country: USA")
check("a country with nothing to buy is explained",
      "No Amazon link" in r["text"], r["text"])

r = post("see https://example.com/ ok")
check("a link that leads nowhere is explained",
      "could not be opened" in r["text"], r["text"])
check("the original link is not echoed back in the explanation",
      "example.com" not in r["text"], r["text"])

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
