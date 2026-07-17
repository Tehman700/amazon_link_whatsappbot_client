import os

from dotenv import load_dotenv

load_dotenv()  # local dev credentials/config from backend/.env (gitignored)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine
from app.models import Marketplace
from app.routers import auth, marketplaces, process, users
from app.routers.auth import require_admin
from app.seed import seed

Base.metadata.create_all(bind=engine)

# Lightweight startup migration: create_all never adds columns to existing
# tables, so bring the live users table up to the current model. Idempotent
# (IF NOT EXISTS on Postgres; duplicate-column errors swallowed on SQLite).
from sqlalchemy import text as _text  # noqa: E402

for _ddl in (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS link_preference VARCHAR(8) DEFAULT 'direct'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS store_name VARCHAR(120) DEFAULT ''",
):
    try:
        with engine.begin() as _conn:
            _conn.execute(_text(_ddl))
    except Exception:
        try:  # SQLite has no IF NOT EXISTS for columns
            with engine.begin() as _conn:
                _conn.execute(_text(_ddl.replace(" IF NOT EXISTS", "")))
        except Exception:
            pass  # column already exists

# Bootstrap a fresh database (e.g. first production deploy) automatically.
# seed() is idempotent, but skip it entirely once marketplaces exist so a
# deliberately emptied table isn't resurrected on restart.
with SessionLocal() as _db:
    if _db.query(Marketplace).first() is None:
        seed()

app = FastAPI(title="Amazon Affiliate Link Bot API")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
# /process-message stays open — the WhatsApp adapter calls it server-to-server.
app.include_router(process.router)
# Admin CRUD requires a login token.
app.include_router(users.router, dependencies=[Depends(require_admin)])
app.include_router(marketplaces.router, dependencies=[Depends(require_admin)])


@app.get("/health")
def health():
    return {"status": "ok"}
