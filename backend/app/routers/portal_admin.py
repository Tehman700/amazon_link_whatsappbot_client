"""Gateway for the admin dashboard's "Portal administration" page.

The admin frontend only ever talks to THIS API (same origin, same admin
token). This router proxies the website's service-key-guarded admin
endpoints and merges in bot-side data (user names, preferences, linked
numbers, who hasn't signed up yet). Requires HUB_API_URL/HUB_SERVICE_KEY —
the same env the hub feature already uses.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..hub import HUB_API_URL, HUB_SERVICE_KEY

router = APIRouter(prefix="/portal-admin", tags=["portal-admin"])

TIMEOUT = 15.0


def _website(method: str, path: str, json_body: dict | None = None) -> dict:
    if not HUB_API_URL:
        raise HTTPException(503, "HUB_API_URL is not configured on this API")
    try:
        r = httpx.request(
            method,
            f"{HUB_API_URL}{path}",
            json=json_body,
            headers={"X-Service-Key": HUB_SERVICE_KEY},
            timeout=TIMEOUT,
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
    """Portal accounts enriched with bot-side info, plus registered bot
    users who have not signed up on the portal yet."""
    data = _website("GET", "/api/admin/accounts")
    accounts = data.get("accounts", [])

    users_by_number = {u.whatsapp_number: u for u in db.query(models.User).all()}
    linked_rows = db.query(models.LinkedNumber).all()
    linked_by_user_id: dict[int, list[str]] = {}
    for ln in linked_rows:
        linked_by_user_id.setdefault(ln.user_id, []).append(ln.whatsapp_number)

    signed_up_numbers = set()
    for a in accounts:
        user = users_by_number.get(a["whatsapp_number"])
        signed_up_numbers.add(a["whatsapp_number"])
        a["name"] = user.name if user else "(not a bot user)"
        a["link_preference"] = user.link_preference if user else "-"
        a["store_name"] = user.store_name if user else ""
        a["linked_numbers"] = linked_by_user_id.get(user.id, []) if user else []

    not_signed_up = [
        {"name": u.name, "whatsapp_number": n}
        for n, u in sorted(users_by_number.items())
        if n not in signed_up_numbers
    ]
    return {"accounts": accounts, "not_signed_up": not_signed_up}


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
