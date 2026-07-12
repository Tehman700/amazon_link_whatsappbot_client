"""Auth flow tests against the API (local by default, or API_BASE).

Credentials come from ADMIN_USERNAME / ADMIN_PASSWORD (backend/.env is
loaded automatically) - never hardcode them; this repo is public.
"""

import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
USERNAME = os.environ["ADMIN_USERNAME"]
PASSWORD = os.environ["ADMIN_PASSWORD"]

passed = failed = 0


def call(path, body=None, token=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if cond else (passed, failed + 1)
    print(("PASS " if cond else "FAIL ") + f" {name}" + ("" if cond else f"  {detail}"))


# 1. Admin routes locked without a token
s, r = call("/users")
check("GET /users without token -> 401", s == 401, (s, r))
s, r = call("/marketplaces")
check("GET /marketplaces without token -> 401", s == 401, (s, r))
s, r = call("/users", body={"name": "x", "whatsapp_number": "+1"}, method="POST")
check("POST /users without token -> 401", s == 401, (s, r))

# 2. Wrong credentials rejected
s, r = call("/auth/login", body={"username": USERNAME, "password": "wrong-password"})
check("login with wrong password -> 401", s == 401, (s, r))
s, r = call("/auth/login", body={"username": "wrong-user", "password": PASSWORD})
check("login with wrong username -> 401", s == 401, (s, r))

# 3. Correct credentials -> token
s, r = call("/auth/login", body={"username": USERNAME, "password": PASSWORD})
check("login with correct creds -> token", s == 200 and "token" in r, (s, r))
token = r.get("token", "")
check("token expiry ~12h", abs(r.get("expires_at", 0) - time.time() - 12 * 3600) < 60, r)

# 4. Token grants access
s, r = call("/users", token=token)
check("GET /users with token -> 200", s == 200 and isinstance(r, list), (s, r))
s, r = call("/marketplaces", token=token)
check("GET /marketplaces with token -> 200", s == 200 and len(r) == 9, (s, r))

# 5. Tampered / expired tokens rejected
s, r = call("/users", token=token[:-4] + "0000")
check("tampered token -> 401", s == 401, (s, r))
s, r = call("/users", token="12345.deadbeef")
check("expired/garbage token -> 401", s == 401, (s, r))

# 6. /process-message stays open for the WhatsApp adapter (no token)
s, r = call("/process-message", body={"sender": "+923111592151", "text": "https://amazon.com/dp/B0X"})
check("/process-message without token still works", s == 200 and r.get("links_replaced") == 1, (s, r))

# 7. /health open
s, r = call("/health")
check("/health open", s == 200, (s, r))

print(f"\n{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
