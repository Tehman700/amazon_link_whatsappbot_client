"""Read-only reporting + the nightly report email (Vercel Cron).

Two entry points, two different callers:

- GET /reports/daily-links  — JSON, guarded by REPORT_KEY. For manual checks
  and any external automation (n8n, scripts).
- GET /reports/daily-email  — builds and SENDS the report email. Called by
  Vercel Cron, guarded by CRON_SECRET (Vercel puts it in an Authorization
  header automatically). Also accepts REPORT_KEY so it can be triggered by
  hand for testing.

REPORT_KEY is deliberately NOT the admin login token, so rotating the
dashboard password never silently breaks the nightly report, and the
automation's credential can be revoked on its own. With the relevant secret
unset, the matching route is closed (403) — an unconfigured deploy exposes
nothing.

Read-only with respect to the database: this router never writes. It joins the
website's link data (WHEN links were made, from which number) against the
bot's users table (WHO that number is) — covering every registered user, not
just those with a portal account.
"""

import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..hub import HUB_API_URL, HUB_SERVICE_KEY

router = APIRouter(prefix="/reports", tags=["reports"])

TIMEOUT = 30.0
# Minutes ahead of UTC used for day boundaries in the emailed report, so
# "yesterday" means yesterday where the owner is, not in UTC. 300 = PKT.
REPORT_TZ_OFFSET = int(os.getenv("REPORT_TZ_OFFSET", "300"))


def require_report_key(x_report_key: str = Header(default="")) -> None:
    expected = os.getenv("REPORT_KEY", "")
    if not expected or x_report_key != expected:
        raise HTTPException(status_code=403, detail="Report key required")


def require_cron_or_report_key(
    authorization: str = Header(default=""),
    x_report_key: str = Header(default=""),
) -> None:
    """Vercel Cron sends `Authorization: Bearer $CRON_SECRET`. A manual test
    can use X-Report-Key instead, so the job can be fired by hand."""
    cron_secret = os.getenv("CRON_SECRET", "")
    report_key = os.getenv("REPORT_KEY", "")
    token = authorization.removeprefix("Bearer ").strip()
    if cron_secret and token == cron_secret:
        return
    if report_key and x_report_key == report_key:
        return
    raise HTTPException(status_code=403, detail="Not authorised")


def _fetch_report(days: int, db: Session, tz_offset: int = 0) -> dict:
    """Website link data joined with this API's user names."""
    if not HUB_API_URL:
        raise HTTPException(503, "HUB_API_URL is not configured on this API")
    days = max(1, min(days, 90))

    try:
        r = httpx.get(
            f"{HUB_API_URL}/api/admin/link-report",
            params={"days": days, "tz_offset": tz_offset},
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
        days_out.append({
            "date": day["date"],
            "total_links": day["links"],
            "active_users": day["active_senders"],
            "revoked": day.get("revoked", 0),
            "users": [
                {
                    "name": name_by_number.get(
                        s["whatsapp_number"], "(not a registered user)"
                    ),
                    "whatsapp_number": s["whatsapp_number"],
                    "links": s["links"],
                }
                for s in day.get("senders", [])
            ],
        })

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "registered_users": len(users),
        "days": days_out,
    }


@router.get("/daily-links", dependencies=[Depends(require_report_key)])
def daily_links(days: int = 1, tz_offset: int = 0, db: Session = Depends(get_db)):
    """Links generated per day with a per-user breakdown (JSON).

    tz_offset is minutes ahead of UTC; 0 keeps the original UTC-day behaviour
    for any existing caller."""
    return _fetch_report(days, db, tz_offset)


def _render_email(report: dict, day: dict) -> tuple[str, str, str]:
    """(subject, html, plain_text) for one day's figures."""
    users = day["users"]
    subject = f"Beast Affiliates — {day['total_links']} links on {day['date']}"

    if users:
        rows = "".join(
            "<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee'>{u['name']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#666'>{u['whatsapp_number']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600'>{u['links']}</td>"
            "</tr>"
            for u in users
        )
        table = (
            "<table style='border-collapse:collapse;width:100%;max-width:560px;font-size:14px'>"
            "<thead><tr>"
            "<th style='text-align:left;padding:8px 12px;border-bottom:2px solid #333'>User</th>"
            "<th style='text-align:left;padding:8px 12px;border-bottom:2px solid #333'>Number</th>"
            "<th style='text-align:right;padding:8px 12px;border-bottom:2px solid #333'>Links</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    else:
        table = "<p style='color:#666'>No links were generated on this day.</p>"

    def stat(value, label):
        return (
            "<div style='display:inline-block;margin:0 24px 20px 0'>"
            f"<div style='font-size:32px;font-weight:700'>{value}</div>"
            f"<div style='color:#666;font-size:13px'>{label}</div></div>"
        )

    html = (
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1b2130\">"
        "<h2 style='margin:0 0 4px'>Beast Affiliates — Daily Report</h2>"
        f"<p style='margin:0 0 20px;color:#666;font-size:14px'>{day['date']}</p>"
        + stat(day["total_links"], "links generated")
        + stat(day["active_users"], "active users")
        + stat(report["registered_users"], "registered total")
        + "<h3 style='margin:16px 0 8px;font-size:15px'>Per user</h3>"
        + table
        + "<p style='margin-top:24px;color:#999;font-size:12px'>"
        f"Generated {report['generated_at']} &middot; {day['revoked']} revoked that day</p>"
        "</div>"
    )

    lines = [f"  {u['name']} ({u['whatsapp_number']}): {u['links']}" for u in users]
    text = "\n".join([
        f"Beast Affiliates — Daily Report for {day['date']}",
        "",
        f"Links generated:  {day['total_links']}",
        f"Active users:     {day['active_users']}",
        f"Registered total: {report['registered_users']}",
        "",
        "Per user:",
        *(lines or ["  (none)"]),
    ])
    return subject, html, text


def _send_email(subject: str, html: str, text: str) -> str:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    # Gmail shows app passwords in groups of four; the real value has no spaces.
    password = password.replace(" ", "")
    mail_from = os.getenv("MAIL_FROM", user)
    mail_to = [a.strip() for a in os.getenv("MAIL_TO", "").split(",") if a.strip()]

    if not (user and password and mail_to):
        raise HTTPException(
            503, "Email not configured: set SMTP_USER, SMTP_PASS and MAIL_TO"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Beast Affiliates", mail_from))
    msg["To"] = ", ".join(mail_to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20,
                                  context=ssl.create_default_context()) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, password)
                s.send_message(msg)
    except Exception as e:
        raise HTTPException(502, f"SMTP send failed: {type(e).__name__}: {e}")
    return ", ".join(mail_to)


@router.get("/daily-email", dependencies=[Depends(require_cron_or_report_key)])
def daily_email(db: Session = Depends(get_db), dry_run: bool = False):
    """Build and send the daily report email for the last COMPLETED local day.

    Called by Vercel Cron. dry_run=true renders the email and returns it
    without sending, for verifying content safely."""
    # Two days so the completed local day is present regardless of where the
    # cron fires relative to the local midnight boundary.
    report = _fetch_report(2, db, REPORT_TZ_OFFSET)
    if not report["days"]:
        return {"sent": False, "reason": "no data returned"}

    target = (
        (datetime.utcnow() + timedelta(minutes=REPORT_TZ_OFFSET)).date()
        - timedelta(days=1)
    ).isoformat()
    day = next((d for d in report["days"] if d["date"] == target), report["days"][0])

    subject, html, text = _render_email(report, day)
    if dry_run:
        return {"sent": False, "dry_run": True, "date": day["date"],
                "subject": subject, "text": text}

    recipients = _send_email(subject, html, text)
    return {"sent": True, "date": day["date"], "to": recipients,
            "total_links": day["total_links"], "active_users": day["active_users"]}
