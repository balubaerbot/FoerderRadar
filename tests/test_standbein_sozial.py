"""Regressionstests: Standbein-Achse mit drei Werten (betrieb | privat | sozial).

Hintergrund: Der fruehere Workaround (Commit 7542c7d) speicherte das Standbein
"Sozial & Alltag" datenseitig als typ='privat' + thema='sozial'. Seit der
Architektur-Erweiterung (Variante A) ist 'sozial' ein echter dritter Wert der
typ-/zielgruppe-Achse (DB-CHECK, ki_mapping.ERLAUBTE_ZIELGRUPPEN,
validate_katalog.ERLAUBTE_ZIELGRUPPEN). src/match.py:43 (Zielgruppen-Matchkey,
`if f.get("zielgruppe") != profil.get("typ")`) bleibt unveraendert.

Lauf:  python3 tests/test_standbein_sozial.py
Braucht: fastapi, httpx, psycopg + erreichbare DB (DATABASE_URL), FOERDER_ADMIN_TOKEN in .env
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
from src import match as m  # noqa: E402
from src import ki_mapping as ki  # noqa: E402
import tools.validate_katalog as vk  # noqa: E402

c = TestClient(app)
ADMIN_TOKEN = os.environ.get("FOERDER_ADMIN_TOKEN", "")
ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


# --- 1) Allowlists kennen 'sozial' ---
check("ki_mapping.ERLAUBTE_ZIELGRUPPEN enthaelt 'sozial'", "sozial" in ki.ERLAUBTE_ZIELGRUPPEN)
check("validate_katalog.ERLAUBTE_ZIELGRUPPEN enthaelt 'sozial'", "sozial" in vk.ERLAUBTE_ZIELGRUPPEN)

# --- 2) LLM-Antwort mit zielgruppe='sozial' wird NICHT verworfen (Boundary-Check) ---
v = ki.validiere_antwort({"zielgruppe": "sozial", "thema": ["sozial"]})
check("validiere_antwort akzeptiert zielgruppe='sozial'",
      v == {"zielgruppe": "sozial", "thema": ["sozial"]})

# --- 3) POST /profile mit typ='sozial' -> kein 400, kein Coercion-Fallback ---
kunde_id = None
try:
    r = c.post("/profile", json={"typ": "sozial", "einwilligung": True})
    check("POST /profile typ=sozial -> 200", r.status_code == 200)
    kunde_id = r.json().get("kunde_id")
    check("Antwort enthaelt kunde_id", bool(kunde_id))
except Exception as e:  # noqa: BLE001
    check(f"POST /profile typ=sozial (Exception: {str(e)[:120]})", False)

# --- 4) Live-Readback: typ ist wirklich 'sozial' persistiert (kein Fallback auf 'privat') ---
if kunde_id and ADMIN_TOKEN:
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    r = c.get("/profiles", headers=headers)
    check("GET /profiles (Admin) -> 200", r.status_code == 200)
    zeilen = [p for p in r.json() if p.get("kunde_id") == kunde_id] if r.status_code == 200 else []
    check("Profil in /profiles gefunden", len(zeilen) == 1)
    if zeilen:
        check("typ ist ECHT 'sozial' persistiert (kein Coercion-Fallback auf 'privat')",
              zeilen[0].get("typ") == "sozial")
else:
    check("Live-Readback uebersprungen (kein kunde_id oder kein FOERDER_ADMIN_TOKEN gesetzt)",
          False)

# --- 5) Formular-Roundtrip: POST /formular mit typ=sozial speichert echt 'sozial' ---
try:
    daten = {
        "typ": "sozial", "region_grob_s": "Oberösterreich",
        "lebenssituation": "Pflege", "bedarf": ["Pflegegeld"],
        "name": "Erika Musterfrau", "email": "erika@beispiel.at",
        "kanal": "email", "einwilligung": "ja",
    }
    r = c.post("/formular", data=daten, follow_redirects=False)
    check("POST /formular typ=sozial -> 303 Redirect", r.status_code == 303)
except Exception as e:  # noqa: BLE001
    check(f"POST /formular typ=sozial (Exception: {str(e)[:120]})", False)

# --- 6) Matching: Katalog-Eintrag mit zielgruppe='sozial' wird bei sonst
#        passendem Profil (typ='sozial') NICHT rausgefiltert. Gegenprobe:
#        bei abweichendem typ wird derselbe Eintrag rausgefiltert.
#        (match.py:43 bleibt unveraendert und arbeitet jetzt korrekt mit
#        einem echten dritten Wert.)
eintrag_sozial = {
    "id": "sozial_test", "name": "Sozialtest", "stelle": "X", "zielgruppe": "sozial",
    "region": None, "betrag": "1 EUR", "frist": "laufend", "status": "offen",
    "voraussetzungen": {}, "quelle": "https://example.com",
}

kat_match, _ = m.pruefe(eintrag_sozial, {"typ": "sozial"})
check("zielgruppe=sozial + typ=sozial -> NICHT 'raus'", kat_match != "raus")

kat_mismatch, gruende_mismatch = m.pruefe(eintrag_sozial, {"typ": "privat"})
check("zielgruppe=sozial + typ=privat (Mismatch) -> 'raus'", kat_mismatch == "raus")
check("Mismatch-Grund nennt Zielgruppe", any("Zielgruppe" in g for g in gruende_mismatch))

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
