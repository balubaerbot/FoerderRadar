-- Apply with the migration/admin role after a verified backup.
-- Existing rows intentionally remain NULL: their consent text/version and lawful
-- retention period cannot safely be reconstructed from current application data.
ALTER TABLE kontakt ADD COLUMN IF NOT EXISTS einwilligung_version TEXT;
ALTER TABLE kontakt ADD COLUMN IF NOT EXISTS einwilligung_widerrufen_am TIMESTAMPTZ;
ALTER TABLE kontakt ADD COLUMN IF NOT EXISTS einwilligung_besondere_daten BOOLEAN NOT NULL DEFAULT FALSE;

-- New records default to deletion two calendar years after collection. Existing
-- deadlines are intentionally preserved; NULL legacy dates need review before intake.
ALTER TABLE kontakt ALTER COLUMN loeschdatum SET DEFAULT ((CURRENT_DATE + INTERVAL '2 years')::date);
