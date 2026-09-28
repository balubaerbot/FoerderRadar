"""Regressionstest: volles Schema-Gate greift beim Laufzeit-Laden.

Hintergrund (Code-Review, Befund #6):
  load_katalog() pruefte zur Laufzeit nur die Einkommens-Einheit. Das
  umfassendere Schema-Gate tools/validate_katalog.py lief nur manuell/CI.
  Ein fehlerhafter Katalog (doppelte ID, fehlende Quelle, unbekannter
  voraussetzungen-Key) waere vom Worker unbemerkt verarbeitet worden.

Ausserdem: Der Laufzeit-Validator in src/matching_service.py und das CLI-Gate
muessen dieselbe Regel kennen (Regression aus 3a588ff: 'einkommen_einheit').

Lauf:  python3 tests/test_katalog_gate.py
"""
import json
import pathlib
import sys
import tempfile

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import matching_service as ms  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def _schreibe(tmp, eintraege, meta=None):
    daten = {
        "meta": meta or {"stand": "2026-09-28", "quellen": ["https://example.org"]},
        "foerderungen": eintraege,
    }
    p = pathlib.Path(tmp) / "foerderungen.json"
    p.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    return str(p)


def gueltig(fid="a", **over):
    f = {
        "id": fid,
        "name": "Test",
        "stelle": "Stelle",
        "zielgruppe": "privat",
        "betrag": "100 EUR",
        "frist": "laufend",
        "status": "offen",
        "quelle": "https://example.org",
    }
    f.update(over)
    return f


print("Katalog-Gate beim Laufzeit-Laden (#6)")

# 1) Echter Katalog muss laden (kein False Positive)
try:
    ms.load_katalog()
    check("echter Katalog laedt ohne Fehler", True)
except Exception as e:  # pragma: no cover
    check(f"echter Katalog laedt ohne Fehler ({e})", False)

with tempfile.TemporaryDirectory() as tmp:
    # 2) fehlende Pflichtquelle -> Fehler
    p = _schreibe(tmp, [gueltig(quelle="")])
    try:
        ms.load_katalog(p)
        check("fehlende quelle wird abgelehnt", False)
    except ValueError:
        check("fehlende quelle wird abgelehnt", True)

    # 3) doppelte ID -> Fehler
    p = _schreibe(tmp, [gueltig("dup"), gueltig("dup")])
    try:
        ms.load_katalog(p)
        check("doppelte ID wird abgelehnt", False)
    except ValueError:
        check("doppelte ID wird abgelehnt", True)

    # 4) unbekannter voraussetzungen-Key -> Fehler
    p = _schreibe(tmp, [gueltig(voraussetzungen={"quatsch": 1})])
    try:
        ms.load_katalog(p)
        check("unbekannter voraussetzungen-Key wird abgelehnt", False)
    except ValueError:
        check("unbekannter voraussetzungen-Key wird abgelehnt", True)

    # 5) einkommen_max ohne Einheit -> Fehler (beide Validatoren einig)
    p = _schreibe(tmp, [gueltig(voraussetzungen={"einkommen_max": 2000})])
    try:
        ms.load_katalog(p)
        check("einkommen_max ohne Einheit wird abgelehnt", False)
    except ValueError:
        check("einkommen_max ohne Einheit wird abgelehnt", True)

    # 6) einkommen_max MIT Einheit -> ok
    p = _schreibe(
        tmp,
        [gueltig(voraussetzungen={"einkommen_max": 2000, "einkommen_einheit": "monat"})],
    )
    try:
        ms.load_katalog(p)
        check("einkommen_max mit Einheit laedt", True)
    except Exception as e:  # pragma: no cover
        check(f"einkommen_max mit Einheit laedt ({e})", False)

print(f"\nErgebnis: {ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
