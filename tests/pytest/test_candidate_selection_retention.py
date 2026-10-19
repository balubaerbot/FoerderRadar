"""Fail-closed retention-date selection against the disposable DB fixture."""
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import versand_service  # noqa: E402


def _insert_candidate(conn, loeschdatum):
    kunde_id = uuid.uuid4()
    conn.execute("INSERT INTO profil (kunde_id, typ) VALUES (%s, 'privat')", (kunde_id,))
    conn.execute(
        "INSERT INTO kontakt (kunde_id, name, email, kanal, einwilligung_am, loeschdatum) "
        "VALUES (%s, 'Retention test', %s, 'email', now(), %s)",
        (kunde_id, f"{kunde_id}@example.invalid", loeschdatum),
    )
    conn.execute(
        "INSERT INTO match (kunde_id, foerderung_id, kategorie, status) "
        "VALUES (%s, %s, 'top', 'identifiziert')",
        (kunde_id, f"test-{kunde_id}"),
    )
    return kunde_id


def test_missing_retention_date_is_not_selected(db_connection):
    # Emulate historical NULL only inside this disposable, fixture-owned database.
    try:
        db_connection.execute("ALTER TABLE kontakt ALTER COLUMN loeschdatum DROP NOT NULL")
        missing_id = _insert_candidate(db_connection, None)
        valid_id = _insert_candidate(db_connection, date.today() + timedelta(days=30))
        today_id = _insert_candidate(db_connection, date.today())
        candidates = {str(kunde_id) for kunde_id in versand_service.offene_kunden(db_connection)}
        assert str(missing_id) not in candidates
        assert str(valid_id) in candidates
        assert str(today_id) not in candidates
        db_connection.execute(
            "DELETE FROM profil WHERE kunde_id IN (%s, %s, %s)",
            (missing_id, valid_id, today_id),
        )
        db_connection.execute("ALTER TABLE kontakt ALTER COLUMN loeschdatum SET NOT NULL")
        db_connection.commit()
    except Exception:
        db_connection.rollback()
        raise
