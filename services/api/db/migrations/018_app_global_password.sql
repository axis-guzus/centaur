-- migrate:up

CREATE TABLE IF NOT EXISTS app_config (
    id              INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    password_hash   TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with SHA-256 of "paradigm-hackathon-pair-of-dimes"
INSERT INTO app_config (password_hash)
VALUES ('c368041942c190aee7163c7de83251a5351249d1ec0b4d59521e60e1e29e8944')
ON CONFLICT (id) DO NOTHING;

-- migrate:down

DROP TABLE IF EXISTS app_config;
