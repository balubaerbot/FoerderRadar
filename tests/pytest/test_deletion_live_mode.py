import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import delete_profile_on_request as tool  # noqa: E402

KID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LIVE = "postgresql://app@db.internal:5432/foerderradar"


def _run(monkeypatch, capsys, url, *extra):
    monkeypatch.setenv("DATABASE_URL_RETENTION", url)
    monkeypatch.setattr(sys, "argv", ["x", str(KID), *extra])
    code = tool.main()
    return code, capsys.readouterr().err


def test_live_requires_flags(monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, LIVE, "--live")
    assert code == 2 and "confirm-id" in err


def test_live_requires_db_confirmation(monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, LIVE, "--live", "--confirm-id", str(KID))
    assert code == 2 and "foerderradar" in err


def test_live_rejects_other_database_name(monkeypatch, capsys):
    url = "postgresql://app@db.internal:5432/other"
    code, _ = _run(monkeypatch, capsys, url, "--live", "--confirm-id", str(KID), "--confirm-db", "foerderradar")
    assert code == 2


def test_live_rejects_query_and_multihost(monkeypatch, capsys):
    for url in (LIVE + "?host=evil", "postgresql://app@a:5432,b:5432/foerderradar"):
        code, _ = _run(monkeypatch, capsys, url, "--live", "--confirm-id", str(KID), "--confirm-db", "foerderradar")
        assert code == 2


def test_live_rejects_wrong_confirm_id(monkeypatch, capsys):
    other = "00000000-0000-0000-0000-000000000002"
    code, err = _run(monkeypatch, capsys, LIVE, "--live", "--confirm-id", other, "--confirm-db", "foerderradar")
    assert code == 2 and "confirm-id" in err


def test_default_mode_still_refuses_production(monkeypatch, capsys):
    code, err = _run(monkeypatch, capsys, LIVE)
    assert code == 2 and "loopback" in err
