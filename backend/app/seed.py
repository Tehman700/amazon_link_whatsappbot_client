"""Idempotent seed: marketplaces + the first real user (tags from client's
WhatsApp message, 2026-07-11). Safe to run multiple times — existing rows
are left untouched.

Run with:  uv run python -m app.seed
"""

from .database import Base, SessionLocal, engine
from .models import Marketplace, TrackingID, User

MARKETPLACES = [
    ("US", "United States", "amazon.com"),
    ("UK", "United Kingdom", "amazon.co.uk"),
    ("CA", "Canada", "amazon.ca"),
    ("DE", "Germany", "amazon.de"),
    ("FR", "France", "amazon.fr"),
    ("IT", "Italy", "amazon.it"),
    ("ES", "Spain", "amazon.es"),
    ("NL", "Netherlands", "amazon.nl"),
    ("AU", "Australia", "amazon.com.au"),
]

# From the client's WhatsApp messages + dashboard edits (2026-07-11).
BEAST_TAGS = {
    "US": "beastaffiliate-20",
    "AU": "beastaffiliate-22",
    "UK": "beastaffiliate-21",
    "CA": "beastaffiliate0a-20",
    "DE": "beastaffiliate04-21",
    "ES": "beastaffiliate00-21",
    "IT": "beastaffiliate06-21",
    "FR": "beastaffiliate07-28",
    "NL": "beastaffiliate09-29",
}

BEAST_WHATSAPP = "+923111592151"


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        marketplaces = {}
        for code, name, domain in MARKETPLACES:
            row = db.query(Marketplace).filter(Marketplace.code == code).first()
            if row is None:
                row = Marketplace(code=code, name=name, domain=domain)
                db.add(row)
                db.flush()
            marketplaces[code] = row

        user = db.query(User).filter(User.whatsapp_number == BEAST_WHATSAPP).first()
        if user is None:
            user = User(name="Beast Affiliate", whatsapp_number=BEAST_WHATSAPP)
            db.add(user)
            db.flush()

        existing = {t.marketplace_id for t in user.tracking_ids}
        for code, tag in BEAST_TAGS.items():
            marketplace = marketplaces[code]
            if marketplace.id not in existing:
                db.add(
                    TrackingID(user_id=user.id, marketplace_id=marketplace.id, tag=tag)
                )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
