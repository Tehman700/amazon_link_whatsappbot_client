# Project Status — WhatsApp Amazon Affiliate Link Bot

Last updated: 2026-07-12. Read [project-handout.md](project-handout.md) first for the
original client spec; this file records everything built and deployed since.

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
- Baileys linked device; session in `whatsapp-adapter/session/` (gitignored) —
  survives restarts; on remote unlink it wipes the session and shows a fresh QR
  automatically (tested live).
- Handles LID chats (`senderPn` fallback) and `append`-type upserts (own-device
  messages), guarded so pairing history sync can't trigger reply floods.
- **Solo testing**: the account's "Message Yourself" chat processes own messages;
  a sent-ID set stops the bot's replies from re-triggering (loop guard).
- Replies only when `links_replaced > 0`; 404 (unregistered) and no-link → silent.
- Status page: QR pairing, connection badge; refresh 10s while pairing, 120s
  otherwise; hidden per-message decision log at `&events=1`.

## Current production data

- Single user "Beast Affiliate", WhatsApp **+923460976174** (= the bot's own
  number — owner tests via Message Yourself). 9 tags: beastaffiliate-20 (US),
  -21 (UK), 0a-20 (CA), 04-21 (DE), 07-28 (FR), 06-21 (IT), 00-21 (ES),
  09-29 (NL), -22 (AU). The sender number in the DB must exactly match the
  E.164 format `+92...`.

## Testing

`backend/tests/` holds the integration scripts (run against a live server):
- `test_api.py` — 21 rewrite-engine cases (needs local server + seeded DB)
- `test_auth.py` — 13 auth cases (needs ADMIN_* env vars)
- `test_funnels.py` — funnel-site resolution (network-dependent)
Run: start the API, then `uv run python tests/test_api.py` (override target with
`API_BASE=https://...`). Update `SENDER` constants if the registered number changes.

## Known constraints / decisions on record

- Linked-device protocol violates WhatsApp ToS — ban risk accepted by owner;
  mitigation path documented below. Bot should ideally run on a dedicated number.
- Client projects 150–200 users (~20k msgs/day). Infra handles it, but: Neon free
  compute-hours and Vercel hobby GB-hours are borderline at that volume
  (~$20–40/mo paid tiers fix it; Vercel hobby is also non-commercial-only), and
  one WhatsApp number at 20k replies/day is a serious ban risk. Agreed plan:
  ramp gradually → add jitter/rate-limit queue in the adapter (not yet built) →
  split across numbers or migrate the adapter to the official WhatsApp Business
  Cloud API (reply-only service conversations are free; only the adapter changes).
- No LLM/AI anywhere — deterministic by spec. No PA-API, no scraping product data.
- render.yaml is a leftover from an abandoned Render deployment option (unused).
