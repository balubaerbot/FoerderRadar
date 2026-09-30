"""Bundesfoerderungen muessen fuer JEDES Bundesland matchen.

Regression: match.pruefe() hat Eintraege mit region="Bund" fuer jedes konkrete
Bundesland verworfen ("Bund" != "OÖ") -> Bundesfoerderungen waren praktisch
unsichtbar. Fix: src/region.ist_bundesweit() + Nutzung in src/match.py.

Deckt ab:
  * region.ist_bundesweit: "Bund"/leer/None = bundesweit, Bundeslaender nicht
  * Matching: Bund-Eintrag trifft in ALLEN neun Bundeslaendern und ohne Region
  * Gegenprobe: Landesfoerderung bleibt landesgebunden
  * Katalog: kein Eintrag mehr, der eine Bundesfoerderung faelschlich bindet
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import match as m  # noqa: E402
from src import region as reg  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def _entry(region_wert, typ="sozial"):
    return {"id": "t", "zielgruppe": typ, "region": region_wert,
            "voraussetzungen": {}}


def main():
    print("== ist_bundesweit ==")
    for w in (None, "", "   ", "Bund", "bund", "Bundesweit", "Österreich", "AT"):
        check(f"bundesweit: {w!r}", reg.ist_bundesweit(w) is True)
    for w in ("OÖ", "Tirol", "Wien", "NÖ", "Steiermark"):
        check(f"landesgebunden: {w!r}", reg.ist_bundesweit(w) is False)

    print("== Bund trifft jedes Bundesland ==")
    for land in reg.KANONISCH:
        kat, gruende = m.pruefe(_entry("Bund"), {"typ": "sozial", "region": land})
        check(f"Bund x {land} -> kein 'raus'", kat != "raus")

    print("== Bund trifft ohne Regionsangabe ==")
    kat, gruende = m.pruefe(_entry("Bund"), {"typ": "sozial"})
    check("Bund ohne Region -> kein 'raus'", kat != "raus")

    print("== Gegenprobe: Landesfoerderung bleibt gebunden ==")
    kat, gruende = m.pruefe(_entry("OÖ"), {"typ": "sozial", "region": "Tirol"})
    check("OÖ x Tirol -> 'raus'", kat == "raus")
    kat2, _ = m.pruefe(_entry("OÖ"), {"typ": "sozial", "region": "OÖ"})
    check("OÖ x OÖ -> kein 'raus'", kat2 != "raus")

    print("== Katalog: Bund/leer konsistent ==")
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "katalog", "foerderungen.json")
    with open(pfad, encoding="utf-8") as fh:
        daten = json.load(fh)
    eintraege = daten["foerderungen"]
    for e in eintraege:
        r = e.get("region")
        check(f"{e['id']}: region bundesweit erkannt",
              reg.ist_bundesweit(r) or r in reg.KANONISCH)

    print(f"\nErgebnis: {ok} OK, {fail} FAIL")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
