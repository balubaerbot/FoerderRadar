# Datenschutz und Aufbewahrung — Freigabesperre

## Aktueller Zustand

GET /formular, POST /formular und POST /profile sind standardmäßig geschlossen. Ohne ausdrückliche Freigabekonfiguration liefern sie HTTP 503, bevor ein Datenbankzugriff oder ein Schreibvorgang stattfindet. Beim JSON-Endpunkt kann das Framework den Request-Body vorher technisch parsen.

Das Formular erhebt unter anderem Angaben zu Pflege/Behinderung und Einkommen. Vor einer Verarbeitung muss der Verantwortliche Zwecke, Erforderlichkeit und Rechtsgrundlagen je Datenkategorie festlegen; bei besonderen Kategorien ist zusätzlich eine einschlägige Ausnahme nach Art. 9 DSGVO erforderlich. Eine Checkbox allein genügt dafür. Dies ist keine Rechtsberatung.

## Betreiber-Freigabe

Vor Aktivierung müssen schriftlich und rechtlich geprüft festgelegt sein: Identität und Datenschutzkontakt des Verantwortlichen; konkrete Zwecke und Rechtsgrundlagen; gegebenenfalls Art.-9-Ausnahme; Empfänger/Auftragsverarbeiter und Drittlandübermittlungen; Information nach Art. 13 DSGVO; Betroffenenrechte und funktionsfähiger Widerrufs-/Löschweg; zweckbezogene Speicherfrist und gesetzliche Ausnahmen. Die bestehende Datenschutzerklärung ist weiterhin unvollständig.

FOERDER_PRIVACY_REVIEWED=1 und FOERDER_SPECIAL_CATEGORY_BASIS_CONFIRMED=1 und FOERDER_WITHDRAWAL_PROCESS_CONFIRMED=1 sind Betreiberbestätigungen, kein automatischer Rechtscheck. Zusätzlich müssen FOERDER_INTAKE_ENABLED=1, ein Verantwortlicher und eine Einwilligungsversion gesetzt sein. Die feste Löschfrist für neue Datensätze ist zwei Jahre; sie wird nicht über FOERDER_RETENTION_DAYS konfiguriert. Nur nach dokumentierter Freigabe aktivieren.

## Speicherbegrenzung

Neue Datensätze erhalten kontakt.loeschdatum zwei Jahre nach Erfassung. Der bestehende Purge löscht fällige Profile samt abhängigen Datensätzen. Kunden können jederzeit per E-Mail die Löschung beantragen. Nach einer Identitätsprüfung muss der Betreiber das vollständige Profil unabhängig vom Alter löschen. Derzeit gibt es keinen automatischen E-Mail-Parser oder Self-Service-Löschendpunkt; bis zu deren Umsetzung ist die Durchführung ein manueller, dokumentierter Betreiberprozess. Die Migration db/migrations/20261018_consent_retention_metadata.sql setzt den Default für neue Zeilen und überschreibt keine bestehenden Daten. Historische NULL-Löschdaten bleiben ungeklärt und müssen vor Aktivierung behandelt werden.

Migration und Purge-Scheduler werden nicht automatisch auf einer Installation ausgeführt. Migration nach verifiziertem Backup mit der vorgesehenen Admin-Rolle anwenden und prüfen. Der Betreiber muss den Purge mit der dedizierten app_retention-Rolle schedulen und überwachen. Keine Purge-Ausführung gegen Produktionsdaten ohne getrennte Freigabe.



## Betreiberangaben und Umsetzung (18.10.2026)

- Betreiber/Datenschutzkontakt: privat, team@foerdora.cloud. Zweck: passende Fördermöglichkeiten ermitteln.
- Widerruf/Löschanfrage: E-Mail an team@foerdora.cloud, gesendet von der Adresse, mit der der Kunde Fördora genutzt hat (die in `kontakt` gespeicherte Adresse). Wird diese Adresse nicht mehr genutzt, muss der Kunde seine Identität auf andere Weise bestätigen; die Art des Nachweises legt der Betreiber im Einzelfall fest. Keine Gesundheits-/Behinderungsangaben per E-Mail anfordern.
- Pflege-/Behinderungsangaben erscheinen nur unter „Sozial & Alltag“ und werden nur bei separater ausdrücklicher Zustimmung angenommen; der Server ignoriert diese Angaben andernfalls. Einwilligungsflag wird mit der Einwilligungsversion getrennt gespeichert. Dies ersetzt keine Prüfung der Art.-9-Rechtsgrundlage.
- Aufbewahrung: regulär spätestens zwei Jahre nach der Erfassung löschen. Kundinnen und Kunden können jederzeit per E-Mail an team@foerdora.cloud die vollständige Löschung beantragen; nach verifizierter Zuordnung wird unabhängig vom Alter gelöscht.
- Neue Datensätze erhalten ein `kontakt.loeschdatum` zwei Jahre nach Erfassung und werden durch den bestehenden Purge nach diesem Datum gelöscht. Der manuelle Betreiberprozess muss Identität prüfen und dann `python3 tools/delete_profile_on_request.py --live <kunde_id> --confirm-id <kunde_id> --confirm-db foerderradar` mit `DATABASE_URL_RETENTION` ausführen (Details: `docs/operator-deletion-runbook.md`). Ohne `--live` läuft das Werkzeug nur gegen eine Loopback-Testdatenbank. Der Live-Modus wurde am 30.10.2026 mit zwei Testprofilen durchgespielt. Das Werkzeug ruft die SECURITY DEFINER-Funktion auf; app_retention darf die Funktion ausführen und Audit-Zeilen einfügen, aber weder Profile direkt löschen noch Auditdaten lesen. Ein automatischer Mail-Parser oder Self-Service-Endpunkt ist nicht implementiert. Eingang, Identitätsprüfung, Bearbeitung, Dokumentation und tatsächliche Löschung müssen organisatorisch eingerichtet und getestet werden.
- Datenschutzseite und Impressum bleiben unvollständige Entwürfe; volle Betreiberidentität/Anschrift, Art.-6-/Art.-9-Rechtsgrundlagen, Empfänger und Pflichtinformationen rechtlich vervollständigen lassen.
- Die Migration setzt den neuen Default für zukünftige Datensätze, überschreibt keine bestehenden Löschdaten und wurde nur lokal gegen Wegwerf-PostgreSQL getestet; nicht auf Produktion angewendet. Historische NULL-Löschdaten sind vor Aktivierung zu prüfen. Unit- und Integrationstests sowie Katalogvalidierung liefen erfolgreich. Keine Aktivierung/Produktionsaktion ohne separate Freigabe.
