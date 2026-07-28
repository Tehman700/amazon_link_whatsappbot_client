"""Read-only reporting for scheduled automation (the nightly n8n email).

Guarded by REPORT_KEY — deliberately NOT the admin login token, so rotating
the dashboard password never silently breaks the nightly report, and the
automation's credential can be revoked on its own. With REPORT_KEY unset every
route here is closed (403), so an unconfigured deploy exposes nothing.

Read-only: this router never writes. It joins the website's link data (which
knows WHEN links were made and by which number) against the bot's users table
(which knows WHO that number is) — covering every registered user, not just
those with a portal account.
"""

import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..hub import HUB_API_URL, HUB_SERVICE_KEY

router = APIRouter(prefix="/reports", tags=["reports"])

TIMEOUT = 30.0


def require_report_key(x_report_key: str = Header(default="")) -> None:
    expected = os.getenv("REPORT_KEY", "")
    if not expected or x_report_key != expected:
        raise HTTPException(status_code=403, detail="Report key required")


@router.get("/daily-links", dependencies=[Depends(require_report_key)])
def daily_links(days: int = 1, db: Session = Depends(get_db)):
    """Links generated per day with a per-user breakdown.

    days=1 (default) is 'today so far' in UTC; the nightly job runs just after
    midnight local time, so it typically asks for 2 days and reads the
    completed one."""
    if not HUB_API_URL:
        raise HTTPException(503, "HUB_API_URL is not configured on this API")
    days = max(1, min(days, 90))

    try:
        r = httpx.get(
            f"{HUB_API_URL}/api/admin/link-report",
            params={"days": days},
            headers={"X-Service-Key": HUB_SERVICE_KEY},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Website unreachable: {e}")
    if r.status_code >= 400:
        raise HTTPException(502, f"Website error HTTP {r.status_code}")
    report = r.json()

    # Resolve a sending number to a user. Links are always attributed to the
    # PRIMARY number (process.py resolves a linked secondary to its owner
    # before minting), but linked numbers are mapped too so a future change
    # can't silently produce "(unknown)" rows.
    users = db.query(models.User).all()
    name_by_number = {u.whatsapp_number: u.name for u in users}
    user_by_id = {u.id: u for u in users}
    for ln in db.query(models.LinkedNumber).all():
        owner = user_by_id.get(ln.user_id)
        if owner is not None:
            name_by_number.setdefault(ln.whatsapp_number, owner.name)

    days_out = []
    for day in report.get("days", []):
        users_out = [
            {
                "name": name_by_number.get(s["whatsapp_number"], "(not a registered user)"),
                "whatsapp_number": s["whatsapp_number"],
                "links": s["links"],
            }
            for s in day.get("senders", [])
        ]
        days_out.append({
            "date": day["date"],
            "total_links": day["links"],
            "active_users": day["active_senders"],
            "revoked": day.get("revoked", 0),
            "users": users_out,
        })

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "registered_users": len(users),
        "days": days_out,
    }
