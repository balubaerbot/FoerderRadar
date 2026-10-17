"""Pytest bridge for existing standalone, local-only test scripts.

These scripts still use their original check()/sys.exit() convention. Running
one in a subprocess keeps module-level code and process-wide environment
changes isolated while pytest provides one discoverable test command.
Database-backed scripts are intentionally excluded; they need a disposable
integration database before they can safely join the default suite.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Verified local-only scripts. Do not add scripts needing .env, a live DB,
# network access, or shared-state mutation here.
UNIT_SCRIPTS = [
    "test_bundesfoerderung.py",
    "test_einkommen.py",
    "test_katalog_gate.py",
    "test_ki_mapping.py",
    "test_mailtext_llm.py",
    "test_match_robust.py",
    "test_region_collision.py",
    "test_thema.py",
    "test_vokabular.py",
]

@pytest.mark.parametrize("script", UNIT_SCRIPTS, ids=UNIT_SCRIPTS)
def test_standalone_unit_script(script: str) -> None:
    env = os.environ.copy()
    # Keep accidental integration/config discovery out of this local-only run.
    env.pop("DATABASE_URL", None)
    env.pop("DATABASE_URL_ADMIN", None)
    env.pop("FOERDER_ADMIN_TOKEN", None)
    env.pop("FOERDER_LLM_API_KEY", None)

    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / script)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        f"{script} failed (exit {result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
