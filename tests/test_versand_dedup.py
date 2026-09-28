#!/usr/bin/env python3
"""Tests: Test-Versand-Dedup (verhindert wiederholte Testmails per Cron).

Prueft am LIVE-Schema (isolierte Testzeilen, danach geloescht):
- offene_entwuerfe liefert test_gesendet_am.
- entwurf_aktualisieren setzt test_gesendet_am zurueck (-> erneuter Testversand
  nur bei geaendertem Text).
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

    vid = vs.entwurf_speichern(conn, kunde_id, "Betreff A", "Body A", "email")
    check("Entwurf angelegt", vid is not None)

    entwuerfe = {e["id"]: e for e in vs.offene_entwuerfe(conn)}
    check("offene_entwuerfe enthaelt test_gesendet_am",
          vid in entwuerfe and "test_gesendet_am" in entwuerfe[vid])
    check("frischer Entwurf: test_gesendet_am ist NULL",
          entwuerfe[vid]["test_gesendet_am"] is None)

    with conn.cursor() as cur:
        cur.execute("UPDATE versand SET test_gesendet_am=now() WHERE id=%s", (vid,))
    conn.commit()
    entwuerfe = {e["id"]: e for e in vs.offene_entwuerfe(conn)}
    check("nach Testversand: test_gesendet_am gesetzt",
          entwuerfe[vid]["test_gesendet_am"] is not None)

    # Textaenderung -> Marke zurueck, damit erneut getestet werden kann.
    n = vs.entwurf_aktualisieren(conn, vid, "Betreff B", "Body B")
    check("entwurf_aktualisieren liefert 1", n == 1)
    entwuerfe = {e["id"]: e for e in vs.offene_entwuerfe(conn)}
    check("Textaenderung setzt test_gesendet_am zurueck",
          entwuerfe[vid]["test_gesendet_am"] is None)
    check("Text ist aktualisiert", entwuerfe[vid]["betreff"] == "Betreff B")

    # Aufraeumen (CASCADE loescht kontakt/versand mit).
    with conn.cursor() as cur:
        cur.execute("DELETE FROM profil WHERE kunde_id=%s", (kunde_id,))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM versand WHERE id=%s", (vid,))
        check("Cleanup: Testzeile entfernt", cur.fetchone() is None)

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)