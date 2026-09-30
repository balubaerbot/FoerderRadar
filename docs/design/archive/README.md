# Design-Archiv — historische Mockups

**Status: ARCHIVIERT. Nicht die Quelle der Wahrheit. Wird nicht gepflegt.**

Diese Dateien sind die Design-Prototypen aus der Entwurfsphase von Fördora.
Sie haben ihren Zweck erfüllt: das Design wurde in den **echten Code** portiert.

## Wo das echte Design jetzt lebt

| Bereich | Ort |
|---|---|
| Seiten-Struktur | `app/templates/*.html` (Jinja, von FastAPI gerendert) |
| Styling | `app/static/style.css` |
| Formular-Logik | `app/main.py` (Route `/formular`) |
| Matching | `src/match.py`, `src/matching_service.py` |

## Inhalt dieses Archivs

- `build_mockup.py` — der damalige Generator (schreibt nach `./mockups/`)
- `mockups/*.html` — die erzeugten statischen Seiten (Standbein, Start, Formular je Zielgruppe, Danke)
- `screenshots/*.png` — Bildschirmfotos für die Design-Abstimmung

## Wichtig

- Diese HTML-Dateien werden **nicht mehr ausgeliefert**. Die früher unter
  `app/static/mockups/` servierte Kopie wurde entfernt.
- **Nicht mehr synchronisieren.** Änderungen am Design gehören ausschließlich
  in `app/templates/**. Wer hier ändert, erzeugt Drift.

_Ausgemustert am 2026-09-30._
