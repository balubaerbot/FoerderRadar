"""Legacy DB script retired: coverage is in tests/pytest/test_db_integration.py.

Never execute this script: its historical implementation read project .env and
could write to the configured database. The pytest integration suite uses only
its fixture-owned disposable PostgreSQL database.
"""
raise SystemExit("Retired unsafe legacy DB test; use opt-in pytest integration suite")
