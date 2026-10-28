"""Privacy fail-closed behaviour; these tests never use a database."""

import importlib
from pathlib import Path
from types import SimpleNamespace

from starlette.datastructures import FormData
from fastapi.testclient import TestClient


def test_retention_approval_uses_fixed_two_year_policy(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    for key, value in {
        "FOERDER_INTAKE_ENABLED": "1",
        "FOERDER_PRIVACY_REVIEWED": "1",
        "FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED": "1",
        "FOERDER_WITHDRAWAL_PROCESS_CONFIRMED": "1",
        "FOERDER_RETENTION_SCHEMA_VERIFIED": "1",
        "FOERDER_PURGE_SCHEDULE_VERIFIED": "1",
        "FOERDER_LEGACY_RETENTION_REVIEWED": "1",
        "FOERDER_DATA_CONTROLLER": "Testverantwortlicher",
        "FOERDER_PRIVACY_CONTACT": "privacy@example.invalid",
        "FOERDER_CONSENT_VERSION": "test-v1",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("FOERDER_RETENTION_DAYS", raising=False)
    import app.main as api
    api = importlib.reload(api)
    try:
        assert api._intake_freigegeben() is True
    finally:
        importlib.reload(api)


def test_public_intake_is_closed_without_privacy_approval(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    for key in (
        "FOERDER_INTAKE_ENABLED", "FOERDER_PRIVACY_REVIEWED",
        "FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED",
        "FOERDER_WITHDRAWAL_PROCESS_CONFIRMED", "FOERDER_RETENTION_SCHEMA_VERIFIED",
        "FOERDER_PURGE_SCHEDULE_VERIFIED", "FOERDER_DATA_CONTROLLER",
        "FOERDER_LEGACY_RETENTION_REVIEWED",
        "FOERDER_PRIVACY_CONTACT", "FOERDER_CONSENT_VERSION",
    ):
        monkeypatch.delenv(key, raising=False)
    import app.main as api
    api = importlib.reload(api)
    client = TestClient(api.app)
    assert client.get("/formular").status_code == 503
    assert client.post("/formular", data={"name": "not stored"}).status_code == 503
    assert client.post("/profile", json={"typ": "privat", "einwilligung": True}).status_code == 503


def test_sensitive_social_fields_are_only_retained_for_social_tab(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    import app.main as api
    api = importlib.reload(api)

    ordinary = api._profil_aus_formular(FormData({
        "typ": "privat", "pflegestufe": "5", "behinderung": "ja",
    }))
    social_without_opt_in = api._profil_aus_formular(FormData({
        "typ": "sozial", "pflegestufe": "5", "behinderung": "ja",
    }))
    social_with_opt_in = api._profil_aus_formular(FormData({
        "typ": "sozial", "besondere_daten_einwilligung": "ja",
        "pflegestufe": "5", "behinderung": "ja",
    }))

    assert ordinary.pflegestufe is None
    assert ordinary.behinderung is None
    assert social_without_opt_in.pflegestufe is None
    assert social_without_opt_in.behinderung is None
    assert social_with_opt_in.pflegestufe == 5
    assert social_with_opt_in.behinderung is True
    assert social_with_opt_in.besondere_daten_einwilligung is True


def test_privacy_contact_and_optional_sensitive_field_scope_are_visible():
    root = Path(__file__).resolve().parents[2]
    form = (root / "app/templates/formular.html").read_text()
    privacy = (root / "app/templates/datenschutz.html").read_text()
    css = (root / "app/static/style.css").read_text()

    assert form.count("mailto:team@foerdora.cloud") == 1
    assert privacy.count("mailto:team@foerdora.cloud") >= 1
    assert 'mailto:team@foerdora.cloud' in form
    assert "Name" in form and "Namen" in privacy
    assert "Fördermöglichkeiten verwendet" in form
    assert "zwei Jahren" in form and "Löschung kann jederzeit" in form
    assert "unabhängig vom Alter" in privacy and "zwei Jahre" in privacy
    assert "INTERVAL '2 years'" in (root / "app/main.py").read_text()
    assert "INTERVAL '2 years'" in (root / "db/init.sql").read_text()
    assert "INTERVAL '2 years'" in (root / "db/migrations/20261018_consent_retention_metadata.sql").read_text()
    assert 'name="besondere_daten_einwilligung" value="ja"' in form
    assert 'class="field nur-sozial"><label for="pflegestufe"' in form
    assert 'class="field nur-sozial"><label for="behinderung"' in form
    assert 'body:has(input[name="typ"][value="sozial"]:checked) .nur-sozial{display:block}' in css
    assert 'body:has(input[name="besondere_daten_einwilligung"]:checked) .nur-besondere-daten{display:grid}' in css


def test_compose_explicitly_disables_uvicorn_proxy_header_trust():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    assert "--no-proxy-headers" in compose
    assert "--forwarded-allow-ips=*" not in compose


def test_rate_limit_identity_ignores_forwarded_for_unless_proxy_trust_is_enabled(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    import app.main as api
    importlib.reload(api)

    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.99, 10.0.0.5"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert api._client_ip(request) == "127.0.0.1"


def test_client_ip_ignores_forwarded_for_even_if_legacy_flag_is_set(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.setenv("FOERDER_TRUST_PROXY", "1")
    import app.main as api
    importlib.reload(api)

    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.99"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    assert api._client_ip(request) == "127.0.0.1"


def test_rate_limit_cannot_be_bypassed_by_rotating_forwarded_for(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.setenv("FOERDER_INTAKE_ENABLED", "1")
    monkeypatch.setenv("FOERDER_PRIVACY_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_LEGACY_RETENTION_REVIEWED", "1")
    monkeypatch.setenv("FOERDER_DATA_CONTROLLER", "Testverantwortlicher")
    monkeypatch.setenv("FOERDER_PRIVACY_CONTACT", "privacy@example.invalid")
    monkeypatch.setenv("FOERDER_CONSENT_VERSION", "test-v1")
    monkeypatch.setenv("FOERDER_WITHDRAWAL_PROCESS_CONFIRMED", "1")
    monkeypatch.setenv("FOERDER_RETENTION_SCHEMA_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_PURGE_SCHEDULE_VERIFIED", "1")
    monkeypatch.setenv("FOERDER_TRUST_PROXY", "1")
    import app.main as api
    importlib.reload(api)

    def accept_profile(_profile):
        return "00000000-0000-0000-0000-000000000001"

    monkeypatch.setattr(api, "_speichere_profil", accept_profile)
    payload = {"typ": "betrieb", "einwilligung": True}
    responses = [
        TestClient(api.app).post(
            "/profile", json=payload,
            headers={"X-Forwarded-For": f"203.0.113.{n}"},
        )
        for n in range(6)
    ]
    assert [r.status_code for r in responses] == [200, 200, 200, 200, 200, 429]


def test_health_is_not_available_without_admin_token(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.setenv("FOERDER_ADMIN_TOKEN", "test-token")
    import app.main as api
    importlib.reload(api)

    response = TestClient(api.app).get("/health")
    assert response.status_code == 401
    assert response.json() == {"detail": "nicht autorisiert"}


def test_health_hides_database_role_and_error_details(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    import app.main as api
    importlib.reload(api)
    monkeypatch.setattr(api, "db", lambda: (_ for _ in ()).throw(RuntimeError("secret db host")))

    assert api.health() == {"status": "degraded"}


def test_sms_submission_is_rejected_before_database_write(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    for key, value in {
        "FOERDER_INTAKE_ENABLED": "1",
        "FOERDER_PRIVACY_REVIEWED": "1",
        "FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED": "1",
        "FOERDER_LEGACY_RETENTION_REVIEWED": "1",
        "FOERDER_DATA_CONTROLLER": "Testverantwortlicher",
        "FOERDER_PRIVACY_CONTACT": "privacy@example.invalid",
        "FOERDER_CONSENT_VERSION": "test-v1",
        "FOERDER_WITHDRAWAL_PROCESS_CONFIRMED": "1",
        "FOERDER_RETENTION_SCHEMA_VERIFIED": "1",
        "FOERDER_PURGE_SCHEDULE_VERIFIED": "1",
    }.items():
        monkeypatch.setenv(key, value)
    import app.main as api
    importlib.reload(api)

    response = TestClient(api.app).post(
        "/profile",
        json={"typ": "betrieb", "kanal": "sms", "telefon": "+431234567", "einwilligung": True},
    )
    assert response.status_code == 400
    assert "SMS" in response.json()["detail"]


def test_sms_is_not_offered_in_intake_form():
    form = (Path(__file__).resolve().parents[2] / "app/templates/formular.html").read_text()
    assert 'option value="sms"' not in form
    assert "SMS" not in form


def test_customer_can_request_deletion_at_any_time():
    root = Path(__file__).resolve().parents[2]
    form = (root / "app/templates/formular.html").read_text()
    privacy = (root / "app/templates/datenschutz.html").read_text()
    assert "Löschung kann jederzeit per E-Mail beantragt werden" in form and "innerhalb des ersten Jahres" not in form
    assert "jederzeit gestellt werden" in privacy and "unabhängig vom Alter" in privacy
