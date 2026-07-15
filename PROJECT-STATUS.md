# Project Status — WhatsApp Amazon Affiliate Link Bot

Last updated: 2026-07-16. Read [project-handout.md](project-handout.md) first for the
original client spec; this file records everything built and deployed since.

**System is LIVE with ~40 real users, ramping toward 150–200.** Latest deployed
commit: `11db95e` (SCALE FIX part 2). All three tiers auto-deploy on `git push`.

### Quick history (newest first)
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
- `resolver.py` — for non-Amazon links: (1) site-specific handlers, (2) follow
  HTTP redirects (`amzn.to`, `a.co`, `amzn.eu`, `amzn.asia`), (3) fetch page HTML
  and scan for the first Amazon URL (works for blogspot pages).
  **Site handlers** (client's own JS-rendered funnel sites whose HTML has no link):
  - `pointmarketing.shop/prodetail/<mongo-id>` → GET
    `https://pointmarketing.shop/api/products/<id>` → JSON `product.Link`
  - `ilearner.dev/link/<id>`, `ilearner-store.com/p/<id>[/slug]`, `*.ilearner.dev`
    → GET `https://api.ilearner.dev/go/<id>` (302 Location = Amazon URL; note:
    this increments their click analytics)
- `routers/auth.py` — `POST /auth/login` checks `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  env vars (set in the Vercel API project; also in local `backend/.env`,
  gitignored). Returns HMAC-signed 12h token; signing key derived from the creds,
  so changing the password invalidates tokens. `/users` + `/marketplaces` CRUD
  require the token; `/process-message` and `/health` stay open (adapter calls
  process-message server-to-server).
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
  clearing a tag deletes it), Users (card editor), Marketplaces, Test message.
- Login page; token in localStorage; auto-logout on 401.
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

## Current production data (as of 2026-07-16)

- **LIVE with ~40 real users**, ramping toward 150–200 over coming weeks.
  See the dashboard Overview tab for the current list. The sender number in the
  DB must exactly match E.164 format (`+92...`).
- **Tags may still be `testabc`** on some/all users from the 2026-07-13 delivery
  testing. Real pre-test tags for the original 9 users are backed up outside this
  public repo (developer's local Claude memory); confirm with the owner what the
  live tag state should be before assuming.
- The bot's own number was `+923460976174`; its matching DB user was deleted
  during testing — register the bot's current number for self-chat testing.
- Owner's own number `+923111592151` is registered as "Tehman".

## Testing

`backend/tests/` holds the integration scripts (run against a live server):
- `test_api.py` — 21 rewrite-engine cases (needs local server + seeded DB)
- `test_auth.py` — 13 auth cases (needs ADMIN_* env vars from `backend/.env`)
- `test_funnels.py` — funnel-site resolution (network-dependent; tag-agnostic
  because DB tags are currently `testabc`)
- `test_canonical.py` — 8 pure-unit cases for canonical short links (no server
  needed), incl. the real monster share URL from the client
Run: start the API, then `uv run python tests/test_api.py` (override target with
`API_BASE=https://...`); `test_canonical.py` runs standalone. Update `SENDER`
constants if the registered number changes.

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
- No LLM/AI anywhere — deterministic by spec. No PA-API, no scraping product data.
- render.yaml is a leftover from an abandoned Render deployment option (unused).
- `hub-prototype/` (gitignored, local only) — an unrelated hub-page experiment;
  not part of the deployed product.

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
