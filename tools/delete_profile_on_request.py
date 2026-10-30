#!/usr/bin/env python3
"""Delete one FoerderRadar profile after the operator verifies the requester.

Requires DATABASE_URL_RETENTION and never loads .env. The function records only
the profile UUID and timestamp in a restricted audit table, not contact data.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import psycopg
import re
import sys
import uuid
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict


def _allowed_retention_target(url: str) -> bool:
    """Allow only one explicit loopback IP and an unmistakably disposable DB name.

    Query strings and multi-host URLs are rejected so libpq cannot silently override
    the checked host or database. Connection kwargs reassert the validated target.
    """
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"postgres", "postgresql"} or parsed.query or parsed.fragment:
            return False
        info = conninfo_to_dict(url)
        host = info.get("host", "")
        database = info.get("dbname", "")
        if not host or "," in host or not database:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host != "localhost":
                return False
            address = ipaddress.ip_address("127.0.0.1")
        if not address.is_loopback:
            return False
        hostaddr = info.get("hostaddr")
        if hostaddr:
            if "," in hostaddr:
                return False
            resolved = ipaddress.ip_address(hostaddr)
            if not resolved.is_loopback:
                return False
            if host != "localhost" and resolved != address:
                return False
        if not re.search(r"(?:^|[_-])(test|drill|disposable|pytest)(?:[_-]|\Z)", database, re.I):
            return False
        port = parsed.port
        return port is None or 1 <= port <= 65535
    except (psycopg.Error, ValueError, UnicodeError, TypeError):
        return False


def _verify_connected_target(conn, expected_database: str, expected_address: str) -> bool:
    """Verify the connected DB name and server IP before any deletion."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr()::text")
            database, address = cur.fetchone()
        return (
            database == expected_database
            and address is not None
            and ipaddress.ip_address(address) == ipaddress.ip_address(expected_address)
        )
    except (ValueError, TypeError):
        return False


LIVE_DB_NAME = "foerderradar"


def _live_target_ok(url: str, confirm_db: str) -> bool:
    """Live mode: exactly one host, no query/fragment, fixed DB name, confirmed by flag."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"postgres", "postgresql"} or parsed.query or parsed.fragment:
            return False
        info = conninfo_to_dict(url)
        host = info.get("host") or ""
        if not host or "," in host or "," in (info.get("hostaddr") or ""):
            return False
        return info.get("dbname") == LIVE_DB_NAME and confirm_db == LIVE_DB_NAME
    except (psycopg.Error, ValueError, UnicodeError, TypeError):
        return False


def _main_live(args, url: str) -> int:
    """Delete one profile on the live DB after explicit double confirmation."""
    if args.confirm_id != args.kunde_id:
        print("Refusing live deletion: --confirm-id must repeat the profile UUID", file=sys.stderr)
        return 2
    if not _live_target_ok(url, args.confirm_db or ""):
        print(
            f"Refusing live deletion: DATABASE_URL_RETENTION must name database '{LIVE_DB_NAME}' "
            "(one host, no query parameters) and --confirm-db must repeat it",
            file=sys.stderr,
        )
        return 2
    try:
        with psycopg.connect(url, connect_timeout=5, application_name="foerderradar-delete-profile-live", options="") as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                if cur.fetchone()[0] != LIVE_DB_NAME:
                    print("Refusing live deletion: connected database does not match", file=sys.stderr)
                    return 2
                cur.execute("SELECT public.delete_profile_on_request(%s)", (args.kunde_id,))
                deleted = cur.fetchone()[0]
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"Deletion failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if not deleted:
        print("No matching profile; nothing deleted")
        return 1
    print(f"Deleted profile {args.kunde_id} on live DB after operator verification")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kunde_id", type=uuid.UUID, help="Profile UUID matched after manual identity verification")
    parser.add_argument("--live", action="store_true", help="Delete on the live database (needs --confirm-id and --confirm-db)")
    parser.add_argument("--confirm-id", type=uuid.UUID, help="Repeat the profile UUID (live mode)")
    parser.add_argument("--confirm-db", help=f"Repeat the database name '{LIVE_DB_NAME}' (live mode)")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL_RETENTION", "").strip()
    if not url:
        print("DATABASE_URL_RETENTION required; refusing to use DATABASE_URL or .env", file=sys.stderr)
        return 2
    if args.live:
        return _main_live(args, url)
    if not _allowed_retention_target(url):
        print(
            "Refusing deletion: DATABASE_URL_RETENTION must point to a loopback PostgreSQL test/drill/disposable/pytest database",
            file=sys.stderr,
        )
        return 2
    if not _allowed_retention_target(url):
        print(
            "Refusing deletion: DATABASE_URL_RETENTION must be one explicit loopback IP "
            "with a test/drill/disposable/pytest database name and no query parameters",
            file=sys.stderr,
        )
        return 2
    try:
        target = conninfo_to_dict(url)
        validated_host = target["host"]
        validated_hostaddr = target.get("hostaddr") or (
            "127.0.0.1" if validated_host == "localhost" else validated_host
        )
        validated_address = ipaddress.ip_address(validated_hostaddr)
        if not validated_address.is_loopback:
            print("Refusing deletion: resolved host address is not loopback", file=sys.stderr)
            return 2
        with psycopg.connect(
            url,
            connect_timeout=5,
            host=validated_host,
            hostaddr=validated_hostaddr,
            dbname=target["dbname"],
            port=target.get("port") or "5432",
            user=target.get("user"),
            password=target.get("password"),
            passfile="/dev/null",
            service="",
            sslmode=target.get("sslmode", "prefer"),
            sslrootcert=target.get("sslrootcert"),
            sslcert=target.get("sslcert"),
            sslkey=target.get("sslkey"),
            sslcrl=target.get("sslcrl"),
            sslcrldir=target.get("sslcrldir"),
            ssl_min_protocol_version=target.get("ssl_min_protocol_version"),
            ssl_max_protocol_version=target.get("ssl_max_protocol_version"),
            require_auth=target.get("require_auth"),
            gssencmode=target.get("gssencmode"),
            channel_binding=target.get("channel_binding"),
            application_name="foerderradar-delete-profile-tool",
            options="",
        ) as conn:
            if not _verify_connected_target(conn, target["dbname"], str(validated_address)):
                print(
                    "Refusing deletion: connected PostgreSQL target does not match the verified disposable target",
                    file=sys.stderr,
                )
                return 2
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
