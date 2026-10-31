# Go-live-Checkliste Fördora

Stand: 30.10.2026. Die Freigabe-Variablen (`FOERDER_*`) setzt ausschließlich der Betreiber, nach eigener Prüfung. Ein Code-Review ersetzt diese Prüfung nicht.

Hinweis: `docs/privacy-retention.md` nennt den Datenschutztext einen Entwurf. Betreiberidentität, Anschrift, Rechtsgrundlagen (Art. 6/9), Empfänger und Pflichtinformationen müssen rechtlich vervollständigt werden.

## 1. FOERDER_PRIVACY_REVIEWED (Datenschutzerklärung)
- [ ] `/datenschutz` komplett gelesen
- [ ] Name und Kontaktadresse korrekt, Adresse wird gelesen
- [ ] Zwecke genannt: Fördermatching, Versand der Treffer per E-Mail
- [ ] Rechtsgrundlagen genannt: Art. 6, für Gesundheitsdaten Art. 9 Abs. 2 lit. a
- [ ] Empfänger/Auftragsverarbeiter vollständig: Hostinger (Server, Mail), LLM-Anbieter (welche Daten gehen dorthin geprüft), GitHub nur ohne Kundendaten
- [ ] Drittlandübermittlung erwähnt, falls LLM-Anbieter außerhalb der EU
- [ ] Speicherdauer im Text (zwei Jahre) = Wert im Code (`kontakt.loeschdatum`, zwei Jahre nach Erfassung) und Purge-Cron (derzeit alle 2 Monate). Hinweis: `FOERDER_RETENTION_DAYS` wird im Code nicht gelesen
- [ ] Betroffenenrechte: Auskunft, Löschung, Widerruf, Beschwerde bei der DSB (Österreich)

## 2. FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED (Gesundheitsdaten)
- [ ] Felder mit Gesundheitsbezug (z. B. Pflegestufe, Behinderung) identifiziert; Notwendigkeit geprüft, sonst weglassen
- [ ] Ausdrückliche, gesonderte Einwilligung für diese Daten
- [ ] Checkbox nicht vorangekreuzt; Absenden ohne Einwilligung nicht möglich, wenn solche Daten angegeben werden
- [ ] Einwilligungstext nennt Verwendung und jederzeitigen Widerruf
- [ ] `einwilligung_version` und `einwilligung_besondere_daten` werden gespeichert (Nachweis)
- [ ] Bewusste Entscheidung, ggf. Beratung eingeholt

## 3. FOERDER_WITHDRAWAL_PROCESS_CONFIRMED (Widerruf)
- [ ] Widerrufsweg steht im Datenschutztext und in jeder Mail
- [ ] Postfach wird mindestens wöchentlich gelesen
- [ ] Löschablauf bekannt: `tools/delete_profile_on_request.py --live --confirm-id <uuid> --confirm-db foerderradar` mit `DATABASE_URL_RETENTION` (siehe `docs/operator-deletion-runbook.md`)
- [x] Löschtool am 30.10.2026 live mit zwei Testprofilen und der Rolle `app_retention` durchgespielt (inkl. Kaskade und Audit); vor dem Live-Gang bei Bedarf wiederholen
- [ ] Antwort innerhalb eines Monats
- [ ] Bekannt: bereits versendete Mails bleiben bei den Empfängern

## 4. FOERDER_LEGACY_RETENTION_REVIEWED (Altdaten)
- [ ] Entscheidung für Bestandsdaten: löschen / behalten mit Begründung / neue Einwilligung
- [x] Altdaten gelöscht (30.10.2026, 68 Testprofile über delete_profile_on_request, Zustimmung gateway-owner, kein Backup)
- [x] Übrige Kontakte: entfällt, Datenbank war nach der Löschung leer
- [x] FOERDER_LEGACY_RETENTION_REVIEWED, FOERDER_DATA_CONTROLLER und FOERDER_PRIVACY_CONTACT in der .env gesetzt (31.10.2026)

## 5. Technische Freigaben
- [ ] FOERDER_RETENTION_SCHEMA_VERIFIED: Migrationen `20261018_consent_retention_metadata`, `20261019_request_deletion`, `20261028_purge_expired_profiles` auf der Live-DB
- [ ] FOERDER_PURGE_SCHEDULE_VERIFIED: Cron "FoerderRadar Retention-Purge" (`2104646e-8ccb-4825-bf44-33d5b8e05d68`, `0 4 1 */2 *`) existiert; noch nie gelaufen, ggf. vorher einmal testen
- [ ] FOERDER_CONSENT_VERSION passt zum aktuellen Einwilligungstext (bei Textänderung erhöhen)

## 6. Stammdaten und Impressum
- [ ] Betreiber- und Datenschutzkontakt-Variablen gesetzt (Namen in `app/` prüfen)
- [ ] Impressum mit Anschrift
- [ ] Löschintervall (aktuell 2 Monate) passt zur Frist im Datenschutztext

## 7. Host (Container)
- [ ] Neue Umgebungsvariablen kommen im Container an (Compose prüfen)
- [ ] Neustart: `cd /docker/openclaw-jpva/data/projects/FoerderRadar && docker compose up -d foerderradar-api`
- [ ] `FOERDER_INTAKE_ENABLED` als letzter Schalter

## 8. Live-Check über die Domain
- [ ] Footer "© 2026 Fördora · v1.0 alpha (Testversion)" und Header-Badge sichtbar (Optik im Browser prüfen)
- [ ] `/datenschutz`, `/impressum` erreichbar
- [ ] `/formular` antwortet nicht mehr mit 503
- [ ] Realtest mit Testkonto, danach Testdaten per Löschtool entfernen
- [ ] Testmail landet nicht im Spam (Gmail: "Kein Spam"; DMARC `rua` ergänzen, später `p=quarantine`)

## 9. Sonstiges
- [ ] Echter CI-Lauf auf GitHub grün
- [ ] Integrationstests nach dem Filter-Fix neu gelaufen
- [ ] Versand an Kunden nur über den Worker; `--send` ohne `--test` ist echter Versand und wird nur auf ausdrückliche Anweisung verwendet
- [x] Entschieden: `gui.py` existiert im Repo nicht (nichts zu löschen); Tirol bleibt sichtbar; Tippfehler "Wachstamsvorhaben" im Katalog nicht gefunden (nur die Katalogeinträge "Wachstumsinvestition", korrekt geschrieben)
