"""Tests fuer die Thema-Achse (grob) - WAS, im Gegensatz zu zielgruppe (WER).

Deckt ab:
  * Validator: thema ist Pflicht, nicht-leere Liste, nur erlaubte Werte, keine Dups
  * Katalog: alle 14 Eintraege tragen thema, alle Werte erlaubt
  * Vokabular: Vorhaben -> grobe Themen (mehrwertig, idempotent)
  * Matching: grobe Achse ist weich (kein Overlap -> pruefenswert, nie raus)
  * Konsistenz: Validator- und Vokabular-Werteset sind identisch

Lauf:  python3 tests/test_thema.py
"""
import json
import pathlib
import sys
import tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import match as m  # noqa: E402
from src import matching_service as ms  # noqa: E402
from src import vokabular as vok  # noqa: E402
from tools import validate_katalog as vk  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def _schreibe(tmp, eintraege):
    daten = {"meta": {"stand": "2026-09-28", "quellen": ["https://example.org"]},
             "foerderungen": eintraege}
    p = pathlib.Path(tmp) / "foerderungen.json"
    p.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    return str(p)


def gueltig(fid="a", **over):
    f = {
        "id": fid, "name": "Test", "stelle": "Stelle", "zielgruppe": "privat",
        "thema": ["sozial"], "betrag": "100 EUR", "frist": "laufend",
        "status": "offen", "quelle": "https://example.org",
    }
    f.update(over)
    return f


print("Thema-Achse (grob)")

# --- Konsistenz der Wertemengen -------------------------------------------
check("Validator- und Vokabular-Themen identisch",
      vk.ERLAUBTE_THEMEN == vok.ERLAUBTE_THEMEN)

# --- Validator -------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    fehler, _ = vk.validate(_schreibe(tmp, [gueltig()]))
    check("gueltiges thema wird akzeptiert", not fehler)

    fehler, _ = vk.validate(_schreibe(tmp, [gueltig(thema=[])]))
    check("leeres thema wird abgelehnt", any("thema" in e for e in fehler))

    f = gueltig()
    del f["thema"]
    fehler, _ = vk.validate(_schreibe(tmp, [f]))
    check("fehlendes thema wird abgelehnt", any("thema" in e for e in fehler))

    fehler, _ = vk.validate(_schreibe(tmp, [gueltig(thema=["quatsch"])]))
    check("unbekannter thema-Wert wird abgelehnt", any("unbekannte thema" in e for e in fehler))

    fehler, _ = vk.validate(_schreibe(tmp, [gueltig(thema=["sozial", "sozial"])]))
    check("thema-Duplikate werden abgelehnt", any("Duplikate" in e for e in fehler))

# --- Echter Katalog --------------------------------------------------------
kat = json.loads((BASE / "katalog" / "foerderungen.json").read_text(encoding="utf-8"))
alle_getaggt = all(isinstance(f.get("thema"), list) and f["thema"] for f in kat["foerderungen"])
check("alle Katalogeintraege tragen ein nicht-leeres thema", alle_getaggt)
nur_erlaubt = all(set(f.get("thema", [])) <= vk.ERLAUBTE_THEMEN for f in kat["foerderungen"])
check("alle Katalog-Themen sind erlaubte Werte", nur_erlaubt)

# --- Vokabular -------------------------------------------------------------
check("sanierung -> energie + wohnen",
      set(vok.thema_aus_vorhaben(["Sanierung"])) == {"energie", "wohnen"})
check("Digitalisierung -> wirtschaft",
      vok.thema_aus_vorhaben(["Digitalisierung"]) == ["wirtschaft"])
check("Schulung -> bildung",
      vok.thema_aus_vorhaben(["schulung"]) == ["bildung"])
check("thema_aus_vorhaben ist idempotent (Slug -> Slug)",
      vok.thema_aus_vorhaben(["sanierung", "pv"]) == vok.thema_aus_vorhaben(["Sanierung", "Photovoltaik"]))
check("unbekanntes Vorhaben traegt kein Thema",
      vok.thema_aus_vorhaben(["irgendwas_neues"]) == [])
check("leere Liste -> leere Themen", vok.thema_aus_vorhaben([]) == [])


# --- Matching --------------------------------------------------------------
def kategorie(katalog, profil, fid):
    r = m.bewerte(profil, katalog)
    for e in r["top"] + r["pruefenswert"] + r["raus"]:
        if e["id"] == fid:
            return e["kategorie"], e["gruende"]
    return None, []


KAT = {"meta": {"stand": "2026-01-01", "quellen": []}, "foerderungen": [
    gueltig("soz", thema=["sozial", "energie"]),
    gueltig("wirt", zielgruppe="betrieb", thema=["wirtschaft"]),
]}

kat_, gr = kategorie(KAT, {"typ": "privat", "thema": ["energie"]}, "soz")
check("grobe Achse: Ueberschneidung -> top", kat_ == "top")

kat_, gr = kategorie(KAT, {"typ": "privat", "thema": ["bildung"]}, "soz")
check("grobe Achse: kein Overlap -> pruefenswert (nicht raus)", kat_ == "pruefenswert")
check("Grund nennt grobes Thema", any("grob" in g for g in gr))

kat_, _ = kategorie(KAT, {"typ": "privat"}, "soz")
check("grobe Achse: Profil ohne Thema -> nicht ausgeschlossen", kat_ == "top")

# Rauchtest mit echtem Katalog + abgeleitetem Thema
try:
    profil = {"typ": "privat", "vorhaben": ["Photovoltaik"]}
    profil["thema"] = vok.thema_aus_vorhaben(profil["vorhaben"])
    m.bewerte(profil, ms.load_katalog())
    check("echter Katalog + abgeleitetes Thema -> kein Crash", True)
except Exception as e:  # noqa: BLE001
    check(f"echter Katalog + abgeleitetes Thema (Exception: {e})", False)

# --- Adapter ---------------------------------------------------------------
profil = ms.profil_row_to_dict({"typ": "privat", "vorhaben": ["Sanierung", "Photovoltaik"]})
check("profil_row_to_dict leitet thema ab",
      set(profil["thema"]) == {"energie", "wohnen"})

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
