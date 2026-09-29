"""Tests fuer das KI-Mapping (Phase 2) - Freitext -> grobe Achse.

Kein Netz: der HTTP-Transport wird als Stub injiziert. Geprueft werden die
Sicherheits-Eigenschaften, auf die es ankommt:
  * Das LLM kann NUR erlaubte Werte liefern (Allowlist-Filter)
  * Jeder Fehler/Timeout/kaputtes JSON -> fail-soft (None), nie eine Exception
  * Ohne API-Key wird gar nicht erst gesendet
  * Chips-Heuristik + KI werden vereinigt (KI ergaenzt nur)
  * Der Freitext wird auf MAX_ZEICHEN begrenzt (Kosten/Abuse)

Lauf:  python3 tests/test_ki_mapping.py
"""
import os
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import ki_mapping as ki  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def _antwort(inhalt):
    """Baut eine OpenAI-kompatible Antwort mit gegebener content-Zeichenkette."""
    return {"choices": [{"message": {"content": inhalt}}]}


def _stub(inhalt, aufrufe=None):
    def t(url, payload, headers, timeout):
        if aufrufe is not None:
            aufrufe.append({"url": url, "payload": payload, "headers": headers})
        return _antwort(inhalt)
    return t


print("KI-Mapping")

# --- Allowlist / Validierung ----------------------------------------------
v = ki.validiere_antwort({"zielgruppe": "privat", "thema": ["sozial", "energie"]})
check("gueltige Antwort wird uebernommen", v == {"zielgruppe": "privat", "thema": ["sozial", "energie"]})

v = ki.validiere_antwort({"zielgruppe": "bundeskanzler", "thema": ["sozial"]})
check("unbekannte zielgruppe wird verworfen", v["zielgruppe"] is None)

v = ki.validiere_antwort({"zielgruppe": "privat", "thema": ["sozial", "quatsch", "energie"]})
check("unbekanntes thema wird verworfen", v["thema"] == ["sozial", "energie"])

v = ki.validiere_antwort({"zielgruppe": "privat", "thema": ["sozial", "sozial"]})
check("thema-Duplikate werden dedupliziert", v["thema"] == ["sozial"])

v = ki.validiere_antwort({"zielgruppe": "BETRIEB", "thema": "SOZIAL"})
check("Gross/klein + Einzelstring werden toleriert",
      v == {"zielgruppe": None, "thema": ["sozial"]})

check("nicht-dict -> None", ki.validiere_antwort(["privat"]) is None)
check("fehlendes thema -> leere Liste",
      ki.validiere_antwort({"zielgruppe": "privat"}) == {"zielgruppe": "privat", "thema": []})

# --- JSON-Extraktion --------------------------------------------------------
check("Code-Fence wird entfernt",
      ki._json_aus_text('```json\n{"zielgruppe":"privat","thema":["sozial"]}\n```')["zielgruppe"] == "privat")
check("Text vor dem JSON stoert nicht",
      ki._json_aus_text('Klar: {"zielgruppe":"privat","thema":[]}')["zielgruppe"] == "privat")
check("kaputtes JSON -> None", ki._json_aus_text("nur gequatsche") is None)

# --- mappe_anliegen mit Stub ------------------------------------------------
r = ki.mappe_anliegen("Ich pflege meine Mutter, die Heizkosten sind kaum leistbar.",
                      typ="privat", transport=_stub('{"zielgruppe":"privat","thema":["sozial","energie"]}'))
check("Stub-Mapping liefert erwartetes Ergebnis",
      r == {"zielgruppe": "privat", "thema": ["sozial", "energie"]})

check("leerer Text -> None (kein Aufruf)",
      ki.mappe_anliegen("   ", transport=_stub("{}")) is None)

# LLM darf nichts erfinden: unerlaubte Werte kommen gefiltert zurueck
r = ki.mappe_anliegen("irgendwas", transport=_stub('{"zielgruppe":"privat","thema":["sozial","militaer"]}'))
check("erfundenes Thema wird gefiltert", r == {"zielgruppe": "privat", "thema": ["sozial"]})

# fail-soft: Transport wirft (Timeout/Netz/HTTP)
def _boom(url, payload, headers, timeout):
    raise TimeoutError("timeout")
check("Transport-Fehler -> None (fail-soft)", ki.mappe_anliegen("text", transport=_boom) is None)

# fail-soft: HTTP-Fehlerobjekt ohne choices
check("Antwort ohne choices -> None",
      ki.mappe_anliegen("text", transport=_stub("nix")) is None)
check("Antwort ohne choices (dict) -> None",
      ki.mappe_anliegen("text", transport=lambda *a: {"error": "nope"}) is None)

# --- Aktiv-Schalter ---------------------------------------------------------
alt = os.environ.pop("FOERDER_LLM_API_KEY", None)
try:
    check("ohne Key ist das Modul inaktiv", ki.ist_aktiv() is False)
    check("inaktiv -> kein Versand, None", ki.mappe_anliegen("text") is None)
    os.environ["FOERDER_LLM_API_KEY"] = "test-key"
    check("mit Key ist das Modul aktiv", ki.ist_aktiv() is True)
finally:
    os.environ.pop("FOERDER_LLM_API_KEY", None)
    if alt is not None:
        os.environ["FOERDER_LLM_API_KEY"] = alt

# --- Datenschutz: nur der Freitext geht raus -------------------------------
aufrufe = []
ki.mappe_anliegen("Heizkosten kaum leistbar", typ="privat", transport=_stub("{}", aufrufe))
gesendet = aufrufe[0]["payload"]["messages"][1]["content"]
check("Freitext ist im Prompt enthalten", "Heizkosten kaum leistbar" in gesendet)
check("kein Kontaktfeld im Payload",
      not any(k in str(aufrufe[0]["payload"]) for k in ("email", "telefon", "@")))

# --- Laengenbegrenzung ------------------------------------------------------
lang = "x" * (ki.MAX_ZEICHEN + 500)
aufrufe = []
ki.mappe_anliegen(lang, transport=_stub("{}", aufrufe))
gesendet = aufrufe[0]["payload"]["messages"][1]["content"]
check(f"Freitext auf {ki.MAX_ZEICHEN} Zeichen begrenzt",
      ("x" * ki.MAX_ZEICHEN) in gesendet and ("x" * (ki.MAX_ZEICHEN + 1)) not in gesendet)

# --- thema_fuer: Vereinigung Chips + KI ------------------------------------
check("ohne KI bleibt die Chips-Heuristik",
      ki.thema_fuer(["Sanierung"], anliegen=None) == ["energie", "wohnen"])
check("KI ergaenzt die Chips",
      ki.thema_fuer(["Sanierung"], anliegen="pflege Mutter",
                    transport=_stub('{"zielgruppe":"privat","thema":["sozial"]}')) == ["energie", "sozial", "wohnen"])
check("KI-Dublette zur Chips-Heuristik wird nicht doppelt",
      ki.thema_fuer(["Photovoltaik"], anliegen="pv",
                    transport=_stub('{"zielgruppe":"privat","thema":["energie"]}')) == ["energie"])
check("kaputte KI-Antwort -> nur Chips",
      ki.thema_fuer(["Photovoltaik"], anliegen="x", transport=_boom) == ["energie"])
check("Ergebnis ist stabil sortiert (reproduzierbar)",
      ki.thema_fuer(["Sanierung"], anliegen="x",
                    transport=_stub('{"zielgruppe":"privat","thema":["wirtschaft"]}')) == ["energie", "wirtschaft", "wohnen"])

# --- Adapter: thema aus DB wird genutzt ------------------------------------
sys.path.insert(0, str(BASE))
from src import matching_service as ms  # noqa: E402
p = ms.profil_row_to_dict({"typ": "privat", "vorhaben": ["Photovoltaik"], "thema": ["sozial"]})
check("gespeichertes thema wird mit den Vorhaben vereinigt",
      p["thema"] == ["energie", "sozial"])
p = ms.profil_row_to_dict({"typ": "privat", "vorhaben": ["Sanierung"]})
check("Altdaten ohne thema -> Ableitung aus Vorhaben",
      p["thema"] == ["energie", "wohnen"])

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
