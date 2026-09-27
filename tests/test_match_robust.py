"""Regressionstests fuer die Match-Robustheit.

Hintergrund: `pruefe()` stuerzte mit TypeError ab, wenn das Profil einen
numerischen Wert NICHT kannte (z.B. Einkommen/Pflegestufe = None) und der
Katalog eine Grenze prueft. Unbekannt darf NIE abstuerzen, sondern wird
sauber als 'pruefenswert' markiert (nicht pruefbar).

Lauf:  python3 tests/test_match_robust.py
"""
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import match as m  # noqa: E402
from src import matching_service as ms  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


KATALOG = {
    "meta": {"stand": "2026-01-01", "quellen": []},
    "foerderungen": [
        {"id": "eink_test", "name": "Einkommenstest", "stelle": "X", "zielgruppe": "privat",
         "region": None, "betrag": "1 EUR", "frist": "laufend", "status": "offen",
         "voraussetzungen": {"einkommen_max": 30000}, "quelle": "https://example.com"},
        {"id": "pflege_test", "name": "Pflegetest", "stelle": "X", "zielgruppe": "privat",
         "region": None, "betrag": "1 EUR", "frist": "laufend", "status": "offen",
         "voraussetzungen": {"pflegestufe_min": 2}, "quelle": "https://example.com"},
    ],
}


def kategorie(katalog, profil, fid):
    r = m.bewerte(profil, katalog)
    for e in r["top"] + r["pruefenswert"] + r["raus"]:
        if e["id"] == fid:
            return e["kategorie"], e["gruende"]
    return None, []


# 1) Einkommen unbekannt -> kein Crash, 'pruefenswert'
try:
    kat, gr = kategorie(KATALOG, {"typ": "privat"}, "eink_test")
    check("Einkommen unbekannt -> kein Crash + pruefenswert", kat == "pruefenswert")
    check("Grund nennt fehlendes Einkommen", any("Einkommen nicht angegeben" in g for g in gr))
except Exception as e:  # noqa: BLE001
    check(f"Einkommen unbekannt -> kein Crash (Exception: {e})", False)

# 2) Einkommen ueber Grenze -> raus
kat, _ = kategorie(KATALOG, {"typ": "privat", "haushaltseinkommen": 50000}, "eink_test")
check("Einkommen ueber Grenze -> raus", kat == "raus")

# 3) Einkommen unter Grenze -> top
kat, _ = kategorie(KATALOG, {"typ": "privat", "haushaltseinkommen": 20000}, "eink_test")
check("Einkommen unter Grenze -> top", kat == "top")

# 4) Pflegestufe unbekannt -> kein Crash, pruefenswert
try:
    kat, gr = kategorie(KATALOG, {"typ": "privat"}, "pflege_test")
    check("Pflegestufe unbekannt -> kein Crash + pruefenswert", kat == "pruefenswert")
except Exception as e:  # noqa: BLE001
    check(f"Pflegestufe unbekannt -> kein Crash (Exception: {e})", False)

# 5) Pflegestufe zu niedrig -> raus
kat, _ = kategorie(KATALOG, {"typ": "privat", "pflegestufe": 1}, "pflege_test")
check("Pflegestufe zu niedrig -> raus", kat == "raus")

# 6) Rauchtest gegen den echten Katalog: minimales Profil darf nicht crashen
try:
    r = m.bewerte({"typ": "privat"}, ms.load_katalog())
    check("Echtes Katalog + Minimalprofil -> kein Crash", True)
except Exception as e:  # noqa: BLE001
    check(f"Echtes Katalog + Minimalprofil (Exception: {e})", False)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
