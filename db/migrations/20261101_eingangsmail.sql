-- Eingangsbestaetigung nach dem Formular (kurze Mail "Ihre Anfrage ist eingegangen").
-- Status je Kontakt, damit jede Anfrage hoechstens EINE Eingangsmail bekommt.
--   NULL           -> noch offen (nur innerhalb von 48 h nach einwilligung_am)
--   'sendet'       -> geclaimt, Versand laeuft
--   'gesendet'     -> verschickt (eingang_mail_am = Zeitpunkt)
--   'uebersprungen'-> bewusst nicht verschickt (gleiche Adresse < 24 h schon bestaetigt)
--   'fehler'       -> Versand fehlgeschlagen, wird NICHT automatisch wiederholt
-- Idempotent. Ausfuehren als Admin-Rolle (DATABASE_URL_ADMIN).

ALTER TABLE kontakt ADD COLUMN IF NOT EXISTS eingang_mail_status TEXT;
ALTER TABLE kontakt ADD COLUMN IF NOT EXISTS eingang_mail_am TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'kontakt_eingang_mail_status_check') THEN
        ALTER TABLE kontakt ADD CONSTRAINT kontakt_eingang_mail_status_check
            CHECK (eingang_mail_status IN ('sendet','gesendet','uebersprungen','fehler'));
    END IF;
END $$;

-- Der Versand-Worker darf NUR diese beiden Spalten aendern (kein UPDATE auf Kontaktdaten).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_worker') THEN
        GRANT UPDATE (eingang_mail_status, eingang_mail_am) ON kontakt TO app_worker;
    END IF;
END $$;
