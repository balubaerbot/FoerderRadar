#!/usr/bin/env python3
"""Delete profiles whose consent-retention date has expired.

Run from an operator-controlled scheduler with DATABASE_URL_RETENTION set to
the dedicated app_retention DB login. This script never loads .env.
"""

from __future__ import annotations

import os
import sys

import psycopg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.versand_service import loesch_abgelaufene_kontakte  # noqa: E402


def main() -> int:
    url = os.environ.get("DATABASE_URL_RETENTION", "")
    if not url:
        print("DATABASE_URL_RETENTION is required; refusing to use DATABASE_URL or .env", file=sys.stderr)
        return 2
    with psycopg.connect(url, connect_timeout=5) as conn:
        deleted = loesch_abgelaufene_kontakte(conn)
    print(f"Expired profiles removed: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
