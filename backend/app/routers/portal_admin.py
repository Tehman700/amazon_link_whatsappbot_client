"""Gateway for the admin dashboard's "Portal administration" page.

The admin frontend only ever talks to THIS API (same origin, same admin
token). This router proxies the website's service-key-guarded admin
endpoints and merges in bot-side data (user names, preferences, linked
numbers, who hasn't signed up yet). Requires HUB_API_URL/HUB_SERVICE_KEY —
the same env the hub feature already uses.
"""

import csv
import io
import json
import zipfile
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..hub import HUB_API_URL, HUB_SERVICE_KEY

router = APIRouter(prefix="/portal-admin", tags=["portal-admin"])

TIMEOUT = 15.0
BACKUP_TIMEOUT = 60.0  # the website dump can be larger than a normal proxy call


def _website(method: str, path: str, json_body: dict | None = None,
             timeout: float = TIMEOUT) -> dict:
    if not HUB_API_URL:
        raise HTTPException(503, "HUB_API_URL is not configured on this API")
    try:
        r = httpx.request(
            method,
            f"{HUB_API_URL}{path}",
            json=json_body,
            headers={"X-Service-Key": HUB_SERVICE_KEY},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Website unreachable: {e}")
    if r.status_code == 404:
        raise HTTPException(404, "Not found on website")
    if r.status_code >= 400:
        raise HTTPException(502, f"Website error HTTP {r.status_code}")
    return r.json() if r.content else {}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    """Portal accounts enriched with bot-side info."""
    data = _website("GET", "/api/admin/accounts")
    accounts = data.get("accounts", [])

    users_by_number = {u.whatsapp_number: u for u in db.query(models.User).all()}
    linked_rows = db.query(models.LinkedNumber).all()
    linked_by_user_id: dict[int, list[str]] = {}
    for ln in linked_rows:
        linked_by_user_id.setdefault(ln.user_id, []).append(ln.whatsapp_number)

    signed_up = set()
    for a in accounts:
        user = users_by_number.get(a["whatsapp_number"])
        signed_up.add(a["whatsapp_number"])
        a["name"] = user.name if user else "(not a bot user)"
        a["link_preference"] = user.link_preference if user else "-"
        a["store_name"] = user.store_name if user else ""
        a["linked_numbers"] = linked_by_user_id.get(user.id, []) if user else []

    # Registered bot users without a portal account yet — the admin can create
    # one for them from here.
    not_signed_up = [
        {"id": u.id, "name": u.name, "whatsapp_number": n}
        for n, u in sorted(users_by_number.items(), key=lambda kv: kv[1].name.lower())
        if n not in signed_up
    ]
    return {"accounts": accounts, "not_signed_up": not_signed_up}


@router.post("/accounts")
async def create_account(request: Request, db: Session = Depends(get_db)):
    """Create a portal account on a registered user's behalf."""
    body = await request.json()
    number = str(body.get("whatsapp_number", "")).strip()
    if db.query(models.User).filter(models.User.whatsapp_number == number).first() is None:
        raise HTTPException(404, "That number is not a registered bot user")
    return _website("POST", "/api/admin/accounts", {
        "whatsapp_number": number,
        "username": str(body.get("username", "")).strip(),
        "password": str(body.get("password", "")),
    })


def _csv(rows: list[dict], columns: list[str]) -> str:
    """A CSV string with a fixed column order (stable even when a row omits a
    key). utf-8-sig so Excel opens the Unicode correctly."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


@router.get("/backup")
def backup(db: Session = Depends(get_db)):
    """One-click admin backup: bot-side users + tracking IDs joined with the
    website's portal accounts and earnings, streamed as a single ZIP of CSVs
    plus a backup.json master. If the website is unreachable the whole thing
    fails (via _website) rather than handing back a half-empty backup."""
    web = _website("GET", "/api/admin/backup", timeout=BACKUP_TIMEOUT)

    users = db.query(models.User).order_by(models.User.name).all()
    marketplaces = {m.id: m for m in db.query(models.Marketplace).all()}

    users_rows = [
        {"id": u.id, "name": u.name, "whatsapp_number": u.whatsapp_number,
         "email": u.email or "", "link_preference": u.link_preference,
         "store_name": u.store_name}
        for u in users
    ]
    tracking_rows = []
    users_json = []
    for u in users:
        tids = []
        for t in u.tracking_ids:
            mk = marketplaces.get(t.marketplace_id)
            row = {
                "user_id": u.id, "user_name": u.name,
                "whatsapp_number": u.whatsapp_number,
                "marketplace_code": mk.code if mk else str(t.marketplace_id),
                "marketplace_name": mk.name if mk else "", "tag": t.tag,
            }
            tracking_rows.append(row)
            tids.append({"marketplace_code": row["marketplace_code"],
                         "marketplace_name": row["marketplace_name"], "tag": t.tag})
        users_json.append({
            "id": u.id, "name": u.name, "whatsapp_number": u.whatsapp_number,
            "email": u.email or "", "link_preference": u.link_preference,
            "store_name": u.store_name, "tracking_ids": tids,
        })

    generated = datetime.now(timezone.utc).isoformat()
    master = {
        "generated_at": generated,
        "counts": {
            "users": len(users_rows), "tracking_ids": len(tracking_rows),
            "portal_accounts": len(web.get("portal_accounts", [])),
            "earnings_entries": len(web.get("earnings_entries", [])),
            "payout_records": len(web.get("payout_records", [])),
            "referrals": len(web.get("referrals", [])),
        },
        "users": users_json,
        "portal_accounts": web.get("portal_accounts", []),
        "earnings_by_user": web.get("earnings_by_user", []),
        "earnings_entries": web.get("earnings_entries", []),
        "payout_records": web.get("payout_records", []),
        "referrals": web.get("referrals", []),
        "settings": web.get("settings", {}),
    }

    readme = (
        "Beast Affiliates backup\n"
        f"Generated: {generated}\n\n"
        "CSV files open in Excel. backup.json is the exact copy used to restore.\n"
        "portal_accounts.csv 'password_hash' is a one-way PBKDF2 hash, NOT a\n"
        "readable password (no plaintext password is stored anywhere). It lets\n"
        "an account be restored with its existing password; to give a user\n"
        "access use Reset PW in Portal administration.\n\n"
        "This file holds phone numbers, bank details and password hashes —\n"
        "keep it private (off shared drives and email).\n"
    )

    settings = web.get("settings", {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme)
        z.writestr("users.csv", _csv(
            users_rows,
            ["id", "name", "whatsapp_number", "email", "link_preference", "store_name"]))
        z.writestr("tracking_ids.csv", _csv(
            tracking_rows,
            ["user_id", "user_name", "whatsapp_number", "marketplace_code",
             "marketplace_name", "tag"]))
        z.writestr("portal_accounts.csv", _csv(
            web.get("portal_accounts", []),
            ["id", "username", "password_hash", "whatsapp_number", "created_at",
             "store_slug", "store_enabled", "bank", "account_title",
             "account_number", "commission_rate", "orders", "disabled"]))
        z.writestr("earnings_by_user.csv", _csv(
            web.get("earnings_by_user", []),
            ["account_id", "username", "whatsapp_number", "rate", "custom_rate",
             "earned", "paid", "balance", "entries_count", "referral_total"]))
        z.writestr("earnings_entries.csv", _csv(
            web.get("earnings_entries", []),
            ["id", "account_id", "username", "kind", "gross_amount", "rate_applied",
             "net_amount", "label", "note", "created_at"]))
        z.writestr("payouts.csv", _csv(
            web.get("payout_records", []),
            ["id", "account_id", "username", "amount", "method", "note", "paid_at"]))
        z.writestr("referrals.csv", _csv(
            web.get("referrals", []),
            ["id", "referrer_account_id", "referrer_username", "referred_name",
             "amount", "note", "created_at"]))
        z.writestr("settings.csv", _csv(
            [settings], ["default_rate", "min_payout"]))
        z.writestr("backup.json",
                   json.dumps(master, indent=2, ensure_ascii=False))
    buf.seek(0)

    fname = f"beast-backup-{datetime.now().strftime('%Y-%m-%d')}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/performance")
def performance(days: int = 30, db: Session = Depends(get_db)):
    data = _website("GET", f"/api/admin/performance?days={days}")
    users_by_number = {u.whatsapp_number: u for u in db.query(models.User).all()}
    for row in data.get("per_user", []):
        user = users_by_number.get(row["whatsapp_number"])
        row["name"] = user.name if user else ""
    return data


@router.post("/accounts/{account_id}/reset-password")
def reset_password(account_id: int):
    return _website("POST", f"/api/admin/accounts/{account_id}/reset-password")


@router.post("/accounts/{account_id}/disabled")
async def set_disabled(account_id: int, request: Request):
    body = await request.json()
    return _website(
        "POST", f"/api/admin/accounts/{account_id}/disabled",
        {"disabled": bool(body.get("disabled"))},
    )


@router.post("/accounts/{account_id}/orders")
async def set_orders(account_id: int, request: Request):
    return _website("POST", f"/api/admin/accounts/{account_id}/orders",
                    await request.json())


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int):
    return _website("DELETE", f"/api/admin/accounts/{account_id}")


@router.get("/accounts/{account_id}/links")
def account_links(account_id: int):
    return _website("GET", f"/api/admin/accounts/{account_id}/links")


@router.delete("/linked/{number}", status_code=204)
def admin_unlink_number(number: str, db: Session = Depends(get_db)):
    """Remove a linked (secondary) WhatsApp number — bot DB is the owner."""
    row = (
        db.query(models.LinkedNumber)
        .filter(models.LinkedNumber.whatsapp_number == number.strip())
        .first()
    )
    if row is None:
        raise HTTPException(404, "Linked number not found")
    db.delete(row)
    db.commit()


# ------------------------------------------------------------- earnings


@router.get("/earnings")
def earnings_overview(db: Session = Depends(get_db)):
    data = _website("GET", "/api/admin/earnings")
    users_by_number = {u.whatsapp_number: u for u in db.query(models.User).all()}
    for row in data.get("users", []):
        user = users_by_number.get(row["whatsapp_number"])
        row["name"] = user.name if user else ""
    return data


@router.put("/earnings/settings")
async def earnings_settings(request: Request):
    return _website("PUT", "/api/admin/earnings/settings", await request.json())


@router.put("/earnings/{account_id}/rate")
async def earnings_rate(account_id: int, request: Request):
    return _website("PUT", f"/api/admin/earnings/{account_id}/rate",
                    await request.json())


@router.get("/earnings/{account_id}")
def earnings_detail(account_id: int):
    return _website("GET", f"/api/admin/earnings/{account_id}")


@router.post("/earnings/{account_id}/entries")
async def earnings_add_entry(account_id: int, request: Request):
    return _website("POST", f"/api/admin/earnings/{account_id}/entries",
                    await request.json())


@router.put("/earnings/{account_id}/entries/{entry_id}")
async def earnings_update_entry(account_id: int, entry_id: int, request: Request):
    return _website("PUT", f"/api/admin/earnings/{account_id}/entries/{entry_id}",
                    await request.json())


@router.delete("/earnings/{account_id}/entries/{entry_id}")
def earnings_delete_entry(account_id: int, entry_id: int):
    return _website("DELETE", f"/api/admin/earnings/{account_id}/entries/{entry_id}")


@router.post("/earnings/{account_id}/payouts")
async def earnings_add_payout(account_id: int, request: Request):
    return _website("POST", f"/api/admin/earnings/{account_id}/payouts",
                    await request.json())


@router.delete("/earnings/{account_id}/payouts/{payout_id}")
def earnings_delete_payout(account_id: int, payout_id: int):
    return _website("DELETE", f"/api/admin/earnings/{account_id}/payouts/{payout_id}")


@router.post("/earnings/{account_id}/referrals")
async def earnings_add_referral(account_id: int, request: Request):
    return _website("POST", f"/api/admin/earnings/{account_id}/referrals",
                    await request.json())


@router.put("/earnings/{account_id}/referrals/{referral_id}")
async def earnings_update_referral(account_id: int, referral_id: int, request: Request):
    return _website("PUT", f"/api/admin/earnings/{account_id}/referrals/{referral_id}",
                    await request.json())


@router.delete("/earnings/{account_id}/referrals/{referral_id}")
def earnings_delete_referral(account_id: int, referral_id: int):
    return _website("DELETE", f"/api/admin/earnings/{account_id}/referrals/{referral_id}")
