"""Offline test for the bot-side report orchestration (_build_entries).

In-memory bot DB (users + US tracking IDs) with the website account list mocked,
so parse + portal-match + entry-building + the duplicate/unmatched alerts run
with no network.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from app.database import Base  # noqa: E402
from app import models  # noqa: E402
from app.routers import portal_admin  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
db = sessionmaker(bind=engine)()

us = models.Marketplace(code="US", name="United States", domain="amazon.com")
uk = models.Marketplace(code="UK", name="United Kingdom", domain="amazon.co.uk")
db.add_all([us, uk]); db.flush()


def mkuser(name, number, us_tag):
    u = models.User(name=name, whatsapp_number=number)
    db.add(u); db.flush()
    db.add(models.TrackingID(user_id=u.id, marketplace_id=us.id, tag=us_tag))
    return u


mkuser("alice", "+900001", "aliceus-20")
mkuser("bob", "+900002", "bobus-20")
mkuser("dup1", "+900003", "dupus-20")   # two portal users share the same US tag
mkuser("dup2", "+900004", "dupus-20")
db.commit()

# website account list — all four have portal accounts (account_id = 1..4)
ACCOUNTS = {"accounts": [
    {"id": 1, "username": "alice", "whatsapp_number": "+900001"},
    {"id": 2, "username": "bob", "whatsapp_number": "+900002"},
    {"id": 3, "username": "dup1", "whatsapp_number": "+900003"},
    {"id": 4, "username": "dup2", "whatsapp_number": "+900004"},
]}
portal_admin._website = lambda method, path, *a, **k: ACCOUNTS if "accounts" in path else {}

H = ("Tracking Id,Clicks,Items Ordered,Ordered Revenue,Items Shipped,Items Returned,"
     "Shipped Revenue,Returned Revenue,Total Earnings,Bonus,Shipped Earnings,Returned Earnings\n")
CSV = H + (
    "aliceus-20,100,10,100,10,0,100,0,5.00,0,5.00,0\n"
    "bobus-20,200,20,200,18,2,180,20,8.00,0,8.80,0.80\n"
    "dupus-20,50,5,50,5,0,50,0,3.00,0,3.00,0\n"        # shared -> duplicate alert
    "xyzun-20,30,7,70,7,0,70,0,4.00,0,4.00,0\n"        # no portal user -> unmatched
    "others,10,1,10,1,0,10,0,1.00,0,1.00,0\n"
)

built = portal_admin._build_entries(db, CSV)
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


by_acc = {e["account_id"]: e for e in built["entries"]}
check("2 matched entries (alice=1, bob=2)", set(by_acc) == {1, 2}, list(by_acc))
check("alice entry earnings 500 cents, 10 ordered",
      by_acc[1]["earnings_usd_cents"] == 500 and by_acc[1]["ordered"] == 10)
check("bob entry: 18 shipped, 2 returned", by_acc[2]["shipped"] == 18 and by_acc[2]["returned"] == 2)
check("duplicate US tag flagged with both usernames",
      built["duplicate_tags"] == [{"tag": "dupus-20", "account_ids": [3, 4],
                                    "usernames": ["dup1", "dup2"]}], built["duplicate_tags"])
check("a tag with no portal user is unmatched",
      built["unmatched_tags"] == ["xyzun-20"], built["unmatched_tags"])
check("rows parsed excludes header + others (4 rows)", built["rows_parsed"] == 4, built["rows_parsed"])
check("the shared tag is NOT in entries (never auto-assigned)",
      all(e["account_id"] not in (3, 4) for e in built["entries"]))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
