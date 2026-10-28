#!/usr/bin/env python3
"""Tests: Doppelversand-Guard - 'gemeldet' bleibt 'gemeldet' beim Re-Run.

Hintergrund: versenden() markiert nach einem ECHTEN Versand alle Treffer eines
Kunden als status='gemeldet'. run_match() loeschte bisher nur 'identifiziert'
und fuegte das aktuelle Match-Set erneut als 'identifiziert' ein. Da die Tabelle
match KEINEN UNIQUE-Index auf (kunde_id, foerderung_id) hat, brachte der
naechste Match-Lauf (z. B. der taegliche Cron-Sweep) denselben Kunden zurueck in
offene_kunden() -> der Worker haette erneut an denselben Kunden gesendet.

Fix: run_match() fuegt Foerderungen, die fuer den Kunden bereits 'gemeldet'
sind, NICHT erneut als 'identifiziert' ein.
"""
import os
import sys
import uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import psycopg  # noqa: E402

from app.main import _lade_env_datei  # noqa: E402
from src import matching_service as ms  # noqa: E402
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
            "VALUES (%s,'privat','Oberoesterreich','eigenheim',ARRAY['photovoltaik'])",
            (kunde_id,),
        )
        cur.execute(
            "INSERT INTO kontakt (kunde_id, name, email, kanal, einwilligung_am) "
            "VALUES (%s,'Guard Test','guard@example.com','email', now())",
            (kunde_id,),
        )
    conn.commit()

    ms.run_match(conn, kunde_id)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM match WHERE kunde_id=%s AND status='identifiziert'",
            (kunde_id,),
        )
        ident_erst = cur.fetchone()[0]
    check("Erster Match-Lauf erzeugt 'identifiziert'-Treffer", ident_erst > 0)

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE match SET status='gemeldet', gemeldet_am=now() "
            "WHERE kunde_id=%s AND status='identifiziert'",
            (kunde_id,),
        )
    conn.commit()

    ms.run_match(conn, kunde_id)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, count(*) FROM match WHERE kunde_id=%s GROUP BY status",
            (kunde_id,),
        )
        zeilen = dict(cur.fetchall())
    check("Nach Re-Run KEINE neuen 'identifiziert'-Treffer", zeilen.get("identifiziert", 0) == 0)
    check("'gemeldet'-Treffer bleiben erhalten", zeilen.get("gemeldet", 0) == ident_erst)
    check(
        "Kunde NICHT mehr in offene_kunden()",
        str(kunde_id) not in [str(x) for x in vs.offene_kunden(conn)],
    )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM profil WHERE kunde_id=%s", (kunde_id,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM match WHERE kunde_id=%s", (kunde_id,))
        check("Cleanup: Testzeilen entfernt (CASCADE)", cur.fetchone()[0] == 0)

print()
print(f"Ergebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
