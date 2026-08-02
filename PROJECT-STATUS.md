# Project Status — WhatsApp Amazon Affiliate Link Bot

Last updated: 2026-08-02. Read [project-handout.md](project-handout.md) first for the
original client spec; this file records everything built and deployed since.

**System is LIVE with 60 real users (540 tracking IDs), ramping toward 150–200.**
Latest deployed commit: `a1d545b` (resolver retry + cache). All three tiers
auto-deploy on `git push`.

### Quick history (newest first)
- **Resolver retry + resolution cache** (`a1d545b`, 2026-08-02) — third-party
  pages refuse Vercel's datacenter IPs about half the time; links are now
  retried and every successful resolution is remembered. See Resolver below.
- **`link.amazon` shortener + browser headers** (`932d13f`, 2026-08-02) — the
  one-line fix that took a client's 15-link sample from 5 to 11 working.
- **Number cap 3 → 6; recent links** (`5d651ba`, 2026-07-27) — a user may link
  6 WhatsApp numbers (primary + 5); the admin user-detail page shows the 10 most
  recent links instead of every link ever.
- **Nightly report email** (`f00ce56`, `e3aeab2`, 2026-07-28) — Vercel Cron mails
  the owner a per-user link report at midnight PKT. See Reporting below.
- **Overview search + dark mode** (`25cafb6`, 2026-07-26) — user search box on the
  Overview grid and a theme toggle in the dashboard navbar.
- **Tracking IDs on account detail** (`4dcfc70`, 2026-07-26) — view-only card,
  same data as the Overview grid.
- **Shipped orders** (`2646182`, 2026-07-25) — admin-set count shown in the
  user's portal Earnings tab, alongside orders; Balance column in Accounts.
- **Earnings merged into the account detail** (`6f5f072`, `c2950af`, 2026-07-24) —
  the separate Earnings sub-tab is GONE; a user's earnings now sit on their
  account page above their links, and global settings moved to a card atop
  Accounts.
- **MUST_LINK_FEATURE** (`408bfab` → `7706d16`) — a bold call-to-action line on
  every reply carrying a link, built as an env flag 2026-07-22 and REMOVED the
  same day at the owner's request. The backend is byte-identical to before it;
  do not reintroduce it unless asked.
- **One-click admin backup** (`e1a81ef`) — Backup button + downloadable ZIP.
- **Editable earnings entries** (`ea9a599`) — every column of an Entries row
  (kind, label, gross, rate, share, date) is editable in Portal administration.
- **Portal admin UI fixes** (`f2301df`, `14326f4`) — flat red nav tab, red
  Create-account button, page container widened to `min(1800px, 96vw)` so the
  9-marketplace Overview grid stops being cut off.
- **Admin-created portal accounts + editable referrals** (`d2b132c`) — admin can
  create a portal login for any registered bot user; referral rewards editable.
- **Built-in tracking IDs** (`d88d0ad`) — per-marketplace `default_tag`,
  auto-filled on user creation.
- **Forwarded article links** (`06f2703`) — our own `/p/` and `/go/` URLs are
  resolved and re-tagged to the forwarding user.
- **Portal administration + Earnings** (`ce97d92` → `42ed286`) — the whole
  `/portal-admin` gateway and dashboard page; see the section below.
- **Hub integration (phase 2)** — per-user `link_preference` ('direct' default /
  'hub') + `store_name` on users (idempotent startup ALTERs in main.py);
  hub-mode replies swap tagged links for article URLs via the Beast Affiliates
  website's mint API (`app/hub.py`; env `HUB_API_URL` + `HUB_SERVICE_KEY` in the
  API Vercel project — unset = feature off). Fail-safe: any mint failure leaves
  the direct tagged link. Admin dashboard Users tab has the preference/store
  controls. See [PORTAL-PLAN.md](PORTAL-PLAN.md).
- **SCALE FIX pt2** (`11db95e`) — adaptive pacing, per-chat fairness, random typing.
- **SCALE FIX pt1** (`43b3320`) — retry store (fixes "waiting for this message"),
  incoming dedupe (fixes double replies), paced reply queue.
- **Canonical short links** (`6abf3c7`) — replies are now `/dp/<ASIN>?tag=` short form.
- **Baileys v7 upgrade** (`79d60bf`) — fixed the LID no-delivery incident.
- Admin login, funnel-site resolver, Overview tab — see sections below.

## ⚠️ 2026-07-12/13 incident: replies not delivered (LID) — RESOLVED

Symptom: bot showed "Connected" and processed messages, but registered users got
no replies. Root cause chain (three stacked findings):

1. The bot's own number had been deleted from the users table when the client
   rebuilt the user list → self-chat tests were rejected as unregistered
   (data issue, re-registered via API).
2. WhatsApp migrated these accounts to **LID privacy addressing** (chat jids
   like `66932...@lid` instead of the phone number). Sender resolution was
   hardened to extract the real number from every known key field.
3. The killer: on Baileys 6.x, replies sent to LID-migrated recipients were
   **accepted by the server but never delivered** — logs said `replied`,
   phones showed nothing. Even routing to the classic phone-number jid didn't
   deliver. Fix: **upgraded to Baileys 7.0.0-rc13** (native LID session
   handling). Delivery confirmed working on real WhatsApp 2026-07-13.

Rules that must survive future edits: never reply to a `@lid` jid (route to the
resolved `@s.whatsapp.net` jid); keep the per-message decision log (status page
`&events=1`) — it is the only way these silent failures are visible. Tag
duplication across users and blank tags were investigated and are NOT failure
causes (blank tag = deliberate silence for that marketplace only).

## What the system does (proven end-to-end on real WhatsApp)

A registered user WhatsApps a message (image + caption or plain text) containing a
product link to the bot's number. The bot replies with the identical message —
image re-attached — where only the link is swapped for a tagged Amazon link using
**that sender's** tracking ID for **that marketplace**. Existing query params are
preserved; someone else's `tag=` is replaced. Non-Amazon links are resolved first
(see Resolver below). Unregistered senders, groups, and messages without a
rewritable link get silence (by design — client wanted no fallback chatter).

Two things layer on top of that core behaviour:

- **Reply format follows the sender's `link_preference`.** `hub` users (now the
  majority — see Current production data) get a link to an article page on the
  Beast Affiliates website instead of the raw tagged link; the article is minted
  within a 7 s budget and **any** failure falls back to the direct tagged link.
  An article is published for every rewritten link regardless of preference, so
  `direct` users still see their articles in the portal.
- **Labelled-ASIN fallback.** A message with no link at all but a recognisable
  ASIN plus a marketplace label builds the tagged link and prepends it. Silent
  unless everything resolves — see `build_from_asin` and `test_asin_fallback.py`.

The one thing the bot will never do is guess: every path that cannot produce a
correct tagged link for that specific sender ends in silence rather than a
wrong or untagged reply.

## Architecture / where everything runs

| Piece | Tech | Where | URL |
|---|---|---|---|
| Core API | FastAPI + SQLAlchemy | Vercel serverless, root dir `backend/` | https://amazon-link-whatsappbot-client.vercel.app (docs at `/docs`) |
| Admin dashboard | React + TS (Vite) | Vercel, root dir `frontend/` | https://amazon-link-whatsappbot-client-t1u5.vercel.app |
| Database | Neon Postgres (free) | Provisioned via Vercel Storage; `DATABASE_URL` injected into the API project | — |
| WhatsApp adapter | Node 20 + Baileys | AWS EC2 (Ubuntu), pm2 app name `wa-adapter`, repo cloned at `~/amazon_link_whatsappbot_client` | `http://<EC2-IP>:4000/?token=<STATUS_TOKEN>` (token in `whatsapp-adapter/.env` on the server) |

GitHub: https://github.com/Tehman700/amazon_link_whatsappbot_client (public — never
commit secrets).

## Deploy pipelines (all automatic on `git push` to main)

- **API + dashboard**: two Vercel projects import the same repo (root dirs
  `backend` / `frontend`); every push redeploys both.
- **Adapter**: `.github/workflows/deploy-adapter.yml` — on pushes touching
  `whatsapp-adapter/**` it SSHes to EC2 (secrets `EC2_HOST`, `EC2_USER`=ubuntu,
  `EC2_SSH_KEY`), git reset --hard, npm ci, pm2 restart. Manual re-run:
  Actions tab → workflow_dispatch. EC2 port 22 is open to 0.0.0.0/0 because
  GitHub runners deploy over SSH; port 4000 open for the status page.
- Fresh EC2 bootstrap: `whatsapp-adapter/deploy/setup.sh` (one curl | bash).

## Key implementation facts

### Backend (`backend/app/`)
- `rewriter.py` — URL detection (regex + trailing-punctuation strip), marketplace
  matching against the **DB table** (longest domain first, so `amazon.com.au`
  never matches `amazon.com`), `tag=` merge via `urllib.parse` (replaces foreign
  tags, keeps other params).
  **Canonical short links (commit `6abf3c7`)**: when the URL path contains a
  10-char ASIN (`/dp/`, `/gp/product/`, `/gp/aw/d/`, `/product/`), the reply is
  rebuilt as `https://<host>/dp/<ASIN>?tag=` keeping only KEEP_PARAMS
  (`th`, `psc`, `smid`, `m`) — this strips the hundreds of chars of share-tracking
  junk (`ref`, `social_share`, `rsd`, `edk`, `linkCode`…) so replies are short
  like the competitor's. No confident ASIN → previous behavior (full URL, tag
  merged). `ASIN_PATH_RE` and `KEEP_PARAMS` at top of file.
- `resolver.py` — for non-Amazon links, in order: (1) site-specific handlers,
  (2) follow HTTP redirects to a marketplace, (3) fetch the page HTML and scan
  for the first Amazon URL (blogspot/WooCommerce posts), (4) if the page instead
  links out via a known Amazon shortener, follow that.
  **Site handlers** (JS-rendered funnel sites whose HTML has no link):
  - `pointmarketing.shop/prodetail/<mongo-id>` → GET
    `https://pointmarketing.shop/api/products/<id>` → JSON `product.Link`
  - `ilearner.dev/link/<id>`, `ilearner-store.com/p/<id>[/slug]`, `*.ilearner.dev`
    → GET `https://api.ilearner.dev/go/<id>` (302 Location = Amazon URL; note:
    this increments their click analytics)
  - **our own** `/p/<id>` and `/go/<id>` on both article domains → the website's
    key-guarded `GET /api/links/{id}/resolve`, which records NO view/click, so
    forwarding never inflates the original creator's stats.
  `SHORT_HOSTS` = `amzn.to`, `amzn.eu`, `amzn.asia`, `a.co`, **`link.amazon`** —
  that last one is Amazon's own `.amazon`-TLD shortener, which affiliate blog
  templates now use *instead of* a marketplace URL, so those pages contain no
  `amazon.com` link at all and step 3 finds nothing without it.
  `HEADERS` sends a full browser header set, not a bare User-Agent: WooCommerce
  storefronts answer a bare UA with 403 and Facebook with 400.

  **Retry + cache (`a1d545b`, 2026-08-02) — read this before "fixing" a link
  that works locally but not in production.** These third-party pages throttle
  traffic from datacenter IP ranges, which is all a serverless host has.
  Measured on production: the *same* page succeeds roughly **half the time** on
  any single attempt, at random, while succeeding 100% of the time from a home
  IP. A throttled refusal returns in **~1 s**; a genuine timeout takes 8 s —
  that timing is how to tell them apart. So:
  - Each link gets `RESOLVE_ATTEMPTS` (3) tries, `RESOLVE_RETRY_DELAY` (0.7 s)
    apart.
  - A page answering **404/410** is deleted, not throttled, so it is tried once
    (the `gone` set threaded through `resolve_amazon_url`).
  - Every success is written to `resolved_links` (see Models) via
    `link_cache.py`, keyed by a SHA-256 of the URL normalised for case, trailing
    slash and fragment — the query string is KEPT, since funnel sites identify
    the product there. A later send of the same link does **no network I/O at
    all** and therefore cannot fail.
  - Entries expire after `RESOLVE_CACHE_TTL_DAYS` (30) so an edited post can
    point somewhere new; if that refresh is refused, the stored answer is used
    anyway rather than dropping the link.
  - The whole step is capped by `RESOLVE_BUDGET_SECONDS` (25) so a message full
    of slow links can never push the reply past the serverless limit.
  - **Facebook is a different problem**: it blocks Vercel IPs *always*, not
    intermittently (verified working from a home IP the same minute). Retrying
    cannot fix it — that needs a residential proxy. Once any single fetch
    succeeds, the cache makes that link permanent.
  All five knobs are env-overridable; the cache is an optimization and every
  failure path in `link_cache.py` degrades to "just fetch it".
- `models.py` — `users`, `linked_numbers`, `marketplaces`, `tracking_ids`, and
  `resolved_links` (the resolver cache: `source_hash` unique+indexed,
  `source_url`, `amazon_url`, `resolved_at`). The hash column exists because
  indexing a 2048-char URL directly risks Postgres' btree key-size limit.
  New tables are created by `Base.metadata.create_all` at startup — only added
  *columns* need the hand-rolled ALTERs in `main.py`.
- `routers/process.py` — the whole pipeline entry point. Also holds
  `MAX_NUMBERS_PER_USER = 6` (primary + 5 linked), enforced when an unregistered
  sender texts a 6-char linking code. **This constant must match
  `MAX_WA_NUMBERS` in the website's `portal.py`** — the portal shows the
  allowance and hands out codes, this enforces it on claim, and the refusal
  message is built from the constant so the two can never disagree in text.
- `routers/reports.py` — the nightly report. `GET /reports/daily-links?days=N&tz_offset=M`
  returns JSON (auth: `X-Report-Key`); `GET /reports/daily-email[?dry_run=true]`
  renders and sends it over stdlib `smtplib`, accepting either Vercel Cron's
  `Authorization: Bearer $CRON_SECRET` or `X-Report-Key` for a manual trigger.
  Scheduled by `crons` in `backend/vercel.json` at `0 19 * * *` UTC = midnight
  PKT (**Hobby fires within ~an hour of schedule, not on the minute**).
  **`tz_offset` is not optional decoration**: link timestamps are UTC but the
  report fires at PKT midnight, so bucketing by UTC days silently mixed the last
  5 h of one local day with 19 h of another. `REPORT_TZ_OFFSET` defaults to 300.
  Env on the API project: `REPORT_KEY`, `CRON_SECRET`, `SMTP_USER`, `SMTP_PASS`
  (Gmail app password — the code strips spaces), `MAIL_TO`, optional
  `MAIL_FROM`/`SMTP_HOST`/`SMTP_PORT`/`REPORT_TZ_OFFSET`.
  Chosen over n8n-on-EC2 purely on cost (~$10–15/mo for one daily email); the
  local n8n prototype worked and was retired. Chosen over the existing
  `/portal-admin/performance`, which only sees users WITH a portal account and
  was therefore blind to most activity.
- `routers/auth.py` — `POST /auth/login` checks `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  env vars (set in the Vercel API project; also in local `backend/.env`,
  gitignored). Returns HMAC-signed 12h token; signing key derived from the creds,
  so changing the password invalidates tokens. `/users` + `/marketplaces` CRUD
  require the token; `/process-message` and `/health` stay open (adapter calls
  process-message server-to-server).
  **Credentials were rotated 2026-07-22** (values live only in the Vercel env
  and the owner's password manager — never in this repo). Rotating them logs
  every open dashboard session out immediately, by design.
- `routers/portal_admin.py` — admin-token-guarded gateway to the website's
  `/api/admin/*` endpoints (adds `X-Service-Key`), merging bot-side data
  (user names, link preference, linked numbers, who has no portal account yet).
  The dashboard only ever talks to THIS API — same origin, same admin token.
  Needs `HUB_API_URL` + `HUB_SERVICE_KEY`; without them the tab 503s cleanly.
- `seed.py` — idempotent; auto-runs on startup only when the marketplaces table
  is empty (fresh-DB bootstrap). 9 marketplaces (US UK CA DE FR IT ES NL AU).
- `database.py` — SQLite locally, `DATABASE_URL` in prod; normalizes
  `postgres://`→`postgresql://`; `pool_pre_ping` for serverless.
- Deps managed by uv, but Vercel installs from `backend/requirements.txt` —
  **re-export after adding deps**: `uv export --no-dev --no-hashes
  --no-emit-project -o requirements.txt`.

### Frontend (`frontend/src/`)
- Tabs: **Overview** (default; stat totals + spreadsheet grid, one row per user,
  one column per marketplace, click-to-edit cells — Enter saves, Esc cancels,
  clearing a tag deletes it, plus a **search box** to find a user in what is now
  a 60-row grid), Users (card editor), Marketplaces (each row also holds a
  `default_tag` used to pre-fill new users), Test message, and the red
  **Portal administration** tab (real route `/portal-admin`, SPA fallback in
  `frontend/vercel.json`).
- Page container is `min(1800px, 96vw)` — the old 1100px cap cut the
  9-marketplace grid off at the FR column.
- **Dark mode** — toggle in the navbar; `:root[data-theme="dark"]` in
  `index.css` overrides the neutral palette only, so the design system in
  [design.md](design.md) still describes the light theme accurately.
- **Backup** button in the header — see the backup entry under Known constraints.
- Login page; token in localStorage; auto-logout on 401.

#### Portal administration (`views/PortalAdminView.tsx`)
Sub-tabs, all served through `/portal-admin/*` on this API. **There is no
Earnings sub-tab any more** (removed `6f5f072`, 2026-07-24) — earnings live on
each user's account page, because the admin was constantly cross-referencing two
tabs for one person.
- **Accounts** — starts with a card of **global earnings settings** (default
  commission rate, minimum payout) that used to sit inside the Earnings tab.
  Then portal accounts merged with bot data: name, reply preference, store page,
  links/views/clicks, admin-set **orders** and **shipped orders** with inline ✎,
  and a **Balance** column. Click a user for the detail view (below).
  Reset password shows a one-time temp password; disable suspends login without
  freeing the number; delete frees the number and keeps the links.
  Below it: **registered bot users with no portal account** — scrollable, search
  box past 10 rows, and a red **Create account** button per row so the admin can
  set a username + password on the user's behalf (shared out of band, no forced
  change at first login). Self-signup is unchanged for everyone else.
- **Account detail** (click a username) — profile summary, then, in this order:
  a view-only **Tracking IDs** card (same data as the Overview grid, so the
  admin does not have to switch tabs to check a tag), that user's **Earnings**,
  best-performing links, and **Recent links — the 10 most recent only**
  (`5d651ba`; it used to list every link ever, which was unusable for the
  heaviest senders).
  The earnings block is the full manage view: per-user rate, add earning with a
  live share preview, bonus / adjustment, payouts, referral rewards, history.
  **Entries and referrals are both editable in place.** For an entry, every
  column can be changed (kind, label, gross, rate, share, date); share follows
  gross × rate live as you type but stays editable, so a figure that differs
  from the arithmetic (what Amazon actually paid) can be recorded. Switching
  kind to bonus/adjustment zeroes gross and rate. Referral rewards allow
  editing amount, note, date and the referred person (portal user ↔ free text).
- **Linked numbers** — admin unlink (the bot DB owns `linked_numbers`).
- **Payout details** — bank/title/account per user, copyable, missing list.
- **Overall performance** — range + metric filters, bar and trend charts,
  conversion leaderboard. Note this only covers users WITH a portal account;
  for whole-system activity use the reporting endpoints instead.
- Prod builds ALWAYS call same-origin `/api/*` — `frontend/vercel.json` rewrites
  to the API project (no CORS, no env). `VITE_API_URL` is honored in dev only —
  deliberate, because a stray Vercel env var once broke prod. Styling follows
  [design.md](design.md) (Nike system: ink/canvas/soft-cloud, pill buttons, flat
  cards, hairline dividers).

### WhatsApp adapter (`whatsapp-adapter/src/index.js`)
- **Baileys 7.0.0-rc13** (required — see LID incident above; 6.x cannot deliver
  to LID-migrated recipients). Linked device; session in
  `whatsapp-adapter/session/` (gitignored) — survives restarts; on remote
  unlink it wipes the session and shows a fresh QR automatically (tested live).
- Handles LID chats (sender resolved via senderPn/participantPn/remoteJidAlt/
  participantAlt/lid-mapping store) and `append`-type upserts (own-device
  messages), guarded so pairing history sync can't trigger reply floods.
  Replies always go to the resolved `@s.whatsapp.net` jid, never to `@lid`.
- Every skip path logs a decision (undecryptable/stub content, non-notify
  upserts, unresolvable sender, unregistered, no link) — visible at `&events=1`.

#### SCALE FIX (2026-07-15/16) — revert anchor: git tag `pre-scale-fix`

Built for the 40→200-user ramp, in two parts, both adapter-only (API, DB,
dashboard, hosting all untouched). To fully revert: `git checkout pre-scale-fix
-- whatsapp-adapter` → commit → push (auto-deploys, session survives, no re-pair).

**Part 1 (commit `43b3320`)**
1. **Sent-message store + `getMessage` hook** — the bot keeps its last ~3000
   sent messages in memory; when a recipient can't decrypt a reply their phone
   sends a retry request, which Baileys fulfils from this store. This is the
   cure for the *"Waiting for this message"* stuck bubbles (a decryption
   failure, not slowness — see the tick note below). Do NOT remove this.
2. **Incoming message-id dedupe** — redelivered messages (retry receipts,
   notify/append overlap) are processed exactly once. Killed the double/triple
   replies that were seen in production. Only ids of messages WITH content are
   recorded, so an undecryptable stub followed by its retried content still works.
3. **Reply queue** (superseded by part 2's per-chat version).

**Part 2 (commit `11db95e`)**
1. **Adaptive pacing** — gap between sends keys off the bot's own send rate in
   the last 60s: ≤5/min → ~0.1–0.4s (effectively instant); 6–12/min → 1–2s;
   higher → 2–4s. Users feel an instant bot almost always; slowdown engages
   only during the aggregate burst that is the actual ban-signal.
2. **Per-chat round-robin queues** — one user's 15-message burst no longer
   blocks other chats; each chat's replies interleave, burst owner absorbs
   their own wait. (Replaced part 1's single global queue.)
3. **Random typing indicator** — shown on ~60% of replies (`Math.random()<0.6`),
   0.6–1.8s, instead of always.

**Retry store and dedupe are independent code paths from the queue** — pacing
changes never touch them.

#### Known cosmetic issue (NOT fixed, discussed 2026-07-16): one grey tick

Since the v7 upgrade, messages sent *to* the bot sometimes show only one tick.
Cause: Baileys v7 deliberately stopped auto-sending delivery ACKs (v7 migration
doc: WhatsApp was banning for it), so the 2nd "delivered" tick now depends on
the bot's *phone* being awake to ACK — hence inconsistent (was double when phone
online, single when only the EC2 device received). Purely cosmetic — messages
are received and answered regardless. Proposed but NOT yet applied (owner
deciding): explicitly mark incoming as read (`readMessages`) → consistent blue
ticks, at the cost of a small deliberate signal + showing "read". Also proposed:
randomize typing vs "recording" presence. Neither implemented yet.
- **Solo testing**: the account's "Message Yourself" chat processes own messages;
  a sent-ID set stops the bot's replies from re-triggering (loop guard).
- Replies only when `links_replaced > 0`; 404 (unregistered) and no-link → silent.
- Status page: QR pairing, connection badge; refresh 10s while pairing, 120s
  otherwise; hidden per-message decision log at `&events=1`.

## Current production data (as of 2026-08-02)

- **LIVE with 60 real users and 540 tracking IDs**, ramping toward 150–200.
  See the dashboard Overview tab for the current list. The sender number in the
  DB must exactly match E.164 format (`+92...`).
- **Reply preference has flipped to hub-first: 48 users on `hub`, 12 on
  `direct`.** The docs elsewhere describe `direct` as "the default", which is
  still true for a newly created user, but it is no longer the common case —
  most replies are now article links, so a website outage degrades far more
  users than it used to (fail-safe still applies: they get the tagged Amazon
  link instead).
- **19 portal accounts** exist (41 registered users have none) — the admin can
  create them from Portal administration → Accounts.
- **Real volume: 137–300 links/day from 16–24 active senders** over the week to
  2026-08-02. So roughly a third of registered users are active on a given day,
  and volume is concentrated: one sender has historically been 55–70% of it.
  This matters for the ban-risk maths in Known constraints — the aggregate is
  well under the 20k/day the client projects.
- **The owner's own row still has placeholder tags** (`testabc` / `test123`) from
  the 2026-07-13 delivery testing, so links the owner generates personally earn
  nothing. Other users' tags looked real as of 2026-07-22 and have not been
  re-verified since. Real pre-test tags for the original 9 users are backed up
  outside this public repo (developer's local Claude memory); confirm with the
  owner before assuming any tag state.
- **Developer testing runs through the owner's own number**, which inflates his
  row in the daily report on days when resolver work happens (e.g. 2026-08-02:
  83 of the day's 98 links were verification traffic, not real usage). Worth
  saying out loud before the owner reads a surprising report.
- The bot's number was replaced in July 2026; the old one's matching DB user was
  deleted during testing — register the bot's CURRENT number for self-chat
  testing. The owner's own number is registered as a normal user ("Tehman").
  **Actual numbers are deliberately not recorded here — this repo is public.**
  They live in the developer's local Claude memory and the dashboard.

## Testing

`backend/tests/` holds the integration scripts (most run against a live server):
- `test_api.py` — 21 rewrite-engine cases (needs local server + seeded DB)
- `test_auth.py` — 13 auth cases (needs ADMIN_* env vars from `backend/.env`)
- `test_asin_fallback.py` — 16 cases for the labelled-ASIN fallback (a message
  with no link but a recognisable ASIN + marketplace)
- `test_funnels.py` — 5 funnel-site resolution cases (network-dependent;
  tag-agnostic because some DB tags are placeholders)
- `test_canonical.py` — 8 pure-unit cases for canonical short links (no server
  needed), incl. the real monster share URL from the client
- `test_resolve_cache.py` — 10 **offline** cases for the resolver's retry and
  cache: the fetch is stubbed, so "refused twice then served", expiry, the
  stale-fallback, the 404-tried-once path and the time budget are all
  reproducible exactly. Runs standalone against in-memory SQLite; no server, no
  network, so this is the one suite that is safe to run anywhere.

63 + 10 = **73 cases total**, all green as of 2026-08-02.

Run: start the API, then `uv run python tests/test_api.py` (override target with
`API_BASE=https://...`); `test_canonical.py` runs standalone. Update `SENDER` constants if the registered number changes.
Note these are plain scripts, **not** pytest — run them with `python`, not
`python -m pytest` (collection blows up on their module-level `SystemExit`).

`test_api.py` needs a seeded fixture user with all 9 tags; if it 404s with
"Sender is not a registered user", the local DB is missing that user.

## Known constraints / decisions on record

- Linked-device protocol violates WhatsApp ToS — ban risk accepted by owner.
  Bot should run on a dedicated number, and **must stay out of all group chats**:
  when the bot was added to a group on Baileys 6.x it triggered LID
  session-poisoning that broke DM delivery. v7 + the no-groups rule mitigate it.
  Not-yet-built protection (owner asked, then paused): auto-leave any group the
  bot is added to (~10-line presence/group-event listener). Cheap first defense
  with zero code: phone → Settings → Privacy → Groups → "Nobody".
- The paced reply queue (jitter/rate-limit) the earlier plan called for is now
  BUILT — see SCALE FIX above.
- Client projects 150–200 users (~20k msgs/day). Infra handles it, but: Neon free
  compute-hours and Vercel hobby GB-hours are borderline at that volume
  (~$20–40/mo paid tiers fix it; Vercel hobby is also non-commercial-only), and
  one WhatsApp number at 20k replies/day is a serious ban risk even paced.
  Endgame options at that scale (owner is NOT using the official Meta API):
  **number sharding** — run the same adapter as 2–4 pm2 processes, each its own
  session/QR, users split across them (a ban then costs ¼ of users, not all);
  do this before ~80–100 users. Longer term the official WhatsApp Cloud API is
  the ban-proof answer (reply-only service conversations are free; only the
  adapter changes) if the owner ever reconsiders.
- **Hosting lifetimes**: Vercel + Neon = free forever at current volume (monthly
  caps, no expiry). AWS EC2 free tier **ends ~September 2026** → then ~$10–12/mo,
  OR migrate (15–20 min: new VM, run `setup.sh`, copy the `session` folder to
  avoid re-pairing, update EC2_* GitHub secrets). Oracle Cloud "Always Free" is
  the $0-forever destination; Lightsail/Hetzner ~$5/mo is the boring-correct one.
- **Admin backup: BUILT 2026-07-22.** A `Backup` button in the dashboard header
  (top-left) downloads a single ZIP — bot `GET /portal-admin/backup` (admin
  token) reads the bot DB (users + tracking IDs) and calls the website
  `GET /api/admin/backup` (service key) for portal accounts + earnings, then
  streams `beast-backup-YYYY-MM-DD.zip` (per-table CSVs + `backup.json` master +
  `README.txt`). If the website is unreachable it returns 503 rather than a
  half-empty zip. Portal passwords export as PBKDF2 **hashes only** — no
  plaintext is stored anywhere, so the backup enables a restore but cannot be
  used to read a password (use Reset PW for that). Download only — no import
  button. **Still NOT backed up:** the Baileys session folder on EC2
  (`whatsapp-adapter/session/`) — if that instance dies the bot cannot reply
  until someone re-pairs by QR. And the two Neon databases otherwise rely only
  on Neon's built-in point-in-time restore window (short on the free plan).
- No LLM/AI anywhere — deterministic by spec. **This bot** neither calls PA-API
  nor scrapes; article content is fetched by the separate website project
  (scrape-first, PA-API parked behind `USE_PAAPI=false`), never in this repo.
- render.yaml is a leftover from an abandoned Render deployment option (unused).
- `hub-prototype/` (gitignored, local only) — the original prototype for the
  portal + hub article pages, now superseded by the shipped
  `beast-affiliates-website` repo. Full design and build history:
  [PORTAL-PLAN.md](PORTAL-PLAN.md).

## Open items / explained but not built (as of 2026-08-02)

1. **Bilingual English + Urdu error replies** — the owner asked for the bot to
   explain *why* it could not answer, in one reply, in both languages. Fully
   scoped and explained; decisions already made: stay silent to unregistered
   senders, and only speak up for real problems (not for "this message has no
   link"). NOT built — the owner never confirmed the wording or the
   website-outage case. Would need an EC2 adapter redeploy, since the adapter
   only sends when `links_replaced > 0`.
2. **Facebook links** need a residential proxy (see Resolver); no proxy service
   has been chosen or costed.
3. **Rotate the Gmail app password** used by the report email — it was passed
   through a chat transcript. Outstanding.
4. **Real contact email for the marketing site** — still the placeholder
   `support@beastaffiliates.com` with a `mailto:` form. Owner never supplied one.
5. **Create-link-from-web** — the last original v1 exclusion still unbuilt.
6. **No restore button** for the backup ZIP (download only), and **no backup of
   the EC2 Baileys `session/` folder** — losing that instance still needs a QR
   re-pair.
7. **Auto-leave-group listener** — asked for, then paused. Zero-code mitigation
   available today: phone → Settings → Privacy → Groups → "Nobody".
8. ~~`Amazon APIs/` folder of live credential CSVs inside this public repo~~ —
   **resolved**: the folder is no longer in the project directory and nothing
   matching it is tracked (verified 2026-08-02). Keep it that way; PA-API keys
   belong only in the website project's Vercel env vars. Two real phone numbers
   were also scrubbed from these docs earlier — note that git *history* still
   contains them, so treat history as public.

## Agreed scale-up test plan (2026-07-13, not yet executed)

150 real users cannot be simulated (WhatsApp accounts need real numbers/devices).
The variance that matters is ~5 account states, each testable with one person:
LID-migrated account (already proven), classic account, WhatsApp Business app
sender, sender with active linked devices, sender on an outdated app version.

- Stage 1: the 9 existing real users each send 4 message shapes (plain link,
  image+caption, funnel link, two links) — verify replies + events log.
- Stage 2: ramp real users 20 → 50 → 150 over weeks, watching `&events=1`.
- BEFORE ramping past ~20 users: build the jitter/rate-limit reply queue in the
  adapter (randomized 2–8s delay, global send cap, typing indicator) — the
  scale risk is WhatsApp ban behavior, not load. Endgame at 150–200 users:
  migrate the adapter to the official WhatsApp Business Cloud API (reply-only
  service conversations are free; only the adapter changes).
