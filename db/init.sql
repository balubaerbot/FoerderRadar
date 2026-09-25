-- FoerderRadar Schema (Phase 1)
-- Trennung: profil = pseudonym (Agent darf lesen), kontakt = Klartext (nur Versand-Worker)

CREATE TABLE IF NOT EXISTS profil (
    kunde_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    typ                TEXT NOT NULL CHECK (typ IN ('betrieb','privat')),
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
    familienstand      TEXT,
    kinder_im_haushalt BOOLEAN,
    -- beide
    vorhaben           TEXT[],
    erstellt_am        TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

-- Pseudonyme Sicht: genau das, was der Agent/Dienst lesen darf (keine Kontaktdaten!)
CREATE OR REPLACE VIEW profil_agent AS
SELECT kunde_id, typ, region_grob, branche, mitarbeiterklasse, wko_mitglied,
       wohnsituation, haushaltsgroesse, einkommen_spanne, heizung, pflegestufe,
       familienstand, kinder_im_haushalt, vorhaben
FROM profil;
