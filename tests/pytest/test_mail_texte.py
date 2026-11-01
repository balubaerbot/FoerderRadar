"""Feste Mailbausteine: Grussformel, Widerrufshinweis, 'k.A.'-Anzeige (ohne Netz/DB)."""

from src import ki_mapping as ki
from src import mail_texte as mt
from src import versand_service as vs

ADRESSE = "team@foerdora.cloud"

KATALOG = {"foerderungen": [
    {"id": "f1", "name": "Schülerbeihilfe", "stelle": "BMB",
     "betrag": "k.A. (einkommensabhängige Transferzahlung); Heimfahrtbeihilfe 19 € bis 58 €",
     "frist": "31. Dezember", "status": "offen", "quelle": "https://example.org/1"},
    {"id": "f2", "name": "Schulstartgeld", "stelle": "BKA",
     "betrag": "121,40 Euro", "frist": "automatisch", "status": "offen",
     "quelle": "https://example.org/2"},
]}
TREFFER = [{"foerderung_id": "f1", "kategorie": "top"},
           {"foerderung_id": "f2", "kategorie": "top"}]


def test_betrag_anzeige_ka_mit_erlaeuterung():
    assert mt.betrag_anzeige("k.A. (einkommensabhängig)") == \
        "Höhe nicht pauschal angegeben (einkommensabhängig)"


def test_betrag_anzeige_ka_nackt_und_varianten():
    assert mt.betrag_anzeige("k.A.") == "Höhe nicht pauschal angegeben, siehe Details"
    assert mt.betrag_anzeige("k. A.") == "Höhe nicht pauschal angegeben, siehe Details"


def test_betrag_anzeige_laesst_normale_werte_und_ist_idempotent():
    assert mt.betrag_anzeige("121,40 Euro") == "121,40 Euro"
    einmal = mt.betrag_anzeige("k.A. (x)")
    assert mt.betrag_anzeige(einmal) == einmal
    assert mt.betrag_anzeige(None) is None


def test_schluss_enthaelt_widerruf_und_gruss():
    s = mt.schluss(ADRESSE)
    assert "Betreff „Widerruf“ an team@foerdora.cloud" in s
    assert s.endswith("Freundliche Grüße\nIhr Fördora-Team")


def test_vorlage_treffer_mail(monkeypatch):
    monkeypatch.setenv("FOERDER_FROM", ADRESSE)
    betreff, body = vs._nachricht_bauen_roh({}, TREFFER, KATALOG, transport=None)
    assert betreff == "Ihre passenden Förderungen (2)"
    assert "k.A." not in body
    assert "Leistung: Höhe nicht pauschal angegeben (einkommensabhängige" in body
    assert "Betreff „Widerruf“ an team@foerdora.cloud" in body
    assert body.endswith("Ihr Fördora-Team")
    assert "Foerdora" not in body


def test_llm_treffer_mail_bekommt_festen_schluss():
    rahmen = {"betreff": "x", "einleitung": "Einleitung.", "hinweise": {},
              "abschluss": "Viel Erfolg."}
    treffer = [{"foerderung_id": "f1", "kategorie": "top", "name": "A", "stelle": "B",
                "betrag": "k.A.", "frist": "-", "status": "offen", "quelle": "q"}]
    body = ki._mail_body_bauen(rahmen, treffer, mt.schluss(ADRESSE))
    assert "Leistung: Höhe nicht pauschal angegeben, siehe Details" in body
    assert "Viel Erfolg.\n\nMöchten Sie keine weiteren Nachrichten" in body
    assert body.endswith("Freundliche Grüße\nIhr Fördora-Team")


def test_keine_treffer_mail_gleicher_schluss(monkeypatch):
    monkeypatch.setenv("FOERDER_FROM", ADRESSE)
    assert vs.keine_treffer_body().endswith(mt.schluss(ADRESSE))
