"""Anmelde-Spam: Domain-Sperre und Honeypot (ohne DB, speichern wird gemockt)."""
import os

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def m(monkeypatch):
    """app.main isoliert laden: FOERDER_TESTING=1 verhindert, dass .env in os.environ gelesen wird."""
    monkeypatch.setenv("FOERDER_TESTING", "1")
    import app.main as api
    return importlib.reload(api)


def test_domain_sperre(m):
    assert m._email_domain_gesperrt("x@fldubai.com")
    assert m._email_domain_gesperrt("x@FLDubai.com")
    assert m._email_domain_gesperrt("x@mail.fldubai.com")
    assert not m._email_domain_gesperrt("x@gmail.com")
    assert not m._email_domain_gesperrt("x@notfldubai.com")
    assert not m._email_domain_gesperrt(None)


def test_domain_sperre_per_env(m, monkeypatch):
    monkeypatch.setenv("FOERDER_BLOCKED_EMAIL_DOMAINS", "spam.example, Bot.test")
    assert m._email_domain_gesperrt("a@spam.example")
    assert m._email_domain_gesperrt("a@bot.test")


def _post(m, monkeypatch, extra):
    gespeichert = []
    monkeypatch.setattr(m, "_pruefe_intake_freigabe", lambda: None)
    monkeypatch.setattr(m, "_speichere_profil", lambda p: gespeichert.append(p) or "id")
    form = {"typ": "sozial", "name": "Max Muster", "email": "max@gmail.com",
            "einwilligung": "ja", "region_grob_s": "Tirol"}
    form.update(extra)
    r = TestClient(m.app).post("/formular", data=form, follow_redirects=False)
    return r, gespeichert


def test_honeypot_speichert_nichts(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {m.HONEYPOT_FELD: "http://spam"})
    assert r.status_code == 303 and r.headers["location"].startswith("/danke")
    assert gespeichert == []


def test_gesperrte_domain_speichert_nichts(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {"email": "abc@fldubai.com"})
    assert r.status_code == 303 and r.headers["location"].startswith("/danke")
    assert gespeichert == []


def test_normale_anmeldung_wird_gespeichert(m, monkeypatch):
    r, gespeichert = _post(m, monkeypatch, {})
    assert r.status_code == 303
    assert len(gespeichert) == 1
