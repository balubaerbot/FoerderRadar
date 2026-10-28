"""Regressionstests fuer Einkommens-Einheiten + PII-Redaktion + Versand-Schutz.

Hintergrund (Code-Review):
  - Das Formular erhebt MONATSNETTO, der Katalog fuehrt Grenzwerte teils jaehrlich
    (Heizkostenzuschuss 30913) und teils monatlich (Wohnbeihilfe 2227). Die alte
    Heuristik `limit > 1000 -> Jahr` hat 2227 faelschlich als Jahreswert gelesen.
  - Versandfehler der Mail-CLI konnten Klartext-Kontaktdaten in Logs/DB tragen.

Lauf:  python3 tests/test_einkommen.py
"""
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import match as m  # noqa: E402
from src import matching_service as ms  # noqa: E402
from src import versand_service as vs  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def kat(programm):
    return {"meta": {"stand": "x", "quellen": []}, "foerderungen": [programm]}


def prog(eink_max, einheit=None):
    vor = {"einkommen_max": eink_max}
    if einheit:
        vor["einkommen_einheit"] = einheit
    return {"id": "p", "name": "P", "stelle": "S", "zielgruppe": "privat",
            "betrag": "x", "frist": "x", "status": "offen", "quelle": "q",
            "voraussetzungen": vor}


# --- 1) Jahresgrenze: 4000/Jahr ist unter 30913 -> raus NICHT ---
kategorie, _ = m.pruefe(prog(30913, "jahr")["foerderungen"][0] if False else prog(30913, "jahr"),
                        {"typ": "privat", "haushaltseinkommen": 4000})
check("Jahresgrenze 30913, Einkommen 4000/Jahr -> treffer", kategorie == "treffer")

# --- 2) Jahresgrenze: 48000/Jahr reisst 30913 -> raus ---
kategorie, gruende = m.pruefe(prog(30913, "jahr"), {"typ": "privat", "haushaltseinkommen": 48000})
check("Jahresgrenze 30913, Einkommen 48000/Jahr -> raus", kategorie == "raus")

# --- 3) Monatsgrenze 2227 -> wird zu 26724/Jahr; 48000 reisst -> raus ---
kategorie, _ = m.pruefe(prog(2227, "monat"), {"typ": "privat", "haushaltseinkommen": 48000})
check("Monatsgrenze 2227 (=26724/Jahr), Einkommen 48000/Jahr -> raus", kategorie == "raus")

# --- 4) Monatsgrenze 2227 vs. 24000/Jahr (=2000/Monat) -> treffer ---
kategorie, _ = m.pruefe(prog(2227, "monat"), {"typ": "privat", "haushaltseinkommen": 24000})
check("Monatsgrenze 2227, Einkommen 24000/Jahr -> treffer", kategorie == "treffer")

# --- 5) Kern-Regression des alten Bugs: 2227 darf NICHT als Jahr gelten ---
#     Alt: limit 2227 > 1000 -> als 2227/Jahr gelesen -> 24000/Jahr faelschlich raus.
kategorie, _ = m.pruefe(prog(2227, "monat"), {"typ": "privat", "haushaltseinkommen": 24000})
check("Alter Bug (2227 faelschlich als Jahr) ist behoben", kategorie == "treffer")

# --- 6) Formular-Monatsspanne -> Jahresschaetzung (x12) ---
check("'über 4.000 €' -> 48000/Jahr", ms.einkommen_jahr_obergrenze("über 4.000 €") == 48000)
check("'2.000–3.000 €' -> 36000/Jahr", ms.einkommen_jahr_obergrenze("2.000–3.000 €") == 36000)
check("None -> None", ms.einkommen_jahr_obergrenze(None) is None)

# --- 7) PII-Redaktion: Adresse/Nummer verschwinden aus Fehlertexten ---
kontakt = {"email": "kunde@example.com", "telefon": "+43 660 1234567"}
roh = "smtp: 550 mailbox kunde@example.com rejected (tel +43 660 1234567)"
red = vs._redigiere(roh, kontakt)
check("E-Mail aus Fehlertext entfernt", "kunde@example.com" not in red)
check("Telefonnummer aus Fehlertext entfernt", "1234567" not in red.replace("*", ""))
check("Redaktion ohne Kontakt crasht nicht", vs._redigiere(None, None) is None)

# --- 8) Kern-Regression gegen den echten Katalog: OÖ-Eigentuemer, 4000/Monat ---
profil = {
    "typ": "privat", "region": "OÖ", "wohnsituation": "eigenheim",
    "heizung": "pellets", "haushaltseinkommen": 48000,
    "vorhaben": ["pv", "sanierung"], "themen": ["pv", "sanierung"],
}
bew = m.bewerte(profil, ms.load_katalog())
# Heizkostenzuschuss OÖ (max 30913/Jahr) muss bei 48000/Jahr raus sein.
raus_ids = {e["id"] for e in bew["raus"]}
check("Heizkostenzuschuss OÖ bei 48000/Jahr korrekt ausgeschlossen", "heizkostenzuschuss_ooe" in raus_ids)

# --- 9) Katalog-Validierung: einkommen_max OHNE Einheit -> harter Fehler ---
def _validierung_faellt():
    try:
        ms.validiere_katalog({"foerderungen": [{"id": "x", "voraussetzungen": {"einkommen_max": 2000}}]})
        return False
    except ValueError:
        return True


check("einkommen_max ohne Einheit -> ValueError", _validierung_faellt())
try:
    ms.validiere_katalog(ms.load_katalog())
    check("echter Katalog validiert ohne Fehler", True)
except ValueError as e:  # noqa: BLE001
    check(f"echter Katalog validiert (Fehler: {e})", False)

# --- 10) Watchdog-Funktion existiert und ist importierbar ---
check("vs.sendet_zuruecksetzen vorhanden", callable(getattr(vs, "sendet_zuruecksetzen", None)))

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)