"""MUST_LINK_FEATURE — placement rules and the off switch.

Pure unit tests against rewriter.append_must_link (no server needed), so the
off state can be exercised by flipping the env var in-process.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rewriter import MUST_LINK_TEXT, append_must_link  # noqa: E402

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail!r}")


class MP:
    def __init__(self, mid, code):
        self.id, self.code = mid, code


DM = {"amazon.com": MP(1, "US"), "amazon.co.uk": MP(2, "UK")}
US = "https://www.amazon.com/dp/B0X?tag=beastaffiliate-20"
ART = "https://www.beastaffiliates.com/p/a3F9kd/sony-headphones"

os.environ["MUST_LINK_FEATURE"] = "true"

# --- single link: end of the line the link sits on ---
check("bare link gets the line",
      append_must_link(US, 1, DM) == f"{US}\n\n{MUST_LINK_TEXT}")

check("caption above, link last",
      append_must_link(f"Great deal\n{US}", 1, DM) == f"Great deal\n{US}\n\n{MUST_LINK_TEXT}")

check("text below the link is not split",
      append_must_link(f"Deal\n{US}\nthanks!", 1, DM)
      == f"Deal\n{US}\n\n{MUST_LINK_TEXT}\nthanks!")

check("link mid-sentence stays intact",
      append_must_link(f"buy {US} now", 1, DM) == f"buy {US} now\n\n{MUST_LINK_TEXT}")

# --- hub article replies get it too ---
check("article link (hub user)",
      append_must_link(f"Nice\n{ART}", 1, DM) == f"Nice\n{ART}\n\n{MUST_LINK_TEXT}")

check("article link with text below",
      append_must_link(f"Nice\n{ART}\nbye", 1, DM) == f"Nice\n{ART}\n\n{MUST_LINK_TEXT}\nbye")

# --- several links: once, at the very end ---
two = f"a {US} b https://www.amazon.co.uk/dp/B02?tag=x-21 c"
check("two links -> one line at the very end",
      append_must_link(two, 2, DM) == f"{two}\n\n{MUST_LINK_TEXT}")
check("appears exactly once with two links",
      append_must_link(two, 2, DM).count(MUST_LINK_TEXT) == 1)

check("three links -> still one line at the end",
      append_must_link(f"{US} {US} {US}", 3, DM).count(MUST_LINK_TEXT) == 1)

# --- never added when there is nothing to buy ---
check("no links -> untouched",
      append_must_link("hello, no links here", 0, DM) == "hello, no links here")
check("plain text with a non-amazon url, 0 links -> untouched",
      append_must_link("see https://example.com/ ok", 0, DM) == "see https://example.com/ ok")

# --- idempotent: forwarding one of our own replies doesn't double it ---
once = append_must_link(US, 1, DM)
check("not appended twice", append_must_link(once, 1, DM) == once)
check("still exactly one line", append_must_link(once, 1, DM).count(MUST_LINK_TEXT) == 1)

# A reply sent under the previous wording, forwarded back in, must not collect
# a second line on top of the old one.
old_wording = f"{US}\n\n*MUST BUY USING THIS ABOVE LINK*"
check("older wording recognized, not doubled",
      append_must_link(old_wording, 1, DM) == old_wording)

check("the line is bold for WhatsApp",
      MUST_LINK_TEXT.startswith("*") and MUST_LINK_TEXT.endswith("*"))

# --- trailing whitespace tidied on the append path ---
check("trailing newlines collapsed",
      append_must_link(f"{US} x\n\n\n", 2, DM) == f"{US} x\n\n{MUST_LINK_TEXT}")

# --- non-amazon single link falls back to the end ---
check("unknown host link -> appended at end",
      append_must_link("see https://example.com/x\nbye", 1, DM)
      == "see https://example.com/x\nbye\n\n" + MUST_LINK_TEXT)

# --- the off switch: replies must be byte-identical to pre-feature output ---
for off in ("false", "0", "no", "off", "FALSE", "Off", ""):
    os.environ["MUST_LINK_FEATURE"] = off
    samples = [US, f"Great deal\n{US}", two, f"Deal\n{US}\nthanks!"]
    ok = all(append_must_link(t, 2, DM) == t for t in samples)
    check(f"flag off via {off!r} -> text unchanged", ok)

os.environ["MUST_LINK_FEATURE"] = "true"
check("flag back on works", append_must_link(US, 1, DM).endswith(MUST_LINK_TEXT))

del os.environ["MUST_LINK_FEATURE"]
check("default (unset) is ON", append_must_link(US, 1, DM).endswith(MUST_LINK_TEXT))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
