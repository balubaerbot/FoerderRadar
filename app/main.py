"""FoerderRadar API - Phase 1 (Skelett).

Sicherheit: Default-Deny. Oeffentlich ist NUR:
  - GET  /            (Info)
  - GET  /health      (Monitoring, nur intern erreichbar)
  - POST /profile     (Website; Consent Pflicht + Rate-Limit)
Alle anderen Endpunkte (Lesen/Matching) erfordern den Admin-Token:
  Header:  Authorization: Bearer <FOERDER_ADMIN_TOKEN>

Trennung: `profil` = pseudonym (Agent darf lesen), `kontakt` = Klartext
(nur Versand-Worker). Der Agent sieht Kontaktdaten NIE.
"""
import hmac
import os
import sys
import time
from collections import defaultdict, deque

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

# Projekt-Root auf den Importpfad, damit `src.*` importierbar ist
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import matching_service as ms  # noqa: E402
from src import region as regionmod  # noqa: E402


def _lade_env_datei():
    """Laedt die gemountete `.env` und setzt sie als massgeblich (overrides Env).

    Grund: `docker restart` liest `env_file` NICHT neu. Damit neu gesetzte Werte
    (z.B. das eingeschraenkte `DATABASE_URL` = app_web) nach einem normalen Neustart
    ankommen, gilt fuer dieses Projekt die `.env` als Quelle der Wahrheit.
    """
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(pfad):
        return
    for zeile in open(pfad, encoding="utf-8"):
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        os.environ[k.strip()] = v.strip()


_lade_env_datei()

app = FastAPI(title="FoerderRadar API", version="0.1.0")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_TOKEN = os.environ.get("FOERDER_ADMIN_TOKEN", "")

# Oeffentliche Routen. Alles andere ist default-deny -> Token noetig.
PUBLIC = {("GET", "/"), ("GET", "/health"), ("POST", "/profile")}

# Rate-Limit fuer den oeffentlichen Schreibpfad: max N pro IP pro Fenster.
RATE_LIMIT = 5
RATE_WINDOW = 60.0
_hits = defaultdict(deque)


def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def _client_ip(request):
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.middleware("http")
async def guard(request: Request, call_next):
    key = (request.method, request.url.path)
    if key not in PUBLIC:
        # Default-Deny: Admin-Token erforderlich.
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
            return JSONResponse({"detail": "nicht autorisiert"}, status_code=401)
    elif key == ("POST", "/profile"):
        # Rate-Limit nur auf dem oeffentlichen Schreibpfad.
        ip = _client_ip(request)
        now = time.monotonic()
        q = _hits[ip]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return JSONResponse({"detail": "zu viele Anfragen"}, status_code=429)
        q.append(now)
    return await call_next(request)


@app.get("/")
def root():
    return {"message": "FoerderRadar API v0.1.0"}


@app.get("/health")
def health():
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            ok = cur.fetchone()[0] == 1
            cur.execute("SELECT current_user")
            rolle = cur.fetchone()[0]
        return {"status": "ok", "db": ok, "role": rolle}
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
    # Einwilligung zur Datenverarbeitung (Pflicht)
    einwilligung: bool = False


@app.post("/profile")
def create_profile(p: ProfilIn):
    if p.typ not in ("betrieb", "privat"):
        raise HTTPException(status_code=400, detail="typ muss 'betrieb' oder 'privat' sein")
    if not p.einwilligung:
        raise HTTPException(status_code=400, detail="Einwilligung erforderlich")
    if p.kanal not in (None, "email", "sms"):
        raise HTTPException(status_code=400, detail="kanal muss 'email' oder 'sms' sein")

    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO profil (typ, region_grob, branche, mitarbeiterklasse, wko_mitglied,
                wohnsituation, haushaltsgroesse, einkommen_spanne, heizung, pflegestufe,
                familienstand, kinder_im_haushalt, vorhaben)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING kunde_id
            """,
            (p.typ, regionmod.normalisiere_region(p.region_grob) or p.region_grob,
             p.branche, p.mitarbeiterklasse, p.wko_mitglied,
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
    # Antwort enthaelt nur die kunde_id - keine Kontaktdaten.
    return {"kunde_id": str(kunde_id)}


@app.get("/profiles")
def list_profiles_agent_view():
    """Pseudonyme Sicht - genau das, was der Agent/Dienst lesen darf. (Admin)"""
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
    (kategorie top/pruefenswert) in `match` ein. Idempotent wiederholbar. (Admin)"""
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
    """Liefert die eingefrorenen Match-Eintraege eines Kunden. (Admin)"""
    with db() as conn:
        rows = ms.get_matches(conn, kunde_id)
    return {"kunde_id": kunde_id, "anzahl": len(rows), "matches": rows}
