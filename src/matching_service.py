"""FoerderRadar - Matching-Dienst.

Liest ein pseudonymes Profil aus der Sicht `profil_agent` (KEINE Kontaktdaten),
bewertet es gegen den Foerderkatalog und friert das Ergebnis in `match` ein.

Wichtig: Der Agent/Dienst sieht hier nie Klartext-Kontaktdaten.
"""
import importlib.util
import json
import os
import re
from typing import Optional

from src import match as matchmod
from src import region as regionmod
from src import vokabular as vok

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KATALOG_PFAD = os.path.join(BASE, "katalog", "foerderungen.json")


_VALIDATOR = None


def _schema_validator():
    """Laedt tools/validate_katalog.py als Gate-Modul (einmalig gecacht).

    Bewusst DERSELBE Code wie das CLI-Gate: eine zweite, driftende Regelkopie
    war die Ursache der Regression aus 3a588ff (Gate OK, Laufzeit strenger).
    """
    global _VALIDATOR
    if _VALIDATOR is None:
        pfad = os.path.join(BASE, "tools", "validate_katalog.py")
        spec = importlib.util.spec_from_file_location("katalog_validator", pfad)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _VALIDATOR = mod
    return _VALIDATOR


def load_katalog(pfad: str = KATALOG_PFAD) -> dict:
    # Fail loud: ein fehlerhafter Katalog darf nicht still ins Matching laufen
    # (doppelte IDs, fehlende Quelle, unbekannte voraussetzungen-Keys ...).
    fehler, _ = _schema_validator().validate(pfad)
    if fehler:
        raise ValueError("Katalog-Schema verletzt: " + "; ".join(fehler))
    with open(pfad, encoding="utf-8") as f:
        kat = json.load(f)
    validiere_katalog(kat)
    return kat


def validiere_katalog(kat: dict) -> None:
    """Stellt sicher, dass `einkommen_max` IMMER eine gueltige Einheit hat.

    Ohne Einheit wuerde stillschweigend 'jahr' angenommen - ein Tippfehler bei
    einem Monatswert haette dann einen Faktor-12-Fehlvergleich zur Folge, ohne
    dass es auffaellt. Darum hart scheitern (fail loud).
    """
    for f in kat.get("foerderungen", []):
        vor = f.get("voraussetzungen") or {}
        if "einkommen_max" in vor and vor.get("einkommen_einheit") not in ("jahr", "monat"):
            raise ValueError(
                f"Katalog-Eintrag '{f.get('id')}': 'einkommen_max' braucht "
                f"'einkommen_einheit' ('jahr' oder 'monat')."
            )


def einkommen_obergrenze(spanne: Optional[str]) -> Optional[float]:
    """Wandelt eine Einkommens-Spanne in eine Zahl.

    Konservativ: nimmt die OBERGRENZE der Spanne, damit niemand faelschlich
    als foerderfaehig gilt (z. B. '35.000-50.000' -> 50000).
    """
    if not spanne:
        return None
    zahlen = [float(x.replace(".", "").replace(",", "."))
              for x in re.findall(r"\d[\d.,]*", str(spanne))]
    return max(zahlen) if zahlen else None


def einkommen_jahr_obergrenze(spanne: Optional[str]) -> Optional[float]:
    """Formular erhebt MONATSNETTO -> konservative Jahresschaetzung (x12).

    Das Matching vergleicht gegen Jahresgrenzen (`einkommen_max` +
    `einkommen_einheit`). Die Obergrenze der Monatsspanne x12 ist bewusst
    konservativ (eher zu hoch -> eher Ausschluss).
    """
    monat = einkommen_obergrenze(spanne)
    return None if monat is None else monat * 12


def profil_row_to_dict(row: dict) -> dict:
    """Adapter: Zeile aus `profil_agent` -> Profil-Dict fuer die Match-Logik.

    Normalisiert hier defensiv auch Wohnsituation/Heizung/Vorhaben auf die
    kanonischen Katalog-Slugs. So matchen auch Altdaten, die noch Anzeige-Labels
    enthalten ('Eigentum', 'Photovoltaik') - die Normalisierung ist idempotent.
    """
    d = dict(row)
    vorhaben = vok.normalisiere_vorhaben(list(d.get("vorhaben") or []))
    # Grobe Thema-Achse: bevorzugt das beim Eintrag EINMAL gespeicherte Ergebnis
    # (Chips + optionales KI-Mapping), sonst aus den Vorhaben abgeleitet. Beides
    # wird vereinigt und auf erlaubte Werte gefiltert - Altdaten ohne `thema`
    # funktionieren unveraendert.
    thema_db = [t for t in (d.get("thema") or []) if t in vok.ERLAUBTE_THEMEN]
    thema = list(thema_db)
    for t in vok.thema_aus_vorhaben(vorhaben):
        if t not in thema:
            thema.append(t)
    thema = sorted(thema)
    return {
        "typ": d.get("typ"),
        "region": regionmod.normalisiere_region(d.get("region_grob")),
        "branche": d.get("branche"),
        "mitarbeiterklasse": d.get("mitarbeiterklasse"),
        "wko_mitglied": d.get("wko_mitglied"),
        "wohnsituation": vok.normalisiere_wohnsituation(d.get("wohnsituation")),
        "haushaltsgroesse": d.get("haushaltsgroesse"),
        "haushaltseinkommen": einkommen_jahr_obergrenze(d.get("einkommen_spanne")),
        "heizung": vok.normalisiere_heizung(d.get("heizung")),
        "pflegestufe": d.get("pflegestufe"),
        "behinderung": d.get("behinderung"),
        "familienstand": d.get("familienstand"),
        "kinder_im_haushalt": d.get("kinder_im_haushalt"),
        "lebenssituation": d.get("lebenssituation"),
        "vorhaben": vorhaben,
        "themen": vorhaben,
        # Grobe Thema-Achse (WAS): gespeichert (inkl. KI) + aus Vorhaben abgeleitet.
        "thema": thema,
        # projektkosten kennt das pseudonyme Profil nicht -> Pruefung wird uebersprungen
        "projektkosten": None,
    }


def lade_profil(conn, kunde_id):
    """Liest ein Profil aus der pseudonymen Sicht. Gibt dict oder None."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM profil_agent WHERE kunde_id = %s", (kunde_id,))
        cols = [c.name for c in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def alle_kunde_ids(conn):
    """Alle kunde_ids aus der pseudonymen Sicht (`profil_agent`).

    Grundlage fuer einen vollen Matching-Lauf: der Versand-Worker bewertet
    damit JEDES Profil gegen den aktuellen Katalog - auch frisch erfasste,
    die noch keine `match`-Zeilen haben (sonst Henne-Ei-Problem).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT kunde_id FROM profil_agent ORDER BY kunde_id")
        return [r[0] for r in cur.fetchall()]


def run_match(conn, kunde_id):
    """Bewertet das Profil und friert das Ergebnis in `match` ein.

    Rueckgabe: Bewertungs-dict (top/pruefenswert/raus) oder None (Profil fehlt).
    """
    roh = lade_profil(conn, kunde_id)
    if roh is None:
        return None

    profil = profil_row_to_dict(roh)
    ergebnis = matchmod.bewerte(profil, load_katalog())

    with conn.cursor() as cur:
        # nur noch nicht gemeldete Eintraege neu setzen (idempotenter Re-Run)
        cur.execute(
            "DELETE FROM match WHERE kunde_id = %s AND status = 'identifiziert'",
            (kunde_id,),
        )
        # Doppelversand-Guard: bereits GEMELDETE Foerderungen (status
        # 'gemeldet' = ein echter Versand hat stattgefunden) werden NICHT
        # erneut als 'identifiziert' eingefuegt. Sonst braechte jeder weitere
        # Match-Lauf (z.B. der taegliche Cron-Sweep) denselben Kunden wieder
        # in offene_kunden() -> zweite Mail an denselben Kunden.
        # Die Tabelle match hat bewusst KEINEN UNIQUE-Index auf
        # (kunde_id, foerderung_id); die Idempotenz wird daher hier explizit
        # sichergestellt. NEUE Foerderungen (noch nicht gemeldet) werden
        # weiterhin erkannt und gemeldet.
        cur.execute(
            "SELECT foerderung_id FROM match WHERE kunde_id = %s AND status = 'gemeldet'",
            (kunde_id,),
        )
        bereits_gemeldet = {r[0] for r in cur.fetchall()}
        for eintrag in ergebnis["top"] + ergebnis["pruefenswert"]:
            if eintrag["id"] in bereits_gemeldet:
                continue
            cur.execute(
                """INSERT INTO match (kunde_id, foerderung_id, kategorie, status)
                   VALUES (%s, %s, %s, 'identifiziert')""",
                (kunde_id, eintrag["id"], eintrag["kategorie"]),
            )
        conn.commit()
    return ergebnis


def get_matches(conn, kunde_id):
    """Liefert die (eingefrorenen) Match-Eintraege eines Kunden."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, foerderung_id, kategorie, status, gemeldet_am, eingefroren_am
               FROM match WHERE kunde_id = %s
               ORDER BY kategorie, foerderung_id""",
            (kunde_id,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
