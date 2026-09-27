"""Tests fuer die API-Absicherung: Default-Deny + Consent + Rate-Limit.

Lauf:  python3 tests/test_api_auth.py
Braucht: fastapi, httpx, psycopg + erreichbare DB (DATABASE_URL), FOERDER_ADMIN_TOKEN in .env
"""
import os
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# .env laden (DATABASE_URL, FOERDER_ADMIN_TOKEN)
for line in (BASE / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
TOKEN = os.environ["FOERDER_ADMIN_TOKEN"]
HEAD = {"Authorization": f"Bearer {TOKEN}"}
ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


# 1) Default-Deny: alles ausser PUBLIC braucht den Token
check("GET /profiles ohne Token -> 401", c.get("/profiles").status_code == 401)
check("GET /profiles mit falschem Token -> 401", c.get("/profiles", headers={"Authorization": "Bearer falsch"}).status_code == 401)
check("GET /profiles mit Token -> 200", c.get("/profiles", headers=HEAD).status_code == 200)
check("POST /match ohne Token -> 401", c.post("/match/00000000-0000-0000-0000-000000000000").status_code == 401)
check("GET /match/{id} ohne Token -> 401", c.get("/match/00000000-0000-0000-0000-000000000000").status_code == 401)
check("GET /docs ohne Token -> 401 (Default-Deny)", c.get("/docs").status_code == 401)

# 2) Oeffentliche Routen
check("GET / -> 200", c.get("/").status_code == 200)
check("GET /health -> 200", c.get("/health").status_code == 200)

# 3) Consent ist Pflicht
check("POST /profile ohne Einwilligung -> 400",
      c.post("/profile", json={"typ": "privat", "einwilligung": False}).status_code == 400)
r = c.post("/profile", json={"typ": "privat", "region_grob": "OOe-Steyr", "vorhaben": ["pv"],
                             "email": "test@example.com", "kanal": "email", "einwilligung": True})
check("POST /profile mit Einwilligung -> 200", r.status_code == 200)
check("Antwort enthaelt nur kunde_id", r.status_code == 200 and set(r.json().keys()) == {"kunde_id"})

# 4) Rate-Limit (5 pro Minute/IP)
codes = [c.post("/profile", json={"typ": "privat", "einwilligung": True}).status_code for _ in range(8)]
check("Rate-Limit greift (429 nach 5/Minute)", 429 in codes)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
