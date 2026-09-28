#!/usr/bin/env python3
"""Tests: 'Stale gesendet' blockiert keine neuen Entwuerfe (Code-Review, Befund 1).

Hintergrund: offener_entwurf() (und der interne Guard in entwurf_speichern())
filterten faelschlich auch auf status='gesendet'. Ein bereits abgeschlossener
Versand hat dadurch JEDEN neuen Treffer fuer denselben Kunden dauerhaft
blockiert - der Worker legte nie wieder einen Entwurf an.

Fix: beide Guards pruefen nur noch auf offene Datensaetze
(status IN ('entwurf','sendet')), passend zum UNIQUE INDEX
versand_ein_offener (db/init.sql).

Prueft am LIVE-Schema (isolierte Testzeilen, danach geloescht):
- Nach einem versand-Datensatz mit status='gesendet' liefert offener_entwurf()
  None (kein Blocker mehr).
- entwurf_speichern() legt danach trotzdem einen neuen Entwurf an (neuer
  Treffer nach abgeschlossenem Versand wird NICHT mehr ignoriert).
- Der alte 'gesendet'-Datensatz bleibt unveraendert erhalten.

Lauf:  python3 tests/test_versand_stale_gesendet.py
"""
import os
import sys
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import psycopg  # noqa: E402

from app.main import _lade_env_datei  # noqa: E402
from src import versand_service as vs  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {name}")
    else:
        fail += 1
        print(f"  FAIL {name}")


_lade_env_datei()
url = os.environ.get("DATABASE_URL_ADMIN") or os.environ["DATABASE_URL"]

kunde_id = str(uuid.uuid4())
with psycopg.connect(url, connect_timeout=5) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO profil (kunde_id, typ, region_grob, wohnsituation, vorhaben) "
            "VALUES (%s,'privat','Oberoesterreich','eigenheim',ARRAY['pv'])",
            (kunde_id,),
        )
    conn.commit()

    # Simuliert einen abgeschlossenen Versand aus einem frueheren Match-Lauf.
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO versand (kunde_id, kanal, betreff, body, status) "
            "VALUES (%s,'email','Alter Betreff','Alter Body','gesendet') RETURNING id",
            (kunde_id,),
        )
        alt_id = cur.fetchone()[0]
    conn.commit()

    offen = vs.offener_entwurf(conn, kunde_id)
    check("offener_entwurf() ignoriert 'gesendet' (kein Blocker mehr)", offen is None)

    # Neuer Treffer nach abgeschlossenem Versand -> muss einen neuen Entwurf ergeben.
    vid = vs.entwurf_speichern(conn, kunde_id, "Neuer Betreff", "Neuer Body", "email")
    check("entwurf_speichern() legt trotz 'gesendet'-Historie neuen Entwurf an",
          vid is not None)

    if vid is not None:
        entwuerfe = {e["id"]: e for e in vs.offene_entwuerfe(conn)}
        check("neuer Entwurf steht in offene_entwuerfe()", vid in entwuerfe)

    with conn.cursor() as cur:
        cur.execute("SELECT status, betreff, body FROM versand WHERE id=%s", (alt_id,))
        r = cur.fetchone()
    check("alter 'gesendet'-Datensatz bleibt unveraendert",
          r == ("gesendet", "Alter Betreff", "Alter Body"))

    # Zweiter offener Entwurf gleichzeitig darf laut UNIQUE INDEX nicht entstehen.
    vid2 = vs.entwurf_speichern(conn, kunde_id, "Noch ein Betreff", "Noch ein Body", "email")
    check("zweiter gleichzeitig offener Entwurf wird verhindert (UNIQUE INDEX)",
          vid2 is None)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM profil WHERE kunde_id=%s", (kunde_id,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM versand WHERE kunde_id=%s", (kunde_id,))
        check("Cleanup: Testzeilen entfernt (CASCADE)", cur.fetchone() is None)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
