#!/usr/bin/env python3
"""FoerderRadar - Prototyp Matching-Logik (Stufe 1: nur melden, nichts ausfuellen).

Laedt den Foerderkatalog und ein Kundenprofil, prueft alle Voraussetzungen
und erzeugt einen kompakten Report: Treffer / knappe Faelle / Ausschluesse.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def profil_vorhaben(profil):
    return set(profil.get("vorhaben", []) + profil.get("themen", []))


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
    if f.get("region") and f["region"] != profil.get("region"):
        return "raus", [f"Region {f['region']} != {profil.get('region')}"]

    # 3) WKO-Mitgliedschaft
    if vor.get("wko_mitglied") and not profil.get("wko_mitglied"):
        return "raus", ["WKO-Mitgliedschaft fehlt"]

    # 4) Wohnsituation (privat)
    if "wohnsituation" in vor:
        if profil.get("wohnsituation") not in vor["wohnsituation"]:
            return "raus", [f"Wohnsituation '{profil.get('wohnsituation')}' nicht foerderfaehig"]

    # 5) Einkommensgrenze
    if "einkommen_max" in vor:
        eink = profil.get("haushaltseinkommen", 0)
        limit = vor["einkommen_max"]
        # Monats- vs. Jahresgrenze grob unterscheiden
        limit_jahr = limit if limit > 1000 else limit * 12
        if eink > limit_jahr:
            return "raus", [f"Einkommen {eink:,.0f} EUR > Grenze {limit_jahr:,.0f} EUR"]
        gruende.append(f"Einkommen unter Grenze ({eink:,.0f} <= {limit_jahr:,.0f} EUR)")

    # 6) Heizung alt
    if "heizung_alt" in vor:
        if profil.get("heizung") not in vor["heizung_alt"]:
            return "raus", [f"Heizung '{profil.get('heizung')}' nicht foerderfaehig"]

    # 7) Pflegestufe
    if "pflegestufe_min" in vor:
        if profil.get("pflegestufe", 0) < vor["pflegestufe_min"]:
            return "raus", [f"Pflegestufe {profil.get('pflegestufe',0)} < {vor['pflegestufe_min']}"]

    # 8) Projektkosten
    if "projektkosten_min" in vor:
        pk = profil.get("projektkosten", 0)
        if pk and pk < vor["projektkosten_min"]:
            return "raus", [f"Projektkosten {pk:,.0f} < Mindest {vor['projektkosten_min']:,.0f} EUR"]

    # 9) Themen/Vorhaben
    if "themen" in vor:
        gemeinsam = profil_vorhaben(profil) & set(vor["themen"])
        if not gemeinsam:
            knapp = True
            gruende.append("Thema passt nicht direkt zu den Vorhaben")
        else:
            gruende.append("Thema passt: " + ", ".join(sorted(gemeinsam)))

    # 10) Status
    if f.get("status") == "ausgeschoepft":
        return "raus", ["Programm ausgeschoepft"]
    if f.get("status") == "fenster_zu":
        knapp = True
        gruende.append("Antragsfenster aktuell geschlossen")

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


if __name__ == "__main__":
    katalog = load(os.path.join(BASE, "katalog", "foerderungen.json"))
    profil_pfad = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "profiles", "test_betrieb.json")
    profil = load(profil_pfad)
    report(profil, katalog)
