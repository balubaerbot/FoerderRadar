"""FoerderRadar - Region-Normalisierung.

Der Katalog kennt `region` als **Bundesland** ("OÖ", "NÖ", ...) oder
"Bund" (= bundesweit, gilt in ganz Oesterreich). Leer/`null` zaehlt
ebenso als bundesweit. Profile speichern aber historisch auch "OOe-Steyr",
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
            if re.match(rf"^{re.escape(a)}([\s\-]|$)", f):
                return kanon
    return None


# Bundesweit-Marker + tolerante Schreibweisen. Eine Bundesfoerderung gilt
# in JEDEM Bundesland und darf nie durch den Bundesland-Filter fallen.
_BUND_ALIASE = ("bund", "bundesweit", "bundesfoerderung",
                "oesterreich", "österreich", "at")


def ist_bundesweit(region) -> bool:
    """True, wenn die Foerderung in ganz Oesterreich gilt.

    Katalog-Konvention: `region` ist ein Bundesland-Kuerzel ("OÖ", ...) oder
    "Bund" (= bundesweit). Leer/None zaehlt ebenfalls als bundesweit.
    """
    if region is None or (isinstance(region, str) and not region.strip()):
        return True
    return str(region).strip().lower() in _BUND_ALIASE


if __name__ == "__main__":
    for probe in ["OOe-Steyr", "OÖ", "ooe", "Oberösterreich", "NÖ", "noe-wien",
                  "Wien", "Steiermark", "graz", "Tirol", "", None, "München"]:
        print(f"  {str(probe):<18} -> {normalisiere_region(probe)}")
