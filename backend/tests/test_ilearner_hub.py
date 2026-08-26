"""Offline tests for the iLearner /w/<token> "Walmart hub" resolver handler.

The hub page is a JS SPA; its product URL comes from
api.ilearner.dev/api/walmart/hub/<token> as JSON ("productUrl"). The network
call is stubbed here so the handler logic is exercised with no network.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app import resolver  # noqa: E402

WALMART = "https://www.walmart.com/ip/19948217614"


class MP:
    def __init__(self, code, domain):
        self.id, self.code, self.domain = 1, code, domain


DOMAIN_MAP = {"walmart.com": MP("WM", "walmart.com"), "amazon.com": MP("US", "amazon.com")}


class FakeResp:
    def __init__(self, status=200, payload=None, location=None):
        self.status_code = status
        self._payload = payload
        self.headers = {"location": location} if location else {}
        self.url = ""
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    async def get(self, url, **kw):
        self.calls.append((url, kw))
        return self._responder(url, kw)


passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


def run(url, responder, domain_map=DOMAIN_MAP):
    return asyncio.run(resolver._site_specific(FakeClient(responder), url, domain_map))


def hub_ok(url, kw):
    assert url == "https://api.ilearner.dev/api/walmart/hub/4Esq2XiKJO", url
    return FakeResp(200, {"found": True, "productUrl": WALMART, "productId": "19948217614"})


check("ilearner /w/ resolves to the hub's walmart productUrl",
      run("https://ilearner.dev/w/4Esq2XiKJO", hub_ok) == WALMART)

check("deals.ilearner.dev/w/ works too",
      run("https://deals.ilearner.dev/w/4Esq2XiKJO", hub_ok) == WALMART)

check("hub with no productUrl -> None",
      run("https://ilearner.dev/w/ZZZ",
          lambda u, k: FakeResp(200, {"found": False, "reason": "not_found"})) is None)

check("hub non-200 -> None",
      run("https://ilearner.dev/w/ZZZ", lambda u, k: FakeResp(404, None)) is None)

check("productUrl on a marketplace we don't run -> None",
      run("https://ilearner.dev/w/4Esq2XiKJO", hub_ok,
          domain_map={"amazon.com": MP("US", "amazon.com")}) is None)


def go_redirect(url, kw):
    assert url == "https://api.ilearner.dev/go/341E", url
    assert kw.get("follow_redirects") is False
    return FakeResp(302, None, location="https://www.amazon.com/dp/B0TEST")


check("regression: ilearner /link/ still uses the /go/ redirect",
      run("https://ilearner.dev/link/341E", go_redirect) == "https://www.amazon.com/dp/B0TEST")

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
