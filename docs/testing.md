# Testing

## Local/default suite (safe, no database)

`python3 -m pytest -q`

This runs local, non-database tests. The standalone scripts left under `tests/` are not auto-discovered by pytest. Their safe unit/regression subset runs in isolated subprocesses with `DATABASE_URL`, secrets, and service credentials removed.

## Disposable database integration tests

Install test dependencies with `python3 -m pip install -r requirements-test.txt`.

Docker is the default backend:

`FOERDER_RUN_DB_TESTS=1 python3 -m pytest -m integration -q`

To explicitly use the installed local PostgreSQL server instead:

`FOERDER_RUN_DB_TESTS=1 FOERDER_TEST_DB_BACKEND=local python3 -m pytest -m integration -q`

The fixture builds a new schema in a uniquely named, temporary PostgreSQL instance. It never reads `.env`, inherits `DATABASE_URL` for DB calls, or uses the project Compose database. The local backend creates a private temporary cluster, binds only to loopback on a free port, and removes the cluster after the run. Docker mode refuses an existing fixture container and deletes only the container it started.

`tests/pytest/test_db_integration.py` covers schema/view shape, delivery draft deduplication and changed-content reset, API default-deny/consent/rate limiting, and the public profile creation response. API tests set `FOERDER_TESTING=1` before import so the application does not load `.env`, set `DATABASE_URL` empty, and replace DB access with either a failing spy or a connection to the guarded fixture.

The old standalone DB scripts were retired; never run them against live configuration. Their tested cases have been migrated into the opt-in integration suite.

## Continuous integration

`.github/workflows/tests.yml` runs the normal suite and catalog validator, then the opt-in DB suite with `FOERDER_TEST_DB_BACKEND=local`. The DB backend does not consume a service DB or project secrets.

## Retention

`tools/purge_expired_contacts.py` calls the schema-owned `public.purge_expired_profiles()` SECURITY DEFINER function using only `DATABASE_URL_RETENTION`. The `app_retention` role receives EXECUTE on that function, not table DELETE grants; the function has a fixed search path and deletes profiles with linked contacts whose `loeschdatum <= CURRENT_DATE`, cascading contact, match, and delivery records. No unattended scheduler is installed by this code change.
