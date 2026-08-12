"""Message understanding: countries, keywords, task fields, and the reply.

Entirely offline — no server, no network, no database. These cases decide what
60 people read on WhatsApp, so the awkward inputs matter more than the tidy
ones: a country word buried in a sentence, a two-letter code that is also an
English word, a misspelt label, a flag instead of a name.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import message  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


def country_of(text):
    return message.parse(text).country


# ------------------------------------------------------------- countries
check("labelled country", country_of("Country: USA") == "US")
check("the old 'Market:' form still works", country_of("Market: UK") == "UK")
check("bare country on its own line", country_of("USA\nFitness Tracker") == "US")
check("flag emoji", country_of("\U0001F1FA\U0001F1F8\nFitness Tracker") == "US")
check("UK flag maps to the UK marketplace, not GB",
      country_of("\U0001F1EC\U0001F1E7\nSomething") == "UK")
check("local spelling", country_of("Country: Deutschland") == "DE")
check("misspelling", country_of("Country: Germny") == "DE")
check("case and spacing", country_of("country  :   united kingdom") == "UK")
check("alternative label", country_of("Region: Canada") == "CA")

# the ones that must NOT fire
check("a country word inside a sentence is ignored",
      country_of("is it available in stock right now") is None,
      "'it' must not mean amazon.it")
check("bare two-letter code is ignored when unlabelled",
      country_of("us\nsomething") is None)
check("...but is accepted when labelled", country_of("Country: it") == "IT")
check("no country at all", country_of("hello there") is None)

# ------------------------------------------------------------- keywords
check("labelled keyword",
      message.parse("Country: USA\nKeyword: Fitness Tracker").keyword == "Fitness Tracker")
check("misspelt label still understood",
      message.parse("Country: USA\nKewyord: Fitness Tracker").keyword == "Fitness Tracker")
check("bare keyword after a country line",
      message.parse("USA\nFitness Tracker").keyword == "Fitness Tracker")
check("bare keyword after a flag",
      message.parse("\U0001F1FA\U0001F1F8\nYoga Mat").keyword == "Yoga Mat")
check("a link is not mistaken for a keyword",
      message.parse("USA\nhttps://www.amazon.com/dp/B0GS64BBG2").keyword == "")
check("an ASIN is not mistaken for a keyword",
      message.parse("USA\nB0GS64BBG2").keyword == "")

# ------------------------------------------------------------- task shape
plain = message.parse("Country: USA")
check("a country alone is not a review task", not plain.is_task)
check("a shared link is not a review task",
      not message.parse("https://www.amazon.com/dp/B0GS64BBG2").is_task)

task = message.parse(
    "Country: USA\nRequire: Text Review\nKeyword: Fitness Tracker\n"
    "Sold By: Smart Gathering\nPrice: $39.99"
)
check("a real task message is recognised", task.is_task)
check("every field is read",
      (task.fields.get("require"), task.fields.get("sold_by"), task.fields.get("price"))
      == ("Text Review", "Smart Gathering", "$39.99"), task.fields)

messy = message.parse(
    "price - 39.99 USD\nsoldby : Smart Gathering\nkeyword: Fitness Tracker\ncountry: usa"
)
check("fields in any order, any separator, any case", messy.is_task, messy.fields)
check("...and still finds the country", messy.country == "US")

# ------------------------------------------------------------- the reply
out = message.format_task_reply(task, "https://example.com/p/ABC", "US")
check("reply carries the country and its flag",
      "Country: USA" in out and "\U0001F1FA\U0001F1F8" in out, out)
check("reply carries the product details header", "Product Details" in out, out)
check("reply carries the link", "https://example.com/p/ABC" in out, out)
check("reply is branded", out.rstrip().endswith("Beast"), out)

partial = message.parse("Country: USA\nKeyword: Yoga Mat")
out2 = message.format_task_reply(partial, "https://example.com/x", "US")
check("fields the sender omitted are dropped, not printed empty",
      "Sold By" not in out2 and "Price" not in out2 and "Refund" not in out2, out2)
check("no empty field is ever printed",
      not any(line.rstrip().endswith(":") for line in out2.splitlines()), out2)

# ------------------------------------------------------------- what we say
msg = message.say("no_country")
check("reply is bilingual", "Country missing" in msg and "ملک" in msg, msg)
check("reply avoids talking about itself", " I " not in f" {msg} " and "I'm" not in msg, msg)
check("reply does not read like an error dump",
      "Error" not in msg and "error" not in msg and "failed" not in msg.lower(), msg)
check("reply is branded", msg.rstrip().endswith("Beast"), msg)
check("reply fills in context",
      "Germany" in message.say("no_tag", country="Germany"))
check("every reply kind renders",
      all(message.say(k, country="X", available="US, UK") for k in message.REPLIES))

# ------------------------------------------------------------- search links
u = message.search_url("amazon.com", "Fitness Tracker", "beast-20")
check("search link is tagged and escaped",
      u == "https://www.amazon.com/s?k=Fitness+Tracker&tag=beast-20", u)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
