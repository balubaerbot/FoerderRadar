import sys

from tools import delete_profile_on_request as deletion_tool
from tools.delete_profile_on_request import _allowed_retention_target


def test_disposable_loopback_target_is_allowed():
    assert _allowed_retention_target("postgresql://app@127.0.0.1:55439/foerderradar_drill")
    assert _allowed_retention_target("postgresql://app@[::1]/pytest_foerderradar")


def test_remote_or_non_disposable_target_is_rejected():
    assert not _allowed_retention_target("postgresql://app@db.example.invalid/foerderradar_test")
    assert not _allowed_retention_target("postgresql://app@127.0.0.1/foerderradar")


def test_name_marker_must_be_a_full_token():
    assert not _allowed_retention_target("postgresql://localhost/latest_foerderradar")
    assert not _allowed_retention_target("postgresql://localhost/contest_foerderradar")
    assert _allowed_retention_target("postgresql://localhost/foerderradar_test")
    assert _allowed_retention_target("postgresql://localhost/pytest-foerderradar")


def test_query_parameters_that_override_libpq_target_are_rejected():
    assert not _allowed_retention_target(
        "postgresql://localhost/foerderradar_test?host=203.0.113.10"
    )
    assert not _allowed_retention_target(
        "postgresql://localhost/foerderradar_test?hostaddr=203.0.113.10"
    )
    assert not _allowed_retention_target(
        "postgresql://localhost/foerderradar_test?dbname=foerderradar"
    )


def test_malformed_credentials_are_rejected_without_traceback():
    assert not _allowed_retention_target(
        "postgresql://app:%zz@127.0.0.1:5432/foerderradar_test"
    )


def test_multiple_hosts_and_ambiguous_urls_are_rejected():
    assert not _allowed_retention_target(
        "postgresql://localhost:5432,203.0.113.10:5432/foerderradar_test"
    )
    assert not _allowed_retention_target("postgresql:///foerderradar_test")
    assert not _allowed_retention_target("mysql://localhost/pytest_db")
    assert not _allowed_retention_target("not-a-postgres-url")


def test_main_pins_routing_kwargs_and_checks_connected_target(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_RETENTION", "postgresql://app@127.0.0.1:5432/foerderradar_test")
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.10")
    monkeypatch.setattr(sys, "argv", ["delete_profile_on_request.py", "00000000-0000-0000-0000-000000000001"])
    seen = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            seen["query"] = query
            seen["params"] = params

        def fetchone(self):
            if seen["query"].startswith("SELECT current_database"):
                return ("foerderradar_test", "127.0.0.1")
            return (True,)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            seen["committed"] = True

    def fake_connect(*args, **kwargs):
        seen["kwargs"] = kwargs
        return FakeConnection()

    monkeypatch.setattr(deletion_tool.psycopg, "connect", fake_connect)
    assert deletion_tool.main() == 0
    kwargs = seen["kwargs"]
    assert kwargs["hostaddr"] == "127.0.0.1"
    assert kwargs["dbname"] == "foerderradar_test"
    assert kwargs["passfile"] == "/dev/null"
    assert kwargs["service"] == ""
    assert seen["committed"]


def test_main_refuses_when_connected_server_ip_does_not_match(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL_RETENTION", "postgresql://app@127.0.0.1:5432/foerderradar_test")
    monkeypatch.setattr(sys, "argv", ["delete_profile_on_request.py", "00000000-0000-0000-0000-000000000001"])
    seen = {"delete_called": False, "committed": False}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=None):
            seen["delete_called"] = query.startswith("SELECT public.delete_profile")

        def fetchone(self):
            return ("foerderradar_test", "203.0.113.10")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            seen["committed"] = True

    monkeypatch.setattr(deletion_tool.psycopg, "connect", lambda *args, **kwargs: FakeConnection())
    assert deletion_tool.main() == 2
    assert not seen["delete_called"]
    assert not seen["committed"]
    assert "Refusing deletion" in capsys.readouterr().err


def test_main_refuses_production_target_before_connecting(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL_RETENTION", "postgresql://app@db.example.invalid/foerderradar")
    monkeypatch.setattr(sys, "argv", ["delete_profile_on_request.py", "00000000-0000-0000-0000-000000000001"])

    def should_not_connect(*args, **kwargs):
        raise AssertionError("target guard must run before opening a database connection")

    monkeypatch.setattr(deletion_tool.psycopg, "connect", should_not_connect)
    assert deletion_tool.main() == 2
    assert "Refusing deletion" in capsys.readouterr().err
