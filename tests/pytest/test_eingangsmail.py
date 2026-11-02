"""Eingangsbestaetigung: Text und Ablauf (DB-Helfer gemockt, kein Netz)."""

import pytest

from src import mail_texte as mt
from src import versand_service as vs

ADRESSE = "team@foerdora.cloud"
PROFIL_BETRIEB = {"typ": "betrieb", "region_grob": "Tirol", "branche": "Handel",
                  "mitarbeiterklasse": "5\u20139", "vorhaben": ["Digitalisierung", "Photovoltaik"]}


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
    monkeypatch.setattr(vs, "eingang_profil", lambda conn, k: dict(PROFIL_BETRIEB))
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


# --- Zusammenfassung (nur unkritische Angaben) ---------------------------

def test_zusammenfassung_betrieb():
    assert vs.eingang_zusammenfassung(PROFIL_BETRIEB) == [
        ("Anfrage als", "Unternehmen"), ("Bundesland", "Tirol"), ("Branche", "Handel"),
        ("Mitarbeitende", "5\u20139"), ("Vorhaben", "Digitalisierung, Photovoltaik"),
    ]


def test_zusammenfassung_privat_ohne_sensible_angaben():
    profil = {"typ": "sozial", "region_grob": "Wien", "branche": "Handel",
              "mitarbeiterklasse": "1\u20134",
              "vorhaben": ["Sanierung", "Heizkostenzuschuss", "Pflege & Betreuung",
                           "Mindestsicherung / Sozialhilfe", "Wohnbeihilfe", "sozial", "Sanierung"],
              # Felder, die eingang_profil gar nicht liest - duerfen nie durchrutschen:
              "einkommen_spanne": "unter 1.200 \u20ac", "pflegestufe": 3, "anliegen": "geheim"}
    z = vs.eingang_zusammenfassung(profil)
    assert z == [("Anfrage als", "Privatperson"), ("Bundesland", "Wien"), ("Vorhaben", "Sanierung")]


def test_zusammenfassung_bundesland_kuerzel():
    for wert, name in (("OÖ", "Oberösterreich"), ("NÖ", "Niederösterreich"),
                       ("Wien", "Wien"), ("Kärnten", "Kärnten")):
        z = vs.eingang_zusammenfassung({"typ": "privat", "region_grob": wert})
        assert ("Bundesland", name) in z


def test_zusammenfassung_unbekannte_werte_und_leer():
    assert vs.eingang_zusammenfassung(None) == []
    assert vs.eingang_zusammenfassung({"typ": "x", "region_grob": "<script>", "vorhaben": ["Frei"]}) == []


def test_body_mit_zusammenfassung(monkeypatch):
    monkeypatch.setenv("FOERDER_FROM", ADRESSE)
    body = vs.eingang_body(vs.eingang_zusammenfassung(PROFIL_BETRIEB))
    assert "Ihre Anfrage im \u00dcberblick:\n- Anfrage als: Unternehmen\n" in body
    assert "- Vorhaben: Digitalisierung, Photovoltaik\n" in body
    assert "aus Datenschutzgr\u00fcnden hier nicht an" in body
    assert body.endswith(mt.schluss(ADRESSE))
    assert "\u00dcberblick" not in vs.eingang_body([])


def _formular_listen():
    # app/main.py nur parsen, nicht importieren (Import laedt Env/KI-Konfiguration
    # und beeinflusst sonst andere Tests).
    import ast
    import pathlib
    quelle = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"
    listen = {}
    for knoten in ast.parse(quelle.read_text(encoding="utf-8")).body:
        if isinstance(knoten, ast.Assign) and isinstance(knoten.targets[0], ast.Name):
            try:
                listen[knoten.targets[0].id] = set(ast.literal_eval(knoten.value))
            except (ValueError, TypeError, SyntaxError):
                pass
    return listen


def test_whitelists_passen_zum_formular():
    f = _formular_listen()
    assert vs.EINGANG_BUNDESLAENDER == f["BUNDESLAENDER"]
    assert vs.EINGANG_BRANCHEN == f["BRANCHEN"]
    assert vs.EINGANG_MITARBEITERKLASSEN == f["MITARBEITERKLASSEN"]
    assert vs.EINGANG_VORHABEN == f["VORHABEN_OPTIONEN"]
    assert not vs.EINGANG_VORHABEN & f["BEDARF_OPTIONEN"]


def test_versand_nutzt_zusammenfassung(db):
    gesendet = []
    vs.eingang_verarbeiten(None, senden=True, limit=1,
                           sender=lambda adr, betreff, body: gesendet.append(body))
    assert gesendet and "- Bundesland: Tirol\n" in gesendet[0]
