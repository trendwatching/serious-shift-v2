-- Recovered from git history for the production reconciliation.
--
-- Production's schema_migrations holds 0001–0006, not 0001–0007 as
-- PRODUCTION-CUTOVER.md assumed, so `reconcile_baseline.sql` refuses: its
-- baseline check requires `shift_module_overrides`, which 0007 creates. This is
-- 0007's UP half only.
--
-- The up/down split matters. The original is a dbmate migration carrying both
-- halves in one file, and `psql -f` on the whole thing runs the down section
-- straight after the up one — creating the table and immediately dropping it,
-- reporting success. That is what happened on the first rehearsal.
--
--   psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/0007_map_rich_fields_up.sql
--   psql "$PROD_DATABASE_URL" -Atc "INSERT INTO schema_migrations(version) VALUES ('0007') ON CONFLICT DO NOTHING;"
--   psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/reconcile_baseline.sql
--   DATABASE_URL="$PROD_DATABASE_URL" python -m serious_shift_pipeline.core.migrate
--
-- Rehearsed 2026-08-08 against a pg_restore of production: 48,104 claims intact,
-- schema afterwards identical to staging (27 tables, zero column differences).

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

