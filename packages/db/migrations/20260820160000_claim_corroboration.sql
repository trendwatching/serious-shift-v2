-- Cross-source corroboration for claims.
--
-- Dedup (steps/deduplicate.py) already union-finds same-assertion claims into
-- groups under a primary via claims.duplicate_of — which means the group,
-- read the other way, is the corroboration signal: how many INDEPENDENT hosts
-- published this assertion. This column stores, on each primary claim, the
-- count of distinct source hosts across its group (1 = single-source).
--
-- Routing then prefers corroborated claims and discounts single-host ones —
-- the Aug 2026 audit's "media echo" problem in one number: one Microsoft blog
-- post reused 23 times was corroboration 1, no matter how many newsletters
-- repeated it, because syndicated repetition collapses into the same group
-- with the same handful of hosts.

-- migrate:up
ALTER TABLE public.claims
    ADD COLUMN corroboration_count integer;

-- migrate:down
ALTER TABLE public.claims
    DROP COLUMN corroboration_count;
