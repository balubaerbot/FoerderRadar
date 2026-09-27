"""FoerderRadar API - Phase 1 (Skelett).

Trennung: `profil` = pseudonym (Agent darf lesen), `kontakt` = Klartext
(nur Versand-Worker). Der Agent sieht Kontaktdaten NIE.
"""
import os
import sys

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# Projekt-Root auf den Importpfad, damit `src.*` importierbar ist
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import matching_service as ms  # noqa: E402

app = FastAPI(title="FoerderRadar API", version="0.1.0")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


@app.get("/")
def root():
    return {"message": "FoerderRadar API v0.1.0"}


@app.get("/health")
def health():
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            ok = cur.fetchone()[0] == 1
        return {"status": "ok", "db": ok}
    except Exception as e:  # noqa: BLE001
        return {"status": "degraded", "db": False, "error": str(e)[:200]}


class ProfilIn(BaseModel):
    typ: str  # betrieb | privat
    region_grob: Optional[str] = None
    branche: Optional[str] = None
    mitarbeiterklasse: Optional[str] = None
    wko_mitglied: Optional[bool] = None
    wohnsituation: Optional[str] = None
    haushaltsgroesse: Optional[str] = None
    einkommen_spanne: Optional[str] = None
    heizung: Optional[str] = None
    pflegestufe: Optional[int] = None
    familienstand: Optional[str] = None
    kinder_im_haushalt: Optional[bool] = None
    vorhaben: list[str] = []
    # Kontaktdaten (getrennt gespeichert)
    name: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    kanal: Optional[str] = None  # email | sms


@app.post("/profile")
def create_profile(p: ProfilIn):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO profil (typ, region_grob, branche, mitarbeiterklasse, wko_mitglied,
                wohnsituation, haushaltsgroesse, einkommen_spanne, heizung, pflegestufe,
                familienstand, kinder_im_haushalt, vorhaben)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING kunde_id
            """,
            (p.typ, p.region_grob, p.branche, p.mitarbeiterklasse, p.wko_mitglied,
             p.wohnsituation, p.haushaltsgroesse, p.einkommen_spanne, p.heizung,
             p.pflegestufe, p.familienstand, p.kinder_im_haushalt, p.vorhaben),
        )
        kunde_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO kontakt (kunde_id, name, email, telefon, kanal, einwilligung_am)
            VALUES (%s,%s,%s,%s,%s, now())
            """,
            (kunde_id, p.name, p.email, p.telefon, p.kanal),
        )
        conn.commit()
    return {"kunde_id": str(kunde_id)}


@app.get("/profiles")
def list_profiles_agent_view():
    """Pseudonyme Sicht - genau das, was der Agent/Dienst lesen darf."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT kunde_id, typ, region_grob, vorhaben FROM profil_agent")
        rows = cur.fetchall()
    return [
        {"kunde_id": str(r[0]), "typ": r[1], "region_grob": r[2], "vorhaben": r[3]}
        for r in rows
    ]


@app.post("/match/{kunde_id}")
def match_profile(kunde_id: str):
    """Bewertet das pseudonyme Profil gegen den Katalog und friert Treffer
    (kategorie top/pruefenswert) in `match` ein. Idempotent wiederholbar."""
    try:
        with db() as conn:
            ergebnis = ms.run_match(conn, kunde_id)
    except psycopg.errors.InvalidTextRepresentation:
        raise HTTPException(status_code=400, detail="kunde_id ist keine gueltige UUID")
    if ergebnis is None:
        raise HTTPException(status_code=404, detail="kunde_id nicht gefunden")
    return {
        "kunde_id": kunde_id,
        "top": len(ergebnis["top"]),
        "pruefenswert": len(ergebnis["pruefenswert"]),
        "ausgeschlossen": len(ergebnis["raus"]),
        "ergebnisse": ergebnis["top"] + ergebnis["pruefenswert"],
    }


@app.get("/match/{kunde_id}")
def get_match(kunde_id: str):
    """Liefert die eingefrorenen Match-Eintraege eines Kunden."""
    with db() as conn:
        rows = ms.get_matches(conn, kunde_id)
    return {"kunde_id": kunde_id, "anzahl": len(rows), "matches": rows}
