import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite by default for local development; set DATABASE_URL to a
# postgresql:// URL in production without any code change.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")

# Some providers (Neon, Heroku-style) hand out postgres:// URLs, which
# SQLAlchemy no longer accepts as a dialect name.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# pool_pre_ping: serverless hosts (Vercel) freeze between invocations, which
# silently kills idle Postgres connections — verify before reuse.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
