import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, SessionLocal, engine
from app.models import Marketplace
from app.routers import marketplaces, process, users
from app.seed import seed

Base.metadata.create_all(bind=engine)

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

app.include_router(process.router)
app.include_router(users.router)
app.include_router(marketplaces.router)


@app.get("/health")
def health():
    return {"status": "ok"}
