# Portal + Hub Pages Plan — "Beast Affiliate" user website

Last updated: 2026-07-22. Companion to [PROJECT-STATUS.md](PROJECT-STATUS.md)
(the live bot). This file records the **agreed design for the user-facing
website module** — decided over 2026-07-15/16 with the owner — plus the full
build log so any session can resume without re-deriving it.

**Status: phases 1–5 are BUILT and DEPLOYED** (article engine, bot integration,
portal, portal administration, earnings) plus a public marketing site. The
"Decisions locked" section below is the original agreement; where later
decisions superseded it, the build log at the bottom says so explicitly.
Code lives in a SEPARATE repo: `c:\Users\tehma\Desktop\beast-affiliates-website`
→ github.com/beastaffiliate/beast-affiliates-website.

## What is being built (one paragraph)

A user-facing portal + article ("hub") pages cloning the competitor
**ilearner.dev** (the same funnel site our resolver already reverse-engineered).
Registered bot users sign into a dashboard, set a per-user **WhatsApp Link
Preference** — `direct` (bot replies with the tagged Amazon link, current
behavior, DEFAULT) or `hub` (bot replies with a link to an article page on our
own domain). The article shows product info and a **"View on Amazon"** button
that 302-redirects through our click counter to the exact same tagged affiliate
URL the bot produces today. Users see analytics (views/clicks) and their link
list in the portal. Amazon only — Walmart explicitly declined.

## Competitor findings (from owner's screenshots of ilearner.dev + article pages)

- Portal: Overview (views/clicks/links/conversion, 7-day trend, top performers,
  recent links), Your Links (filter table, view/revoke), Earnings, Payouts,
  Profile (WhatsApp linking via code sent to their bot, up to 3 numbers,
  link-preference dropdown, public store page slug, bank details).
- Article page anatomy (template, all pages identical): header with **per-user
  store brand** ("Sufi"/"Azaan"), H1 title, catalog image, sidebar CTA
  "View on Amazon" + affiliate disclosure, "You May Also Like" (4 cross-links
  into their own other articles), description, pros/cons ("What We Like &
  What to Consider"), "Ideal For", "Worth Knowing", "Readers also viewed" /
  "Before you go" cross-links. Content is auto-generated boilerplate from
  product data (their pages cite star ratings → they fetch Amazon product data).
- They run **multiple registrable domains** (ilearner.dev + deals.ilearner.dev +
  ilearner-store.com + thehproducts.com) — reputation/risk spreading.
- URL shape: `/p/<4-char-id>/<seo-slug>`; buy button hits `api.ilearner.dev/go/<id>`
  (302 to tagged Amazon URL — that redirect IS their click counter).
- **Their earnings model ("How It Works" slides)**: the platform owns the Amazon
  Associates account(s); users are sub-affiliates. Amazon report ZIPs are
  downloaded from Associates Central, uploaded/parsed into their system, users
  see the same report-based numbers, platform receives Amazon's USD payout
  (~60 days after month end), converts, pays users their cut in PKR
  (min PKR 5,000, window 1st–10th). Per-product attribution is *estimated*
  (shared tags + "reservations & scoring rules").

## Client's model (confirmed via their existing WordPress admin screenshots)

The client already runs a **manual** earnings admin (WordPress at
beastaffiliate.com — see Domains below; built by a previous developer, client
may lose access). It shows: per-affiliate commission rate (varies per user:
80/70/20%), estimated payable, minimum payout (PKR 1,000), **referral bonuses**
(user A rewarded for referring user B), currency PKR. So: client owns the
Amazon side (claims an **Amazon Influencer account** — which is an Associates
account with a storefront; functionally identical for tags/tracking-IDs/reports),
users get a per-user percentage share.

## Decisions locked (owner confirmed each)

1. **Amazon only.** No Walmart.
2. **Link preference per user**: `direct` (default — pipeline byte-identical to
   today) vs `hub`. Stored on the user; the bot branch happens in
   `/process-message` at reply-format time only.
3. **Article data source**: PA-API if the client's credentials check out
   (client claims API access — MUST VERIFY: Access Key + Secret from Associates
   Central, and which marketplaces), else scrape (prototype-proven), always
   falling back to the sender's own WhatsApp image+caption. Note PA-API v5 has
   NO star ratings. **Articles are cached per (marketplace domain, ASIN)** —
   content shared across users; slug/tag/analytics stay per-link. Prototype
   measured 3,179 ms (fresh scrape) vs 18 ms (cache hit).
4. **Scraping vs PA-API is IRRELEVANT to earnings** (owner explicitly asked):
   earnings data comes ONLY from Amazon Associates Central **reports** (ZIP/CSV)
   or manual admin entry — PA-API is product data only, contains no earnings.
5. **Earnings feature: later phase but REQUIRED** (do not design it out).
   Client controls user shares in the admin dashboard. Schema must support:
   per-user commission %, per-user tracking IDs (exact attribution — better
   than competitor's estimates; ~100 tracking IDs per Associates account),
   report ingestion, payout records, referral bonuses. Risk on record: running
   sub-affiliates under one Associates account violates Amazon's operating
   agreement → suspension risk with ~2 months of commissions exposed; owner's
   client accepts (it's the competitor's whole business).
6. **Portal signup (client's chosen flow)**: user enters WhatsApp number → if it
   exists in the bot's users table AND is unclaimed → one-time signup (choose
   username+password) → afterwards login only. No OTP (hijack-window risk
   accepted); admin manages/resets portal accounts from the admin dashboard.
7. **Branding**: one site brand + per-user **store name** shown in the article
   header. Multi-domain branding deferred.
8. **US split (client requirement)**: articles for amazon.com links live on a
   DIFFERENT registrable domain than all other marketplaces. Subdomains do NOT
   satisfy this if the motive is isolation (reputation is scored at
   registrable-domain level). One domain → marketplace lookup table at
   link-creation time; same single app serves all domains via Host header.
9. ~~**Earnings pages, create-link-from-web, public store page (/u/slug),
   multi-number linking: OUT of v1.**~~ **SUPERSEDED** — earnings, the public
   store page and multi-number linking were all built by 2026-07-19. Only
   create-link-from-web remains unbuilt.

## Domains

- **Owned: `beastaffiliates.com`** (Namecheap, bought 2026-07-15 by owner).
- `beastaffiliate.com` (singular) belongs to the previous developer (hosts the
  client's current WordPress earnings admin on Hostinger); **no access, not
  ours, do not build on it**. Advised client to export their WordPress data
  (Reports → Export CSV) while they still have login access.
- **Need to buy ONE more clean .com (~$10/yr)** for the US/non-US split
  (decision #8). Avoid $0.98 promo TLDs (.shop/.online/.icu…): renewal traps +
  spam-flagged on WhatsApp — domain reputation is core functionality here,
  and article links are permanent once shared.

## Hosting (ALL NEW ACCOUNTS — owner explicit: do not reuse the bot's
Vercel/Neon/AWS; client creates accounts under their email and shares creds)

| Account | Plan | Purpose |
|---|---|---|
| Cloudflare | Free | DNS both domains, CDN cache for article pages, R2 bucket (product images; 10 GB free, zero egress) |
| Vercel | Free Hobby | New FastAPI app: article pages (SSR w/ OG tags for WhatsApp previews), /go redirects, portal API |
| Neon | Free | New Postgres: portal accounts, links, article cache, view/click events |
| GitHub | Free | New repo the new Vercel project deploys from |

- **NO AWS in the new stack** (rejected: egress pricing ~$0.09/GB is the worst
  fit for image-heavy pages; the "rotate free-tier accounts every 6 months"
  idea rejected — ToS violation, detection risk, forced migrations). Hostinger
  shared hosting rejected (PHP/MySQL — can't run FastAPI/Postgres; 48-month
  prepay; throttles on spikes). The bot's EC2 adapter is untouched/unrelated.
- Cost: $0/mo now; realistic ceiling ~`$40/mo` (Vercel Pro + Neon Launch) at
  hundreds of active users. Article pages are static per product → Cloudflare
  edge cache absorbs traffic; `/go` redirect must never be cached (it counts
  clicks); views counted via uncached beacon (page HTML itself is cached).
- Storage math (owner asked): article = DB row (~3 KB text), NOT a stored page;
  images are the only real storage (~50–100 KB each → R2). WhatsApp media URLs
  expire → images must be copied to R2 at link-creation.

## Architecture deltas (when building starts)

- New tables: `portal_accounts` (user_id, username, password_hash),
  `links` (slug, user_id, marketplace, asin, tagged_url, created),
  `products` (domain+asin PK: title, image_ref, bullets, generated copy,
  scraped_at), `link_events` (link_id, view|click, ts). `users` gains
  `link_preference` (default 'direct') and `store_name`.
- `/process-message`: after existing rewrite, if sender preference = hub →
  ensure product cached → create link row → reply with article URL instead.
  **Failure rule: if article creation fails for ANY reason, reply with the
  direct tagged Amazon link (never silence, never a broken reply).** Existing
  users are untouched until they opt in (default 'direct').
- Domain routing: marketplace → article-domain lookup (US → domain A, rest →
  domain B), Host-header aware app, extensible to more domains.
- Adapter: unchanged (it just relays reply text).

## Local prototype (WORKING, tested by owner)

`hub-prototype/` (gitignored, local-only, single file `app.py` + SQLite).
Run: `cd hub-prototype && "../backend/.venv/Scripts/python.exe" -m uvicorn
app:app --port 4100 --reload` → http://localhost:4100. Proves: Amazon scrape
(title/image/rating/bullets via regex, browser UA), template article generation
(no LLM), per-ASIN cache, per-link tag on /go redirect, view/click counting,
competitor-style page, Reset-all button. Uses stdlib body parsing (backend venv
has no python-multipart). Note: uvicorn --reload does NOT reliably pick up this
harness's file edits — restart the process after editing.

## Build progress

- **2026-07-16 — Phase 1 backend BUILT + locally tested** in the separate repo
  folder `c:\Users\tehma\Desktop\beast-affiliates-website` (own git repo,
  commit `28f89b6`; not yet pushed to GitHub/Vercel). backend/ = FastAPI (uv),
  frontend/ = Vite react-ts scaffold. Working + tested locally: mint API
  (`POST /api/links`, X-Service-Key auth), SSR article page w/ OG tags,
  `/go` click redirect (no-store), `/b` view beacon, per-ASIN cache, canonical
  tag merge, US-vs-INTL article-domain routing, PA-API SigV4 client (all 9
  marketplaces, env-driven creds), scrape fallback. Verified live: US scrape OK
  from owner's IP. Second domain bought: **beastassociate.com** (spelling
  confirmed). NL has no PA-API account (8 CSVs: US UK CA DE FR IT ES AU).
- **2026-07-16 — owner switched data source to SCRAPE-FIRST** (PA-API kept in
  tree behind `USE_PAAPI=false` env flag). Scraper = the proven hub-prototype
  extraction (title/hiRes image/star rating/bullets) + hardening: 3 browser
  identities tried in random order (desktop Chrome/Firefox/mobile Safari,
  0.5–1.5s pause between) — this DEFEATED the amazon.co.uk CAPTCHA that blocked
  the single-UA prototype; + title cleaner (strips "Amazon.co.uk: Category"
  chrome from meta/title fallbacks). Verified: US 4.8★/6 bullets, UK 4.6★
  clean title, cache hit ~0.3s, rating line in article copy. Caveat on
  record: scraping from Vercel datacenter IPs will block more often than from
  a home IP — if production failure rate is high, options are USE_PAAPI=true
  or a scrape proxy. Repo pushed to
  github.com/beastaffiliate/beast-affiliates-website (latest changes staged
  locally, commit pending owner push).

- **2026-07-16/17 — Phase 1 DEPLOYED + verified on production.** Owner set up
  new-account Vercel (project root `backend/`) + Neon + Cloudflare; domains
  live: www.beastaffiliates.com (portal+US articles), www.beastassociate.com
  (non-US articles); apex 308s to www. Fixed on deploy: missing
  psycopg2-binary (FUNCTION_INVOCATION_FAILED). SERVICE_KEY set (mint API
  401s without it; key known only to owner). Real articles created by owner
  from Vercel IPs via scrape — datacenter scraping WORKS. Fixed after owner
  test: non-US images missing (mobile UA pages lack our image fields —
  now desktop-first identity order + data-a-dynamic-image parsing +
  best-result selection + self-heal of imageless cached products on next
  link-create) and canonical-domain redirect (article opened on the wrong
  domain 308s to its marketplace's domain; localhost/previews unaffected).
  Verified live: CA article on US domain → 308 → beastassociate.com 200;
  US article on US domain → 200 direct. Products cached before the image fix
  heal when a new link for the same ASIN is created (owner re-creates once).

- **Phase 2 — bot integration DEPLOYED, owner-confirmed on real WhatsApp.**
  Per-user `link_preference` decides the reply format; `app/hub.py` mints the
  article (7s budget) and any failure leaves the direct tagged link untouched.
  Env `HUB_API_URL` + `HUB_SERVICE_KEY` on the bot's API project.

- **Phase 3 — portal DEPLOYED (2026-07-18).** Number-gate signup (no OTP),
  Overview / Earnings / WhatsApp Linking / Profile. Design follows the owner's
  "Frontend Design Files" (aubergine, Slack-ish). Extras shipped the same week:
  Your Links merged into Overview; centered wider Profile with a data-URL
  avatar; public store page `/u/<slug>` (SSR, today/yesterday/week + country
  filters); payout details with the PK bank list; mobile responsiveness for
  portal and articles.
  **Multi-number linking**: portal generates a 6-char single-use code (3 min
  TTL, `wa_link_codes`); an unregistered sender texting exactly that code to the
  bot gets linked (`linked_numbers` in the BOT db, inheriting the primary's tags
  and preference; the confirmation reply rides a `links_replaced=1` hack because
  the adapter only replies when that is > 0). Cap 3 numbers including the
  primary; all attribution stays under the main account. Unlink from the portal
  via the bot's guarded `/service` router.

- **Phase 4 — Portal administration DEPLOYED (2026-07-19).** Red tab in the bot
  dashboard at real route `/portal-admin`. Sub-tabs: Accounts, Linked numbers,
  Payout details, Overall performance, Earnings. The dashboard talks only to the
  bot API (`/portal-admin/*`, admin token), which proxies the website's
  `/api/admin/*` (X-Service-Key) and merges bot-side data.

- **Phase 5 — EARNINGS DEPLOYED (2026-07-19), admin-managed, NO Amazon API.**
  Attribution comes from per-user tracking IDs the admin reads manually from
  the client's Amazon dashboard. `portal_settings` (default_rate 20, min_payout
  1000), `portal_accounts.commission_rate` (NULL = default), `earnings_entries`
  (earning = gross PKR × frozen rate; bonus; adjustment ±), `payout_records`
  with a method snapshot. Users see **net share only** — no gross, no rate
  (verified for leakage). Decisions: PKR only, freeform entry labels, rates
  hidden from users, threshold admin-configurable.
  *Client reminder on record*: each user needs a unique tracking ID or Amazon
  cannot split the earnings.

- **Orders + referrals (2026-07-19/20).** `portal_accounts.orders` — an
  admin-entered purchase count shown in the user's Overview. `referrals` — the
  admin rewards a referrer for a referred portal user OR a free-text name; the
  amount adds to the referrer's balance.

- **Always-publish articles (owner decision, 2026-07-20).** EVERY rewritten link
  now creates a fresh article for ALL users (per-user link dedup removed from
  `service.create_link`). The reply still respects preference: hub users get the
  article URL, direct users keep the tagged Amazon link but the article still
  appears in their portal. The per-(marketplace, ASIN) product cache is KEPT, so
  this adds no extra scraping.

- **Forwarded article links (2026-07-21).** The bot's resolver now recognizes our
  own `/p/<id>` and `/go/<id>` URLs on both domains and resolves them through a
  key-guarded `GET /api/links/{id}/resolve`, which records **no** view or click —
  so forwarding never inflates the original creator's stats. The forwarded link
  is re-tagged to the NEW sender and answered per their preference. `create_link`
  accepts `source_link_id` so forwarding your OWN article returns that same
  article instead of a duplicate.

- **Public marketing site (2026-07-21).** An earlier "demo portal with dummy
  data" homepage was built and then **replaced entirely** at the owner's
  request with a real business website: Home, Articles & Guides, About, Contact,
  Privacy Policy, Terms. Server-rendered (`app/site.py`) so BOTH domains share
  one implementation; the portal SPA moved to `/dashboard`. No popups; a Log in
  button on every page. Cards show product images linking to `/go/<id>`.
  Gotchas hit and fixed: Vercel rewrites run after the filesystem check (so
  `dist/index.html` won `/` until explicit routes were used); the CSS string uses
  `%(accent)s` named formatting, so every literal `%` must be escaped as `%%`.

- **Built-in tracking IDs (2026-07-22).** `marketplaces.default_tag` per country;
  Add User has an auto-fill checkbox, and the per-user editor has "Fill empty
  from defaults" (fills blanks only). Existing users are never touched.

- **Admin-created portal accounts + editable earnings (2026-07-22).** Portal
  administration → Accounts lists registered bot users with no portal account
  (scrollable, search past 10 rows) with a Create-account button per row: the
  admin sets username + password and shares them out of band, no forced change
  at first login. Referral rewards became editable (amount, note, date, and the
  referred person, switching between a portal user and free text), and then
  every column of an earnings entry became editable (kind, label, gross, rate,
  share, date) — share follows gross × rate live but stays overridable so the
  figure Amazon actually paid can be recorded.

## Open items

1. Client's PA-API credentials + marketplace coverage — still unverified.
   Currently irrelevant in practice: the site is scrape-first and
   `USE_PAAPI=false`. NL has no PA-API account (8 CSVs: US UK CA DE FR IT ES AU).
2. ~~Buy the second domain~~ — done: **beastassociate.com**.
3. ~~Client creates the new accounts + nameserver change~~ — done; both domains
   live behind Cloudflare.
4. ~~Decide which domain gets US vs rest~~ — done: US → beastaffiliates.com
   (also hosts the portal and marketing site), all others → beastassociate.com.
5. **Contact details are placeholders** — `support@beastaffiliates.com` appears
   throughout the marketing site and the contact form is a `mailto:` link.
   Owner has not supplied a real address or said whether the form should do
   real submissions.
6. ~~No backup system~~ — **BUILT 2026-07-22.** Backup button in the dashboard
   header downloads a zip of users+tracking IDs, portal accounts (password
   hashes only) and all earnings; bot `/portal-admin/backup` → website
   `/api/admin/backup`. Download only (no import), and the EC2 Baileys
   `session/` folder is still not backed up. See PROJECT-STATUS.md.
7. Create-link-from-web (users minting a link in the portal rather than over
   WhatsApp) is the only original v1 exclusion still unbuilt.
