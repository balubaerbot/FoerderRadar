#!/usr/bin/env python3
"""Delete one FoerderRadar profile after the operator verifies the requester.

Requires DATABASE_URL_RETENTION and never loads .env. The function records only
the profile UUID and timestamp in a restricted audit table, not contact data.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kunde_id", type=uuid.UUID, help="Profile UUID matched after manual identity verification")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL_RETENTION", "").strip()
    if not url:
        print("DATABASE_URL_RETENTION required; refusing to use DATABASE_URL or .env", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT public.delete_profile_on_request(%s)", (args.kunde_id,))
                deleted = cur.fetchone()[0]
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"Deletion failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if not deleted:
        print("No matching profile; nothing deleted")
        return 1
    print(f"Deleted profile {args.kunde_id} after operator verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
