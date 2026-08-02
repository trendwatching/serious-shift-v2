-- Reconcile a database that ran the pre-squash migrations with the squashed
-- baseline (20250101000000_baseline.sql).
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/reconcile_baseline.sql
--
-- `core/migrate.py` refuses to run against an un-reconciled database, so the
-- failure mode is a loud refusal rather than an attempt to CREATE tables that
-- already exist. This script is what clears that refusal.
--
-- It handles two shapes:
--
--   * fully migrated (0001-0008) — pure bookkeeping, no DDL.
--   * stopped before 0008 (production is here) — 0008 only DROPped five empty
--     tables from an abandoned concept-graph idea, which had no producer and no
--     reader. They are dropped here so the schema matches the baseline, then
--     the bookkeeping runs.
--
-- Everything is guarded: the script verifies the tables the baseline defines are
-- actually present before it claims the baseline has been applied, so a database
-- that stopped even earlier is refused rather than mislabelled.
--
-- Idempotent: re-running against a reconciled database is a no-op.

BEGIN;

DO $$
DECLARE
    versions   text[];
    pre_squash text[] := ARRAY['0001','0002','0003','0004','0005','0006','0007','0008'];
    missing    text;
    dropped    text[];
BEGIN
    SELECT array_agg(version ORDER BY version) INTO versions FROM schema_migrations;

    IF versions @> ARRAY['20250101000000'] THEN
        RAISE NOTICE 'Already reconciled — nothing to do.';
        RETURN;
    END IF;

    IF versions IS NULL OR NOT (pre_squash @> versions) THEN
        RAISE EXCEPTION
            'Unexpected schema_migrations state: %. Expected a subset of the '
            'pre-squash set {0001..0008}, or an already-reconciled database.',
            versions;
    END IF;

    -- The baseline's tables must all exist, or this database stopped somewhere
    -- this script cannot honestly call "equivalent to the baseline".
    SELECT string_agg(t, ', ') INTO missing
    FROM unnest(ARRAY[
        'thinkers','sources','claims','predictions','documents',
        'domains_v2','domain_key_trends','domain_sub_trends','domain_sub_trend_claims',
        'domain_synthesis_insights','domain_synthesis_insight_claims',
        'domain_links','domain_flows','scrape_sources','source_state',
        'reputable_venues','shift_module_overrides','innovations'
    ]) AS t
    WHERE to_regclass('public.' || t) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION
            'Cannot reconcile: the baseline expects tables that do not exist (%). '
            'This database is behind the pre-squash chain, not merely un-squashed.',
            missing;
    END IF;

    -- What 0008 did, if it never ran here. All five were empty in every
    -- environment and had no producer in the pipeline; the only readers were
    -- API endpoints the front end never called, and those are gone too.
    SELECT array_agg(t) INTO dropped
    FROM unnest(ARRAY['claim_concepts','concept_thinkers','thinker_disagreements',
                      'tensions','concepts']) AS t
    WHERE to_regclass('public.' || t) IS NOT NULL;

    IF dropped IS NOT NULL THEN
        -- Refuse to drop anything that somehow acquired rows: "empty in every
        -- environment" is an observation, and this is a one-way operation.
        DECLARE
            n bigint;
            tbl text;
        BEGIN
            FOREACH tbl IN ARRAY dropped LOOP
                EXECUTE format('SELECT count(*) FROM public.%I', tbl) INTO n;
                IF n > 0 THEN
                    RAISE EXCEPTION
                        'Refusing to drop %: it has % rows. It was expected to be '
                        'empty. Inspect it before reconciling.', tbl, n;
                END IF;
            END LOOP;
        END;

        DROP TABLE IF EXISTS claim_concepts;
        DROP TABLE IF EXISTS concept_thinkers;
        DROP TABLE IF EXISTS thinker_disagreements;
        DROP TABLE IF EXISTS tensions;
        DROP TABLE IF EXISTS concepts;
        RAISE NOTICE 'Applied 0008 retroactively: dropped %.', array_to_string(dropped, ', ');
    END IF;

    INSERT INTO schema_migrations (version) VALUES ('20250101000000')
      ON CONFLICT DO NOTHING;
    DELETE FROM schema_migrations WHERE version = ANY(pre_squash);

    RAISE NOTICE 'Reconciled: % replaced by 20250101000000.',
                 array_to_string(versions, ', ');
END $$;

COMMIT;

SELECT array_agg(version ORDER BY version) AS schema_migrations_now
FROM schema_migrations;
