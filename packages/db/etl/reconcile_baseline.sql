-- Reconcile a database that ran the pre-squash migrations (0001-0008) with the
-- squashed baseline (20250101000000_baseline.sql).
--
-- Pure bookkeeping: it records the baseline version and drops the eight
-- superseded rows. No DDL, no application data touched. `core/migrate.py`
-- refuses to run until this has been applied, so the failure mode is a loud
-- refusal rather than an attempt to CREATE tables that already exist.
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f packages/db/etl/reconcile_baseline.sql
--
-- Idempotent: re-running against an already-reconciled database is a no-op.

BEGIN;

-- Guard: refuse unless the recorded versions are exactly the pre-squash set or
-- the reconciliation has already happened. Anything else means this database is
-- in a state this script was not written for, and guessing would be worse than
-- stopping.
DO $$
DECLARE
    versions text[];
BEGIN
    SELECT array_agg(version ORDER BY version) INTO versions FROM schema_migrations;

    IF versions = ARRAY['20250101000000'] THEN
        RAISE NOTICE 'Already reconciled — nothing to do.';
        RETURN;
    END IF;

    IF versions IS DISTINCT FROM
       ARRAY['0001','0002','0003','0004','0005','0006','0007','0008'] THEN
        RAISE EXCEPTION
            'Unexpected schema_migrations state: %. Expected the pre-squash set '
            '{0001..0008} or the reconciled {20250101000000}.', versions;
    END IF;

    INSERT INTO schema_migrations (version) VALUES ('20250101000000')
      ON CONFLICT DO NOTHING;
    DELETE FROM schema_migrations
      WHERE version IN ('0001','0002','0003','0004','0005','0006','0007','0008');

    RAISE NOTICE 'Reconciled: 0001-0008 replaced by 20250101000000.';
END $$;

COMMIT;

SELECT array_agg(version ORDER BY version) AS schema_migrations_now
FROM schema_migrations;
