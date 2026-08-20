-- Evidence packs: the per-shift research bundle the AI-research pipeline
-- publishes from (thinkers pipeline removed, 2026-08-20 pivot).
--
-- A pack links one shift (durable slug key, same convention as shift_art) to
-- the evidence items a deep-research pass produced for it in one run.
-- Items are `claims` rows (kept: quote span anchors, statistic verification,
-- primary_source_id all live there) whose sources are documents WE fetched
-- and stored — the research agent only points at URLs; steps/research.py
-- re-fetches each one client-side and every quote must locate verbatim in
-- our own stored copy or the item is downgraded.
--
-- `coverage` is the pack's self-audit (counts by kind/host/sector, newest
-- evidence date, primary-source share) — what the coverage gates read, and
-- what the run report prints.

-- migrate:up
CREATE TABLE public.evidence_packs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shift_slug text NOT NULL,
    run_id text NOT NULL,
    item_ids bigint[] NOT NULL DEFAULT '{}',
    coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT evidence_packs_slug_run_key UNIQUE (shift_slug, run_id)
);

CREATE INDEX evidence_packs_slug_idx
    ON public.evidence_packs (shift_slug, created_at DESC);

-- migrate:down
DROP TABLE public.evidence_packs;
