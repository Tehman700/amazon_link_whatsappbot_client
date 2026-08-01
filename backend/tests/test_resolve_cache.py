"""Retry-and-remember tests for the link resolver.

Offline by design: the point is the logic around the fetch, so the fetch
itself is stubbed and every third-party outcome (refused, then refused, then
served) can be reproduced exactly.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory, nothing on disk

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import link_cache, models, resolver  # noqa: E402
from app.database import Base  # noqa: E402

resolver.RETRY_DELAY_SECONDS = 0.01  # keep the suite fast

PAGE = "https://affecteddisc.blogspot.com/2026/07/twirest-mattress.html"
AMAZON = "https://www.amazon.de/dp/B0DBDPJ4KC"


class MP:
    def __init__(self, code, domain):
        self.id, self.code, self.domain = 1, code, domain


DOMAIN_MAP = {"amazon.de": MP("DE", "amazon.de")}

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


def fresh_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def stub(outcomes, deleted=False):
    """Replace the network call with a scripted sequence of results.
    `deleted` mimics a host answering 404 for a blog that no longer exists."""
    calls = []

    async def fake(client, url, domain_map, gone=None):
        calls.append(url)
        if deleted and gone is not None:
            gone.add(url)
        return outcomes[min(len(calls) - 1, len(outcomes) - 1)]

    resolver.resolve_amazon_url = fake
    return calls


real_resolve = resolver.resolve_amazon_url

# 1. a page refused twice then served is still resolved
calls = stub([None, None, AMAZON])
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP))
check(
    "retries past two refusals",
    out.get(PAGE) == AMAZON and len(calls) == 3,
    f"{out} after {len(calls)} tries",
)

# 2. a genuinely dead page gives up, and does not retry forever
calls = stub([None])
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP))
check(
    "gives up after RESOLVE_ATTEMPTS",
    out == {} and len(calls) == resolver.RESOLVE_ATTEMPTS,
    f"{out} after {len(calls)} tries",
)

# 3. a success is remembered
db = fresh_db()
calls = stub([AMAZON])
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP, db))
cached, is_fresh = link_cache.get(db, PAGE)
check(
    "successful resolution is written to the cache",
    out.get(PAGE) == AMAZON and cached == AMAZON and is_fresh,
    f"{out} / cached={cached} fresh={is_fresh}",
)

# 4. the next send of the same link costs no network call at all
calls = stub([None])  # would fail if it were fetched
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP, db))
check(
    "cache hit skips the fetch entirely",
    out.get(PAGE) == AMAZON and len(calls) == 0,
    f"{out} after {len(calls)} fetches",
)

# 5. same product, link written with a trailing slash and a #fragment
calls = stub([None])
out = asyncio.run(resolver.resolve_all([PAGE + "/#buy"], DOMAIN_MAP, db))
check(
    "trailing slash and fragment hit the same cache entry",
    out.get(PAGE + "/#buy") == AMAZON and len(calls) == 0,
    f"{out} after {len(calls)} fetches",
)

# 6. an expired entry is refreshed when the page answers
row = db.query(models.ResolvedLink).first()
row.resolved_at = datetime.utcnow() - (link_cache.CACHE_TTL + timedelta(days=1))
db.commit()
NEWER = "https://www.amazon.de/dp/B0NEWPROD1"
calls = stub([NEWER])
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP, db))
check(
    "expired entry re-resolves to the current product",
    out.get(PAGE) == NEWER and len(calls) == 1,
    f"{out} after {len(calls)} fetches",
)

# 7. ...but if the refresh is refused, the remembered answer is still used
row = db.query(models.ResolvedLink).first()
row.resolved_at = datetime.utcnow() - (link_cache.CACHE_TTL + timedelta(days=1))
db.commit()
calls = stub([None])
out = asyncio.run(resolver.resolve_all([PAGE], DOMAIN_MAP, db))
check(
    "failed refresh falls back to the stored link, never to nothing",
    out.get(PAGE) == NEWER,
    out,
)

# 8. a direct Amazon link is never fetched or cached
calls = stub([AMAZON])
out = asyncio.run(resolver.resolve_all(["https://www.amazon.de/dp/B0ABCDEFGH"], DOMAIN_MAP, db))
check("direct Amazon link needs no resolving", out == {} and len(calls) == 0, out)

# 9. a deleted blog answers definitively, so it is not retried
calls = stub([None], deleted=True)
out = asyncio.run(resolver.resolve_all(["https://united-usa-deals.blogspot.com/gone.html"], DOMAIN_MAP))
check("a 404'd page is tried once, not three times", out == {} and len(calls) == 1, f"{len(calls)} tries")

# 10. the retry budget cannot blow the serverless time limit
resolver.RESOLVE_BUDGET_SECONDS = 0.0
calls = stub([None])
out = asyncio.run(resolver.resolve_all(["https://slowsite.example/x"], DOMAIN_MAP, db))
check("exhausted budget stops the retry loop", out == {} and len(calls) == 0, f"{len(calls)} tries")
resolver.RESOLVE_BUDGET_SECONDS = 25.0

resolver.resolve_amazon_url = real_resolve
print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
