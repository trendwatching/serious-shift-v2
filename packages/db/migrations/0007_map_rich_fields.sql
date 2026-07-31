-- migrate:up

-- ── Rich editorial fields for the shift reading views ─────────────────────────
--
-- The "Swipe the Domains" front end renders a shift as a sequence of editorial
-- sections (From→To, What's changing / Why now, a stat band, human needs, a
-- consumer tension, a now/next/beyond horizon, implications by industry and
-- opportunity territories). Each section is rendered only when its field is
-- present, so every column here is nullable: the site degrades to hero + dek
-- until the pipeline backfills a row.
--
-- JSONB is used where the shape is a list or a small record, matching how the
-- map document already stores hero_stat.

ALTER TABLE domain_key_trends
    ADD COLUMN from_text        TEXT,    -- "From" side of the shift
    ADD COLUMN to_text          TEXT,    -- "To" side of the shift
    ADD COLUMN whats_changing   TEXT,
    ADD COLUMN why_now          TEXT,
    ADD COLUMN stat_text        TEXT,    -- prose beside hero_stat.value
    ADD COLUMN human_needs      JSONB,   -- { unlocked, threatened }
    ADD COLUMN consumer_tension TEXT,    -- the pull-quote
    ADD COLUMN timeline         JSONB,   -- [{ label, text }] now / next / beyond
    ADD COLUMN industries       JSONB,   -- [{ name, text }]
    ADD COLUMN opportunities    JSONB,   -- [{ name, text }] opportunity territories
    ADD COLUMN read_time        TEXT;    -- "6 min read"

ALTER TABLE domain_sub_trends
    ADD COLUMN lede             TEXT,
    ADD COLUMN from_text        TEXT,
    ADD COLUMN to_text          TEXT,
    ADD COLUMN tension          TEXT,
    ADD COLUMN stat             JSONB,   -- { value, text, source }
    ADD COLUMN whats_changing   TEXT,
    ADD COLUMN why_now          TEXT,
    ADD COLUMN human_needs      JSONB,   -- { unlocked, threatened }
    ADD COLUMN signals          JSONB,   -- [text]
    ADD COLUMN counter_signals  JSONB,   -- [text]
    ADD COLUMN timeline         JSONB,   -- [{ label, text }]
    ADD COLUMN territories      JSONB;   -- [{ name, text }]

-- The deck labels each domain with a horizon year.
ALTER TABLE domains_v2
    ADD COLUMN horizon TEXT;

-- migrate:down

ALTER TABLE domain_key_trends
    DROP COLUMN from_text,
    DROP COLUMN to_text,
    DROP COLUMN whats_changing,
    DROP COLUMN why_now,
    DROP COLUMN stat_text,
    DROP COLUMN human_needs,
    DROP COLUMN consumer_tension,
    DROP COLUMN timeline,
    DROP COLUMN industries,
    DROP COLUMN opportunities,
    DROP COLUMN read_time;

ALTER TABLE domain_sub_trends
    DROP COLUMN lede,
    DROP COLUMN from_text,
    DROP COLUMN to_text,
    DROP COLUMN tension,
    DROP COLUMN stat,
    DROP COLUMN whats_changing,
    DROP COLUMN why_now,
    DROP COLUMN human_needs,
    DROP COLUMN signals,
    DROP COLUMN counter_signals,
    DROP COLUMN timeline,
    DROP COLUMN territories;

ALTER TABLE domains_v2
    DROP COLUMN horizon;
