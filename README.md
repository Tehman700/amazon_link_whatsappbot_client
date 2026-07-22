# WhatsApp Amazon Affiliate Link Bot

Rewrites Amazon product links in WhatsApp messages with the sender's own
affiliate tracking tag for the detected marketplace. See
[project-handout.md](project-handout.md) for full client context.

## Structure

- `backend/` — FastAPI + SQLAlchemy (uv-managed). Core link-rewrite engine,
  `POST /process-message`, and admin CRUD for users / marketplaces / tracking IDs.
- `frontend/` — React + TypeScript (Vite) admin dashboard: manage users,
  their per-marketplace tracking IDs, marketplaces, and a live test panel.
  Styled per [design.md](design.md).

## Run locally

Backend (port 8000):

```sh
cd backend
uv run python -m app.seed        # first time only — seeds marketplaces + first user
uv run uvicorn main:app --reload
```

Frontend (port 5173):

```sh
cd frontend
npm run dev
```

API docs: <http://localhost:8000/docs>
Dashboard: <http://localhost:5173>

## Database

SQLite (`backend/bot.db`) by default for development. Set the `DATABASE_URL`
environment variable to a `postgresql://...` URL for production — no code change.

## Key API

`POST /process-message`

```json
{ "sender": "+92XXXXXXXXXX", "text": "Usa review\nhttps://www.amazon.com/dp/B0GS64BBG2?th=1" }
```

Response contains the text with only the link(s) rewritten (`&tag=` merged
correctly with existing query params), plus a list of replacements and any
skipped links (marketplace the sender has no tag for).

Unknown sender → `404`. No Amazon link → text returned unchanged, `links_replaced: 0`.

**Link resolution:** non-Amazon links are followed automatically — `amzn.to` /
`a.co` short links (redirects) and landing/blog pages containing a "View on
Amazon" link (page HTML is fetched and scanned). The original link in the
message is replaced by the tagged Amazon product link. If a page can't be
fetched or holds no Amazon link, it is left untouched.

## The rest of the system

This repo is one of two. The bot API and admin dashboard live here; the
user-facing website (marketing pages, portal, hub article pages, and the admin
endpoints behind the dashboard's "Portal administration" tab) lives in the
separate `beast-affiliates-website` repo. See
[PORTAL-PLAN.md](PORTAL-PLAN.md) for the design and full build log, and
[PROJECT-STATUS.md](PROJECT-STATUS.md) for what is deployed where.

The WhatsApp side runs on a Baileys linked-device adapter
(`whatsapp-adapter/`, deployed to EC2), not the Meta Cloud API.
