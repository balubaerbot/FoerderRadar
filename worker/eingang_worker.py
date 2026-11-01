"""FoerderRadar - Eingangsbestaetigung nach dem Formular.

Kurze Mail "Ihre Anfrage ist eingegangen" an neue E-Mail-Kontakte (< 48 h,
nicht widerrufen, noch keine Eingangsmail). Laeuft haeufig (z.B. alle 10 min).

  python3 worker/eingang_worker.py                  # DRY-RUN: zeigt nur, was ginge
  python3 worker/eingang_worker.py --send           # ECHT versenden
  python3 worker/eingang_worker.py --muster-an ADR  # nur Mustermail an ADR, keine DB

Ausgabe ist maskiert. Exit-Code 1 bei Versandfehlern, 2 bei Andrang
(mehr offene Bestaetigungen als pro Lauf erlaubt -> Double-Opt-in erwaegen).
"""

import argparse
import os
import sys

import psycopg

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from src import versand_service as vs          # noqa: E402
from worker import versand_worker as vw         # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--send", action="store_true", help="ECHT versenden")
    ap.add_argument("--muster-an", metavar="ADRESSE",
                    help="nur eine Mustermail an ADRESSE schicken (ohne DB)")
    ap.add_argument("--limit", type=int, default=vs.EINGANG_MAX_PRO_LAUF)
    args = ap.parse_args(argv)

    vw._lade_env_datei()

    if args.muster_an:
        vs._senden_email(args.muster_an, vs.EINGANG_BETREFF, vs.eingang_body())
        print(f"Mustermail gesendet an {vs.maskiere_email(args.muster_an)}")
        return 0

    with psycopg.connect(vw.laden_env(), connect_timeout=5) as conn:
        erg = vs.eingang_verarbeiten(conn, senden=args.send, limit=args.limit)

    modus = "SEND" if args.send else "DRY-RUN"
    print(f"Eingangsmails [{modus}]: offen={erg['offen']} gesendet={erg['gesendet']} "
          f"uebersprungen={erg['uebersprungen']} fehler={erg['fehler']}")
    for z in erg["zeilen"]:
        print("  " + z)
    if erg["fehler"]:
        print(f"FEHLER: {erg['fehler']} Eingangsmail(s) nicht versendet", file=sys.stderr)
        return 1
    if erg["andrang"]:
        print(f"ANDRANG: {erg['offen']} offene Eingangsmails (> {args.limit} pro Lauf) - "
              "Rest folgt im naechsten Lauf; Bestaetigungslink (Double-Opt-in) erwaegen.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
