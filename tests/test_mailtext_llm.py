"""Tests fuer den LLM-Mailtext (Phase 2) - formuliere_mail().

Kein Netz: der HTTP-Transport wird als Stub injiziert. Geprueft werden die
Sicherheits-Eigenschaften, auf die es ankommt:
  * Ohne API-Key/Transport wird gar nicht erst gesendet -> fail-soft (None)
  * Mit injiziertem Fake-Transport liefert eine gueltige Antwort ein Dict
    {"betreff": str, "body": str}
  * STRICT GROUNDING: Erfundene Betraege/Fristen in Betreff/Einleitung/
    Abschluss fuehren zum kompletten Fallback (None); ein Hinweis zu einer
    unbekannten ("erfundenen") Foerderung-id wird verworfen; ein Hinweis mit
    einem erfundenen Betrag/Frist wird bereinigt (Hinweis entfernt, der
    Treffer bleibt mit den ECHTEN Katalogfakten erhalten)
  * Niemals werden Klartext-Kontaktdaten (name/email/telefon) an das LLM
    gesendet - auch nicht, wenn sie (fehlerhaft) im Profil-Dict stecken
  * Schlaegt formuliere_mail fehl, verwendet versand_service.nachricht_bauen
    unveraendert die deterministische Vorlage aus Phase 1

Lauf:  python3 tests/test_mailtext_llm.py
"""
import json
import os
import pathlib
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src import ki_mapping as ki  # noqa: E402
from src import versand_service as vs  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    print(("  OK  " if cond else "  FAIL") + "  " + name)
    ok += bool(cond)
    fail += (not cond)


def _antwort(objekt):
    """Baut eine OpenAI-kompatible Antwort mit JSON-Inhalt."""
    return {"choices": [{"message": {"content": json.dumps(objekt, ensure_ascii=False)}}]}


def _stub(objekt, aufrufe=None):
    def t(url, payload, headers, timeout):
        if aufrufe is not None:
            aufrufe.append({"url": url, "payload": payload, "headers": headers})
        return _antwort(objekt)
    return t


TREFFER = [
    {
        "foerderung_id": "kmu_digital", "kategorie": "top", "name": "KMU.DIGITAL",
        "stelle": "Bund / aws", "betrag": "bis zu 50.000 Euro", "frist": "31.12.2026",
        "status": "offen", "quelle": "https://aws.at/kmu-digital",
    },
]
PROFIL = {
    "typ": "privat", "region_grob": "ooe", "wohnsituation": "miete",
    "vorhaben": ["Sanierung"], "thema": ["energie"],
}
KATALOG = {"foerderungen": [{
    "id": "kmu_digital", "name": "KMU.DIGITAL", "stelle": "Bund / aws",
    "betrag": "bis zu 50.000 Euro", "frist": "31.12.2026", "status": "offen",
    "quelle": "https://aws.at/kmu-digital",
}]}
TREFFER_ROH = [{"foerderung_id": "kmu_digital", "kategorie": "top"}]

print("LLM-Mailtext")

# --- (a) Fail-soft ohne Key / ohne Transport --------------------------------
alt_key = os.environ.pop("FOERDER_LLM_API_KEY", None)
try:
    check("ohne Key ist das Modul inaktiv", ki.ist_aktiv() is False)
    check("ohne Key/Transport -> None (kein Versand)",
          ki.formuliere_mail(PROFIL, TREFFER, transport=None) is None)
    check("ohne Treffer -> None (nichts zu formulieren)",
          ki.formuliere_mail(PROFIL, [], transport=_stub({"betreff": "x", "einleitung": "x",
                                                            "zeilen": [], "abschluss": "x"})) is None)
finally:
    if alt_key is not None:
        os.environ["FOERDER_LLM_API_KEY"] = alt_key

# --- (b) Mit injiziertem Fake-Transport -> gueltiges Dict -------------------
gueltig = {
    "betreff": "Neue Foerderungen fuer Ihre Sanierung",
    "einleitung": "wir haben passende Foerderungen fuer Ihr Vorhaben gefunden.",
    "zeilen": [{"id": "kmu_digital", "hinweis": "passt gut zu Ihrem Thema Energie."}],
    "abschluss": "Bei Fragen antworten Sie gerne auf diese Mail.",
}
res = ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(gueltig))
check("mit Fake-Transport -> dict mit betreff+body", bool(res) and "betreff" in res and "body" in res)
check("betreff kommt vom LLM", res and res["betreff"] == gueltig["betreff"])
check("body enthaelt echte Katalogfakten (Betrag)", res and "bis zu 50.000 Euro" in res["body"])
check("body enthaelt echte Katalogfakten (Frist/Status)",
      res and "31.12.2026" in res["body"] and "offen" in res["body"])
check("body enthaelt LLM-Einleitung", res and gueltig["einleitung"] in res["body"])
check("body enthaelt Pflicht-Disclaimer (wie Phase-1-Vorlage)",
      res and "keine Rechts- oder Steuerberatung und ohne Gewähr" in res["body"])

# --- (c) Grounding: erfundener Betrag -> kompletter Fallback (None) ---------
erfundener_betrag = {
    "betreff": "Ihre Foerderungen",
    "einleitung": "Sie koennten bis zu 999999 Euro zusaetzlich erhalten.",
    "zeilen": [],
    "abschluss": "Danke.",
}
check("erfundener Betrag in Einleitung -> None (Fallback)",
      ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(erfundener_betrag)) is None)

erfundener_betrag_betreff = {
    "betreff": "Bis zu 777777 Euro moeglich!",
    "einleitung": "Wir haben etwas fuer Sie gefunden.",
    "zeilen": [],
    "abschluss": "Danke.",
}
check("erfundener Betrag im Betreff -> None (Fallback)",
      ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(erfundener_betrag_betreff)) is None)

# --- (c) Grounding: erfundene Foerderung (unbekannte id) -> verworfen -------
erfundene_foerderung = {
    "betreff": "Ihre Foerderungen",
    "einleitung": "Wir haben passende Foerderungen gefunden.",
    "zeilen": [
        {"id": "kmu_digital", "hinweis": "passt zu Ihrem Vorhaben."},
        {"id": "nicht_existent_123", "hinweis": "Diese Foerderung gibt es gar nicht."},
    ],
    "abschluss": "Freundliche Gruesse.",
}
res2 = ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(erfundene_foerderung))
check("erfundene Foerderung-id macht die Rahmung nicht ungueltig", res2 is not None)
check("erfundene Foerderung-id taucht NICHT im Body auf",
      res2 and "nicht_existent_123" not in res2["body"] and "gibt es gar nicht" not in res2["body"])
check("echte Foerderung bleibt im Body", res2 and "KMU.DIGITAL" in res2["body"])

# --- (c) Grounding: erfundener Betrag NUR im Hinweis -> bereinigt -----------
erfundener_hinweis = {
    "betreff": "Ihre Foerderungen",
    "einleitung": "Wir haben passende Foerderungen gefunden.",
    "zeilen": [{"id": "kmu_digital", "hinweis": "Sie erhalten dafuer 123456 Euro extra."}],
    "abschluss": "Freundliche Gruesse.",
}
res3 = ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(erfundener_hinweis))
check("erfundener Hinweis-Betrag macht die Rahmung nicht ungueltig", res3 is not None)
check("erfundene Zahl aus dem Hinweis fehlt im Body", res3 and "123456" not in res3["body"])
check("echter Betrag steht weiterhin im Body", res3 and "bis zu 50.000 Euro" in res3["body"])

# --- (c) Kaputtes JSON -> fail-soft (None) ----------------------------------
def _stub_kaputt(url, payload, headers, timeout):
    return {"choices": [{"message": {"content": "das ist kein json"}}]}

check("kaputtes JSON -> None", ki.formuliere_mail(PROFIL, TREFFER, transport=_stub_kaputt) is None)

# --- (c) Fehlendes Pflichtfeld (betreff) -> None ----------------------------
unvollstaendig = {"einleitung": "x", "zeilen": [], "abschluss": "x"}
check("fehlender Betreff -> None",
      ki.formuliere_mail(PROFIL, TREFFER, transport=_stub(unvollstaendig)) is None)

# --- (c) Exception im Transport -> fail-soft (None), keine Exception -------
def _stub_exception(url, payload, headers, timeout):
    raise TimeoutError("simulierter Timeout")

try:
    res_exc = ki.formuliere_mail(PROFIL, TREFFER, transport=_stub_exception)
    check("Exception im Transport -> None (keine Exception nach aussen)", res_exc is None)
except Exception:  # noqa: BLE001
    check("Exception im Transport -> None (keine Exception nach aussen)", False)

# --- (d) Keine Klartext-Kontaktdaten im Prompt/Payload ----------------------
profil_mit_kontaktdaten = dict(PROFIL)
profil_mit_kontaktdaten.update({
    "email": "max.mustermann@example.com",
    "telefon": "0660 1234567",
    "name": "Max Mustermann",
    "kontakt": {"email": "max.mustermann@example.com", "telefon": "0660 1234567"},
})
aufrufe = []
ki.formuliere_mail(profil_mit_kontaktdaten, TREFFER, transport=_stub(gueltig, aufrufe))
payload_text = json.dumps(aufrufe[0]["payload"], ensure_ascii=False)
check("Kontaktdaten (email) NICHT im Payload", "max.mustermann@example.com" not in payload_text)
check("Kontaktdaten (telefon) NICHT im Payload", "0660 1234567" not in payload_text)
check("Kontaktdaten (name) NICHT im Payload", "Max Mustermann" not in payload_text)
check("Authorization-Header gesetzt, kein Payload-Leck im Header",
      "Bearer" in aufrufe[0]["headers"]["Authorization"])

# --- (d) profil_pseudonym liefert ohnehin nie Kontaktspalten (View-Vertrag) -
felder_profil_agent = {
    "kunde_id", "typ", "region_grob", "branche", "mitarbeiterklasse", "wko_mitglied",
    "wohnsituation", "haushaltsgroesse", "einkommen_spanne", "heizung", "pflegestufe",
    "familienstand", "kinder_im_haushalt", "lebenssituation", "vorhaben", "thema", "anliegen",
}
check("MAIL_PROFIL_FELDER ist Teilmenge der profil_agent-Spalten (kein Fremdfeld)",
      set(ki.MAIL_PROFIL_FELDER) <= felder_profil_agent)
check("MAIL_PROFIL_FELDER enthaelt keine Kontaktspalte",
      not ({"email", "telefon", "name", "kontakt"} & set(ki.MAIL_PROFIL_FELDER)))

# --- Integration: versand_service.nachricht_bauen -------------------------
betreff_ki, body_ki = vs.nachricht_bauen(PROFIL, TREFFER_ROH, KATALOG, transport=_stub(gueltig))
check("nachricht_bauen nutzt LLM-Ergebnis, wenn vorhanden", betreff_ki == gueltig["betreff"])

alt_key2 = os.environ.pop("FOERDER_LLM_API_KEY", None)
try:
    betreff_fb, body_fb = vs.nachricht_bauen(PROFIL, TREFFER_ROH, KATALOG, transport=None)
    check("nachricht_bauen faellt ohne Key/Transport auf die Vorlage zurueck",
          betreff_fb == f"Ihre passenden Foerderungen ({len(TREFFER_ROH)})")
    check("Fallback-Body entspricht der unveraenderten Phase-1-Vorlage",
          "auf Basis Ihrer Angaben koennen folgende Foerderungen fuer Sie relevant sein" in body_fb)
finally:
    if alt_key2 is not None:
        os.environ["FOERDER_LLM_API_KEY"] = alt_key2

print(f"\nErgebnis: {ok} OK, {fail} FAIL")
sys.exit(1 if fail else 0)
