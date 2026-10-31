#!/usr/bin/env python3
"""Widerrufe aus dem Betreiberpostfach verarbeiten (Mail -> Loeschung).

Ablauf je Mail im Posteingang (und Junk) mit "Widerruf" im Betreff:
  1. Echtheit pruefen: oberster Authentication-Results-Header des eigenen
     Eingangsservers (Hostinger) muss dmarc=pass fuer genau die Domain der
     Absenderadresse melden. Sonst: nichts loeschen, Betreiber meldet sich.
  2. Loeschen ueber public.withdraw_by_email() (Rolle app_retention): alle
     Profile, deren Kontaktadresse der Absenderadresse entspricht, inkl.
     Kontakt, Treffer, Versand (Cascade). Audit nur mit UUID.
  3. Bestaetigung an den Absender, Mail als beantwortet markieren.

Bereits verarbeitete Mails werden ueber einen Hash der Message-ID erkannt
(Statusdatei, keine Kontaktdaten). Alle Ausgaben sind maskiert.
Standard ist Dry-Run; geloescht/versendet wird nur mit --apply.
Benoetigt DATABASE_URL_RETENTION; laedt keine .env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.versand_service import absender, absender_name, maskiere_email  # noqa: E402

LIVE_DB_NAME = "foerderradar"
# Eindeutig: Betreff BEGINNT (nach Re:/AW:/Fwd:) mit "Widerruf..." - so wie der
# Abbestell-Link ihn setzt. "widerruf" irgendwo sonst (z. B. "Frage zum Widerruf")
# wird nicht geloescht, sondern zur manuellen Pruefung gemeldet.
PRAEFIX_RE = re.compile(r"^\s*((re|aw|wg|fw|fwd|antwort)\s*:\s*)*", re.IGNORECASE)
BETREFF_RE = re.compile(r"^widerruf\w*\b", re.IGNORECASE)
ERWAEHNT_RE = re.compile(r"widerruf", re.IGNORECASE)
AUTHSERV_RE = re.compile(
    os.environ.get("FOERDER_AUTHSERV_PATTERN", r"^[a-z0-9.-]+\.hostinger\.io$"), re.IGNORECASE
)
STATE_DEFAULT = Path(
    os.environ.get("FOERDER_WIDERRUF_STATE", str(Path.home() / ".local/state/foerderradar/widerruf_verarbeitet.txt"))
)
POSTFAECHER = [m.strip() for m in os.environ.get("FOERDER_WIDERRUF_MAILBOXES", "INBOX,INBOX.Junk").split(",") if m.strip()]

TEXT_GELOESCHT = (
    "Guten Tag,\n\n"
    "Ihren Widerruf haben wir erhalten. Ihre bei Fördora gespeicherten Daten "
    "(Profil, Kontaktdaten, gefundene Förderungen) wurden gelöscht. "
    "Sie erhalten von uns keine weiteren Nachrichten.\n\n"
    "Mit freundlichen Grüßen\nFördora\n"
)
TEXT_KEINE_DATEN = (
    "Guten Tag,\n\n"
    "Ihren Widerruf haben wir erhalten. Zu dieser E-Mail-Adresse sind bei Fördora "
    "keine Daten gespeichert. Falls Sie Fördora mit einer anderen Adresse genutzt "
    "haben, senden Sie den Widerruf bitte von dieser Adresse.\n\n"
    "Mit freundlichen Grüßen\nFördora\n"
)


# --------------------------------------------------------------------------
# Reine Pruefungen (unit-getestet)

def betreff_art(betreff: str | None) -> str | None:
    """"widerruf" (eindeutig), "unklar" (erwaehnt Widerruf) oder None."""
    if not betreff:
        return None
    rest = PRAEFIX_RE.sub("", betreff).strip()
    if BETREFF_RE.match(rest):
        return "widerruf"
    return "unklar" if ERWAEHNT_RE.search(betreff) else None


def ist_widerruf(betreff: str | None) -> bool:
    return betreff_art(betreff) == "widerruf"


def absender_adresse(msg) -> str | None:
    """Genau eine syntaktisch plausible From-Adresse, sonst None."""
    werte = msg.get_all("From") or []
    if len(werte) != 1:
        return None
    _, addr = parseaddr(str(werte[0]))
    addr = addr.strip().lower()
    if addr.count("@") != 1 or not re.fullmatch(r"[^@\s<>]+@[a-z0-9.-]+\.[a-z]{2,}", addr):
        return None
    return addr


def echtheit_fehler(msg, addr: str) -> str | None:
    """None wenn echt, sonst kurzer Grund.

    Nur der oberste Authentication-Results-Header zaehlt: ihn setzt der eigene
    Eingangsserver; tiefer liegende kann ein Absender selbst mitschicken.
    """
    werte = msg.get_all("Authentication-Results") or []
    if not werte:
        return "kein Authentication-Results"
    oberster = " ".join(str(werte[0]).split())
    authserv = oberster.split(";", 1)[0].strip()
    if not AUTHSERV_RE.match(authserv):
        return "fremder Pruefserver"
    m = re.search(r"\bdmarc=(\w+)[^;]*?header\.from=([^\s;]+)", oberster, re.IGNORECASE)
    if not m:
        return "kein DMARC-Ergebnis"
    if m.group(1).lower() != "pass":
        return f"dmarc={m.group(1).lower()}"
    if m.group(2).lower().rstrip(".") != addr.rsplit("@", 1)[1]:
        return "DMARC-Domain passt nicht zum Absender"
    return None


def mail_schluessel(msg, raw: bytes) -> str:
    mid = str(msg.get("Message-ID") or "").strip()
    basis = mid.encode() if mid else raw
    return hashlib.sha256(basis).hexdigest()


def db_ziel_ok(url: str, db_name: str) -> bool:
    try:
        p = urlsplit(url)
        if p.scheme not in {"postgres", "postgresql"} or p.query or p.fragment:
            return False
        if not p.hostname or "," in (p.netloc or ""):
            return False
        return p.path.lstrip("/") == db_name
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Seiteneffekte

def _himalaya(*args, eingabe: str | None = None) -> subprocess.CompletedProcess:
    konto = os.environ.get("HIMALAYA_ACCOUNT", "foerdora")
    return subprocess.run(
        ["himalaya", "-a", konto, *args], input=eingabe, capture_output=True, timeout=90,
        text=eingabe is not None,
    )


def umschlaege(postfach: str) -> list[dict]:
    p = _himalaya("envelope", "list", "-m", postfach, "-s", "500", "--json")
    if p.returncode != 0:
        raise RuntimeError(f"Postfach {postfach} nicht lesbar")
    daten = json.loads(p.stdout)
    return daten.get("envelopes", []) if isinstance(daten, dict) else daten


def roh_lesen(postfach: str, mail_id: str) -> bytes:
    p = _himalaya("message", "read", "-m", postfach, "--raw", mail_id)
    if p.returncode != 0:
        raise RuntimeError(f"Mail {mail_id} nicht lesbar")
    return p.stdout


def als_beantwortet(postfach: str, mail_id: str) -> None:
    _himalaya("flag", "add", "-m", postfach, "--flag", "answered", mail_id)


def bestaetigung_senden(an: str, original_mid: str | None, geloescht: int) -> None:
    msg = EmailMessage()
    adresse = absender()
    msg["From"] = formataddr((absender_name(), adresse))
    msg["To"] = an
    msg["Subject"] = "Ihr Widerruf bei Fördora"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=adresse.rsplit("@", 1)[-1])
    if original_mid:
        msg["In-Reply-To"] = original_mid
        msg["References"] = original_mid
    msg.set_content(TEXT_GELOESCHT if geloescht else TEXT_KEINE_DATEN)
    p = _himalaya("message", "send", eingabe=msg.as_string())
    if p.returncode != 0:
        raise RuntimeError("Bestaetigung nicht versendet")


def db_verbinden(url: str, db_name: str):
    import psycopg

    conn = psycopg.connect(url, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        if cur.fetchone()[0] != db_name:
            conn.close()
            raise RuntimeError("verbundene Datenbank stimmt nicht")
    return conn


def widerrufen(conn, addr: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT public.withdraw_by_email(%s)", (addr,))
        n = cur.fetchone()[0]
    conn.commit()
    return int(n or 0)


def status_laden(pfad: Path) -> set[str]:
    try:
        return {z.strip() for z in pfad.read_text().splitlines() if z.strip()}
    except FileNotFoundError:
        return set()


def status_merken(pfad: Path, schluessel: str) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("a") as f:
        f.write(schluessel + "\n")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="wirklich loeschen, bestaetigen, merken")
    ap.add_argument("--db", default=LIVE_DB_NAME, help="erwarteter Datenbankname")
    ap.add_argument("--state", type=Path, default=STATE_DEFAULT)
    args = ap.parse_args()

    erledigt = status_laden(args.state)
    zeilen, fehler, pruefen = [], 0, 0
    conn = None
    try:
        for postfach in POSTFAECHER:
            for env in umschlaege(postfach):
                art = betreff_art(env.get("subject"))
                if art is None:
                    continue
                mail_id = str(env["id"])
                raw = roh_lesen(postfach, mail_id)
                msg = message_from_bytes(raw, policy=policy.default)
                schluessel = mail_schluessel(msg, raw)
                if schluessel in erledigt:
                    continue
                addr = absender_adresse(msg)
                if art == "unklar":
                    grund = "Betreff erwaehnt Widerruf, beginnt aber nicht damit"
                elif not addr:
                    grund = "Absender unklar"
                else:
                    grund = echtheit_fehler(msg, addr)
                maske = maskiere_email(addr) if addr else "?"
                if grund:
                    pruefen += 1
                    zeilen.append(f"MANUELL PRUEFEN [{postfach} #{mail_id}] {maske}: {grund} - nichts geloescht")
                    if args.apply:
                        status_merken(args.state, schluessel)
                    continue
                if not args.apply:
                    zeilen.append(f"DRY-RUN [{postfach} #{mail_id}] {maske}: wuerde loeschen + bestaetigen")
                    continue
                if conn is None:
                    url = os.environ.get("DATABASE_URL_RETENTION", "").strip()
                    if not url or not db_ziel_ok(url, args.db):
                        raise RuntimeError("DATABASE_URL_RETENTION fehlt oder zeigt nicht auf die erwartete DB")
                    conn = db_verbinden(url, args.db)
                n = widerrufen(conn, addr)
                status_merken(args.state, schluessel)
                erledigt.add(schluessel)
                try:
                    bestaetigung_senden(addr, msg.get("Message-ID"), n)
                    als_beantwortet(postfach, mail_id)
                    best = "bestaetigt"
                except Exception as exc:  # Loeschung steht, nur Bestaetigung fehlt
                    fehler += 1
                    best = f"BESTAETIGUNG FEHLGESCHLAGEN ({type(exc).__name__})"
                zeilen.append(f"GELOESCHT [{postfach} #{mail_id}] {maske}: {n} Profil(e), {best}")
    except Exception as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        fehler += 1
    finally:
        if conn is not None:
            conn.close()

    for z in zeilen:
        print(z)
    print(f"Widerrufe: {len(zeilen)} neu, {pruefen} manuell pruefen, {fehler} Fehler"
          + ("" if args.apply else " (Dry-Run, nichts geaendert)"))
    if fehler:
        return 1
    return 3 if pruefen else 0


if __name__ == "__main__":
    sys.exit(main())
