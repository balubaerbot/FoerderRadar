"""FoerderRadar API - Phase 1 (Skelett).

Sicherheit: Default-Deny. Ohne Token zugaenglich sind nur die Routen in
PUBLIC (Info, Formularseiten; schreibende Pfade sind Intake-Gates unterworfen).
/health und alle sonstigen geschuetzten Endpunkte erfordern den Admin-Token:
  Header:  Authorization: Bearer <FOERDER_ADMIN_TOKEN>

Trennung: `profil` = pseudonym (Agent darf lesen), `kontakt` = Klartext
(nur Versand-Worker). Der Agent sieht Kontaktdaten NIE.
"""
import hmac
import ipaddress
import logging
import os
import re
import sys
import time
import unicodedata
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
from pydantic import BaseModel, Field
from typing import Optional

# Projekt-Root auf den Importpfad, damit `src.*` importierbar ist
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import ki_mapping as ki  # noqa: E402
from src import matching_service as ms  # noqa: E402
from src import region as regionmod  # noqa: E402
from src import vokabular as vok  # noqa: E402

# Anmelde-Spam: Domains, die nachweislich automatisiert angemeldet wurden.
# Erweiterbar ohne Code-Aenderung ueber FOERDER_BLOCKED_EMAIL_DOMAINS (kommagetrennt).
BLOCKED_EMAIL_DOMAINS = frozenset({"fldubai.com"})
# Verstecktes Formularfeld (Honeypot): Menschen sehen es nicht, Bots fuellen es aus.
# Bewusst kein Name wie "website"/"url": Passwortmanager und Autofill fuellen die gern aus.
HONEYPOT_FELD = "kontakt_ref"

_spam_log = logging.getLogger("foerder.spam")


def _norm_domain(d):
    """Domain vergleichbar machen: NFKC, ohne Zero-Width-Zeichen, Kleinschreibung,
    ohne Port/Klammern/fuehrende '@*.'/Trailing-Dot, IDNA (Punycode)."""
    d = unicodedata.normalize("NFKC", str(d or ""))
    d = "".join(c for c in d if unicodedata.category(c) != "Cf")
    d = re.sub(r":\d+$", "", d.strip().lower())
    d = d.strip("[] ").lstrip("@*.").rstrip(".")
    try:
        d = d.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return d


def _gesperrte_domains():
    extra = os.environ.get("FOERDER_BLOCKED_EMAIL_DOMAINS", "")
    eintraege = {_norm_domain(d) for d in extra.split(",")}
    return (BLOCKED_EMAIL_DOMAINS | eintraege) - {""}


def _email_domain_gesperrt(email):
    if not email or "@" not in email:
        return False
    domain = _norm_domain(email.rsplit("@", 1)[1])
    if not domain:
        return False
    gesperrt = _gesperrte_domains()
    return domain in gesperrt or any(domain.endswith("." + d) for d in gesperrt)


def _spam_grund(form, email):
    """'honeypot' | 'domain' | None. Ein Nicht-Text-Wert (z. B. Datei-Upload) im Honeypot zaehlt als Treffer."""
    wert = form.get(HONEYPOT_FELD)
    if wert is not None and (not isinstance(wert, str) or wert.strip()):
        return "honeypot"
    if _email_domain_gesperrt(email):
        return "domain"
    return None


def _lade_env_datei():
    """Laedt die gemountete `.env`, ausser in explizit isolierten Tests.

    Grund: `docker restart` liest `env_file` NICHT neu. Damit neu gesetzte Werte
    (z.B. das eingeschraenkte `DATABASE_URL` = app_web) nach einem normalen Neustart
    ankommen, gilt fuer dieses Projekt die `.env` als Quelle der Wahrheit.
    """
    if os.environ.get("FOERDER_TESTING") == "1":
        return
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

APP_VERSION = "1.3.0-alpha"
app = FastAPI(title="FoerderRadar API", version=APP_VERSION)


def _intake_freigegeben() -> bool:
    """Fail closed until privacy and retention requirements are approved."""
    if os.environ.get("FOERDER_INTAKE_ENABLED") != "1":
        return False
    if os.environ.get("FOERDER_PRIVACY_REVIEWED") != "1":
        return False
    if os.environ.get("FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED") != "1":
        return False
    if os.environ.get("FOERDER_WITHDRAWAL_PROCESS_CONFIRMED") != "1":
        return False
    if os.environ.get("FOERDER_RETENTION_SCHEMA_VERIFIED") != "1":
        return False
    if os.environ.get("FOERDER_PURGE_SCHEDULE_VERIFIED") != "1":
        return False
    # Legacy rows can have NULL deadlines; do not accept new data until an
    # operator has reviewed and resolved them under an approved policy.
    if os.environ.get("FOERDER_LEGACY_RETENTION_REVIEWED") != "1":
        return False
    if not os.environ.get("FOERDER_DATA_CONTROLLER", "").strip():
        return False
    if not os.environ.get("FOERDER_PRIVACY_CONTACT", "").strip():
        return False
    if not os.environ.get("FOERDER_CONSENT_VERSION", "").strip():
        return False
    # Betreiberregel: regulär nach zwei Jahren löschen; verifizierte
    # Kundenanfragen zur Löschung gelten unabhängig vom Datensatzalter.
    return True


def _pruefe_intake_freigabe() -> None:
    if not _intake_freigegeben():
        raise HTTPException(
            status_code=503,
            detail="Die Datenerfassung ist derzeit deaktiviert.",
            headers={"Retry-After": "3600"},
        )

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASIS, "app", "templates"))
templates.env.globals["honeypot_feld"] = HONEYPOT_FELD
app.mount("/static", StaticFiles(directory=os.path.join(BASIS, "app", "static")), name="static")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_TOKEN = os.environ.get("FOERDER_ADMIN_TOKEN", "")

# Oeffentliche Routen. Alles andere ist default-deny -> Token noetig.
PUBLIC = {
    ("GET", "/"), ("GET", "/info"), ("POST", "/profile"),
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
# Drittes Standbein "Sozial & Alltag" (datenseitig: typ='privat' + thema enthaelt 'sozial').
LEBENSSITUATIONEN = ["Pflege eines Angehörigen", "Geringes Einkommen / Arbeitssuchend",
                     "Behinderung / Beeinträchtigung", "Alleinerziehend",
                     "Familie mit Kindern", "Pension"]
# Jede Option ist an mindestens eine reale Beihilfe im Katalog gekoppelt
# (kein Chip ohne Trefferquelle).
BEDARF_OPTIONEN = ["Heizkostenzuschuss", "Wohnbeihilfe", "Pflege & Betreuung",
                   "Mindestsicherung / Sozialhilfe", "Familien- & Schulbeihilfe",
                   "Behinderung & Rehabilitation", "Barrierefreies Wohnen"]

# Optionen mit Gesundheitsbezug (Art. 9 DSGVO): nur mit gesonderter Einwilligung.
GESUNDHEITS_LEBENSSITUATIONEN = {"Pflege eines Angehörigen", "Behinderung / Beeinträchtigung"}
GESUNDHEITS_BEDARF = {"Pflege & Betreuung", "Behinderung & Rehabilitation", "Barrierefreies Wohnen"}


def _hat_gesundheitsangaben(pflegestufe, behinderung, lebenssituation, vorhaben):
    return (
        pflegestufe is not None
        or behinderung is not None
        or lebenssituation in GESUNDHEITS_LEBENSSITUATIONEN
        or any(v in GESUNDHEITS_BEDARF for v in (vorhaben or []))
    )


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
        "lebenssituationen": LEBENSSITUATIONEN, "bedarf_optionen": BEDARF_OPTIONEN,
        "gesundheits_lebenssituationen": GESUNDHEITS_LEBENSSITUATIONEN, "gesundheits_bedarf": GESUNDHEITS_BEDARF,
    }


def db():
    return psycopg.connect(DATABASE_URL, connect_timeout=5)


_STANDARD_PROXIES = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


def _lade_proxy_netze():
    """FOERDER_TRUSTED_PROXIES (kommagetrennt, IP oder CIDR) schraenkt das Vertrauen ein,
    z. B. auf das Docker-Gateway (172.18.0.1). Ungueltige Eintraege werden ignoriert."""
    roh = os.environ.get("FOERDER_TRUSTED_PROXIES") or _STANDARD_PROXIES
    netze = []
    for eintrag in roh.split(","):
        try:
            netze.append(ipaddress.ip_network(eintrag.strip(), strict=False))
        except ValueError:
            continue
    return netze


_PROXY_NETZE = _lade_proxy_netze()


def _normalisiere_ip(host):
    """IPv4-mapped IPv6 (::ffff:a.b.c.d) -> IPv4; sonst unveraendert. None bei Muell."""
    try:
        a = ipaddress.ip_address(host)
    except ValueError:
        return None
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a


def _vertrauenswuerdiger_proxy(host):
    """True nur fuer Loopback/private Adressen (nginx auf dem Host bzw. Docker-Gateway)."""
    ip = _normalisiere_ip(host)
    if ip is None:
        return False
    return any(ip.version == n.version and ip in n for n in _PROXY_NETZE)


def _client_ip(request):
    """Client-IP fuer das Rate-Limit.

    X-Real-IP wird nur ausgewertet, wenn die direkte Gegenstelle ein vertrauens-
    wuerdiger Proxy ist (Loopback/privates Netz: nginx ueberschreibt den Header
    immer mit $remote_addr; der Container-Port ist nur an 127.0.0.1 gebunden).
    Bei anderen Gegenstellen zaehlt allein die Socket-Adresse. IPv6 wird auf das
    /64-Praefix zusammengefasst, damit Adresswechsel innerhalb eines Anschlusses
    das Limit nicht umgehen.
    """
    peer = request.client.host if request.client else "?"
    ip = peer
    if _vertrauenswuerdiger_proxy(peer):
        real = _normalisiere_ip(request.headers.get("x-real-ip", "").strip())
        if real is not None:
            ip = str(real)
    a = _normalisiere_ip(ip)
    if a is None:
        return ip
    if a.version == 6:
        return str(ipaddress.ip_network(f"{a}/64", strict=False))
    return str(a)


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
    global _letzter_cleanup
    now = time.monotonic()
    if len(_hits) > 5000 and now - _letzter_cleanup > RATE_WINDOW:
        _letzter_cleanup = now
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > RATE_WINDOW]:
            _hits.pop(k, None)
    return await call_next(request)


_letzter_cleanup = 0.0

SICHERHEITSHEADER = {
    "Strict-Transport-Security": "max-age=31536000",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def sicherheitsheader(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001 - nie Details an den Client
        logging.getLogger("foerderradar").exception("Unbehandelter Fehler")
        response = JSONResponse({"detail": "Interner Fehler."}, status_code=500)
    for k, v in SICHERHEITSHEADER.items():
        if k not in response.headers:
            response.headers[k] = v
    return response


@app.get("/info")
def info():
    return {"message": "FoerderRadar API v0.1.0"}


_MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"]


def _katalog_stand_text():
    """Katalog-Stand fuer die Startseite, z. B. '5. November 2026'.

    Liest meta.stand aus dem Katalog; faellt bei jedem Problem auf None zurueck,
    damit die Startseite nie an einer Katalog-Panne scheitert.
    """
    try:
        stand = ms.load_katalog()["meta"]["stand"]
        jahr, monat, tag = (int(x) for x in stand.split("-"))
        return f"{tag}. {_MONATE[monat - 1]} {jahr}"
    except Exception:
        return None


@app.get("/")
def startseite(request: Request):
    return _render(request, "start.html", {"katalog_stand": _katalog_stand_text()})


@app.get("/health")
def health():
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            ok = cur.fetchone()[0] == 1
        return {"status": "ok" if ok else "degraded"}
    except Exception:  # noqa: BLE001 - Details bleiben serverseitig.
        return {"status": "degraded"}


class ProfilIn(BaseModel):
    typ: str  # betrieb | privat | sozial
    region_grob: Optional[str] = None
    branche: Optional[str] = None
    mitarbeiterklasse: Optional[str] = None
    wko_mitglied: Optional[bool] = None
    wohnsituation: Optional[str] = None
    haushaltsgroesse: Optional[str] = None
    einkommen_spanne: Optional[str] = None
    heizung: Optional[str] = None
    pflegestufe: Optional[int] = Field(None, ge=0, le=7)
    behinderung: Optional[bool] = None   # Bedarfs-Trigger (Behinderung/Beeintraechtigung)
    familienstand: Optional[str] = None
    kinder_im_haushalt: Optional[bool] = None
    # Nur Standbein "Sozial & Alltag" (typ wird dabei datenseitig zu 'privat')
    lebenssituation: Optional[str] = None
    vorhaben: list[str] = []
    # Freitext "Anliegen" (optional). Wird per LLM in die grobe Achse uebersetzt
    # (fail-soft: ohne Key/bei Fehler bleibt die Chips-Heuristik).
    anliegen: Optional[str] = None
    # Kontaktdaten (getrennt gespeichert)
    name: Optional[str] = None
    email: Optional[str] = None
    telefon: Optional[str] = None
    kanal: Optional[str] = None  # email only; sms is not implemented
    # Einwilligung zur Datenverarbeitung (Pflicht)
    einwilligung: bool = False
    besondere_daten_einwilligung: bool = False


MAX_FELD = 200
MAX_ANLIEGEN = 2000
MAX_VORHABEN = 20
MAX_VORHABEN_LAENGE = 100


def _pruefe_laengen(p: ProfilIn):
    """Begrenzt Feldlaengen (Speicher-/LLM-Missbrauch ueber den oeffentlichen Schreibpfad)."""
    zu_lang = HTTPException(status_code=400, detail="Eingabe zu lang oder ungueltig.")
    for name, wert in vars(p).items():
        if name == "vorhaben":
            if len(wert) > MAX_VORHABEN or any(
                not isinstance(v, str) or len(v) > MAX_VORHABEN_LAENGE or "\x00" in v for v in wert
            ):
                raise zu_lang
        elif isinstance(wert, str):
            if len(wert) > (MAX_ANLIEGEN if name == "anliegen" else MAX_FELD) or "\x00" in wert:
                raise zu_lang


def _speichere_profil(p: ProfilIn) -> str:
    """Validiert und speichert ein Profil (pseudonym + Kontakt getrennt)."""
    _pruefe_intake_freigabe()
    _pruefe_laengen(p)
    if p.typ not in ("betrieb", "privat", "sozial"):
        raise HTTPException(status_code=400, detail="typ muss 'betrieb', 'privat' oder 'sozial' sein")
    if not p.einwilligung:
        raise HTTPException(status_code=400, detail="Einwilligung erforderlich")
    if _hat_gesundheitsangaben(p.pflegestufe, p.behinderung, p.lebenssituation, p.vorhaben) and not p.besondere_daten_einwilligung:
        raise HTTPException(
            status_code=400,
            detail="Für Pflege-/Behinderungsangaben ist eine gesonderte ausdrückliche Einwilligung erforderlich.",
        )
    if p.kanal not in (None, "email"):
        raise HTTPException(status_code=400, detail="SMS-Versand ist derzeit nicht verfügbar")
    if p.email and not EMAIL_RE.fullmatch(p.email):
        raise HTTPException(status_code=400, detail="Ungueltige E-Mail-Adresse.")
    if _email_domain_gesperrt(p.email):
        # Bewusst dieselbe Meldung wie bei ungueltigem Format: kein Orakel fuer die Sperrliste.
        _spam_log.info("signup_discarded reason=domain via=api")
        raise HTTPException(status_code=400, detail="Ungueltige E-Mail-Adresse.")
    # Der Versand unterstützt derzeit ausschließlich E-Mail.
    if p.kanal == "email" and not p.email:
        raise HTTPException(status_code=400, detail="Fuer den Kanal 'email' wird eine E-Mail-Adresse benoetigt.")

    # Freitext begrenzen (Kosten-/Missbrauchsschutz) und Thema-Achse ableiten.
    anliegen = (p.anliegen or "").strip()[: ki.MAX_ZEICHEN] or None
    vorhaben = vok.normalisiere_vorhaben(p.vorhaben)
    # Chips-Heuristik + optionales KI-Mapping. Das Ergebnis wird EINMAL gespeichert
    # (reproduzierbar), nicht bei jedem Matching-Lauf neu erfragt.
    thema = ki.thema_fuer(vorhaben, anliegen=anliegen, typ=p.typ)

    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO profil (typ, region_grob, branche, mitarbeiterklasse, wko_mitglied,
                wohnsituation, haushaltsgroesse, einkommen_spanne, heizung, pflegestufe,
                behinderung, familienstand, kinder_im_haushalt, lebenssituation, vorhaben,
                anliegen, thema)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING kunde_id
            """,
            (p.typ, regionmod.normalisiere_region(p.region_grob) or p.region_grob,
             p.branche, p.mitarbeiterklasse, p.wko_mitglied,
             # Anzeige-Labels -> kanonische Katalog-Slugs (sonst kein Treffer)
             vok.normalisiere_wohnsituation(p.wohnsituation), p.haushaltsgroesse,
             p.einkommen_spanne, vok.normalisiere_heizung(p.heizung),
             p.pflegestufe, p.behinderung, p.familienstand, p.kinder_im_haushalt,
             p.lebenssituation, vorhaben, anliegen, thema),
        )
        kunde_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO kontakt (kunde_id, name, email, telefon, kanal, einwilligung_am,
                einwilligung_version, einwilligung_besondere_daten, loeschdatum)
            VALUES (%s,%s,%s,%s,%s, now(), %s, %s, (CURRENT_DATE + INTERVAL '2 years')::date)
            """,
            (kunde_id, p.name, p.email, p.telefon, p.kanal,
             os.environ["FOERDER_CONSENT_VERSION"].strip(),
             p.besondere_daten_einwilligung),
        )
        conn.commit()
    # Rueckgabe enthaelt nur die kunde_id - keine Kontaktdaten.
    return str(kunde_id)


@app.post("/profile")
def create_profile(p: ProfilIn):
    _pruefe_intake_freigabe()
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
    # Standbein "Sozial & Alltag": UI-typ "sozial" wird jetzt als echter
    # typ-Wert gespeichert (DB-Constraint erlaubt 'sozial'); thema bekommt
    # zusaetzlich das grobe Topic-Tag 'sozial' fuer die Thema-Achse.
    typ_roh = (form.get("typ") or "betrieb").strip()
    sozial = typ_roh == "sozial"
    privat = typ_roh == "privat" or sozial
    typ = typ_roh
    if sozial:
        region = form.get("region_grob_s")
    elif privat:
        region = form.get("region_grob_p")
    else:
        region = form.get("region_grob")
    # Diese Angaben werden ausschließlich bei einer ausdrücklich gewählten
    # Sozial-/Alltags-Suche akzeptiert, auch wenn ein Client Felder mitsendet,
    # die im UI verborgen waren.
    besondere_daten_ok = sozial and form.get("besondere_daten_einwilligung") == "ja"
    pf = (form.get("pflegestufe") or "").strip() if besondere_daten_ok else ""
    # Bedarf-Chips (nur Sozial) zaehlen wie Vorhaben zur Thema-Achse; die
    # explizite Standbein-Wahl erzwingt zusaetzlich das grobe Thema 'sozial'.
    vorhaben = list(form.getlist("vorhaben")) + list(form.getlist("bedarf"))
    lebenssituation = (form.get("lebenssituation") or None) if sozial else None
    if not besondere_daten_ok:
        # Ohne gesonderte Einwilligung werden Optionen mit Gesundheitsbezug verworfen.
        vorhaben = [v for v in vorhaben if v not in GESUNDHEITS_BEDARF]
        if lebenssituation in GESUNDHEITS_LEBENSSITUATIONEN:
            lebenssituation = None
    if sozial and "sozial" not in vorhaben:
        vorhaben.append("sozial")
    return ProfilIn(
        typ=typ,
        region_grob=(region or None),
        branche=None if privat else (form.get("branche") or None),
        mitarbeiterklasse=None if privat else (form.get("mitarbeiterklasse") or None),
        wko_mitglied=None if privat else _ja_nein(form.get("wko_mitglied")),
        wohnsituation=(form.get("wohnsituation") or None) if (privat and not sozial) else None,
        haushaltsgroesse=((form.get("haushaltsgroesse_s") if sozial
                           else form.get("haushaltsgroesse")) or None) if privat else None,
        einkommen_spanne=((form.get("einkommen_spanne_s") if sozial
                           else form.get("einkommen_spanne")) or None) if privat else None,
        heizung=(form.get("heizung") or None) if (privat and not sozial) else None,
        pflegestufe=(int(pf) if re.fullmatch(r"[0-7]", pf) else None) if besondere_daten_ok else None,
        behinderung=_ja_nein(form.get("behinderung")) if besondere_daten_ok else None,
        familienstand=(form.get("familienstand") or None) if (privat and not sozial) else None,
        kinder_im_haushalt=_ja_nein(form.get("kinder_im_haushalt")) if (privat and not sozial) else None,
        lebenssituation=lebenssituation,
        vorhaben=vorhaben,
        anliegen=((form.get("anliegen") or "").strip() or None),
        name=(form.get("name") or "").strip() or None,
        email=(form.get("email") or "").strip() or None,
        telefon=(form.get("telefon") or "").strip() or None,
        kanal=(form.get("kanal") or None),
        einwilligung=(form.get("einwilligung") == "ja"),
        besondere_daten_einwilligung=besondere_daten_ok,
    )


def _werte_aus_formular(form):
    werte = dict(form)
    werte["vorhaben"] = list(form.getlist("vorhaben"))
    werte["bedarf"] = list(form.getlist("bedarf"))
    return werte


@app.get("/formular")
def formular(request: Request, typ: str = "betrieb"):
    _pruefe_intake_freigabe()
    typ = typ if typ in ("betrieb", "privat", "sozial") else "betrieb"
    return _render(request, "formular.html", _formular_kontext(typ=typ))


@app.post("/formular")
async def formular_post(request: Request):
    _pruefe_intake_freigabe()
    form = await request.form()
    p = _profil_aus_formular(form)
    if p.typ != "sozial":
        p.pflegestufe = None
        p.behinderung = None
    werte = _werte_aus_formular(form)
    if p.typ != "sozial":
        werte["pflegestufe"] = ""
        werte["behinderung"] = ""
    # Fuer Re-Rendering bei Fehlern: typ_anzeige spiegelt den vom Nutzer
    # gewaehlten Tab (identisch zu p.typ, seit 'sozial' ein echter Wert ist).
    typ_anzeige = (form.get("typ") or "betrieb").strip()
    if typ_anzeige not in ("betrieb", "privat", "sozial"):
        typ_anzeige = "betrieb"

    def _zurueck(fehler):
        return _render(request, "formular.html",
                       _formular_kontext(werte=werte, fehler=fehler, typ=typ_anzeige),
                       status_code=400)

    if not p.name or not p.email:
        return _zurueck("Bitte Name und E-Mail angeben.")
    if not p.einwilligung:
        return _zurueck("Ohne Einwilligung koennen wir Ihre Angaben nicht verarbeiten.")
    if p.region_grob not in BUNDESLAENDER:
        return _zurueck("Bitte ein Bundesland auswaehlen.")
    # Bot-Abwehr erst nach den Pflichtfeld-Pruefungen: Spam- und Normalpfad antworten
    # bei ungueltigen Eingaben identisch (kein Orakel). Nichts speichern, aber die normale
    # Danke-Seite zeigen. Geloggt wird nur der Grund, keine personenbezogenen Daten.
    grund = _spam_grund(form, p.email)
    if grund:
        _spam_log.info("signup_discarded reason=%s via=form", grund)
        vorname = (p.name or "").split(" ")[0]
        return RedirectResponse("/danke?" + urlencode({"n": vorname, "e": _maske_email(p.email)}), status_code=303)
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
