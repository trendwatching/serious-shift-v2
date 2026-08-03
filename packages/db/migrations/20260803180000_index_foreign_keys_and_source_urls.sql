-- migrate:up

-- Two gaps in the schema, both found by auditing the live staging database
-- rather than by reading the DDL.
--
-- 1. SEVEN FOREIGN KEY COLUMNS HAD NO SUPPORTING INDEX.
--
-- Postgres indexes the *referenced* side of a foreign key automatically (it has
-- to — that side is a primary key or unique constraint). It never indexes the
-- *referencing* side. That costs twice:
--
--   * Every join through the constraint seq-scans the child. `export.py` joins
--     domain_sub_trend_claims to claims on `claim_id` for every sub-shift, and
--     `select_hero_stat` does the same per key shift.
--   * Every DELETE on the parent scans the whole child to prove no row still
--     references the deleted one. `_targeted_repair_once` deletes from
--     domain_sub_trends, and mapgen's weekly rebuild deletes and reinserts the
--     entire taxonomy — so this is on the hot path of the run that matters.
--
-- The child tables are small today (1,585 rows in the largest), which is why
-- this has not hurt yet. `claims` is 43,655 rows and grows by ~1,000 a week;
-- the scans grow with it.
--
-- 2. sources.url IS THE INGESTION DEDUPE KEY, UNINDEXED AND UNENFORCED.
--
-- Three call sites ask "have I already stored this URL?" before writing —
-- steps/scraper/content.py, and process_raw.py in two places — once per
-- scraped item. Unindexed, each is a seq scan over every source row, so a
-- 137-item ingest performs 137 full scans of a 2,359-row table, and that cost
-- is linear in both items and corpus size.
--
-- Worse, the invariant those three checks exist to maintain is not enforced
-- anywhere: a check-then-insert is a race, and nothing stops two rows sharing a
-- URL. A partial unique index fixes both at once — it answers the lookup and
-- makes the duplicate structurally impossible.
--
-- It must be PARTIAL. 195 of 2,359 sources carry url = '' (the empty string,
-- not NULL — NULLs would already be exempt from a plain UNIQUE), all of them
-- manual or transcript-derived rows with no canonical address. A plain unique
-- index would reject 194 of them. Verified before writing this: zero genuine
-- duplicates among non-empty URLs, so the index builds clean.
--
-- CREATE INDEX (not CONCURRENTLY): dbmate wraps each migration in a
-- transaction, which CONCURRENTLY cannot join. These tables are small and the
-- weekly writer is a batch job, so a brief lock is the cheaper trade.

CREATE INDEX IF NOT EXISTS idx_predictions_claim
    ON public.predictions USING btree (claim_id);

CREATE INDEX IF NOT EXISTS idx_predictions_source
    ON public.predictions USING btree (source_id);

CREATE INDEX IF NOT EXISTS idx_dst_domain
    ON public.domain_sub_trends USING btree (domain_id);

CREATE INDEX IF NOT EXISTS idx_dstc_claim
    ON public.domain_sub_trend_claims USING btree (claim_id);

CREATE INDEX IF NOT EXISTS idx_dsi_domain
    ON public.domain_synthesis_insights USING btree (domain_id);

CREATE INDEX IF NOT EXISTS idx_dsic_claim
    ON public.domain_synthesis_insight_claims USING btree (claim_id);

CREATE INDEX IF NOT EXISTS idx_domain_flows_target
    ON public.domain_flows USING btree (target_id);

-- Serves the three dedupe lookups AND enforces the invariant they check for.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_url_unique
    ON public.sources USING btree (url)
    WHERE (url IS NOT NULL AND url <> ''::text);

-- migrate:down

DROP INDEX IF EXISTS public.idx_sources_url_unique;
DROP INDEX IF EXISTS public.idx_domain_flows_target;
DROP INDEX IF EXISTS public.idx_dsic_claim;
DROP INDEX IF EXISTS public.idx_dsi_domain;
DROP INDEX IF EXISTS public.idx_dstc_claim;
DROP INDEX IF EXISTS public.idx_dst_domain;
DROP INDEX IF EXISTS public.idx_predictions_source;
DROP INDEX IF EXISTS public.idx_predictions_claim;
