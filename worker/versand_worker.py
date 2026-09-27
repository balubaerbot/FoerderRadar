#!/usr/bin/env python3
"""FoerderRadar - Versand-Worker.

Holt Kunden mit offenen Treffern, baut Textentwuerfe (Phase 1: Vorlage) und
zeigt/versendet sie. Standard ist DRY-RUN - es geht NICHTS raus.

  python3 worker/versand_worker.py             # Dry-Run: zeigt, was rausgehen WUERDE (maskiert)
  python3 worker/versand_worker.py --status    # nur Queue-Status
  python3 worker/versand_worker.py --send      # ECHTER Versand (Phase 3, noch nicht aktiv)
  python3 worker/versand_worker.py --kunde <uuid>   # nur ein Kunde

Ausgabe enthaelt NIE Klartext-Kontaktdaten (nur maskiert).
"""
import argparse
import os
import sys

import psycopg

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from src import matching_service as ms  # noqa: E402
from src import versand_service as vs   # noqa: E402


def laden_env():
    """DB-URL fuer den Versand-Worker.

    Nutzt bevorzugt DATABASE_URL_WORKER (Rolle app_worker darf `kontakt` lesen).
    Fallback DATABASE_URL (nur fuer Umgebungen ohne getrennte Rollen).
    """
    def aus_datei(schluessel):
        pfad = os.path.join(BASE, ".env")
        if os.path.exists(pfad):
            for zeile in open(pfad, encoding="utf-8"):
                if zeile.startswith(schluessel + "="):
                    return zeile.split("=", 1)[1].strip()
        return None

    return (
        os.environ.get("DATABASE_URL_WORKER")
        or aus_datei("DATABASE_URL_WORKER")
        or os.environ.get("DATABASE_URL")
        or aus_datei("DATABASE_URL")
        or (_ for _ in ()).throw(SystemExit("DATABASE_URL_WORKER/DATABASE_URL nicht gefunden"))
    )


def entwuerfe_anlegen(conn, katalog, nur_kunde=None):
    """Fuer jeden offenen Kunden ohne bestehenden Entwurf einen anlegen."""
    neu = []
    for kunde_id in vs.offene_kunden(conn):
        if nur_kunde and str(kunde_id) != str(nur_kunde):
            continue
        if vs.hat_offenen_entwurf(conn, kunde_id):
            continue
        profil = vs.profil_pseudonym(conn, kunde_id)
        if not profil:
            continue
        # WICHTIG: Gegen den AKTUELLEN Katalog neu bewerten, damit eingefrorene
        # Treffer (z.B. inzwischen ausgeschoepft) nicht veraltet beim Kunden landen.
        ms.run_match(conn, kunde_id)
        treffer = vs.treffer_fuer(conn, kunde_id)
        if not treffer:
            continue
        kanal = "email"  # Phase 1: nur E-Mail
        betreff, body = vs.nachricht_bauen(profil, treffer, katalog)
        vid = vs.entwurf_speichern(conn, kunde_id, betreff, body, kanal)
        neu.append({"versand_id": vid, "kunde_id": str(kunde_id), "anzahl_treffer": len(treffer)})
    return neu


def main():
    ap = argparse.ArgumentParser(description="FoerderRadar Versand-Worker")
    ap.add_argument("--send", action="store_true", help="ECHT versenden")
    ap.add_argument("--test", action="store_true", help="ECHT versenden, aber alles an das TEST-Postfach umleiten")
    ap.add_argument("--status", action="store_true", help="nur Queue-Status anzeigen")
    ap.add_argument("--kunde", help="nur diesen kunde_id bearbeiten")
    args = ap.parse_args()

    if args.test:
        args.send = True

    url = laden_env()
    katalog = ms.load_katalog()

    with psycopg.connect(url, connect_timeout=5) as conn:
        if args.status:
            entwuerfe = vs.offene_entwuerfe(conn)
            print(f"Offene Entwuerfe: {len(entwuerfe)}")
            for e in entwuerfe:
                k = vs.kontakt_holen(conn, e["kunde_id"])
                ziel = vs._ziel_maskiert(e["kanal"], k) if k else "<kein Kontakt>"
                print(f"  #{e['id']}  {e['kanal']:<5} -> {ziel}  | {e['betreff']}")
            return 0

        neu = entwuerfe_anlegen(conn, katalog, args.kunde)
        if neu:
            print(f"Neue Entwuerfe angelegt: {len(neu)}")
            for n in neu:
                print(f"  #{n['versand_id']}  {n['kunde_id'][:8]}...  ({n['anzahl_treffer']} Treffer)")

        entwuerfe = vs.offene_entwuerfe(conn)
        if args.kunde:
            entwuerfe = [e for e in entwuerfe if str(e["kunde_id"]) == str(args.kunde)]

        modus = "TEST -> " + vs.maskiere_email(vs.ABSENDER) if args.test else ("SENDEN" if args.send else "DRY-RUN")
        print(f"\n=== Versand ({modus}) - {len(entwuerfe)} Entwurf/Entwuerfe ===")
        ergebnisse = []
        test_recipient = vs.ABSENDER if args.test else None
        for e in entwuerfe:
            r = vs.versenden(conn, e["id"], dry_run=not args.send, test_recipient=test_recipient)
            ergebnisse.append(r)
            if not r.get("ok"):
                print(f"  #{e['id']}  FEHLER: {r.get('fehler')}")
                continue
            if r.get("dry_run"):
                print(f"  #{e['id']}  -> {r['ziel']}  | {r['betreff']}")
                print("     ----- Text (Vorschau) -----")
                for zeile in r["body"].splitlines():
                    print(f"     | {zeile}")
                print("     ----------------------------")
            elif r.get("test"):
                print(f"  #{e['id']}  TEST-GESENDET -> {r['ziel']}  (Kunde waere {r['empfaenger_kunde']})")
            else:
                print(f"  #{e['id']}  GESENDET -> {r['ziel']}")

        ok = sum(1 for r in ergebnisse if r.get("ok"))
        print(f"\nErgebnis: {ok}/{len(ergebnisse)} ok" + (" (nichts versendet - DRY-RUN)" if not args.send else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
