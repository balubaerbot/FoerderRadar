-- FoerderRadar Schema (Phase 1)
-- Trennung: profil = pseudonym (Agent darf lesen), kontakt = Klartext (nur Versand-Worker)

CREATE TABLE IF NOT EXISTS profil (
    kunde_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    typ                TEXT NOT NULL CHECK (typ IN ('betrieb','privat','sozial')),
    region_grob        TEXT,
    -- nur Betrieb
    branche            TEXT,
    mitarbeiterklasse  TEXT,
    wko_mitglied       BOOLEAN,
    -- nur Privat
    wohnsituation      TEXT,
    haushaltsgroesse   TEXT,
    einkommen_spanne   TEXT,
    heizung            TEXT,
    pflegestufe        INTEGER,
    behinderung        BOOLEAN,
    familienstand      TEXT,
    kinder_im_haushalt BOOLEAN,
    -- beide
    vorhaben           TEXT[],
    erstellt_am        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phase 2 (KI-Mapping): Freitext-Anliegen + daraus abgeleitete grobe Thema-Achse.
-- Idempotent (IF NOT EXISTS), damit bestehende Datenbanken beim Re-Init mitwandern.
-- `anliegen` ist ein pseudonymes Feld (Kundentext, keine Kontaktdaten).
-- `thema` speichert das Ergebnis EINMAL (reproduzierbar), statt bei jedem
-- Matching-Lauf erneut das LLM zu fragen.
ALTER TABLE profil ADD COLUMN IF NOT EXISTS anliegen TEXT;
ALTER TABLE profil ADD COLUMN IF NOT EXISTS thema TEXT[];

-- Phase 3 (Standbein "Sozial & Alltag"): Lebenssituation als eigenes Feld.
ALTER TABLE profil ADD COLUMN IF NOT EXISTS lebenssituation TEXT;

-- Phase 4: `typ` fuehrt 'sozial' als echten dritten Wert (ersetzt den
-- frueheren Workaround typ='privat' + thema='sozial'). Idempotente Migration
-- fuer bereits initialisierte DBs: CHECK-Constraint droppen + neu anlegen
-- (ein CHECK laesst sich nicht per ALTER aendern, nur ersetzen).
ALTER TABLE profil DROP CONSTRAINT IF EXISTS profil_typ_check;
ALTER TABLE profil ADD CONSTRAINT profil_typ_check CHECK (typ IN ('betrieb','privat','sozial'));

CREATE INDEX IF NOT EXISTS profil_thema_idx ON profil USING GIN (thema);

CREATE TABLE IF NOT EXISTS kontakt (
    kunde_id        UUID PRIMARY KEY REFERENCES profil(kunde_id) ON DELETE CASCADE,
    name            TEXT,
    email           TEXT,
    telefon         TEXT,
    kanal           TEXT CHECK (kanal IN ('email','sms')),
    einwilligung_am TIMESTAMPTZ,
    loeschdatum     DATE
);

CREATE TABLE IF NOT EXISTS match (
    id             BIGSERIAL PRIMARY KEY,
    kunde_id       UUID NOT NULL REFERENCES profil(kunde_id) ON DELETE CASCADE,
    foerderung_id  TEXT NOT NULL,
    kategorie      TEXT CHECK (kategorie IN ('top','pruefenswert')),
    gemeldet_am    TIMESTAMPTZ,
    status         TEXT DEFAULT 'identifiziert',
    eingefroren_am TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Versand-Queue: Textentwuerfe + Sendeprotokoll.
-- Der Agent schreibt den Text (ohne Kontaktdaten); der Worker liest `kontakt`
-- selbst und verschickt. So bleibt die Klartext-Trennung gewahrt.
CREATE TABLE IF NOT EXISTS versand (
    id          BIGSERIAL PRIMARY KEY,
    kunde_id    UUID NOT NULL REFERENCES profil(kunde_id) ON DELETE CASCADE,
    kanal       TEXT CHECK (kanal IN ('email','sms')),
    betreff     TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'entwurf' CHECK (status IN ('entwurf','sendet','gesendet','fehler')),
    fehler_text TEXT,
    erstellt_am TIMESTAMPTZ NOT NULL DEFAULT now(),
    gesendet_am TIMESTAMPTZ,
    -- Zeitpunkt des atomaren Claims ('sendet') -> Watchdog kann haengende
    -- Versuche nach einer Frist zuruecksetzen.
    sendet_seit TIMESTAMPTZ,
    -- Zeitpunkt des letzten Test-Versands (Prototyp: eigenes Postfach).
    -- Verhindert, dass ein Cron denselben unveraenderten Entwurf wiederholt
    -- test-versendet; wird bei Textaenderung auf NULL zurueckgesetzt.
    test_gesendet_am TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS versand_status_idx ON versand (status);
CREATE INDEX IF NOT EXISTS match_status_idx ON match (status);
-- Hoechstens EIN offener (nicht abgeschlossener) Versand pro Kunde -> kein Doppelversand.
CREATE UNIQUE INDEX IF NOT EXISTS versand_ein_offener ON versand (kunde_id)
    WHERE status IN ('entwurf','sendet');

-- Pseudonyme Sicht: genau das, was der Agent/Dienst lesen darf (keine Kontaktdaten!)
CREATE OR REPLACE VIEW profil_agent AS
SELECT kunde_id, typ, region_grob, branche, mitarbeiterklasse, wko_mitglied,
       wohnsituation, haushaltsgroesse, einkommen_spanne, heizung, pflegestufe,
       behinderung, familienstand, kinder_im_haushalt, lebenssituation, vorhaben,
       thema, anliegen
FROM profil;
