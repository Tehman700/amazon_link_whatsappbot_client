"""Hub-page PROTOTYPE — local testing only, not wired to the bot pipeline.

Paste an Amazon product link on http://localhost:4100 -> it scrapes the
product page (title, image, rating, feature bullets), generates a
competitor-style article, and serves it at /p/<id>/<slug>. The article's
"View on Amazon" button goes through /go/<id> (click counter) and lands on
the tagged affiliate URL — same tag-merge logic as the real rewriter.

Run:  "backend/.venv/Scripts/python.exe" -m uvicorn app:app --port 4100
      (from the hub-prototype directory)
"""

import html as htmllib
import json
import random
import re
import sqlite3
import string
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

DB_PATH = Path(__file__).parent / "prototype.db"
DEFAULT_TAG = "testabc"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

app = FastAPI(title="Hub Page Prototype")


# ------------------------------------------------------------------ storage

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS links (
            id TEXT PRIMARY KEY, slug TEXT, original_url TEXT, tagged_url TEXT,
            title TEXT, image TEXT, rating TEXT, bullets TEXT, store TEXT,
            source TEXT, created TEXT, views INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0
        )"""
    )
    # Per-product scrape cache: one row per (marketplace domain, ASIN). Article
    # content is shared across links; slugs/tags/analytics stay per-link.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS products (
            domain TEXT, asin TEXT, title TEXT, image TEXT, rating TEXT,
            bullets TEXT, scraped_at TEXT, PRIMARY KEY (domain, asin)
        )"""
    )
    return conn


def new_id(conn) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        candidate = "".join(random.choices(alphabet, k=4))
        if conn.execute("SELECT 1 FROM links WHERE id=?", (candidate,)).fetchone() is None:
            return candidate


# ------------------------------------------------------- tag merge (as prod)

def rewrite_url(url: str, tag: str) -> str:
    parts = urlsplit(url)
    params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() != "tag"
    ]
    params.append(("tag", tag))
    query = urlencode(params, quote_via=quote)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


# ---------------------------------------------------------------- scraping

# ASIN = the 10-char product code in /dp/<ASIN>, /gp/product/<ASIN>, etc.
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?=[/?]|$)", re.I)


def extract_asin(url: str) -> tuple[str, str] | None:
    """(marketplace domain, ASIN) cache key, or None if no ASIN in the URL."""
    parts = urlsplit(url)
    m = ASIN_RE.search(parts.path or "")
    if not m:
        return None
    domain = (parts.hostname or "").lower().removeprefix("www.")
    return (domain, m.group(1).upper())


def _strip_tags(fragment: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def scrape_amazon(url: str) -> dict:
    """Best-effort scrape of an Amazon product page. Returns a dict with
    whatever could be extracted plus a 'source' marker; raises ValueError
    with a human-readable reason when the page is unusable."""
    try:
        r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=20)
    except httpx.HTTPError as e:
        raise ValueError(f"fetch failed: {e}")
    if r.status_code != 200:
        raise ValueError(f"Amazon returned HTTP {r.status_code}")
    text = r.text
    if "captcha" in text[:30000].lower():
        raise ValueError("Amazon served a CAPTCHA page (bot detection)")

    m = re.search(r'id="productTitle"[^>]*>\s*(.*?)\s*</span>', text, re.S)
    title = _strip_tags(m.group(1)) if m else None
    if not title:
        m = re.search(r'<meta name="title" content="([^"]+)"', text)
        title = htmllib.unescape(m.group(1)) if m else None
    if not title:
        raise ValueError("could not find a product title in the page")

    image = None
    m = re.search(r'"hiRes":"(https://[^"]+)"', text)
    if m:
        image = m.group(1)
    if not image:
        m = re.search(r'id="landingImage"[^>]+data-old-hires="([^"]+)"', text)
        image = m.group(1) if m else None
    if not image:
        m = re.search(r'"large":"(https://[^"]+)"', text)
        image = m.group(1) if m else None

    m = re.search(r"([0-9.]+) out of 5 stars", text)
    rating = m.group(1) if m else None

    bullets = []
    m = re.search(r'id="feature-bullets".*?</ul>', text, re.S)
    if m:
        for raw in re.findall(
            r'<span class="a-list-item"[^>]*>\s*(.*?)\s*</span>', m.group(0), re.S
        ):
            cleaned = _strip_tags(raw)
            if cleaned and "hide" not in cleaned.lower()[:8]:
                bullets.append(cleaned)

    return {"title": title, "image": image, "rating": rating, "bullets": bullets[:6]}


# --------------------------------------------------- article copy generation

def make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return "-".join(slug.split("-")[:8]) or "product"


def sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return (text[0].upper() + text[1:] + ".") if text else ""


def generate_copy(title: str, rating: str | None, bullets: list[str]) -> dict:
    """Template-based article copy from scraped data (no LLM — prototype)."""
    short = title.split(",")[0].strip()
    if bullets:
        para1 = " ".join(sentence(b) for b in bullets[:2])
        para2 = " ".join(sentence(b) for b in bullets[2:4])
    else:
        para1 = (
            f"Based on the product listing, {short} targets buyers who want "
            "reliable everyday performance without overpaying."
        )
        para2 = ""
    if rating:
        para2 += (
            f" With {rating} stars on Amazon, it's earning solid feedback from "
            "real buyers — check recent reviews to see if it fits your needs."
        )
    pros = [b if len(b) <= 90 else b[:87] + "…" for b in bullets[:3]] or [
        "Straightforward, no-frills option for its category"
    ]
    cons = [
        "Prices and availability can change quickly on Amazon",
        "May not meet professional or heavy-duty requirements",
    ]
    ideal = [
        f"Shoppers looking for {short.lower()[:60]}",
        "Buyers who prefer ordering through Amazon with fast shipping",
        "Anyone comparing options before committing to a bigger purchase",
    ]
    tips = [
        "Check the size/specification table on Amazon before ordering",
        "Read the most recent reviews — products get revised over time",
        "Confirm the return policy for your region at checkout",
    ]
    return {"para1": para1, "para2": para2.strip(), "pros": pros, "cons": cons,
            "ideal": ideal, "tips": tips}


# -------------------------------------------------------------------- pages

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font:16px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif;color:#1a1a2e;background:#fff}
a{color:#1151ff;text-decoration:none}
header{background:#101828;color:#fff;padding:14px 32px;display:flex;justify-content:space-between;align-items:center}
header .brand{display:flex;gap:10px;align-items:center;font-weight:700;font-size:18px}
header .logo{width:30px;height:30px;border-radius:8px;background:#3b82f6;display:grid;place-items:center;font-size:15px}
header a{color:#cbd5e1;font-size:14px}
.wrap{max-width:1200px;margin:0 auto;padding:28px 32px}
h1{font-size:30px;margin:6px 0 22px;font-weight:650}
.grid{display:grid;grid-template-columns:1fr 330px;gap:28px;align-items:start}
.imgcard{border:1px solid #e5e7eb;border-radius:12px;padding:36px;display:grid;place-items:center;min-height:420px}
.imgcard img{max-width:100%;max-height:480px}
.side{display:flex;flex-direction:column;gap:16px}
.cta{display:block;text-align:center;background:#f59e0b;color:#fff;font-weight:700;font-size:17px;
     padding:15px 10px;border-radius:10px;box-shadow:0 2px 8px rgba(245,158,11,.35)}
.cta:hover{background:#d97706}
.note{border:1px solid #e5e7eb;border-radius:10px;padding:14px 16px;font-size:13.5px;color:#475569;background:#f8fafc}
.also{border:1px solid #e5e7eb;border-radius:12px;padding:18px}
.also h3{font-size:16px;margin-bottom:12px}
.also .item{display:flex;gap:10px;align-items:center;padding:9px;border-radius:8px;background:#f8fafc;margin-bottom:8px}
.also .item img{width:44px;height:44px;object-fit:contain;background:#fff;border-radius:6px}
.also .item div{font-size:13.5px;line-height:1.35}
.also .item a{display:block;font-size:12.5px;margin-top:2px}
section{margin:30px 0}
h2{font-size:21px;margin-bottom:10px}
section p{margin-bottom:12px;color:#334155}
.box{border:1px solid #e5e7eb;border-radius:12px;padding:20px 22px;margin:18px 0}
.box h3{font-size:16px;margin-bottom:12px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.cols h4{font-size:13px;letter-spacing:.4px;margin-bottom:8px}
.pros h4{color:#059669}.cons h4{color:#dc2626}
.box li{margin:6px 0 6px 18px;color:#334155;font-size:14.5px}
.crossbar{border:1px dashed #cbd5e1;border-radius:10px;padding:12px 16px;margin:16px 0;font-size:14px;
          display:flex;justify-content:space-between;align-items:center;background:#fafafa}
.crossbar span{color:#94a3b8;font-size:12px;display:block}
footer{border-top:1px solid #e5e7eb;margin-top:40px;padding:18px 32px;color:#94a3b8;font-size:13px;text-align:center}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
/* admin/index page */
.card{border:1px solid #e5e7eb;border-radius:12px;padding:22px;margin-bottom:22px}
form.create{display:grid;gap:10px}
form.create input{padding:11px 13px;border:1px solid #cbd5e1;border-radius:8px;font-size:15px;width:100%}
form.create button{padding:12px;border:0;border-radius:8px;background:#101828;color:#fff;font-weight:600;font-size:15px;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
th{color:#64748b;font-size:12px;letter-spacing:.4px}
td img{width:38px;height:38px;object-fit:contain}
.err{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px}
.okmsg{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px}
.pill{background:#eef2ff;color:#3730a3;border-radius:999px;padding:2px 10px;font-size:12px}
"""


def esc(v) -> str:
    return htmllib.escape(str(v or ""))


def page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}<footer>© 2026 Hub Page Prototype — local testing only</footer></body></html>"
    )


@app.get("/", response_class=HTMLResponse)
def index(error: str = "", created: str = "", src: str = "", ms: str = ""):
    conn = db()
    rows = conn.execute("SELECT * FROM links ORDER BY created DESC").fetchall()
    conn.close()
    table = ""
    if rows:
        body_rows = "".join(
            f"<tr><td><img src='{esc(r['image'])}'></td>"
            f"<td><a href='/p/{r['id']}/{r['slug']}' target='_blank'>{esc(r['title'][:70])}</a>"
            f"<br><span class='pill'>{r['id']}</span></td>"
            f"<td>{esc(r['created'][:16].replace('T', ' '))}</td>"
            f"<td><span class='pill'>{esc(r['source'])}</span></td>"
            f"<td>{r['views']}</td><td>{r['clicks']}</td>"
            f"<td><a href='/go/{r['id']}' target='_blank'>test button →</a></td></tr>"
            for r in rows
        )
        table = (
            "<div class='card'><div style='display:flex;justify-content:space-between;align-items:center'>"
            "<h2>Your links</h2>"
            "<form method='post' action='/reset' "
            "onsubmit=\"return confirm('Delete ALL links and the product cache?')\">"
            "<button style='background:#dc2626;color:#fff;border:0;border-radius:8px;"
            "padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer'>Reset all</button>"
            "</form></div><br><table>"
            "<tr><th></th><th>PRODUCT / ARTICLE</th><th>CREATED</th><th>SOURCE</th>"
            "<th>VIEWS</th><th>CLICKS</th><th>AMAZON REDIRECT</th></tr>"
            f"{body_rows}</table></div>"
        )
    msg = ""
    if error:
        msg = f"<div class='err'>Scrape failed: {esc(error)}</div>"
    if created:
        how = ""
        if src == "cache":
            how = f" — took {esc(ms)} ms, <b>served from cache</b> (product already scraped before, Amazon not contacted)"
        elif src == "scrape":
            how = f" — took {esc(ms)} ms, scraped fresh from Amazon"
        msg = f"<div class='okmsg'>Article created: <a href='{esc(created)}' target='_blank'>{esc(created)}</a>{how}</div>"
    body = f"""
<header><div class='brand'><div class='logo'>H</div>Hub Prototype</div>
<a href='/'>refresh stats</a></header>
<div class='wrap'>
  {msg}
  <div class='card'>
    <h2>Create a test hub link</h2><br>
    <form class='create' method='post' action='/create'>
      <input name='url' placeholder='Paste an Amazon product URL' required>
      <input name='tag' placeholder='Affiliate tag (default: {DEFAULT_TAG})'>
      <input name='store' placeholder='Store name shown in article header (default: Beast Affiliate)'>
      <button>Create link &amp; generate article</button>
    </form>
  </div>
  {table}
</div>"""
    return page("Hub Prototype", body)


@app.post("/create")
async def create(request: Request):
    # Parse the urlencoded body with the stdlib — this venv has no python-multipart.
    form = parse_qs((await request.body()).decode())
    url = form.get("url", [""])[0].strip()
    tag = form.get("tag", [""])[0].strip() or DEFAULT_TAG
    store = form.get("store", [""])[0].strip() or "Beast Affiliate"
    if not url:
        return RedirectResponse("/?error=no%20URL%20given", status_code=303)

    started = time.perf_counter()
    conn = db()

    # Cache first: same product (domain+ASIN) already scraped -> reuse it.
    key = extract_asin(url)
    cached = (
        conn.execute(
            "SELECT * FROM products WHERE domain=? AND asin=?", key
        ).fetchone()
        if key
        else None
    )
    if cached:
        data = {
            "title": cached["title"], "image": cached["image"],
            "rating": cached["rating"], "bullets": json.loads(cached["bullets"]),
        }
        source = "cache"
    else:
        try:
            data = scrape_amazon(url)
        except ValueError as e:
            conn.close()
            return RedirectResponse(f"/?error={quote(str(e))}", status_code=303)
        source = "scrape"
        if key:
            conn.execute(
                "INSERT OR REPLACE INTO products (domain, asin, title, image, rating,"
                " bullets, scraped_at) VALUES (?,?,?,?,?,?,?)",
                (*key, data["title"], data["image"], data["rating"],
                 json.dumps(data["bullets"]), datetime.now().isoformat()),
            )

    link_id = new_id(conn)
    slug = make_slug(data["title"])
    conn.execute(
        "INSERT INTO links (id, slug, original_url, tagged_url, title, image, rating,"
        " bullets, store, source, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            link_id, slug, url, rewrite_url(url, tag), data["title"], data["image"],
            data["rating"], json.dumps(data["bullets"]), store, source,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    ms = int((time.perf_counter() - started) * 1000)
    return RedirectResponse(
        f"/?created={quote(f'/p/{link_id}/{slug}')}&src={source}&ms={ms}",
        status_code=303,
    )


@app.post("/reset")
def reset():
    """Wipe all links AND the product scrape cache — fresh start for testing."""
    conn = db()
    conn.execute("DELETE FROM links")
    conn.execute("DELETE FROM products")
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.get("/p/{link_id}/{slug}", response_class=HTMLResponse)
def article(link_id: str, slug: str):
    conn = db()
    row = conn.execute("SELECT * FROM links WHERE id=?", (link_id,)).fetchone()
    if row is None:
        conn.close()
        return HTMLResponse(page("Not found", "<div class='wrap'><h1>Link not found</h1></div>"), 404)
    conn.execute("UPDATE links SET views = views + 1 WHERE id=?", (link_id,))
    conn.commit()
    others = conn.execute(
        "SELECT * FROM links WHERE id != ? ORDER BY created DESC LIMIT 4", (link_id,)
    ).fetchall()
    conn.close()

    copy = generate_copy(row["title"], row["rating"], json.loads(row["bullets"]))
    also_items = "".join(
        f"<div class='item'><img src='{esc(o['image'])}'>"
        f"<div>{esc(o['title'][:48])}<a href='/p/{o['id']}/{o['slug']}'>View product →</a></div></div>"
        for o in others
    ) or "<div style='color:#94a3b8;font-size:13.5px'>Create more links to see cross-promotions here.</div>"
    readers_also = (
        f"<div class='crossbar'><div><span>Readers also viewed</span>"
        f"<a href='/p/{others[0]['id']}/{others[0]['slug']}'>{esc(others[0]['title'][:70])}</a></div><div>→</div></div>"
        if others else ""
    )
    pros_lis = "".join(f"<li>{esc(p)}</li>" for p in copy["pros"])
    cons_lis = "".join(f"<li>{esc(c)}</li>" for c in copy["cons"])
    ideal_lis = "".join(f"<li>{esc(i)}</li>" for i in copy["ideal"])
    tips_lis = "".join(f"<li>{esc(t)}</li>" for t in copy["tips"])
    initial = esc(row["store"][:1].upper())

    body = f"""
<header><div class='brand'><div class='logo'>{initial}</div>{esc(row['store'])}</div>
<a href='#'>Affiliate Disclosure</a></header>
<div class='wrap'>
  <h1>{esc(row['title'][:90])}</h1>
  <div class='grid'>
    <div>
      <div class='imgcard'><img src='{esc(row['image'])}' alt='{esc(row['title'][:60])}'></div>
      <section>
        <h2>A closer look at {esc(row['title'][:60])}</h2>
        <p>{esc(copy['para1'])}</p>
        {f"<p>{esc(copy['para2'])}</p>" if copy['para2'] else ""}
      </section>
      {readers_also}
      <div class='box'>
        <h3>What We Like &amp; What to Consider</h3>
        <div class='cols'>
          <div class='pros'><h4>✓ PROS</h4><ul>{pros_lis}</ul></div>
          <div class='cons'><h4>✗ CONS</h4><ul>{cons_lis}</ul></div>
        </div>
      </div>
      <div class='box'><h3>Ideal For</h3><ul>{ideal_lis}</ul></div>
      <div class='box'><h3>Worth Knowing</h3><ul>{tips_lis}</ul></div>
    </div>
    <div class='side'>
      <a class='cta' href='/go/{row['id']}' target='_blank' rel='nofollow sponsored'>View on Amazon</a>
      <div class='note'><b>Affiliate Link:</b> We earn a small commission when you buy
        through this link — at no extra cost to you.</div>
      <div class='note'><b>Note:</b> Product prices and availability are subject to change.
        Final prices are determined by the retailer at checkout.</div>
      <div class='also'><h3>You May Also Like</h3>{also_items}</div>
    </div>
  </div>
</div>"""
    return page(row["title"][:70], body)


@app.get("/go/{link_id}")
def go(link_id: str):
    conn = db()
    row = conn.execute("SELECT tagged_url FROM links WHERE id=?", (link_id,)).fetchone()
    if row is None:
        conn.close()
        return HTMLResponse(page("Not found", "<div class='wrap'><h1>Link not found</h1></div>"), 404)
    conn.execute("UPDATE links SET clicks = clicks + 1 WHERE id=?", (link_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(row["tagged_url"], status_code=302)
