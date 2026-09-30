"""FoerderRadar - Vokabular-Normalisierung.

Formular und Katalog benutzen unterschiedliche Schreibweisen fuer dieselbe
Sache:

    Formular (Anzeige)      Katalog (kanonischer Slug)
    ------------------      ---------------------------
    "Eigentum"          ->  "eigenheim"
    "Miete"             ->  "miete"
    "Öl"                ->  "oel"
    "Pellets / Holz"    ->  "pellets"
    "Photovoltaik"      ->  "pv"
    "Sanierung"         ->  "sanierung"

Ohne diese Uebersetzung vergleicht die Match-Logik 'Eigentum' mit
['eigenheim','miete'] und wirft jeden Treffer weg.

Alle Funktionen sind **idempotent**: ein bereits kanonischer Slug bleibt
unveraendert (slug -> slug). Dadurch lassen sie sich gefahrlos zweimal
anwenden - beim Speichern UND beim Lesen -, und auch Altdaten mit Labels
werden beim Matching korrekt uebersetzt.
"""
import re

# --- Anzeige-Label (klein) -> Katalog-Slug ---
_WOHNSITUATION = {
    "eigentum": "eigenheim",
    "miete": "miete",
    "genossenschaft": "genossenschaft",
    "bei angehörigen": "angehoerige",
    "bei angehoerigen": "angehoerige",
}

_HEIZUNG = {
    "fernwärme": "fernwaerme",
    "fernwaerme": "fernwaerme",
    "gas": "gas",
    "öl": "oel",
    "oel": "oel",
    "pellets / holz": "pellets",
    "pellets": "pellets",
    "holz": "pellets",
    "wärmepumpe": "waermepumpe",
    "waermepumpe": "waermepumpe",
    "strom": "strom",
    "sonstiges": "sonstiges",
}

_VORHABEN = {
    "digitalisierung": "digitalisierung",
    "investition": "investition",
    "schulung": "schulung",
    "energieeffizienz": "energieeffizienz",
    "photovoltaik": "pv",
    "pv": "pv",
    "gründung": "gruendung",
    "gruendung": "gruendung",
    "sanierung": "sanierung",
    "weiterbildung": "weiterbildung",
    "mobilität": "mobilitaet",
    "mobilitaet": "mobilitaet",
    "dämmung": "daemmung",
    "daemmung": "daemmung",
    "fenster": "fenster",
    "heizungstausch": "heizungstausch",
    "speicher": "speicher",
    "beratung": "beratung",
    "innovation": "innovation",
    "modernisierung": "modernisierung",
    "übernahme": "uebernahme",
    "uebernahme": "uebernahme",
    "automatisierung": "automatisierung",
    "ki": "ki",
    "cybersecurity": "cybersecurity",
    "umwelt": "umwelt",
}

_UMLAUT = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}

# ---------------------------------------------------------------- Thema-Achse
# Grobe Themen (WAS) - kanonisch auch in tools/validate_katalog.py (ERLAUBTE_THEMEN).
# Die Fein-Vorhaben des Formulars werden darauf abgebildet, damit auch ohne
# KI-Freitext eine grobe Zuordnung existiert. Ein Vorhaben darf mehrere grobe
# Themen tragen (z. B. sanierung -> energie + wohnen).
ERLAUBTE_THEMEN = {"wirtschaft", "sozial", "energie", "wohnen", "bildung"}

_THEMA_VORHABEN = {
    # Betrieb / Foerderung
    "digitalisierung": ["wirtschaft"],
    "automatisierung": ["wirtschaft"],
    "ki": ["wirtschaft"],
    "cybersecurity": ["wirtschaft"],
    "investition": ["wirtschaft"],
    "modernisierung": ["wirtschaft"],
    "gruendung": ["wirtschaft"],
    "uebernahme": ["wirtschaft"],
    "beratung": ["wirtschaft"],
    "innovation": ["wirtschaft"],
    # Wissen
    "schulung": ["bildung"],
    "weiterbildung": ["bildung"],
    # Energie
    "energieeffizienz": ["energie"],
    "pv": ["energie"],
    "speicher": ["energie"],
    "heizungstausch": ["energie"],
    "umwelt": ["energie"],
    "mobilitaet": ["energie"],
    # Wohnen (und Energie, weil Gebaeudehuelle)
    "sanierung": ["energie", "wohnen"],
    "daemmung": ["energie", "wohnen"],
    "fenster": ["energie", "wohnen"],
    # Sozial & Alltag (3. Standbein: zielgruppe=sozial; hier nur das feine
    # Topic-Tag fuer die Thema-Achse)
    "sozial": ["sozial"],
    "heizkostenzuschuss": ["sozial", "energie"],
    "pflegegeld": ["sozial"],
    "kinderbetreuung": ["sozial"],
    "wohnbeihilfe": ["sozial", "wohnen"],
    "ausbildung": ["sozial", "bildung"],
    "barrierefreiheit": ["sozial", "wohnen"],
    # Feine Bedarfs-Labels des Sozial-Formulars (nachgeschaerft an echten Beihilfen)
    "pflege_betreuung": ["sozial"],
    "mindestsicherung_sozialhilfe": ["sozial"],
    "familien_schulbeihilfe": ["sozial", "bildung"],
    "behinderung_rehabilitation": ["sozial"],
    "barrierefreies_wohnen": ["sozial", "wohnen"],
}


def _slug(wert):
    """Fallback: beliebigen Text in einen Slug verwandeln (ä -> ae usw.)."""
    w = str(wert or "").strip().lower()
    for u, e in _UMLAUT.items():
        w = w.replace(u, e)
    w = re.sub(r"[^a-z0-9]+", "_", w).strip("_")
    return w


def _uebersetze(wert, tabelle):
    if wert is None or str(wert).strip() == "":
        return wert
    return tabelle.get(str(wert).strip().lower(), _slug(wert))


def normalisiere_wohnsituation(wert):
    return _uebersetze(wert, _WOHNSITUATION)


def normalisiere_heizung(wert):
    return _uebersetze(wert, _HEIZUNG)


def normalisiere_vorhaben(liste):
    """Liste von Vorhaben/Themen -> kanonische, deduplizierte Slugs."""
    if not liste:
        return liste
    aus = []
    for x in liste:
        s = _uebersetze(x, _VORHABEN)
        if s and s not in aus:
            aus.append(s)
    return aus


def thema_aus_vorhaben(liste):
    """Fein-Vorhaben -> grobe Thema-Achse (mehrwertig, dedupliziert).

    Idempotent: nimmt auch bereits normalisierte Slugs entgegen. Unbekannte
    Vorhaben tragen kein grobes Thema bei (leere Liste) - die Zuordnung ist
    bewusst konservativ, die Fein-Pruefung im Matching laeuft ohnehin daneben.
    """
    if not liste:
        return []
    aus = []
    for x in liste:
        s = _uebersetze(x, _VORHABEN)
        for t in _THEMA_VORHABEN.get(s, []):
            if t not in aus:
                aus.append(t)
    return aus