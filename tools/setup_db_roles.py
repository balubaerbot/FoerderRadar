#!/usr/bin/env python3
"""FoerderRadar - DB-Rollen einrichten (Least Privilege).

Erzeugt zwei Login-Rollen und setzt minimale Grants:

  app_web     - API + Agent/Matching: profil schreiben/lesen, profil_agent lesen,
                match verwalten, kontakt SCHREIBEN (aber NICHT lesen!)
  app_worker  - nur Versand-Worker: zusaetzlich kontakt LESEN

Der Superuser bleibt fuer Migrationen erhalten (DATABASE_URL_ADMIN in .env).

Idempotent: kann mehrfach laufen (setzt Passwoerter neu).

Lauf:  python3 tools/setup_db_roles.py
"""
import os
import pathlib
import secrets
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

BASE = pathlib.Path(__file__).resolve().parent.parent
ENV = BASE / ".env"


def lies_env():
    daten = {}
    for zeile in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in zeile and not zeile.strip().startswith("#"):
            k, v = zeile.split("=", 1)
            daten[k.strip()] = v.strip()
    return daten


def schreibe_env(daten):
    ENV.write_text(
        "".join(f"{k}={v}\n" for k, v in daten.items()), encoding="utf-8"
    )


def mit_zugang(url, user, pw):
    t = urlsplit(url)
    host = t.hostname or "foerderradar-db"
    port = t.port or 5432
    netloc = f"{user}:{pw}@{host}:{port}"
    return urlunsplit((t.scheme or "postgresql", netloc, t.path, "", ""))


GRANTS = {
    "app_web": [
        "GRANT USAGE ON SCHEMA public TO {r}",
        "GRANT SELECT, INSERT ON profil TO {r}",
        "GRANT INSERT ON kontakt TO {r}",            # schreiben, NICHT lesen
        "GRANT SELECT ON profil_agent TO {r}",
        "GRANT SELECT, INSERT, DELETE ON match TO {r}",
        "GRANT USAGE ON SEQUENCE match_id_seq TO {r}",
    ],
    "app_worker": [
        "GRANT USAGE ON SCHEMA public TO {r}",
        "GRANT SELECT ON profil_agent TO {r}",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON match TO {r}",
        "GRANT USAGE ON SEQUENCE match_id_seq TO {r}",
        "GRANT SELECT ON kontakt TO {r}",
        "GRANT SELECT, INSERT, UPDATE ON versand TO {r}",
        "GRANT USAGE ON SEQUENCE versand_id_seq TO {r}",
    ],
}


def main():
    env = lies_env()
    admin_url = env.get("DATABASE_URL_ADMIN") or env.get("DATABASE_URL")
    if not admin_url:
        raise SystemExit("DATABASE_URL(_ADMIN) fehlt in .env")

    zugangsdaten = {}
    with psycopg.connect(admin_url, connect_timeout=5, autocommit=True) as conn:
        for rolle in ("app_web", "app_worker"):
            pw = secrets.token_urlsafe(24)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (rolle,))
                existiert = cur.fetchone() is not None
                if existiert:
                    cur.execute(
                        sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                            sql.Identifier(rolle), sql.Literal(pw)
                        )
                    )
                else:
                    cur.execute(
                        sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(
                            sql.Identifier(rolle), sql.Literal(pw)
                        )
                    )
                for g in GRANTS[rolle]:
                    cur.execute(sql.SQL(g).format(r=sql.Identifier(rolle)))
            zugangsdaten[rolle] = pw
            print(f"  Rolle {rolle}: {'aktualisiert' if existiert else 'angelegt'} + Grants gesetzt")

    env["DATABASE_URL_ADMIN"] = admin_url
    env["DATABASE_URL"] = mit_zugang(admin_url, "app_web", zugangsdaten["app_web"])
    env["DATABASE_URL_WORKER"] = mit_zugang(admin_url, "app_worker", zugangsdaten["app_worker"])
    schreibe_env(env)
    print("  .env aktualisiert: DATABASE_URL=app_web, DATABASE_URL_WORKER=app_worker, "
          "DATABASE_URL_ADMIN=Superuser (nur fuer Migrationen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
