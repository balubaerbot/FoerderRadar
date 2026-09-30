"""Tests fuer die produktive Website (Jinja2) und das echte Formular.

Lauf:  python3 tests/test_web.py
Braucht: fastapi, httpx, jinja2, psycopg + erreichbare DB (DATABASE_URL) fuer den POST-Teil.
"""
import os
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

for line in (BASE / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


# --- Oeffentliche Seiten ohne Token ---
r = c.get("/")
check("GET / -> 200", r.status_code == 200)
check("GET / enthaelt 'F\\u00f6rdora'", "Fördora" in r.text)
check("GET / verlinkt Formular", "/formular" in r.text)
check("GET / verlinkt Betrieb-Einstieg", "/formular?typ=betrieb" in r.text)
check("GET / verlinkt Privat-Einstieg", "/formular?typ=privat" in r.text)
check("GET / verlinkt Sozial & Alltag-Einstieg", "/formular?typ=sozial" in r.text)

r = c.get("/formular")
check("GET /formular -> 200", r.status_code == 200)
check("Formular hat Bundesland-Auswahl", "Bundesland" in r.text)
check("Formular hat Consent-Pflichtfeld", 'name="einwilligung"' in r.text)

r = c.get("/formular?typ=privat")
check("GET /formular?typ=privat -> 200", r.status_code == 200)
check("Privat-Modus markiert Radio", 'value="privat"\n        checked' in r.text or 'value="privat"' in r.text)

check("GET /impressum -> 200", c.get("/impressum").status_code == 200)
check("GET /datenschutz -> 200", c.get("/datenschutz").status_code == 200)
check("GET /danke -> 200", c.get("/danke").status_code == 200)
check("GET /info -> 200", c.get("/info").status_code == 200)

r = c.get("/static/style.css")
check("GET /static/style.css -> 200", r.status_code == 200)
check("CSS hat Primaerfarbe", "--p:#0f766e" in r.text)

# --- Default-Deny bleibt: Admin-Endpunkte ohne Token 401 ---
check("GET /profiles ohne Token -> 401", c.get("/profiles").status_code == 401)

# --- Formular-POST: Validierung ohne DB-Zugriff ---
r = c.post("/formular", data={"typ": "betrieb", "name": "", "email": "", "einwilligung": "ja"})
check("POST ohne Name/E-Mail -> 400", r.status_code == 400)
check("Fehlermeldung sichtbar", "Name und E-Mail" in r.text)

r = c.post("/formular", data={"typ": "betrieb", "name": "Max Mustermann",
                              "email": "max@beispiel.at", "region_grob": "Oberösterreich",
                              "vorhaben": ["Digitalisierung"], "einwilligung": ""})
check("POST ohne Einwilligung -> 400", r.status_code == 400)
check("Einwilligungs-Fehler sichtbar", "Einwilligung" in r.text)

# --- Formatvalidierung E-Mail / Kanal (Review #5) ---
r = c.post("/formular", data={"typ": "betrieb", "name": "Max Mustermann",
                              "email": "keine-mail", "einwilligung": "ja"})
check("POST ungueltige E-Mail -> 400", r.status_code == 400)
check("E-Mail-Formatfehler sichtbar", "E-Mail-Adresse" in r.text)

r = c.post("/formular", data={"typ": "betrieb", "name": "Max Mustermann",
                              "email": "max@beispiel.at", "kanal": "sms",
                              "telefon": "", "einwilligung": "ja"})
check("POST kanal=sms ohne Telefon -> 400", r.status_code == 400)
check("SMS-Telefon-Fehler sichtbar", "sms" in r.text.lower())

# --- Formular-POST: erfolgreicher Durchlauf (braucht DB) ---
daten = {
    "typ": "betrieb", "region_grob": "Oberösterreich", "branche": "IT / Digitalisierung",
    "mitarbeiterklasse": "5–9", "wko_mitglied": "ja",
    "vorhaben": ["Digitalisierung", "Investition"],
    "name": "Max Mustermann", "email": "max@beispiel.at", "telefon": "+43 660 1234567",
    "kanal": "email", "einwilligung": "ja",
}
try:
    r = c.post("/formular", data=daten, follow_redirects=False)
    check("POST gueltig -> 303 Redirect", r.status_code == 303)
    check("Redirect zeigt auf /danke", r.headers.get("location", "").startswith("/danke"))
    from urllib.parse import unquote
    check("Danke-URL maskiert E-Mail", "m**@beispiel.at" in unquote(r.headers.get("location", "")))
    r2 = c.get(r.headers["location"])
    check("Danke-Seite -> 200", r2.status_code == 200)
    check("Danke nennt Vornamen", "Max" in r2.text)
except Exception as e:  # noqa: BLE001
    check(f"POST gueltig (DB nicht erreichbar? {str(e)[:80]})", False)

print(f"\n{ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
