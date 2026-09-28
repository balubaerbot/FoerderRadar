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
import re
import sys
import time
from collections import defaultdict, deque

from urllib.parse import urlencode

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Einfache, bewusst grosszuegige Formatpruefung (kein RFC-Vollparser):
# verhindert offensichtlichen Muell, endgueltige Zustellbarkeit zeigt erst der Versand.
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
from pydantic import BaseModel
from typing import Optional

# Projekt-Root auf den Importpfad, damit `src.*` importierbar ist
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import matching_service as ms  # noqa: E402
from src import region as regionmod  # noqa: E402
from src import vokabular as vok  # noqa: E402


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

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASIS, "app", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASIS, "app", "static")), name="static")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_TOKEN = os.environ.get("FOERDER_ADMIN_TOKEN", "")

# Oeffentliche Routen. Alles andere ist default-deny -> Token noetig.
PUBLIC = {
    ("GET", "/"), ("GET", "/info"), ("GET", "/health"), ("POST", "/profile"),
    ("GET", "/formular"), ("POST", "/formular"), ("GET", "/danke"),
    ("GET", "/impressum"), ("GET", "/datenschutz"),
}
# Oeffentliche Schreibpfade: nur diese bekommen das Rate-Limit.
OEFFENTLICH_SCHREIBEN = {("POST", "/profile"), ("POST", "/formular")}

# Rate-Limit fuer den oeffentlichen Schreibpfad: max N pro IP pro Fenster.
RATE_LIMIT = 5
RATE_WINDOW = 60.0
_hits = defaultdict(deque)

# Auswahl-Listen fuer das Web-Formular
BUNDESLAENDER = ["Burgenland", "K\u00e4rnten", "Nieder\u00f6sterreich", "Ober\u00f6sterreich",
                 "Salzburg", "Steiermark", "Tirol", "Vorarlberg", "Wien"]
BRANCHEN = ["Handwerk / Gewerbe", "IT / Digitalisierung", "Handel", "Produktion",
            "Tourismus / Gastronomie", "Sonstiges"]
MITARBEITERKLASSEN = ["1\u20134", "5\u20139", "10\u201349", "50\u2013249", "250+"]
WOHNSITUATIONEN = ["Eigentum", "Miete", "Genossenschaft", "bei Angeh\u00f6rigen"]
HAUSHALTSGROESSEN = ["1", "2", "3", "4", "5+"]
EINKOMMENSSPANNEN = ["unter 1.000 \u20ac", "1.000\u20132.000 \u20ac", "2.000\u20133.000 \u20ac",
                     "3.000\u20134.000 \u20ac", "\u00fcber 4.000 \u20ac"]
HEIZUNGEN = ["Fernw\u00e4rme", "Gas", "\u00d6l", "Pellets / Holz", "W\u00e4rmepumpe", "Strom", "Sonstiges"]
FAMILIENSTAENDE = ["ledig", "verheiratet / Partnerschaft", "geschieden", "verwitwet"]
VORHABEN_OPTIONEN = ["Digitalisierung", "Investition", "Schulung", "Energieeffizienz",
                     "Photovoltaik", "Gr\u00fcndung", "Sanierung", "Weiterbildung", "Mobilit\u00e4t"]


def _render(request, name, ctx=None, status_code=200):
    """Rendert ein Template - kompatibel mit alter und neuer Starlette-Signatur."""
    ctx = dict(ctx or {})
    try:
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)
    except TypeError:
        ctx["request"] = request
        return templates.TemplateResponse(name, ctx, status_code=status_code)


def _formular_kontext(werte=None, fehler=None, typ="betrieb"):
    return {
        "typ": typ, "werte": werte or {}, "fehler": fehler,
        "bundeslaender": BUNDESLAENDER, "branchen": BRANCHEN,
        "mitarbeiterklassen": MITARBEITERKLASSEN, "wohnsituationen": WOHNSITUATIONEN,
        "haushaltsgroessen": HAUSHALTSGROESSEN, "einkommensspannen": EINKOMMENSSPANNEN,
        "heizungen": HEIZUNGEN, "familienstaende": FAMILIENSTAENDE,
        "vorhaben_optionen": VORHABEN_OPTIONEN,
    }


def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


def _client_ip(request):
    """Client-IP fuer das Rate-Limit.

    X-Forwarded-For NUR auswerten, wenn ein vertrauenswuerdiger Proxy
    konfiguriert ist (FOERDER_TRUST_PROXY=1). Sonst koennte jeder das Limit
    mit einem gefaelschten Header umgehen.
    """
    if os.environ.get("FOERDER_TRUST_PROXY") == "1":
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.middleware("http")
async def guard(request: Request, call_next):
    pfad = request.url.path
    if pfad.startswith("/static/"):
        return await call_next(request)
    key = (request.method, pfad)
    if key not in PUBLIC:
        # Default-Deny: Admin-Token erforderlich.
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
            return JSONResponse({"detail": "nicht autorisiert"}, status_code=401)
    elif key in OEFFENTLICH_SCHREIBEN:
        # Rate-Limit nur auf den oeffentlichen Schreibpfaden.
        ip = _client_ip(request)
        now = time.monotonic()
        q = _hits[ip]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return JSONResponse({"detail": "zu viele Anfragen"}, status_code=429)
        q.append(now)
    return await call_next(request)


@app.get("/info")
def info():
    return {"message": "FoerderRadar API v0.1.0"}


@app.get("/")
def startseite(request: Request):
    return _render(request, "start.html")


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


def _speichere_profil(p: ProfilIn) -> str:
    """Validiert und speichert ein Profil (pseudonym + Kontakt getrennt)."""
    if p.typ not in ("betrieb", "privat"):
        raise HTTPException(status_code=400, detail="typ muss 'betrieb' oder 'privat' sein")
    if not p.einwilligung:
        raise HTTPException(status_code=400, detail="Einwilligung erforderlich")
    if p.kanal not in (None, "email", "sms"):
        raise HTTPException(status_code=400, detail="kanal muss 'email' oder 'sms' sein")
    if p.email and not EMAIL_RE.fullmatch(p.email):
        raise HTTPException(status_code=400, detail="Ungueltige E-Mail-Adresse.")
    # Kanal 'email' verlangt eine Adresse; 'sms' eine Telefonnummer.
    if p.kanal == "email" and not p.email:
        raise HTTPException(status_code=400, detail="Fuer den Kanal 'email' wird eine E-Mail-Adresse benoetigt.")
    if p.kanal == "sms" and not p.telefon:
        raise HTTPException(status_code=400, detail="Fuer den Kanal 'sms' wird eine Telefonnummer benoetigt.")

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
             # Anzeige-Labels -> kanonische Katalog-Slugs (sonst kein Treffer)
             vok.normalisiere_wohnsituation(p.wohnsituation), p.haushaltsgroesse,
             p.einkommen_spanne, vok.normalisiere_heizung(p.heizung),
             p.pflegestufe, p.familienstand, p.kinder_im_haushalt,
             vok.normalisiere_vorhaben(p.vorhaben)),
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
    # Rueckgabe enthaelt nur die kunde_id - keine Kontaktdaten.
    return str(kunde_id)


@app.post("/profile")
def create_profile(p: ProfilIn):
    # Antwort enthaelt nur die kunde_id - keine Kontaktdaten.
    return {"kunde_id": _speichere_profil(p)}


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


# ---------------------------------------------------------------- Website

def _ja_nein(wert):
    w = (wert or "").strip().lower()
    if w in ("ja", "true", "1", "on"):
        return True
    if w in ("nein", "false", "0"):
        return False
    return None


def _maske_email(email):
    """max@beispiel.at -> m**@beispiel.at (nur Maskierung fuer die Anzeige)."""
    if not email or "@" not in email:
        return ""
    lokal, _, domain = email.partition("@")
    if not lokal:
        return email
    return lokal[0] + "*" * (len(lokal) - 1) + "@" + domain


def _profil_aus_formular(form) -> ProfilIn:
    typ = (form.get("typ") or "betrieb").strip()
    privat = typ == "privat"
    region = form.get("region_grob_p") if privat else form.get("region_grob")
    pf = (form.get("pflegestufe") or "").strip()
    return ProfilIn(
        typ=typ,
        region_grob=(region or None),
        branche=None if privat else (form.get("branche") or None),
        mitarbeiterklasse=None if privat else (form.get("mitarbeiterklasse") or None),
        wko_mitglied=None if privat else _ja_nein(form.get("wko_mitglied")),
        wohnsituation=(form.get("wohnsituation") or None) if privat else None,
        haushaltsgroesse=(form.get("haushaltsgroesse") or None) if privat else None,
        einkommen_spanne=(form.get("einkommen_spanne") or None) if privat else None,
        heizung=(form.get("heizung") or None) if privat else None,
        pflegestufe=(int(pf) if pf.isdigit() else None) if privat else None,
        familienstand=(form.get("familienstand") or None) if privat else None,
        kinder_im_haushalt=_ja_nein(form.get("kinder_im_haushalt")) if privat else None,
        vorhaben=list(form.getlist("vorhaben")),
        name=(form.get("name") or "").strip() or None,
        email=(form.get("email") or "").strip() or None,
        telefon=(form.get("telefon") or "").strip() or None,
        kanal=(form.get("kanal") or None),
        einwilligung=(form.get("einwilligung") == "ja"),
    )


def _werte_aus_formular(form):
    werte = dict(form)
    werte["vorhaben"] = list(form.getlist("vorhaben"))
    return werte


@app.get("/formular")
def formular(request: Request, typ: str = "betrieb"):
    return _render(request, "formular.html",
                   _formular_kontext(typ=("privat" if typ == "privat" else "betrieb")))


@app.post("/formular")
async def formular_post(request: Request):
    form = await request.form()
    p = _profil_aus_formular(form)
    werte = _werte_aus_formular(form)

    def _zurueck(fehler):
        return _render(request, "formular.html",
                       _formular_kontext(werte=werte, fehler=fehler, typ=p.typ),
                       status_code=400)

    if not p.name or not p.email:
        return _zurueck("Bitte Name und E-Mail angeben.")
    if not p.einwilligung:
        return _zurueck("Ohne Einwilligung koennen wir Ihre Angaben nicht verarbeiten.")
    try:
        _speichere_profil(p)
    except HTTPException as e:
        return _zurueck(str(e.detail))

    vorname = (p.name or "").split(" ")[0]
    ziel = "/danke?" + urlencode({"n": vorname, "e": _maske_email(p.email)})
    return RedirectResponse(ziel, status_code=303)


@app.get("/danke")
def danke(request: Request, n: str = "", e: str = ""):
    return _render(request, "danke.html", {"vorname": n, "email_maskiert": e})


@app.get("/impressum")
def impressum(request: Request):
    return _render(request, "impressum.html")


@app.get("/datenschutz")
def datenschutz(request: Request):
    return _render(request, "datenschutz.html")
