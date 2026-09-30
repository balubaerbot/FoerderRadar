#!/usr/bin/env python3
"""FoerderRadar - Prototyp Matching-Logik (Stufe 1: nur melden, nichts ausfuellen).

Laedt den Foerderkatalog und ein Kundenprofil, prueft alle Voraussetzungen
und erzeugt einen kompakten Report: Treffer / knappe Faelle / Ausschluesse.
"""
import json
import os
import sys

try:
    from src import region as regionmod
except ImportError:  # direkt als Skript gestartet (python src/match.py)
    import region as regionmod  # type: ignore

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def profil_vorhaben(profil):
    return set(profil.get("vorhaben", []) + profil.get("themen", []))


def profil_thema(profil):
    """Grobe Thema-Achse des Profils (WAS), z. B. {'sozial', 'energie'}.

    Gegenstueck zu `profil_vorhaben` (fein). Kommt aus dem Formular/der KI
    (`thema`) bzw. abgeleitet aus den Vorhaben. Ohne Angabe leer -> die grobe
    Pruefung wird uebersprungen (kein falscher Ausschluss).
    """
    return set(profil.get("thema") or [])


def pruefe(f, profil):
    """Gibt (kategorie, gruende) zurueck.

    kategorie: 'treffer' | 'knapp' | 'raus'
    """
    vor = f.get("voraussetzungen", {})
    gruende = []
    knapp = False

    # 1) Zielgruppe
    if f.get("zielgruppe") != profil.get("typ"):
        return "raus", ["Zielgruppe passt nicht"]

    # 2) Region
    # Bundesfoerderungen gelten in ganz Oesterreich -> fuer JEDES Bundesland
    # ein Treffer. "Bund"/leer = bundesweit (siehe src/region.ist_bundesweit).
    if not regionmod.ist_bundesweit(f.get("region")) \
            and f.get("region") != profil.get("region"):
        return "raus", [f"Region {f['region']} != {profil.get('region')}"]

    # 3) WKO-Mitgliedschaft
    if vor.get("wko_mitglied") and not profil.get("wko_mitglied"):
        return "raus", ["WKO-Mitgliedschaft fehlt"]

    # 4) Wohnsituation (privat)
    if "wohnsituation" in vor:
        if profil.get("wohnsituation") not in vor["wohnsituation"]:
            return "raus", [f"Wohnsituation '{profil.get('wohnsituation')}' nicht foerderfaehig"]

    # 5) Einkommensgrenze
    #    Die Einheit ist explizit: der Katalog sagt ueber `einkommen_einheit`,
    #    ob der Grenzwert ein Monats- oder Jahresnetto ist. Das Profil fuehrt
    #    `haushaltseinkommen` IMMER als Jahresschaetzung. Verglichen wird in
    #    Jahreseinheiten - keine Ratevermutung ueber die Groessenordnung mehr.
    if "einkommen_max" in vor:
        eink = profil.get("haushaltseinkommen")  # Jahresnetto
        limit = vor["einkommen_max"]
        einheit = vor.get("einkommen_einheit", "jahr")
        limit_jahr = limit * 12 if einheit == "monat" else limit
        if eink is None:
            knapp = True
            gruende.append("Einkommen nicht angegeben - Grenze nicht pruefbar")
        elif eink > limit_jahr:
            return "raus", [f"Einkommen {eink:,.0f} EUR/Jahr > Grenze {limit_jahr:,.0f} EUR/Jahr"]
        else:
            gruende.append(f"Einkommen unter Grenze ({eink:,.0f} <= {limit_jahr:,.0f} EUR/Jahr)")

    # 6) Heizung alt
    if "heizung_alt" in vor:
        if profil.get("heizung") not in vor["heizung_alt"]:
            return "raus", [f"Heizung '{profil.get('heizung')}' nicht foerderfaehig"]

    # 7) Pflegestufe
    if "pflegestufe_min" in vor:
        ps = profil.get("pflegestufe")
        if ps is None:
            knapp = True
            gruende.append("Pflegestufe nicht angegeben - nicht pruefbar")
        elif ps < vor["pflegestufe_min"]:
            return "raus", [f"Pflegestufe {ps} < {vor['pflegestufe_min']}"]

    # 8) Projektkosten
    if "projektkosten_min" in vor:
        pk = profil.get("projektkosten", 0)
        if pk and pk < vor["projektkosten_min"]:
            return "raus", [f"Projektkosten {pk:,.0f} < Mindest {vor['projektkosten_min']:,.0f} EUR"]

    # 9) Themen/Vorhaben (fein)
    if "themen" in vor:
        gemeinsam = profil_vorhaben(profil) & set(vor["themen"])
        if not gemeinsam:
            knapp = True
            gruende.append("Thema passt nicht direkt zu den Vorhaben")
        else:
            gruende.append("Thema passt: " + ", ".join(sorted(gemeinsam)))

    # 9b) Thema-Achse (grob): standbein-uebergreifende Einordnung.
    #     Gibt es ein Profilthema, aber keine gemeinsame Schnittmenge mit dem
    #     Eintrag -> 'knapp' (nicht 'raus'): die grobe Achse ist heuristisch/aus
    #     Freitext abgeleitet und darf einen Treffer nicht hart verwerfen.
    if f.get("thema"):
        mein_thema = profil_thema(profil)
        if mein_thema:
            gemeinsam = mein_thema & set(f["thema"])
            if not gemeinsam:
                knapp = True
                gruende.append("Thema (grob) passt nicht zu den Angaben")
            else:
                gruende.append("Thema passt: " + ", ".join(sorted(gemeinsam)))

    # 10) Status
    st = f.get("status")
    if st == "ausgeschoepft":
        return "raus", ["Programm ausgeschoepft"]
    if st == "fenster_zu":
        knapp = True
        gruende.append("Antragsfenster aktuell geschlossen")
    if st == "angekuendigt":
        knapp = True
        gruende.append("Call angekuendigt - noch nicht offen")

    # 11) Zusaetzliche Bedingungen (nur Anzeige, NICHT maschinell geprueft)
    for h in f.get("hinweise", []):
        gruende.append("Hinweis: " + h)

    return ("knapp" if knapp else "treffer"), gruende


def report(profil, katalog):
    treffer, knapp, raus = [], [], []
    for f in katalog["foerderungen"]:
        kat, gruende = pruefe(f, profil)
        (treffer if kat == "treffer" else knapp if kat == "knapp" else raus).append((f, gruende))

    print("=" * 70)
    print(f"FOERDER-REPORT fuer: {profil['name']}  ({profil['typ']}, {profil.get('standort','?')})")
    print(f"Katalog-Stand: {katalog['meta']['stand']} | {len(katalog['foerderungen'])} Programme geprueft")
    print("=" * 70)

    def zeile(f, gruende):
        print(f"\n* {f['name']}  [{f['stelle']}]")
        print(f"    Betrag: {f['betrag']}")
        print(f"    Frist:  {f['frist']}   (Status: {f['status']})")
        print(f"    Warum:  {'; '.join(gruende) if gruende else '-'}")
        print(f"    Quelle: {f['quelle']}")

    print(f"\n>>> TREFFER ({len(treffer)})")
    for f, g in treffer:
        zeile(f, g)

    print(f"\n>>> KNAPP / zu pruefen ({len(knapp)})")
    for f, g in knapp:
        zeile(f, g)

    print(f"\n>>> AUSGESCHLOSSEN ({len(raus)})")
    for f, g in raus:
        print(f"  - {f['name']}: {'; '.join(g)}")

    print("\n" + "=" * 70)
    print("Hinweis: Prototyp mit Testdaten. Betraege/Fristen vor Nutzung verifizieren.")
    return len(treffer), len(knapp), len(raus)


def bewerte(profil, katalog):
    """Strukturierte Bewertung OHNE Ausgabe - fuer Dienst/API.

    Rueckgabe: {"top": [...], "pruefenswert": [...], "raus": [...]}
    Jeder Eintrag enthaelt die Katalogfelder + kategorie + gruende.
    """
    top, pruefen, raus = [], [], []
    for f in katalog["foerderungen"]:
        kat, gruende = pruefe(f, profil)
        eintrag = {
            "id": f.get("id"),
            "name": f.get("name"),
            "stelle": f.get("stelle"),
            "thema": f.get("thema", []),
            "betrag": f.get("betrag"),
            "frist": f.get("frist"),
            "status": f.get("status"),
            "quelle": f.get("quelle"),
            "kategorie": {"treffer": "top", "knapp": "pruefenswert", "raus": "raus"}[kat],
            "gruende": gruende,
        }
        if kat == "treffer":
            top.append(eintrag)
        elif kat == "knapp":
            pruefen.append(eintrag)
        else:
            raus.append(eintrag)
    return {"top": top, "pruefenswert": pruefen, "raus": raus}


if __name__ == "__main__":
    katalog = load(os.path.join(BASE, "katalog", "foerderungen.json"))
    profil_pfad = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "profiles", "test_betrieb.json")
    profil = load(profil_pfad)
    report(profil, katalog)
