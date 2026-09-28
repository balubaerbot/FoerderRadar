# FoerderRadar — Architektur & Entscheidungen

> **Produktname:** Fördora · **Domain:** `foerdora.cloud` (gewählt 27.09.2026)
> Der Repo-/Arbeitsname „FoerderRadar" bleibt vorerst bestehen.

## Pipeline (Soll)

1. **Erfassung** — Webseite: Kunde erfasst Daten → `POST /profile` → DB.
   - `profil` (pseudonym, Agent-lesbar ueber View `profil_agent`)
   - `kontakt` (Klartext: name/email/telefon — nur Versand-Worker)
2. **Matching** — aktueller Katalog × Profil → relevante Foerderungen.
3. **Versand** — passende **E-Mail** an den Kunden *(in Arbeit)*. SMS-Kanal
   ist vorgesehen, aber **noch nicht implementiert** (`_senden_sms` = Platzhalter).

## Entscheidung: Hybrid (Variante A)

**LLM an den Raendern, Code in der Mitte — „LLM uebersetzt, Code urteilt".**

- **Agent/LLM uebernimmt:**
  - Katalog pflegen (Web-Recherche → strukturierte Bedingungen)
  - Profile interpretieren, wenn Kundenangaben unscharf sind
  - Kundentext (E-Mail) schreiben — aus der *verifizierten* Trefferliste
    (SMS-Kanal geplant, siehe Pipeline-Punkt 3)
  - Grenz-/„pruefen"-Faelle bewerten (widerspruechliche Quellen)
- **Code (`src/match.py`) uebernimmt:**
  - Anwendung der strukturierten Katalog-Bedingungen auf ein Profil

**Begruendung:** Eine Zusage an den Kunden („du bekommst Foerderung X") muss
**reproduzierbar** (gleiches Profil → gleiches Ergebnis), **nachweisbar**
(welche Bedingung wurde geprueft?) und **kostenlos/testsicher** sein.
Ein LLM, der pro Anfrage neu entscheidet, driftet, kostet Tokens und kann
Foerderungen/Deadlines erfinden.

## Katalog

- `katalog/foerderungen.json` = Datenquelle (Feldtrennung siehe unten).
- `tools/validate_katalog.py` = **Qualitaets-Gate** (laeuft vor jedem Merge).
- **Pflege = Aufgabe des Agenten.** Job *„FoerderRadar Katalog-Update"*:
  - Testphase: **monatlich** · Echtbetrieb: **woechentlich**
  - Regeln: `katalog/research_instruction.txt`
  - Nur **belegte** Aenderungen; keine Quelle = keine Aenderung; Unklares unangetastet.

**Feldtrennung:**
- `voraussetzungen` = **nur maschinell geprueffte** Keys
  (`wko_mitglied`, `projektkosten_min`, `themen`, `wohnsituation`,
  `einkommen_max`, `heizung_alt`, `pflegestufe_min`)
- `hinweise` = nur Anzeige, **nicht** geprueft
- `status` ∈ {`offen`, `ausgeschoepft`, `fenster_zu`, `angekuendigt`}

## Branches

- `develop` = Entwicklung.
- `main` = Produktion. **Nur von hier werden echte Kunden informiert.**
  (Der Katalog-Pflege-Job arbeitet in der Testphase auf `develop`.)

## Datenschutz

- Agent sieht **nie** Klartext-Kontaktdaten — nur `kunde_id` + pseudonyme Felder.
- Klartext (`kontakt`) ausschliesslich im Versand-Worker.
