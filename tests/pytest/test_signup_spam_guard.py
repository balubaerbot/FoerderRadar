"""Anmelde-Spam: Domain-Sperre und Honeypot (ohne DB, speichern wird gemockt)."""
import importlib
import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def m(monkeypatch):
    """app.main isoliert laden: FOERDER_TESTING=1 verhindert, dass .env in os.environ gelesen wird."""
    monkeypatch.setenv("FOERDER_TESTING", "1")
    monkeypatch.delenv("FOERDER_BLOCKED_EMAIL_DOMAINS", raising=False)
    import app.main as api
    return importlib.reload(api)


def test_domain_sperre(m):
    assert m._email_domain_gesperrt("x@fldubai.com")
    assert m._email_domain_gesperrt("x@FLDubai.com")
    assert m._email_domain_gesperrt("x@mail.fldubai.com")
    assert m._email_domain_gesperrt("x+tag@fldubai.com")
    assert not m._email_domain_gesperrt("x@gmail.com")
    assert not m._email_domain_gesperrt("x@notfldubai.com")
    assert not m._email_domain_gesperrt("x@evilfldubai.com")
    assert not m._email_domain_gesperrt("x@fldubai.com.evil.org")
    assert not m._email_domain_gesperrt(None)
    assert not m._email_domain_gesperrt("")


@pytest.mark.parametrize("email", [
    "x@fldubai.com.",            # Trailing Dot (FQDN)
    "x@fldubai.com:25",          # Port
    "x@[fldubai.com]",           # Klammern
    "x@ｆｌｄｕｂａｉ.com",        # Fullwidth
    "x@fld​ubai.com",       # Zero-Width-Space
    "x@ FLDUBAI.com ",           # Leerzeichen/Gross
    "x@a.fldubai.com.",          # Subdomain + Trailing Dot
])
def test_domain_sperre_umgehungen(m, email):
    assert m._email_domain_gesperrt(email)


def test_domain_sperre_per_env(m, monkeypatch):
    monkeypatch.setenv("FOERDER_BLOCKED_EMAIL_DOMAINS", "spam.example, Bot.test, @at.example, .dot.example, *.star.example, ,,")
    for d in ("spam.example", "bot.test", "at.example", "dot.example", "star.example"):
        assert m._email_domain_gesperrt(f"a@{d}"), d
    assert not m._email_domain_gesperrt("a@gmail.com")


def test_domain_sperre_leere_env(m, monkeypatch):
    monkeypatch.setenv("FOERDER_BLOCKED_EMAIL_DOMAINS", "")
    assert "" not in m._gesperrte_domains()
    assert not m._email_domain_gesperrt("a@gmail.com")
    monkeypatch.setenv("FOERDER_BLOCKED_EMAIL_DOMAINS", " , ,")
    assert "" not in m._gesperrte_domains()
    assert not m._email_domain_gesperrt("a@gmail.com")


def _post(m, monkeypatch, extra, files=None):
    gespeichert = []
    monkeypatch.setattr(m, "_pruefe_intake_freigabe", lambda: None)
    monkeypatch.setattr(m, "_speichere_profil", lambda p: gespeichert.append(p) or "id")
    form = {"typ": "sozial", "name": "Max Muster", "email": "max@gmail.com",
            "einwilligung": "ja", "region_grob_s": "Tirol"}
    form.update(extra)
    r = TestClient(m.app).post("/formular", data=form, files=files, follow_redirects=False)
    return r, gespeichert


def test_honeypot_feldname_ist_kein_autofill_kandidat(m):
    assert m.HONEYPOT_FELD not in {"website", "url", "homepage", "email", "phone", "name"}


def test_formular_rendert_honeypot_aus_konstante(m, monkeypatch):
    monkeypatch.setattr(m, "_pruefe_intake_freigabe", lambda: None)
    html = TestClient(m.app).get("/formular").text
    assert f'name="{m.HONEYPOT_FELD}"' in html
    assert "inert" in html


def test_honeypot_speichert_nichts(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {m.HONEYPOT_FELD: "http://spam"})
    assert r.status_code == 303 and r.headers["location"].startswith("/danke")
    assert gespeichert == []


@pytest.mark.parametrize("wert", ["", "   "])
def test_leerer_honeypot_ist_normale_anmeldung(m, monkeypatch, wert):
    r, gespeichert = _post(m, monkeypatch, {m.HONEYPOT_FELD: wert})
    assert r.status_code == 303
    assert len(gespeichert) == 1


def test_honeypot_als_datei_ist_kein_500(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {}, files={m.HONEYPOT_FELD: ("x.txt", b"x")})
    assert r.status_code == 303 and r.headers["location"].startswith("/danke")
    assert gespeichert == []


def test_gesperrte_domain_speichert_nichts(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {"email": "abc@fldubai.com"})
    assert r.status_code == 303 and r.headers["location"].startswith("/danke")
    assert gespeichert == []


def test_gesperrte_domain_trailing_dot_speichert_nichts(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {"email": "abc@fldubai.com."})
    assert r.status_code == 303 and gespeichert == []


def test_normale_anmeldung_wird_gespeichert(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {})
    assert r.status_code == 303
    assert len(gespeichert) == 1


def test_kein_orakel_bei_ungueltiger_eingabe(m, monkeypatch):
    """Ohne Einwilligung antworten Spam- und Normalpfad gleich (400), nicht 303 vs. 400."""
    normal, _ = _post(m, monkeypatch, {"einwilligung": ""})
    spam, gespeichert = _post(m, monkeypatch, {"einwilligung": "", "email": "abc@fldubai.com"})
    honey, _ = _post(m, monkeypatch, {"einwilligung": "", m.HONEYPOT_FELD: "x"})
    assert normal.status_code == spam.status_code == honey.status_code == 400
    assert gespeichert == []


def test_log_enthaelt_nur_grund_keine_pii(m, monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger="foerder.spam"):
        _post(m, monkeypatch, {"email": "geheim@fldubai.com", "name": "Erika Geheim"})
        _post(m, monkeypatch, {m.HONEYPOT_FELD: "x", "name": "Erika Geheim"})
    text = caplog.text
    assert "reason=domain" in text and "reason=honeypot" in text
    assert "geheim" not in text.lower() and "fldubai" not in text.lower() and "Erika" not in text


def test_api_pfad_sperrt_domain_mit_generischer_meldung(m, monkeypatch):
    monkeypatch.setattr(m, "_pruefe_intake_freigabe", lambda: None)
    client = TestClient(m.app)
    body = {"typ": "privat", "einwilligung": True, "kanal": "email", "email": "x@fldubai.com", "name": "A"}
    r = client.post("/profile", json=body)
    assert r.status_code == 400
    ungueltig = client.post("/profile", json={**body, "email": "kein-format"})
    assert ungueltig.status_code == 400
    assert r.json()["detail"] == ungueltig.json()["detail"]
    assert "fldubai" not in r.text and "Domain" not in r.text
