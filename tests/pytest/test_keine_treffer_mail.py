"""Keine-Treffer-Mail: einmalige Rueckmeldung, wenn ein Profil leer ausgeht."""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "worker"))
sys.path.insert(0, os.path.dirname(__file__))

from src import versand_service as vs  # noqa: E402
from test_versand_blocker import _Conn  # noqa: E402

HEUTE = datetime.date.today()
ZUKUNFT = HEUTE + datetime.timedelta(days=30)
JETZT = datetime.datetime.now(datetime.timezone.utc)


def test_kennung_ueber_betreff():
    assert vs.ist_keine_treffer_mail(vs.KEINE_TREFFER_BETREFF)
    assert not vs.ist_keine_treffer_mail("Ihre persönlichen Fördermöglichkeiten")
    assert not vs.ist_keine_treffer_mail(None)


def test_body_nennt_widerrufsweg_und_absender(monkeypatch):
    monkeypatch.setenv("FOERDER_FROM", "team@example.org")
    body = vs.keine_treffer_body()
    assert "„Widerruf“" in body and "team@example.org" in body
    assert "keine davon" in body
    assert "- [" not in body  # keine Trefferliste


def test_blocker_ohne_trefferpruefung_fuer_keine_treffer_mail():
    gueltig = (JETZT, ZUKUNFT, "email", None)
    conn = _Conn(gueltig, hat_treffer=False)
    assert "keine offenen Treffer" in vs._versandblocker(conn, "k")
    assert vs._versandblocker(conn, "k", keine_treffer=True) is None
    # Kontaktbedingungen gelten weiterhin
    abgelaufen = _Conn((JETZT, HEUTE, "email", None), hat_treffer=False)
    assert vs._versandblocker(abgelaufen, "k", keine_treffer=True) == "Loeschfrist abgelaufen"


def test_worker_legt_keine_treffer_entwurf_nur_ohne_treffer_an(monkeypatch):
    import versand_worker as w

    monkeypatch.setattr(w, "matching_lauf", lambda conn, nur_kunde=None: 2)
    monkeypatch.setattr(w.vs, "offene_kunden", lambda conn: [])
    monkeypatch.setattr(w.vs, "kunden_ohne_versand", lambda conn: ["leer", "voll"])
    monkeypatch.setattr(w.vs, "treffer_fuer", lambda conn, k: [] if k == "leer" else [{"foerderung_id": "x"}])
    monkeypatch.setattr(w.vs, "offene_treffer_filtern", lambda t, kat: t)
    gespeichert = []

    def speichern(conn, kunde_id, betreff, body, kanal):
        gespeichert.append((kunde_id, betreff, kanal))
        return 99

    monkeypatch.setattr(w.vs, "entwurf_speichern", speichern)
    _, neu, akt = w.entwuerfe_anlegen(None, {"foerderungen": []})
    assert gespeichert == [("leer", vs.KEINE_TREFFER_BETREFF, "email")]
    assert neu == [{"versand_id": 99, "kunde_id": "leer", "anzahl_treffer": 0}]
    assert akt == []
