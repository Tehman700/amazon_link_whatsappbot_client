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

# ---------------------------------------- the client's real forwarded messages
# Copied from a screenshot of live traffic. Both were answered with silence:
# the fields use "..." rather than a colon, and the country sits on a line with
# another word, so nothing at all was recognised.

REAL_1 = ("Sold by...Viconor-US\n\nKeyword...red light therapy for body\n\n"
          "Price...67.99\n\nUsa review")
REAL_2 = ("Sold by...Smart Gathering\n\nKeyword...fitness tracker\n\n"
          "Price...39.99\n\nUSA review\nneed text review")

p1 = message.parse(REAL_1)
check("real message 1: country found on a line with another word", p1.country == "US", p1)
check("real message 1: keyword read through the dots",
      p1.keyword == "red light therapy for body", p1)
check("real message 1: seller read", p1.fields.get("sold_by") == "Viconor-US", p1.fields)
check("real message 1: price read", p1.fields.get("price") == "67.99", p1.fields)
check("real message 1: recognised as a task", p1.is_task, p1)

p2 = message.parse(REAL_2)
check("real message 2: country found", p2.country == "US", p2)
check("real message 2: keyword read", p2.keyword == "fitness tracker", p2)
check("real message 2: seller read", p2.fields.get("sold_by") == "Smart Gathering", p2.fields)
check("real message 2: unlabelled requirement read",
      p2.fields.get("require") == "Text Review", p2.fields)

# A task that resolves to a SEARCH link must still keep its layout — these
# forwarded messages carry a seller and a price, and answering with a bare
# search link would throw away everything the sender wrote.
task_search = message.format_task_reply(
    p2, "https://www.amazon.com/s?k=fitness+tracker&tag=t", "US", note="Disclaimer here",
)
check("a task answered by a search link keeps the full layout",
      all(x in task_search for x in ("Sold By: Smart Gathering", "Price: 39.99",
                                     "Require: Text Review", "/s?k=")), task_search)
check("the search disclaimer sits above the branding",
      task_search.index("Disclaimer here") < task_search.index(message.BRANDING),
      task_search)

out3 = message.format_task_reply(p1, "https://www.amazon.com/s?k=x&tag=y", "US")
check("country is named properly when the sender never labelled it",
      "Country: USA" in out3, out3)
check("no Require line when there is no requirement", "Require" not in out3, out3)

# the dotted separator must not swallow ordinary writing
check("ordinary sentence with dots is not read as a field",
      not message.parse("ok...thanks for that").is_task)
check("a country word inside a sentence is still ignored",
      country_of("is it in stock right now") is None)
check("a seller name ending in -US does not decide the country",
      message.parse("Sold by...Viconor-US\nKeyword...lamp").country is None,
      "only 'Usa review' should set the country in message 1")

# ------------------------------- nothing the sender wrote is thrown away
# From live traffic: a store name written a way we do not recognise, and a
# buyer instruction that is the whole point of the message. Both used to vanish.
REAL_3 = (
    "Location     UK\n"
    "Keywords: Fungal Nail Treatment for Toenails Extra Strong\n"
    "Price: 9.99\n"
    "Store Name: Putianchengxiangpeiman Trading Co., Ltd.\n\n"
    "https://lexofinds.blogspot.com/2026/07/fungal-nail-treatment-for.html\n\n"
    "Must order through link otherwise not accept cancel"
)
p3 = message.parse(REAL_3)
check("recognised fields still read", p3.fields.get("price") == "9.99", p3.fields)
check("an unknown label is carried, not dropped",
      any("Store Name" in x for x in p3.extra), p3.extra)
check("the sender's own instruction is carried",
      any("Must order through link" in x for x in p3.extra), p3.extra)

reply3 = message.format_task_reply(p3, "https://www.amazon.co.uk/dp/B0H28DCVYF?tag=t", "UK")
check("carried text sits after the link",
      reply3.index("Must order through link") > reply3.index("Link:"), reply3)
check("carried text sits above the sign-off",
      reply3.index("Must order through link") < reply3.index(message.BRANDING), reply3)

# the one that would cost real money if it were wrong
check("the sender's original link is NOT echoed back",
      "lexofinds.blogspot.com" not in reply3,
      "echoing it hands the buyer an untagged route to the product")
check("a line that was only a link carries nothing",
      not any("http" in x for x in p3.extra), p3.extra)

# no duplication of what is already formatted above
p4 = message.parse("USA\nYoga Mat")
check("a line that is only the country is not repeated", p4.extra == [], p4.extra)
p5 = message.parse("Country: USA\nKeyword: Fitness Tracker")
check("recognised field lines are not repeated", p5.extra == [], p5.extra)
p6 = message.parse("Usa review\nKeyword: Lamp")
check("a country line with other words keeps those words",
      any("review" in x for x in p6.extra), p6.extra)

flood = message.parse("Keyword: x\n" + "\n".join(f"line {i}" for i in range(40)))
check("a pasted essay cannot flood the reply",
      len(flood.extra) <= message.MAX_CARRY_LINES, len(flood.extra))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
