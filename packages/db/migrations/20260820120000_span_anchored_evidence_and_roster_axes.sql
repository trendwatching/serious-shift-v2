-- Span-anchored evidence and roster diversity axes.
--
-- The evidence store is the existing `sources` table: it already carries the
-- bitemporal pair (date_published = event date, created_at = ingest date) and
-- — since the extraction truncations were removed — the full fetched text.
-- Claim-level verification anchors into it instead of duplicating it:
--
--  * claims.quote_start / quote_end — character span in sources.full_text
--    where the verbatim quote was located at extraction. Verification becomes
--    an exact slice comparison from then on, replacing fuzzy-match-only
--    checking, and content_sha256 lets any later sweep prove the text a span
--    was verified against is the text still on record.
--  * claims.primary_source_id — the fetched ORIGINAL document, for a claim
--    that repeats someone else's figure ("per Stanford HAI…" in a newsletter).
--    The claim keeps its author (thinker_id) and its quote anchor
--    (source_id); publication prefers the primary URL and names the
--    commentator as the via. The August 2026 content audit found zero primary
--    sources among the served map's top-cited statistics — every number was
--    laundered through a commentator. This column is where that ends.
--  * thinkers.stance / region / discipline / incentive — the diversity axes
--    the roster expansion labels and routing spreads on. Same audit: 70
--    thinkers, overwhelmingly US and investor-adjacent. _diversify can only
--    balance what is labeled.

-- migrate:up
ALTER TABLE public.claims
    ADD COLUMN quote_start integer,
    ADD COLUMN quote_end integer,
    ADD COLUMN primary_source_id bigint REFERENCES public.sources(id);

CREATE INDEX claims_primary_source_id_idx ON public.claims (primary_source_id);

ALTER TABLE public.sources
    ADD COLUMN content_sha256 text;

ALTER TABLE public.thinkers
    ADD COLUMN stance text
        CONSTRAINT thinkers_stance_check
        CHECK (stance IN ('advocate', 'critic', 'analyst')),
    ADD COLUMN region text,
    ADD COLUMN discipline text,
    ADD COLUMN incentive text;

-- migrate:down
ALTER TABLE public.thinkers
    DROP COLUMN incentive,
    DROP COLUMN discipline,
    DROP COLUMN region,
    DROP COLUMN stance;

ALTER TABLE public.sources
    DROP COLUMN content_sha256;

ALTER TABLE public.claims
    DROP COLUMN primary_source_id,
    DROP COLUMN quote_start,
    DROP COLUMN quote_end;
