#!/usr/bin/env python3
"""Regionshinweis: Bundeslaender ohne Landesprogramme bekommen einen festen Mailhinweis.

Lauf:  python3 tests/test_region_hinweis.py
"""
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import region  # noqa: E402
from src import versand_service as vs  # noqa: E402

KATALOG = {"foerderungen": [{
    "id": "kmu_digital", "name": "KMU.DIGITAL", "stelle": "Bund / aws",
    "betrag": "bis zu 50.000 Euro", "frist": "31.12.2026", "status": "offen",
    "quelle": "https://www.aws.at"}]}
TREFFER = [{"foerderung_id": "kmu_digital", "kategorie": "top"}]


def test_luecke():
    assert region.landeskatalog_luecke("Wien")
    assert region.landeskatalog_luecke("Steiermark")
    assert region.landeskatalog_luecke("noe")
    assert not region.landeskatalog_luecke("Oberoesterreich")
    assert not region.landeskatalog_luecke("ooe")
    assert not region.landeskatalog_luecke("Tirol")
    assert not region.landeskatalog_luecke(None)
    assert not region.landeskatalog_luecke("Bund")


def _body(reg):
    prof = {"typ": "betrieb", "region_grob": reg, "thema": ["wirtschaft"]}
    return vs.nachricht_bauen(prof, TREFFER, KATALOG, transport=None)[1]


def test_mail_hinweis():
    assert vs.LANDES_HINWEIS in _body("Wien")
    assert vs.LANDES_HINWEIS not in _body("Ober\u00f6sterreich")
    assert vs.LANDES_HINWEIS not in _body("Tirol")
    assert _body("Wien").count(vs.LANDES_HINWEIS) == 1


if __name__ == "__main__":
    test_luecke(); test_mail_hinweis(); print("OK")
