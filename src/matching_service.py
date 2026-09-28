"""FoerderRadar - Matching-Dienst.

Liest ein pseudonymes Profil aus der Sicht `profil_agent` (KEINE Kontaktdaten),
bewertet es gegen den Foerderkatalog und friert das Ergebnis in `match` ein.

Wichtig: Der Agent/Dienst sieht hier nie Klartext-Kontaktdaten.
"""
import json
import os
import re
from typing import Optional

from src import match as matchmod
from src import region as regionmod
from src import vokabular as vok

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KATALOG_PFAD = os.path.join(BASE, "katalog", "foerderungen.json")


def load_katalog(pfad: str = KATALOG_PFAD) -> dict:
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


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


def profil_row_to_dict(row: dict) -> dict:
    """Adapter: Zeile aus `profil_agent` -> Profil-Dict fuer die Match-Logik.

    Normalisiert hier defensiv auch Wohnsituation/Heizung/Vorhaben auf die
    kanonischen Katalog-Slugs. So matchen auch Altdaten, die noch Anzeige-Labels
    enthalten ('Eigentum', 'Photovoltaik') - die Normalisierung ist idempotent.
    """
    d = dict(row)
    vorhaben = vok.normalisiere_vorhaben(list(d.get("vorhaben") or []))
    return {
        "typ": d.get("typ"),
        "region": regionmod.normalisiere_region(d.get("region_grob")),
        "branche": d.get("branche"),
        "mitarbeiterklasse": d.get("mitarbeiterklasse"),
        "wko_mitglied": d.get("wko_mitglied"),
        "wohnsituation": vok.normalisiere_wohnsituation(d.get("wohnsituation")),
        "haushaltsgroesse": d.get("haushaltsgroesse"),
        "haushaltseinkommen": einkommen_obergrenze(d.get("einkommen_spanne")),
        "heizung": vok.normalisiere_heizung(d.get("heizung")),
        "pflegestufe": d.get("pflegestufe"),
        "familienstand": d.get("familienstand"),
        "kinder_im_haushalt": d.get("kinder_im_haushalt"),
        "vorhaben": vorhaben,
        "themen": vorhaben,
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
        for eintrag in ergebnis["top"] + ergebnis["pruefenswert"]:
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
