#!/usr/bin/env python3
"""FoerderRadar - Katalog-Validator (Qualitaets-Gate).

Prueft katalog/foerderungen.json deterministisch:
- Schema: Pflichtfelder, erlaubte Werte (status, zielgruppe)
- Eindeutige IDs
- Jede Foerderung hat eine Quelle (URL) - keine Quelle, kein Eintrag
- voraussetzungen nutzt nur bekannte Schluessel (Match-Logik)
- meta.stand ist ein ISO-Datum

Exit-Code 0 = ok, 1 = Fehler. Damit kann jede Katalog-Aenderung
maschinell abgesichert werden, bevor sie gemergt wird.

Aufruf:  python3 tools/validate_katalog.py [pfad]
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(BASE, "katalog", "foerderungen.json")

ERLAUBTE_ZIELGRUPPEN = {"betrieb", "privat", "sozial"}
# Thema-Achse = WAS (wer = zielgruppe). Mehrwertige Liste, ein Eintrag darf
# mehrere Themen tragen. Kanonisch auch in src/vokabular.py (ERLAUBTE_THEMEN).
ERLAUBTE_THEMEN = {"wirtschaft", "sozial", "energie", "wohnen", "bildung"}
ERLAUBTE_STATUS = {"offen", "ausgeschoepft", "fenster_zu", "angekuendigt"}
ERLAUBTE_VORAUSSETZUNGEN = {
    "wko_mitglied",
    "projektkosten_min",
    "themen",
    "wohnsituation",
    "einkommen_max",
    "einkommen_einheit",
    "heizung_alt",
    "pflegestufe_min",
    "behinderung",
}
PFLICHTFELDER = ["id", "name", "stelle", "zielgruppe", "thema", "betrag", "frist", "status", "quelle"]


def validate(pfad=DEFAULT):
    fehler, warnungen = [], []

    if not os.path.exists(pfad):
        return [f"Datei nicht gefunden: {pfad}"], []

    with open(pfad, encoding="utf-8") as f:
        daten = json.load(f)

    # --- meta ---
    meta = daten.get("meta", {})
    stand = meta.get("stand")
    if not stand:
        fehler.append("meta.stand fehlt")
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(stand)):
        fehler.append(f"meta.stand kein ISO-Datum (YYYY-MM-DD): {stand!r}")
    if not meta.get("quellen"):
        warnungen.append("meta.quellen ist leer")

    # --- foerderungen ---
    liste = daten.get("foerderungen")
    if not isinstance(liste, list) or not liste:
        fehler.append("'foerderungen' fehlt oder ist leer")
        return fehler, warnungen

    gesehen = {}
    for i, f in enumerate(liste):
        if not isinstance(f, dict):
            fehler.append(f"[{i}] kein Objekt")
            continue
        fid = f.get("id", f"<index {i}>")

        for feld in PFLICHTFELDER:
            if not f.get(feld) and f.get(feld) != 0:
                fehler.append(f"[{fid}] Pflichtfeld fehlt/leer: {feld}")

        if fid in gesehen:
            fehler.append(f"[{fid}] doppelte ID (auch bei Index {gesehen[fid]})")
        gesehen[fid] = i

        zg = f.get("zielgruppe")
        if zg not in ERLAUBTE_ZIELGRUPPEN:
            fehler.append(f"[{fid}] ungueltige zielgruppe: {zg!r}")

        st = f.get("status")
        if st not in ERLAUBTE_STATUS:
            fehler.append(f"[{fid}] ungueltiger status: {st!r}")

        # Thema-Achse: nicht-leere Liste erlaubter, grober Themen.
        thema = f.get("thema")
        if not isinstance(thema, list) or not thema:
            if thema is not None or "thema" in f:
                fehler.append(f"[{fid}] 'thema' muss eine nicht-leere Liste sein")
            else:
                fehler.append(f"[{fid}] Pflichtfeld fehlt/leer: thema")
        else:
            unbekannt = [t for t in thema if t not in ERLAUBTE_THEMEN]
            if unbekannt:
                fehler.append(f"[{fid}] unbekannte thema-Werte: {sorted(unbekannt)}")
            if len(thema) != len(set(thema)):
                fehler.append(f"[{fid}] 'thema' enthaelt Duplikate")

        q = f.get("quelle")
        if q and not re.match(r"^https?://", str(q)):
            fehler.append(f"[{fid}] quelle ist keine http(s)-URL: {q!r}")

        vor = f.get("voraussetzungen", {})
        if not isinstance(vor, dict):
            fehler.append(f"[{fid}] voraussetzungen ist kein Objekt")
        else:
            unbekannt = set(vor) - ERLAUBTE_VORAUSSETZUNGEN
            if unbekannt:
                fehler.append(f"[{fid}] unbekannte voraussetzungen-Schluessel: {sorted(unbekannt)}")
            if "themen" in vor and not isinstance(vor["themen"], list):
                fehler.append(f"[{fid}] voraussetzungen.themen ist keine Liste")
            if "behinderung" in vor and not isinstance(vor["behinderung"], bool):
                fehler.append(f"[{fid}] voraussetzungen.behinderung muss true/false sein")
            for k in ("wohnsituation", "heizung_alt"):
                if k in vor and not isinstance(vor[k], list):
                    fehler.append(f"[{fid}] voraussetzungen.{k} ist keine Liste")
            for k in ("projektkosten_min", "einkommen_max", "pflegestufe_min"):
                if k in vor and not isinstance(vor[k], (int, float)):
                    fehler.append(f"[{fid}] voraussetzungen.{k} ist keine Zahl")
            # einkommen_max ohne Einheit -> stiller Faktor-12-Fehler moeglich.
            # Muss zur Laufzeitpruefung in src/matching_service.py passen.
            if "einkommen_max" in vor and vor.get("einkommen_einheit") not in ("jahr", "monat"):
                fehler.append(
                    f"[{fid}] voraussetzungen.einkommen_max braucht "
                    f"'einkommen_einheit' ('jahr' oder 'monat')"
                )

        if st == "offen" and not f.get("frist"):
            warnungen.append(f"[{fid}] status 'offen' ohne Frist")

        # hinweise = nur Anzeige, NICHT maschinell geprueft -> muss Textliste sein
        if "hinweise" in f:
            hw = f["hinweise"]
            if not isinstance(hw, list) or not all(isinstance(x, str) for x in hw):
                fehler.append(f"[{fid}] 'hinweise' muss eine Liste von Texten sein")

    return fehler, warnungen


def main():
    pfad = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    fehler, warnungen = validate(pfad)

    with open(pfad, encoding="utf-8") as f:
        n = len(json.load(f).get("foerderungen", []))

    print(f"Katalog: {pfad}")
    print(f"Eintraege: {n}")

    for w in warnungen:
        print(f"  WARNUNG: {w}")
    for e in fehler:
        print(f"  FEHLER:  {e}")

    if fehler:
        print(f"\nERGEBNIS: NICHT OK ({len(fehler)} Fehler, {len(warnungen)} Warnungen)")
        return 1
    print(f"\nERGEBNIS: OK ({len(warnungen)} Warnungen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
