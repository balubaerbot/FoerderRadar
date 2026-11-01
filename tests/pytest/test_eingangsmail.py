"""Eingangsbestaetigung: Text und Ablauf (DB-Helfer gemockt, kein Netz)."""

import pytest

from src import mail_texte as mt
from src import versand_service as vs

ADRESSE = "team@foerdora.cloud"


def test_eingang_body_fest_und_ohne_profildaten(monkeypatch):
    monkeypatch.setenv("FOERDER_FROM", ADRESSE)
    body = vs.eingang_body()
    assert "Ihre Angaben sind bei uns eingegangen" in body
    assert "innerhalb von 24 Stunden" in body
    assert body.endswith(mt.schluss(ADRESSE))
    for verboten in ("Einkommen", "Behinderung", "Pflegestufe", "Foerdora"):
        assert verboten not in body
    assert vs.EINGANG_BETREFF != vs.KEINE_TREFFER_BETREFF


@pytest.fixture
def db(monkeypatch):
    zustand = {"status": {}, "offen": None, "kuerzlich": set()}
    kandidaten = [("k1", "a@example.org"), ("k2", "b@example.org"), ("k3", "c@example.org")]
    monkeypatch.setattr(vs, "eingang_offen_anzahl",
                        lambda conn: zustand["offen"] if zustand["offen"] is not None else len(kandidaten))
    monkeypatch.setattr(vs, "eingang_kandidaten", lambda conn, limit=20: kandidaten[:limit])
    monkeypatch.setattr(vs, "_eingang_adresse_kuerzlich_bestaetigt",
                        lambda conn, k, e: k in zustand["kuerzlich"])

    def status(conn, k, s, nur_wenn=None):
        if nur_wenn == "offen" and k in zustand["status"]:
            return False
        zustand["status"][k] = s
        return True
    monkeypatch.setattr(vs, "_eingang_status", status)
    return zustand


def test_dry_run_aendert_nichts_und_sendet_nicht(db):
    gesendet = []
    erg = vs.eingang_verarbeiten(None, senden=False, sender=lambda *a: gesendet.append(a))
    assert gesendet == [] and db["status"] == {}
    assert len(erg["zeilen"]) == 3
    klar = ("a@example.org", "b@example.org", "c@example.org")
    assert not any(k in z for z in erg["zeilen"] for k in klar)


def test_send_ok_fehler_und_sperre(db):
    db["kuerzlich"].add("k2")
    gesendet = []

    def sender(to, betreff, body):
        if to.startswith("c@"):
            raise RuntimeError("smtp kaputt fuer c@example.org")
        gesendet.append((to, betreff))

    erg = vs.eingang_verarbeiten(None, senden=True, sender=sender)
    assert gesendet == [("a@example.org", vs.EINGANG_BETREFF)]
    assert db["status"] == {"k1": "gesendet", "k2": "uebersprungen", "k3": "fehler"}
    assert (erg["gesendet"], erg["uebersprungen"], erg["fehler"]) == (1, 1, 1)
    klar = ("a@example.org", "b@example.org", "c@example.org")
    assert not any(k in z for z in erg["zeilen"] for k in klar)


def test_bereits_geclaimt_wird_nicht_doppelt_gesendet(db):
    db["status"]["k1"] = "sendet"
    gesendet = []
    vs.eingang_verarbeiten(None, senden=True, sender=lambda to, b, t: gesendet.append(to))
    assert "a@example.org" not in gesendet


def test_andrang_wird_gemeldet(db):
    db["offen"] = 50
    erg = vs.eingang_verarbeiten(None, senden=False, limit=2)
    assert erg["andrang"] is True and len(erg["zeilen"]) == 2
