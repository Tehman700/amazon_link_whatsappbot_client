"""End-to-end tests against the running API on :8000."""

import json
import os
import urllib.error
import urllib.request

BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
SENDER = "+923460976174"  # Beast Affiliate (updated via dashboard)

passed = 0
failed = 0


def post(path, body, timeout=30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


# 1. Real client message format (screenshot): caption + US link with existing param
text = "Usa review\nStore name: YusersaEssentials\nhttps://www.amazon.com/dp/B0GS64BBG2?th=1"
status, r = post("/process-message", {"sender": SENDER, "text": text})
check("US link, existing ?th=1 param merged with &tag=",
      status == 200 and r["text"].endswith("https://www.amazon.com/dp/B0GS64BBG2?th=1&tag=beastaffiliate-20"),
      r)
check("caption text untouched",
      r["text"].startswith("Usa review\nStore name: YusersaEssentials\n"), r["text"])

# 2. No existing params -> ?tag=
status, r = post("/process-message", {"sender": SENDER, "text": "https://www.amazon.co.uk/dp/B0ABC123"})
check("UK link, no params -> ?tag=beastaffiliate-21",
      r["text"] == "https://www.amazon.co.uk/dp/B0ABC123?tag=beastaffiliate-21", r)

# 3. Every marketplace (all 9 now have tags)
for domain, tag in [
    ("amazon.com", "beastaffiliate-20"),
    ("amazon.co.uk", "beastaffiliate-21"),
    ("amazon.ca", "beastaffiliate0a-20"),
    ("amazon.de", "beastaffiliate04-21"),
    ("amazon.fr", "beastaffiliate07-28"),
    ("amazon.it", "beastaffiliate06-21"),
    ("amazon.es", "beastaffiliate00-21"),
    ("amazon.nl", "beastaffiliate09-29"),
    ("amazon.com.au", "beastaffiliate-22"),
]:
    status, r = post("/process-message", {"sender": SENDER, "text": f"check this https://www.{domain}/dp/B0TEST"})
    check(f"{domain} -> {tag}", r["text"] == f"check this https://www.{domain}/dp/B0TEST?tag={tag}", r)

# 4. amazon.com.au must NOT be treated as amazon.com
status, r = post("/process-message", {"sender": SENDER, "text": "https://www.amazon.com.au/dp/B0X"})
check("com.au detected as AU not US", "beastaffiliate-22" in r["text"] and "beastaffiliate-20" not in r["text"], r)

# 5. Existing foreign tag replaced, other params kept
status, r = post("/process-message",
                 {"sender": SENDER, "text": "https://www.amazon.de/dp/B0X?th=1&tag=someoneelse-21&psc=1"})
check("foreign tag replaced, th & psc kept",
      r["text"] == "https://www.amazon.de/dp/B0X?th=1&psc=1&tag=beastaffiliate04-21", r)

# 6. Multiple links in one message -> all replaced
status, r = post("/process-message",
                 {"sender": SENDER, "text": "a https://amazon.com/dp/B01 b https://amazon.ca/dp/B02 c"})
check("two links both replaced",
      r["links_replaced"] == 2
      and r["text"] == "a https://amazon.com/dp/B01?tag=beastaffiliate-20 b https://amazon.ca/dp/B02?tag=beastaffiliate0a-20 c", r)

# 7. Non-Amazon URL with no Amazon link on the page -> untouched
status, r = post("/process-message", {"sender": SENDER, "text": "see https://example.com/ ok"})
check("non-amazon URL (no amazon on page) untouched",
      r["text"] == "see https://example.com/ ok" and r["links_replaced"] == 0, r)

# 8. No link at all -> text unchanged
status, r = post("/process-message", {"sender": SENDER, "text": "hello, no links here"})
check("no link -> unchanged", r["text"] == "hello, no links here" and r["links_replaced"] == 0, r)

# 9. Unknown sender -> 404
status, r = post("/process-message", {"sender": "+99999999999", "text": "https://amazon.com/dp/B0X"})
check("unknown sender -> 404", status == 404, (status, r))

# 10. URL followed by punctuation
status, r = post("/process-message", {"sender": SENDER, "text": "buy (https://www.amazon.com/dp/B0X), thanks!"})
check("trailing punctuation not swallowed",
      r["text"] == "buy (https://www.amazon.com/dp/B0X?tag=beastaffiliate-20), thanks!", r)

# 11. Emojis / unicode preserved
status, r = post("/process-message", {"sender": SENDER, "text": "ðŸ”¥ deal! https://amazon.com/dp/B0X ðŸ”¥"})
check("emojis preserved", r["text"] == "ðŸ”¥ deal! https://amazon.com/dp/B0X?tag=beastaffiliate-20 ðŸ”¥", r)

# 12. NEW: real client blogspot page (screenshot) -> resolves to amazon.de + DE tag
blog = "https://lexofindsde.blogspot.com/2026/07/fingerprint-fingerprint-lock-locker.html"
msg = f"Sold by\nAnweller DE\n{blog}\nMust order through link"
status, r = post("/process-message", {"sender": SENDER, "text": msg}, timeout=60)
ok = (
    status == 200
    and r["links_replaced"] == 1
    and blog not in r["text"]
    and "amazon.de" in r["text"]
    and "tag=beastaffiliate04-21" in r["text"]
    and r["text"].startswith("Sold by\nAnweller DE\n")
    and r["text"].endswith("\nMust order through link")
)
check("blogspot page resolved to tagged amazon.de link", ok, r)
if status == 200 and r["replacements"]:
    print("      resolved:", r["replacements"][0]["rewritten"][:120])

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
