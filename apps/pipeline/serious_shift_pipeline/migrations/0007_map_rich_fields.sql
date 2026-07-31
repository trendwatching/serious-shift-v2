-- migrate:up
-- =============================================================================
-- 0007 — Module-driven shift pages.
--
-- A shift page is an ordered list of MODULES ({type, data}) rather than a fixed
-- sequence of sections, so composition is data: the pipeline emits the list, the
-- front end renders whatever it is given and skips types it does not know.
--
-- Two places store modules, and the split is deliberate:
--
--   * GENERATED modules live in a JSONB column on the row they describe. The
--     rebuild TRUNCATEs domain_key_trends/domain_sub_trends with RESTART
--     IDENTITY CASCADE (see generate_map_data.reset_v2_tables), so a child table
--     keyed on those ids would be emptied every week and a recycled id would
--     point at a different shift. A column travels with its row and is written
--     in the same run that creates it, which sidesteps identity entirely.
--
--   * AUTHORED modules live in shift_module_overrides, which is intentionally
--     NOT a child of the v2 tables — that is the whole point, since TRUNCATE …
--     CASCADE cannot reach it. It is keyed by the URL slug (what an editor sees
--     in the address bar), so an override keeps applying across rebuilds.
-- =============================================================================

ALTER TABLE domain_key_trends
    ADD COLUMN modules   JSONB,   -- generated: [{type, data}], render order
    ADD COLUMN read_time TEXT;    -- "6 min read" — shown on the domain sheet row

ALTER TABLE domain_sub_trends
    ADD COLUMN modules JSONB;

-- The deck labels each domain with a horizon year.
ALTER TABLE domains_v2
    ADD COLUMN horizon TEXT;

-- Editor-authored module lists. Full replacement: when an enabled row exists for
-- a slug, its ordered list is served instead of the generated one. Seed a row
-- from the generated list to start editing (see DEPLOY-RAILWAY.md).
CREATE TABLE shift_module_overrides (
    scope      TEXT NOT NULL CHECK (scope IN ('key_trend', 'sub_trend')),
    -- URL slug: 'cognitive-erosion' for a shift,
    -- 'cognitive-erosion/capacity-collapse' for a sub-shift.
    slug       TEXT NOT NULL,
    modules    JSONB NOT NULL,
    note       TEXT,
    enabled    BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, slug)
);

-- migrate:down

DROP TABLE shift_module_overrides;

ALTER TABLE domains_v2
    DROP COLUMN horizon;

ALTER TABLE domain_sub_trends
    DROP COLUMN modules;

ALTER TABLE domain_key_trends
    DROP COLUMN modules,
    DROP COLUMN read_time;
