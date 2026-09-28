"""Regressionstests fuer die Vokabular-Normalisierung.

Hintergrund: Das Web-Formular speichert Anzeige-Labels ('Eigentum',
'Photovoltaik'), der Katalog prueft aber kanonische Slugs ('eigenheim',
'pv'). Ohne Uebersetzung warf die Match-Logik jeden Treffer weg - ein privat
erfasstes Profil bekam 0 Foerderungen, obwohl es klar qualifizierte.

Lauf:  python3 tests/test_vokabular.py
"""
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import match as m  # noqa: E402
from src import matching_service as ms  # noqa: E402
from src import vokabular as v  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


# --- 1) Einzel-Uebersetzungen ---
check("Eigentum -> eigenheim", v.normalisiere_wohnsituation("Eigentum") == "eigenheim")
check("Miete -> miete", v.normalisiere_wohnsituation("Miete") == "miete")
check("Pellets / Holz -> pellets", v.normalisiere_heizung("Pellets / Holz") == "pellets")
check("Öl -> oel", v.normalisiere_heizung("Öl") == "oel")
check("Wärmepumpe -> waermepumpe", v.normalisiere_heizung("Wärmepumpe") == "waermepumpe")

# --- 2) Idempotenz: Slug bleibt Slug ---
check("eigenheim -> eigenheim (idempotent)", v.normalisiere_wohnsituation("eigenheim") == "eigenheim")
check("oel -> oel (idempotent)", v.normalisiere_heizung("oel") == "oel")
check("pv bleibt pv (idempotent)", v.normalisiere_vorhaben(["pv"]) == ["pv"])

# --- 3) Vorhaben-Liste (Label -> Slug, dedupliziert) ---
ergebnis = v.normalisiere_vorhaben(["Photovoltaik", "Sanierung", "Weiterbildung", "Photovoltaik"])
check("Vorhaben Labels -> Slugs", ergebnis == ["pv", "sanierung", "weiterbildung"])

# --- 4) None / leer bleiben unangetastet ---
check("None -> None (Wohnsituation)", v.normalisiere_wohnsituation(None) is None)
check("leere Liste -> leere Liste", v.normalisiere_vorhaben([]) == [])

# --- 5) Kern-Regression: Formular-Labels treffen echten Katalog ---
#    Ein OÖ-Eigentuemer mit PV/Sanierung/Vorhaben muss Treffer bekommen.
profil_labels = {
    "typ": "privat", "region": "OÖ", "wohnsituation": "Eigentum",
    "heizung": "Pellets / Holz",
    "vorhaben": ["Photovoltaik", "Sanierung", "Weiterbildung"],
    "themen": ["Photovoltaik", "Sanierung", "Weiterbildung"],
}
profil_norm = ms.profil_row_to_dict({
    "typ": "privat", "region_grob": "OÖ", "wohnsituation": "Eigentum",
    "heizung": "Pellets / Holz",
    "vorhaben": ["Photovoltaik", "Sanierung", "Weiterbildung"],
})
check("Adapter uebersetzt Wohnsituation", profil_norm["wohnsituation"] == "eigenheim")
check("Adapter uebersetzt Themen", set(profil_norm["themen"]) == {"pv", "sanierung", "weiterbildung"})

bewertung = m.bewerte(profil_norm, ms.load_katalog())
treffer = len(bewertung["top"]) + len(bewertung["pruefenswert"])
check(f"Label-Profil liefert Treffer (erhalten: {treffer})", treffer > 0)

# --- 6) Ohne Normalisierung waere derselbe Fall leer (Bug-Reproduktion) ---
roh = dict(profil_norm)
roh["wohnsituation"] = "Eigentum"
roh["themen"] = ["Photovoltaik"]
roh["vorhaben"] = ["Photovoltaik"]
roh_ergebnis = m.bewerte(roh, ms.load_katalog())
roh_treffer = len(roh_ergebnis["top"]) + len(roh_ergebnis["pruefenswert"])
check(f"Unnormalisiertes Profil = 0 Treffer (Bug sichtbar: {roh_treffer})", roh_treffer == 0)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)