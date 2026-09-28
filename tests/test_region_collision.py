#!/usr/bin/env python3
"""Regressionstest: Regions-Praefixbug (Code-Review, Befund 2).

Hintergrund: normalisiere_region() nutzte reinen Praefixvergleich
(f.startswith(a)). Das matcht 'Wiener Neustadt' und 'Wienerwald'
faelschlich auf den Alias 'wien' -> Bundesland 'Wien'. Der Fix ersetzt
das durch einen Wortgrenzen-Regex (^alias gefolgt von Leerzeichen/Bindestrich/Ende).

Lauf:  python3 tests/test_region_collision.py
"""
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.region import normalisiere_region as n  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


# Falsch-Positive: klingen nach 'Wien', sind es aber nicht.
check("'Wiener Neustadt' -> nicht 'Wien'", n("Wiener Neustadt") != "Wien")
check("'Wienerwald' -> nicht 'Wien'", n("Wienerwald") != "Wien")
check("'wienerberg' -> nicht 'Wien'", n("wienerberg") != "Wien")

# Weiterhin korrekt erkannte Faelle (duerfen durch den Fix nicht kaputt gehen).
check("'Wien' -> 'Wien'", n("Wien") == "Wien")
check("'Wien-Favoriten' -> 'Wien'", n("Wien-Favoriten") == "Wien")
check("'Wien Favoriten' -> 'Wien'", n("Wien Favoriten") == "Wien")
check("'wien' -> 'Wien'", n("wien") == "Wien")
check("'OÖ-Steyr' -> 'OÖ'", n("OÖ-Steyr") == "OÖ")
check("'OOe-Steyr' -> 'OÖ'", n("OOe-Steyr") == "OÖ")
check("'ooe' -> 'OÖ'", n("ooe") == "OÖ")
check("'Oberösterreich' -> 'OÖ'", n("Oberösterreich") == "OÖ")
check("'noe-wien' -> 'NÖ'", n("noe-wien") == "NÖ")
check("None -> None", n(None) is None)
check("'' -> None", n("") is None)
check("unbekannter Text -> None", n("München") is None)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
