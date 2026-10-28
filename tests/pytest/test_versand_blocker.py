"""Regression: _versandblocker muss mit allen Kontakt-/Match-Zustaenden laufen.

Hintergrund: Commit 3b9849d hatte _kontakt_status versehentlich entfernt; jeder
echte Versand brach mit NameError ab, ohne dass ein Test das bemerkte.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src import versand_service as vs


class _Cur:
    def __init__(self, kontakt, hat_treffer):
        self.kontakt, self.hat_treffer, self._last = kontakt, hat_treffer, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self._last = sql

    def fetchone(self):
        if "FROM kontakt" in self._last:
            return self.kontakt
        if "FROM match" in self._last:
            return (1,) if self.hat_treffer else None
        raise AssertionError(self._last)


class _Conn:
    def __init__(self, kontakt, hat_treffer=True):
        self.kontakt, self.hat_treffer = kontakt, hat_treffer

    def cursor(self):
        return _Cur(self.kontakt, self.hat_treffer)


HEUTE = datetime.date.today()
ZUKUNFT = HEUTE + datetime.timedelta(days=30)
JETZT = datetime.datetime.now()


def test_gueltiger_kontakt_hat_keinen_blocker():
    assert vs._versandblocker(_Conn((JETZT, ZUKUNFT, "email", None)), "k") is None


def test_kontakt_status_liefert_vier_spalten():
    assert vs._kontakt_status(_Conn((JETZT, ZUKUNFT, "email", None)), "k") == (JETZT, ZUKUNFT, "email", None)


def test_blocker_gruende():
    f = lambda k, t=True: vs._versandblocker(_Conn(k, t), "k")
    assert f(None) is not None
    assert f((None, ZUKUNFT, "email", None)) == "Einwilligung fehlt"
    assert f((JETZT, ZUKUNFT, "email", JETZT)) == "Einwilligung widerrufen"
    assert f((JETZT, None, "email", None)) == "Loeschfrist unbekannt"
    assert f((JETZT, HEUTE, "email", None)) == "Loeschfrist abgelaufen"
    assert "nicht versendbar" in f((JETZT, ZUKUNFT, "post", None))
    assert "keine offenen Treffer" in f((JETZT, ZUKUNFT, "email", None), False)
