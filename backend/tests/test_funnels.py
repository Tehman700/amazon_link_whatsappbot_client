"""Funnel-site resolution tests (pointmarketing + ilearner)."""

import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
SENDER = "+923111592151"

passed = failed = 0


def post(text):
    req = urllib.request.Request(
        BASE + "/process-message",
        data=json.dumps({"sender": SENDER, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


# 1. pointmarketing prodetail -> product.Link is amazon.co.uk -> UK tag
s, r = post("check this out https://www.pointmarketing.shop/prodetail/6a1b0ec2e55c70941a8bf9d7 nice product")
check(
    "pointmarketing -> tagged amazon.co.uk link",
    s == 200
    and r["links_replaced"] == 1
    and "amazon.co.uk" in r["text"]
    and "tag=" in r["text"]
    and "pointmarketing.shop" not in r["text"]
    and r["text"].startswith("check this out ")
    and r["text"].endswith(" nice product"),
    r,
)
if r.get("replacements"):
    print("      ->", r["replacements"][0]["rewritten"][:130])

# 2. ilearner-store product page -> amazon.fr -> FR tag
s, r = post("https://ilearner-store.com/p/341E/collagen-real-deep-mask-hydratation-intense-pour")
check(
    "ilearner-store -> tagged amazon.fr link",
    s == 200
    and r["links_replaced"] == 1
    and "amazon.fr" in r["text"]
    and "tag=" in r["text"]
    and "ilearner-store.com" not in r["text"],
    r,
)
if r.get("replacements"):
    print("      ->", r["replacements"][0]["rewritten"][:130])

# 3. ilearner.dev short link -> same amazon.fr
s, r = post("Sold by\nAmazon EU\nhttps://ilearner.dev/link/341E\nMust order through link")
check(
    "ilearner.dev/link -> tagged amazon.fr link, caption intact",
    s == 200
    and r["links_replaced"] == 1
    and "amazon.fr" in r["text"]
    and "tag=" in r["text"]
    and r["text"].startswith("Sold by\nAmazon EU\n")
    and r["text"].endswith("\nMust order through link"),
    r,
)
if r.get("replacements"):
    print("      ->", r["replacements"][0]["rewritten"][:130])

# 4. regression: blogspot page still resolves
s, r = post("https://lexofindsde.blogspot.com/2026/07/fingerprint-fingerprint-lock-locker.html")
check(
    "blogspot still resolves (regression)",
    s == 200 and r["links_replaced"] == 1 and "tag=" in r["text"],
    r,
)

# 5. regression: direct amazon link untouched pipeline
s, r = post("https://www.amazon.com/dp/B0GS64BBG2?th=1")
check(
    "direct amazon link still works (regression)",
    s == 200 and r["text"] == "https://www.amazon.com/dp/B0GS64BBG2?th=1&tag=beastaffiliate-20",
    r,
)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
