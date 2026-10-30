import importlib

import pytest
from fastapi import HTTPException
from starlette.datastructures import FormData


def _api(monkeypatch):
    monkeypatch.setenv("FOERDER_TESTING", "1")
    import app.main as api
    return importlib.reload(api)


def _form(extra, consent):
    data = [("typ", "sozial")] + extra
    if consent:
        data.append(("besondere_daten_einwilligung", "ja"))
    return FormData(data)


def test_health_life_situation_dropped_without_opt_in(monkeypatch):
    api = _api(monkeypatch)
    for wert in api.GESUNDHEITS_LEBENSSITUATIONEN:
        p = api._profil_aus_formular(_form([("lebenssituation", wert)], consent=False))
        assert p.lebenssituation is None


def test_non_health_life_situation_kept_without_opt_in(monkeypatch):
    api = _api(monkeypatch)
    p = api._profil_aus_formular(_form([("lebenssituation", "Alleinerziehend")], consent=False))
    assert p.lebenssituation == "Alleinerziehend"


def test_health_bedarf_dropped_without_opt_in(monkeypatch):
    api = _api(monkeypatch)
    extra = [("bedarf", b) for b in api.GESUNDHEITS_BEDARF] + [("bedarf", "Heizkostenzuschuss")]
    p = api._profil_aus_formular(_form(extra, consent=False))
    assert not set(p.vorhaben) & api.GESUNDHEITS_BEDARF
    assert "Heizkostenzuschuss" in p.vorhaben


def test_health_values_kept_with_opt_in(monkeypatch):
    api = _api(monkeypatch)
    extra = [("lebenssituation", "Behinderung / Beeinträchtigung"), ("bedarf", "Barrierefreies Wohnen")]
    p = api._profil_aus_formular(_form(extra, consent=True))
    assert p.lebenssituation == "Behinderung / Beeinträchtigung"
    assert "Barrierefreies Wohnen" in p.vorhaben


def test_options_with_health_relevance_exist_in_form_lists(monkeypatch):
    api = _api(monkeypatch)
    assert api.GESUNDHEITS_LEBENSSITUATIONEN <= set(api.LEBENSSITUATIONEN)
    assert api.GESUNDHEITS_BEDARF <= set(api.BEDARF_OPTIONEN)


@pytest.mark.parametrize("felder", [
    {"lebenssituation": "Pflege eines Angehörigen"},
    {"vorhaben": ["Pflege & Betreuung"]},
    {"behinderung": True},
])
def test_api_validation_requires_opt_in_for_health_values(monkeypatch, felder):
    api = _api(monkeypatch)
    assert api._hat_gesundheitsangaben(
        felder.get("pflegestufe"), felder.get("behinderung"),
        felder.get("lebenssituation"), felder.get("vorhaben"),
    )


def test_no_health_values_means_no_requirement(monkeypatch):
    api = _api(monkeypatch)
    assert not api._hat_gesundheitsangaben(None, None, "Pension", ["Heizkostenzuschuss"])
