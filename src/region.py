"""FoerderRadar - Region-Normalisierung.

Der Katalog kennt `region` nur als **Bundesland** ("OÖ", "NÖ", ...) oder
`null` (= bundesweit). Profile speichern aber historisch auch "OOe-Steyr",
"ooe", "Oberösterreich" usw. Diese Funktion bringt beliebige Regionstexte
auf das kanonische Bundesland - damit "OOe-Steyr" nicht mehr durchfaellt.

Wird an ZWEI Stellen genutzt:
  - Schreiben:  POST /profile (app/main.py)
  - Lesen:      Adapter profil_agent -> Match (src/matching_service.py)
"""
import re

KANONISCH = [
    "OÖ", "NÖ", "Wien", "Salzburg", "Tirol", "Vorarlberg",
    "Kärnten", "Steiermark", "Burgenland",
]

# Bereits "gefaltet" (klein, Umlaute aufgeloest: ö->oe, ä->ae, ü->ue, ß->ss)
_ALIASE = {
    "OÖ": ["ooe", "oö", "oberoesterreich", "oberoesterreichs", "ooesterreich"],
    "NÖ": ["noe", "nö", "niederoesterreich", "niederoesterreichs"],
    "Wien": ["wien", "wien-", "vienna"],
    "Salzburg": ["salzburg", "sbg"],
    "Tirol": ["tirol"],
    "Vorarlberg": ["vorarlberg", "vbg"],
    "Kärnten": ["kaernten", "kärnten", "ktn", "koroska"],
    "Steiermark": ["steiermark", "stmk"],
    "Burgenland": ["burgenland", "bgld"],
}


def _falte(text):
    t = str(text).strip().lower()
    t = (t.replace("ö", "oe").replace("ä", "ae").replace("ü", "ue")
           .replace("ß", "ss").replace("é", "e"))
    # nur Buchstaben/Ziffern/Bindestrich/Leerzeichen behalten
    t = re.sub(r"[^a-z0-9\- ]+", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    return t


def normalisiere_region(text):
    """Gibt das kanonische Bundesland zurueck oder None (unbekannt/leer).

    Erkennt Praefixe, damit 'OOe-Steyr', 'OÖ-Steyr', 'ooe', 'Oberösterreich'
    alle zu 'OÖ' werden.
    """
    if not text:
        return None
    f = _falte(text)
    if not f:
        return None
    for kanon, aliase in _ALIASE.items():
        for a in aliase:
            if f == a or f.startswith(a + "-") or f.startswith(a + " ") or f.startswith(a):
                return kanon
    return None


if __name__ == "__main__":
    for probe in ["OOe-Steyr", "OÖ", "ooe", "Oberösterreich", "NÖ", "noe-wien",
                  "Wien", "Steiermark", "graz", "Tirol", "", None, "München"]:
        print(f"  {str(probe):<18} -> {normalisiere_region(probe)}")
