"""Opt-in smoke tests of the schema against a disposable PostgreSQL instance."""

import importlib.util
import sys
from pathlib import Path

import pytest
import importlib
import uuid

import psycopg
from fastapi.testclient import TestClient

from tests.pytest.conftest import _assert_safe_test_target

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def test_schema_has_expected_tables_and_view(db_connection):
    rows = db_connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
    ).fetchall()
    names = {row[0] for row in rows}

    assert {"profil", "kontakt", "match", "versand"} <= names


def test_schema_view_excludes_contact_fields(db_connection):
    rows = db_connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        ("profil_agent",),
    ).fetchall()
    columns = {row[0] for row in rows}

    assert "kunde_id" in columns
    assert "email" not in columns
    assert "telefon" not in columns


def test_matching_service_can_be_imported_without_app_env_loader(monkeypatch):
    # The matching service itself does not load .env; importing app.main does.
    monkeypatch.syspath_prepend(str(ROOT))
    monkeypatch.syspath_prepend(str(ROOT / "src"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://invalid:invalid@127.0.0.1:1/should_not_connect")
    sys.modules.pop("matching_service", None)
    spec = importlib.util.spec_from_file_location("matching_service", ROOT / "src" / "matching_service.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.run_match)

def _insert_profile(conn):
    kunde_id = uuid.uuid4()
    conn.execute("INSERT INTO profil (kunde_id, typ) VALUES (%s, 'privat')", (kunde_id,))
    conn.execute(
        "INSERT INTO kontakt (kunde_id, name, email, kanal, einwilligung_am) "
        "VALUES (%s, 'OnlyTest', 'integration@example.invalid', 'email', now())",
        (kunde_id,),
    )
    conn.commit()
    return kunde_id


def test_delivery_dedup_and_changed_draft_reset(db_connection):
    from src import versand_service as service

    kunde_id = _insert_profile(db_connection)
    try:
        draft_id = service.entwurf_speichern(db_connection, kunde_id, "Subject A", "Body A", "email")
        assert draft_id is not None
        # A repeated request for the same customer must not create another open draft.
        assert service.entwurf_speichern(db_connection, kunde_id, "Subject B", "Body B", "email") is None
        rows = db_connection.execute(
            "SELECT id, status, test_gesendet_am FROM versand WHERE kunde_id=%s",
            (kunde_id,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1:] == ("entwurf", None)

        db_connection.execute("UPDATE versand SET test_gesendet_am=now() WHERE id=%s", (draft_id,))
        db_connection.commit()
        updated = service.entwurf_aktualisieren(db_connection, draft_id, "Subject C", "Body C")
        assert updated == 1
        subject, body, test_sent_at = db_connection.execute(
            "SELECT betreff, body, test_gesendet_am FROM versand WHERE id=%s", (draft_id,)
        ).fetchone()
        assert (subject, body, test_sent_at) == ("Subject C", "Body C", None)
        # A modified open draft still blocks a second active row.
        assert service.entwurf_speichern(db_connection, kunde_id, "Subject D", "Body D", "email") is None
    finally:
        db_connection.execute("DELETE FROM profil WHERE kunde_id=%s", (kunde_id,))
        db_connection.commit()


def test_api_default_deny_consent_and_rate_limit(db_connection, monkeypatch):
    _assert_safe_test_target(db_connection)
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("FOERDER_ADMIN_TOKEN", "pytest-admin-token")
    monkeypatch.setenv("FOERDER_INTAKE_ENABLED", "1")
    monkeypatch.setenv("FOERDER_PRIVACY_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_WITHDRAWAL_PROCESS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_RETENTION_SCHEMA_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_PURGE_SCHEDULE_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_LEGACY_RETENTION_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_DATA_CONTROLLER", "Integrationstest-Verantwortlicher")
    monkeypatch.setenv("FOERDER_PRIVACY_CONTACT", "privacy@example.invalid")
    monkeypatch.setenv("FOERDER_CONSENT_VERSION", "test-v1")
    import app.main as api
    api = importlib.reload(api)
    client = TestClient(api.app, raise_server_exceptions=False)
    monkeypatch.setattr(api, "_client_ip", lambda request: request.headers.get("x-test-ip", "pytest-client"))

    # Public endpoint does not use the database; protected route rejects before DB access.
    assert client.get("/info").status_code == 200
    assert client.get("/profiles").status_code == 401
    assert client.get("/profiles", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/profile", json={"typ": "privat"}).status_code == 400

    def forbidden_db():
        raise AssertionError("request reached a database other than the isolated fixture")

    monkeypatch.setattr(api, "db", forbidden_db)
    denied = client.get("/profiles", headers={"Authorization": "Bearer pytest-admin-token"})
    assert denied.status_code == 500  # auth passed; DB spy blocked the route before any connection
    # The previous invalid-consent request used one request from pytest-client.
    # Four more reach the cap; the next must be rejected before DB access.
    for _ in range(4):
        assert client.post(
            "/profile", json={"typ": "privat", "einwilligung": True}
        ).status_code == 500
    assert client.post(
        "/profile", json={"typ": "privat", "einwilligung": True}
    ).status_code == 429


def test_api_profile_insert_and_contact_is_not_returned(db_connection, integration_db, monkeypatch):
    _assert_safe_test_target(db_connection)
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("FOERDER_ADMIN_TOKEN", "pytest-admin-token")
    monkeypatch.setenv("FOERDER_INTAKE_ENABLED", "1")
    monkeypatch.setenv("FOERDER_PRIVACY_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_WITHDRAWAL_PROCESS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_RETENTION_SCHEMA_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_LEGACY_RETENTION_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_PURGE_SCHEDULE_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_DATA_CONTROLLER", "Integrationstest-Verantwortlicher")
    monkeypatch.setenv("FOERDER_PRIVACY_CONTACT", "privacy@example.invalid")
    monkeypatch.setenv("FOERDER_CONSENT_VERSION", "test-v1")
    import app.main as api
    api = importlib.reload(api)
    client = TestClient(api.app, raise_server_exceptions=False)

    def safe_db():
        conn = psycopg.connect(integration_db)
        try:
            _assert_safe_test_target(conn)
        except BaseException:
            conn.close()
            raise
        return conn

    monkeypatch.setattr(api, "db", safe_db)
    response = client.post("/profile", json={
        "typ": "privat", "einwilligung": True,
        "name": "OnlyTest", "email": "integration@example.invalid", "kanal": "email",
    })
    assert response.status_code == 200
    payload = response.json()
    consent_version, special_data_opt_in, loeschdatum, expected_loeschdatum = db_connection.execute(
        "SELECT einwilligung_version, einwilligung_besondere_daten, loeschdatum, (CURRENT_DATE + INTERVAL '2 years')::date "
        "FROM kontakt WHERE kunde_id=%s",
        (payload["kunde_id"],),
    ).fetchone()
    assert (consent_version, special_data_opt_in, loeschdatum) == ("test-v1", False, expected_loeschdatum)
    assert set(payload) == {"kunde_id"}
    kunde_id = uuid.UUID(payload["kunde_id"])
    row = db_connection.execute(
        "SELECT p.kunde_id, k.email FROM profil AS p JOIN kontakt AS k USING (kunde_id) WHERE p.kunde_id=%s",
        (kunde_id,),
    ).fetchone()
    assert row == (kunde_id, "integration@example.invalid")
    try:
        listed = client.get("/profiles", headers={"Authorization": "Bearer pytest-admin-token"})
        assert listed.status_code == 200
        assert all("email" not in item and "kontakt" not in item for item in listed.json())
    finally:
        db_connection.execute("DELETE FROM profil WHERE kunde_id=%s", (kunde_id,))
        db_connection.commit()

def test_retention_cleanup_removes_expired_profile_and_cascades(db_connection):
    from psycopg import sql
    from src import versand_service as service

    expired_id = uuid.uuid4()
    current_id = uuid.uuid4()
    role = "fr_retention_" + uuid.uuid4().hex[:12]
    for kunde_id, typ in ((expired_id, "privat"), (current_id, "betrieb")):
        db_connection.execute("INSERT INTO profil (kunde_id, typ) VALUES (%s, %s)", (kunde_id, typ))
    db_connection.execute(
        "INSERT INTO kontakt (kunde_id, email, kanal, einwilligung_am, loeschdatum) "
        "VALUES (%s, 'old@example.invalid', 'email', now(), CURRENT_DATE - 1), "
        "(%s, 'keep@example.invalid', 'email', now(), CURRENT_DATE + 30)",
        (expired_id, current_id),
    )
    db_connection.execute(
        "INSERT INTO match (kunde_id, foerderung_id, kategorie) VALUES (%s, 'test-grant', 'top')",
        (expired_id,),
    )
    db_connection.execute(
        "INSERT INTO versand (kunde_id, kanal, betreff, body, status) "
        "VALUES (%s, 'email', 'test', 'test', 'entwurf')",
        (expired_id,),
    )
    db_connection.commit()

    role_created = False
    try:
        db_connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        role_created = True
        db_connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        db_connection.execute(sql.SQL("GRANT EXECUTE ON FUNCTION public.purge_expired_profiles() TO {}").format(sql.Identifier(role)))
        assert db_connection.execute("SELECT has_table_privilege(%s, 'profil', 'DELETE')", (role,)).fetchone()[0] is False
        assert db_connection.execute("SELECT has_table_privilege(%s, 'kontakt', 'SELECT')", (role,)).fetchone()[0] is False
        assert db_connection.execute("SELECT has_function_privilege(%s, 'public.purge_expired_profiles()', 'EXECUTE')", (role,)).fetchone()[0] is True

        db_connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        assert service.loesch_abgelaufene_kontakte(db_connection) == 1
        db_connection.execute("RESET ROLE")

        assert db_connection.execute("SELECT 1 FROM profil WHERE kunde_id=%s", (expired_id,)).fetchone() is None
        assert db_connection.execute("SELECT 1 FROM kontakt WHERE kunde_id=%s", (expired_id,)).fetchone() is None
        assert db_connection.execute("SELECT 1 FROM match WHERE kunde_id=%s", (expired_id,)).fetchone() is None
        assert db_connection.execute("SELECT 1 FROM versand WHERE kunde_id=%s", (expired_id,)).fetchone() is None
        assert db_connection.execute("SELECT 1 FROM profil WHERE kunde_id=%s", (current_id,)).fetchone() is not None
        assert service.loesch_abgelaufene_kontakte(db_connection) == 0
    finally:
        db_connection.execute("RESET ROLE")
        db_connection.execute("DELETE FROM profil WHERE kunde_id IN (%s, %s)", (expired_id, current_id))
        if role_created:
            db_connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db_connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        db_connection.commit()


def test_requested_profile_deletion_ignores_retention_deadline(db_connection):
    from src import versand_service as service

    profile_id = db_connection.execute(
        "INSERT INTO profil (typ) VALUES (%s) RETURNING kunde_id", ("privat",)
    ).fetchone()[0]
    db_connection.execute(
        "INSERT INTO kontakt (kunde_id, name, email, kanal, einwilligung_am, loeschdatum) VALUES (%s, %s, %s, %s, now(), CURRENT_DATE + 365)",
        (profile_id, "Delete Test", "delete-test@example.invalid", "email"),
    )
    db_connection.execute(
        "INSERT INTO match (kunde_id, foerderung_id, kategorie) VALUES (%s, %s, %s)",
        (profile_id, "delete-test-grant", "top"),
    )
    db_connection.execute(
        "INSERT INTO versand (kunde_id, kanal, betreff, body, status) VALUES (%s, %s, %s, %s, %s)",
        (profile_id, "email", "test", "test", "entwurf"),
    )
    db_connection.commit()

    assert service.loesche_kundenprofil_auf_anfrage(db_connection, profile_id) is True
    db_connection.commit()
    for table in ("profil", "kontakt", "match", "versand"):
        assert db_connection.execute(
            f"SELECT 1 FROM {table} WHERE kunde_id = %s", (profile_id,)
        ).fetchone() is None
    assert service.loesche_kundenprofil_auf_anfrage(db_connection, profile_id) is False


def test_withdraw_by_email_deletes_only_matching_profiles(db_connection):
    from psycopg import sql

    match_id, other_id = uuid.uuid4(), uuid.uuid4()
    role = "fr_withdraw_" + uuid.uuid4().hex[:12]
    for kunde_id in (match_id, other_id):
        db_connection.execute("INSERT INTO profil (kunde_id, typ) VALUES (%s, 'privat')", (kunde_id,))
    db_connection.execute(
        "INSERT INTO kontakt (kunde_id, email, kanal, einwilligung_am) "
        "VALUES (%s, ' Kunde@Example.invalid ', 'email', now()), (%s, 'andere@example.invalid', 'email', now())",
        (match_id, other_id),
    )
    db_connection.execute(
        "INSERT INTO match (kunde_id, foerderung_id, kategorie) VALUES (%s, 'test-grant', 'top')", (match_id,)
    )
    db_connection.commit()

    role_created = False
    try:
        db_connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        role_created = True
        db_connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        db_connection.execute(
            sql.SQL("GRANT EXECUTE ON FUNCTION public.withdraw_by_email(text) TO {}").format(sql.Identifier(role))
        )
        assert db_connection.execute(
            "SELECT has_function_privilege('public', 'public.withdraw_by_email(text)', 'EXECUTE')"
        ).fetchone()[0] is False
        assert db_connection.execute("SELECT has_table_privilege(%s, 'kontakt', 'SELECT')", (role,)).fetchone()[0] is False
        db_connection.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        assert db_connection.execute("SELECT public.withdraw_by_email('kunde@example.INVALID')").fetchone()[0] == 1
        assert db_connection.execute("SELECT public.withdraw_by_email('kunde@example.invalid')").fetchone()[0] == 0
        assert db_connection.execute("SELECT public.withdraw_by_email('niemand')").fetchone()[0] == 0
        assert db_connection.execute("SELECT public.withdraw_by_email(NULL)").fetchone()[0] == 0
        db_connection.execute("RESET ROLE")
        db_connection.commit()
    finally:
        db_connection.rollback()
        db_connection.execute("RESET ROLE")
        if role_created:
            db_connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db_connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        db_connection.commit()

    for table in ("profil", "kontakt", "match"):
        assert db_connection.execute(f"SELECT 1 FROM {table} WHERE kunde_id = %s", (match_id,)).fetchone() is None
    assert db_connection.execute("SELECT 1 FROM kontakt WHERE kunde_id = %s", (other_id,)).fetchone() is not None
    assert db_connection.execute(
        "SELECT count(*) FROM profile_deletion_audit WHERE kunde_id = %s", (match_id,)
    ).fetchone()[0] == 1
