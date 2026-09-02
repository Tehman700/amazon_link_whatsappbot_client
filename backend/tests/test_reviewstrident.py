"""Offline test for the reviewstrident.com resolver handler.

reviewstrident.com blocks plain HTTP, so the resolver renders it through Jina
Reader (_render_via_jina) and scans the result for the Amazon link. The Jina
render is stubbed here so the handler's matching logic runs with no network.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from app import resolver  # noqa: E402

AMZ = "https://www.amazon.com/dp/B0H417KB7X?ref=cm_sw_r_x&tag=someoneelse-20"
JINA_OK = ("Title: X\n\nMarkdown Content:\n## Introduction\ntext\n\n"
           f"Links/Buttons:\n- [Buy Now]({AMZ})\n")


class MP:
    def __init__(self, code, domain):
        self.id, self.code, self.domain = 1, code, domain


DOMAIN_MAP = {"amazon.com": MP("US", "amazon.com")}
called = []


def stub_render(text):
    async def _r(url):
        called.append(url)
        return text
    return _r


passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


def run(url, render_text):
    called.clear()
    resolver._render_via_jina = stub_render(render_text)
    # the passed client is unused on the reviewstrident path; a bare object is fine
    return asyncio.run(resolver._site_specific(object(), url, DOMAIN_MAP))


check("reviewstrident post resolves via Jina to the amazon link",
      run("https://reviewstrident.com/post/some-slug", JINA_OK) == AMZ)
check("the reviewstrident URL (not the jina-wrapped one) is what's rendered",
      called and called[-1] == "https://reviewstrident.com/post/some-slug")
check("www. subdomain works too",
      run("https://www.reviewstrident.com/post/some-slug", JINA_OK) == AMZ)
check("Jina output with no amazon link -> None",
      run("https://reviewstrident.com/post/x", "Title: X\nno links here") is None)
check("Jina failure (empty) -> None",
      run("https://reviewstrident.com/post/x", "") is None)

# a non-reviewstrident host must NOT render via Jina (no general fallback)
called.clear()
resolver._render_via_jina = stub_render(JINA_OK)
res = asyncio.run(resolver._site_specific(object(), "https://example.com/post/x", DOMAIN_MAP))
check("a non-reviewstrident host does not call Jina (no fallback)",
      res is None and called == [], called)

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
