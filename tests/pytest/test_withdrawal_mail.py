"""Widerrufs-Mails: Erkennung und Echtheitspruefung (ohne Netz/DB)."""
from email import message_from_string, policy

from tools import process_withdrawals as pw

HOSTINGER_PASS = (
    "Authentication-Results: fr-int-smtpin37.hostinger.io;\n"
    "\tdkim=pass header.d=gmail.com header.s=20260707 header.b=abc;\n"
    "\tdmarc=pass (policy=none) header.from=gmail.com;\n"
    "\tspf=pass smtp.mailfrom=kunde@gmail.com\n"
)


def _mail(kopf, from_="Kunde <Kunde@Gmail.com>", subject="Widerruf"):
    return message_from_string(
        f"{kopf}From: {from_}\nTo: team@foerdora.cloud\nSubject: {subject}\n"
        "Message-ID: <x1@mail.gmail.com>\n\nbitte loeschen\n",
        policy=policy.default,
    )


def test_betreff_erkennung():
    assert pw.ist_widerruf("Widerruf")
    assert pw.ist_widerruf("AW: widerruf meiner Einwilligung")
    assert pw.ist_widerruf("WIDERRUF")
    assert pw.ist_widerruf("Re: AW: Widerruf")
    assert pw.ist_widerruf("Widerrufen der Einwilligung")
    # erwaehnt, aber nicht eindeutig -> nur manuell pruefen, nie loeschen
    assert pw.betreff_art("Test Eingang (kein Widerruf)") == "unklar"
    assert pw.betreff_art("Frage zum Widerruf") == "unklar"
    assert pw.betreff_art("Ich widerrufe hiermit") == "unklar"
    assert pw.betreff_art("Frage zur Förderung") is None
    assert not pw.ist_widerruf("Frage zur Förderung")
    assert not pw.ist_widerruf(None)


def test_echter_widerruf_besteht():
    msg = _mail(HOSTINGER_PASS)
    addr = pw.absender_adresse(msg)
    assert addr == "kunde@gmail.com"
    assert pw.echtheit_fehler(msg, addr) is None


def test_ohne_pruefkopf_abgelehnt():
    msg = _mail("")
    assert pw.echtheit_fehler(msg, "kunde@gmail.com") == "kein Authentication-Results"


def test_dmarc_fail_abgelehnt():
    msg = _mail(HOSTINGER_PASS.replace("dmarc=pass", "dmarc=fail"))
    assert pw.echtheit_fehler(msg, "kunde@gmail.com") == "dmarc=fail"


def test_gefaelschter_kopf_unter_echtem_zaehlt_nicht():
    # Oberster (echter) Kopf sagt fail; ein mitgeschickter "pass"-Kopf darunter darf nicht helfen.
    echt = HOSTINGER_PASS.replace("dmarc=pass", "dmarc=fail")
    msg = _mail(echt + HOSTINGER_PASS)
    assert pw.echtheit_fehler(msg, "kunde@gmail.com") == "dmarc=fail"


def test_fremder_pruefserver_abgelehnt():
    msg = _mail(HOSTINGER_PASS.replace("fr-int-smtpin37.hostinger.io", "evil.example.com"))
    assert pw.echtheit_fehler(msg, "kunde@gmail.com") == "fremder Pruefserver"


def test_dmarc_domain_muss_zum_absender_passen():
    msg = _mail(HOSTINGER_PASS, from_="opfer@gmx.at")
    assert pw.echtheit_fehler(msg, "opfer@gmx.at") == "DMARC-Domain passt nicht zum Absender"


def test_mehrdeutiger_absender_abgelehnt():
    msg = _mail(HOSTINGER_PASS, from_="a@gmail.com, b@gmail.com")
    assert pw.absender_adresse(msg) is None


def test_db_ziel_pruefung():
    assert pw.db_ziel_ok("postgresql://u:p@db:5432/foerderradar", "foerderradar")
    assert not pw.db_ziel_ok("postgresql://u:p@db:5432/foerderradar?host=x", "foerderradar")
    assert not pw.db_ziel_ok("postgresql://u:p@db:5432/andere", "foerderradar")
    assert not pw.db_ziel_ok("mysql://u:p@db/foerderradar", "foerderradar")


def test_status_einmalig(tmp_path):
    pfad = tmp_path / "s" / "state.txt"
    assert pw.status_laden(pfad) == set()
    pw.status_merken(pfad, "abc")
    assert pw.status_laden(pfad) == {"abc"}


def test_absender_muss_betreiberadresse_sein(monkeypatch):
    monkeypatch.delenv("FOERDER_FROM", raising=False)
    assert not pw.absender_ok()
    monkeypatch.setenv("FOERDER_FROM", "baluopenclaw@gmail.com")
    assert not pw.absender_ok()
    monkeypatch.setenv("FOERDER_FROM", "team@foerdora.cloud")
    assert pw.absender_ok()
