"""Guarded integration-test database provisioned as a disposable PostgreSQL instance."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "db" / "init.sql"
TEST_DB = "foerderradar_test"
CONTAINER = "foerderradar-pytest-db"
IMAGE = "postgres:16-alpine"
HOST = "127.0.0.1"


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=check, timeout=45)


def _runtime_mode() -> str:
    """Choose a test-only DB backend explicitly; never infer it from project config."""
    if os.environ.get("FOERDER_RUN_DB_TESTS") != "1":
        return ""
    mode = os.environ.get("FOERDER_TEST_DB_BACKEND", "docker").lower()
    if mode not in {"docker", "local"}:
        pytest.fail("FOERDER_TEST_DB_BACKEND must be 'docker' or 'local'")
    return mode


def _docker_available() -> bool:
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10, check=False
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _local_postgres_bin(name: str) -> str | None:
    """Find installed server utilities, including versioned Homebrew keg-only paths."""
    import shutil

    found = shutil.which(name)
    if found:
        return found
    for base in (Path("/data/linuxbrew/.linuxbrew/opt"), Path("/home/linuxbrew/.linuxbrew/opt")):
        if base.exists():
            for candidate in sorted(base.glob("postgresql*/bin/" + name), reverse=True):
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    return str(candidate)
    return None




def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _assert_safe_test_target_for_db(conn: psycopg.Connection, expected: str) -> None:
    current_db = conn.execute("SELECT current_database()").fetchone()[0]
    if current_db != expected:
        raise RuntimeError(f"Refusing test DB operation on unexpected database {current_db!r}")



def _assert_safe_test_target(conn: psycopg.Connection) -> None:
    current_db = conn.execute("SELECT current_database()").fetchone()[0]
    if isinstance(current_db, bytes):
        current_db = current_db.decode("utf-8")
    if current_db != TEST_DB:
        raise RuntimeError(f"Refusing test DB operation on unexpected database {current_db!r}")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: uses a disposable local PostgreSQL test database")


@pytest.fixture(scope="session")
def integration_db():
    """Start a fresh, isolated PostgreSQL backend and always stop/remove its data."""
    mode = _runtime_mode()
    if not mode:
        pytest.skip("DB integration suite is opt-in: set FOERDER_RUN_DB_TESTS=1")

    # Once explicitly enabled, missing infrastructure fails rather than silently skipping CI coverage.
    if mode == "docker":
        if not _docker_available():
            pytest.fail("Docker backend selected but Docker is unavailable; choose FOERDER_TEST_DB_BACKEND=local for installed PostgreSQL")
        # Refuse to collide with an existing container; never remove or reuse it.
        exists = _run("docker", "container", "inspect", CONTAINER, check=False).returncode == 0
        if exists:
            pytest.fail(f"Refusing to reuse existing container {CONTAINER!r}; inspect/remove it manually")
        started = False
        random_password = uuid.uuid4().hex
        try:
            _run(
                "docker", "run", "--detach", "--rm",
                "--name", CONTAINER,
                "--label", "io.foerderradar.role=pytest-disposable",
                "--publish", f"{HOST}:{PORT}:5432",
                "--env", f"POSTGRES_DB={TEST_DB}",
                "--env", "POSTGRES_USER=postgres",
                "--env", f"POSTGRES_PASSWORD={random_password}",
                IMAGE,
            )
            started = True
            url = f"postgresql://postgres:{random_password}@{HOST}:{port}/{TEST_DB}"
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    with psycopg.connect(url, connect_timeout=2) as conn:
                        _assert_safe_test_target(conn)
                        conn.execute(SCHEMA.read_text(encoding="utf-8"))
                    break
                except psycopg.OperationalError:
                    time.sleep(1)
            else:
                raise RuntimeError("Disposable PostgreSQL container did not become ready")
            yield url
        finally:
            if started:
                _run("docker", "rm", "--force", CONTAINER, check=False)
        return

    initdb = _local_postgres_bin("initdb")
    pg_ctl = _local_postgres_bin("pg_ctl")
    postgres = _local_postgres_bin("postgres")
    if not (initdb and pg_ctl and postgres):
        pytest.fail("Local backend selected, but initdb/pg_ctl/postgres are unavailable")
    data_dir = Path(tempfile.mkdtemp(prefix="foerderradar-pytest-pg-"))
    os.chmod(data_dir, 0o700)
    port = _free_local_port()
    started = False
    try:
        _run(initdb, "-D", str(data_dir), "-A", "trust", "-U", "postgres", "--no-locale", "--encoding=UTF8")
        _run(pg_ctl, "-D", str(data_dir), "-l", str(data_dir / "postgres.log"), "-o", f"-h {HOST} -p {port} -F", "-w", "start")
        started = True
        url = f"postgresql://postgres@{HOST}:{port}/{TEST_DB}"
        with psycopg.connect(f"postgresql://postgres@{HOST}:{port}/postgres", autocommit=True) as conn:
            bootstrap_db = conn.execute("SELECT current_database()").fetchone()[0]
            if isinstance(bootstrap_db, bytes):
                bootstrap_db = bootstrap_db.decode("utf-8")
            if bootstrap_db != "postgres":
                raise RuntimeError(f"Refusing database creation outside bootstrap database: {bootstrap_db!r}")
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        with psycopg.connect(url) as conn:
            _assert_safe_test_target(conn)
            conn.execute(SCHEMA.read_text(encoding="utf-8"))
        yield url
    finally:
        # This uniquely named cluster belongs to this fixture; stop on all paths.
        _run(pg_ctl, "-D", str(data_dir), "-m", "fast", "-w", "stop", check=False)
        shutil.rmtree(data_dir, ignore_errors=True)

@pytest.fixture
def db_connection(integration_db: str):
    """Per-test connection; common test wrappers must commit, so rollback alone is insufficient."""
    conn = psycopg.connect(integration_db)
    try:
        _assert_safe_test_target(conn)
        yield conn
    finally:
        conn.close()
