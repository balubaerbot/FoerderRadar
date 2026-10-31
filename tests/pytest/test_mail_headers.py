"""Kopfzeilen der Kunden-Mail (Zustellbarkeit + Widerrufsweg)."""
from email.message import EmailMessage
from email.utils import parseaddr

from src import versand_service as vs


def _msg(monkeypatch, **env):
    monkeypatch.setenv("FOERDER_FROM", "team@foerdora.cloud")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    msg = EmailMessage()
    vs.setze_kopfzeilen(msg, "kunde@example.org", "Betreff")
    msg.set_content("Text")
    return msg


def test_from_mit_anzeigename(monkeypatch):
    msg = _msg(monkeypatch)
    name, addr = parseaddr(str(msg["From"]))
    assert addr == "team@foerdora.cloud"
    assert name == "Fördora"


def test_anzeigename_konfigurierbar(monkeypatch):
    msg = _msg(monkeypatch, FOERDER_FROM_NAME="Test")
    assert parseaddr(str(msg["From"]))[0] == "Test"


def test_message_id_eigene_domain_und_date(monkeypatch):
    msg = _msg(monkeypatch)
    assert str(msg["Message-ID"]).endswith("@foerdora.cloud>")
    assert msg["Date"]


def test_list_unsubscribe_ist_widerruf_an_betreiber(monkeypatch):
    msg = _msg(monkeypatch)
    assert msg["List-Unsubscribe"] == "<mailto:team@foerdora.cloud?subject=Widerruf>"
    assert msg["To"] == "kunde@example.org"
    # Header muessen serialisierbar sein (Umlaut im Namen -> RFC 2047)
    assert "Message-ID" in msg.as_string()
