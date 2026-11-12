"""Haertung: Rate-Limit pro Client-IP, Feldlimits, Sicherheitsheader, CSP-taugliches Formular."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def m(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.delenv("FOERDER_BLOCKED_EMAIL_DOMAINS", raising=False)
    import app.main as api
    return importlib.reload(api)


class _Req:
    def __init__(self, host, headers=None):
        class C:  # noqa
            pass
        self.client = C()
        self.client.host = host
        self.headers = headers or {}


def test_ip_proxy_vertrauenswuerdig(m):
    assert m._client_ip(_Req("172.18.0.1", {"x-real-ip": "203.0.113.7"})) == "203.0.113.7"
    assert m._client_ip(_Req("127.0.0.1", {"x-real-ip": "203.0.113.8"})) == "203.0.113.8"


def test_ip_header_von_fremder_gegenstelle_ignoriert(m):
    assert m._client_ip(_Req("198.51.100.9", {"x-real-ip": "203.0.113.7"})) == "198.51.100.9"


def test_ip_muell_im_header_faellt_auf_peer_zurueck(m):
    assert m._client_ip(_Req("172.18.0.1", {"x-real-ip": "kein-ip"})) == "172.18.0.1"
    assert m._client_ip(_Req("172.18.0.1", {})) == "172.18.0.1"


def test_ipv6_wird_auf_64er_praefix_zusammengefasst(m):
    a = m._client_ip(_Req("172.18.0.1", {"x-real-ip": "2001:db8:1:2::1"}))
    b = m._client_ip(_Req("172.18.0.1", {"x-real-ip": "2001:db8:1:2:ffff::9"}))
    assert a == b == "2001:db8:1:2::/64"


def test_rate_limit_ist_pro_ip(m, monkeypatch):
    monkeypatch.setattr(m, "_speichere_profil", lambda p: "x")
    c = TestClient(m.app, client=("172.18.0.1", 5000))
    body = {"typ": "privat", "einwilligung": True}
    angreifer = {"X-Real-IP": "203.0.113.50"}
    codes = [c.post("/profile", json=body, headers=angreifer).status_code for _ in range(m.RATE_LIMIT + 2)]
    assert codes[-1] == 429
    # andere Besucherin ist nicht gesperrt
    assert c.post("/profile", json=body, headers={"X-Real-IP": "203.0.113.51"}).status_code != 429


def test_laengenlimits(m):
    P = m.ProfilIn
    m._pruefe_laengen(P(typ="privat", einwilligung=True, vorhaben=["a"] * 20))
    for p in (
        P(typ="privat", vorhaben=["a"] * 21),
        P(typ="privat", vorhaben=["a" * 101]),
        P(typ="privat", branche="x" * 201),
        P(typ="privat", anliegen="x" * 2001),
    ):
        with pytest.raises(m.HTTPException) as e:
            m._pruefe_laengen(p)
        assert e.value.status_code == 400
    m._pruefe_laengen(P(typ="privat", anliegen="x" * 2000))


def test_profile_zu_langes_feld_400(m, monkeypatch):
    monkeypatch.setattr(m, "_pruefe_intake_freigabe", lambda: None)
    c = TestClient(m.app)
    r = c.post("/profile", json={"typ": "privat", "einwilligung": True, "vorhaben": ["a"] * 500})
    assert r.status_code == 400


def test_sicherheitsheader_auch_bei_401(m):
    c = TestClient(m.app)
    for r in (c.get("/"), c.get("/formular"), c.get("/profiles")):
        h = r.headers
        assert h["strict-transport-security"].startswith("max-age=")
        csp = h["content-security-policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "'unsafe-inline'" not in csp.split("style-src")[0]
        assert h["x-content-type-options"] == "nosniff"


def test_formular_ohne_inline_script(m, monkeypatch):
    monkeypatch.setattr(m, "_intake_freigegeben", lambda: True)
    html = TestClient(m.app).get("/formular").text
    assert "<script>" not in html
    assert '/static/formular.js' in html
    assert 'id="anliegen-platzhalter"' in html


def test_formular_js_ausgeliefert(m):
    r = TestClient(m.app).get("/static/formular.js")
    assert r.status_code == 200 and "anliegen-platzhalter" in r.text
