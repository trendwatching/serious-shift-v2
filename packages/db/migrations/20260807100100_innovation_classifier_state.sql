-- migrate:up

-- What the classifier already decided about, so a rerun that changes nothing
-- costs nothing.
--
-- Three things can invalidate a classification, and all three have to be
-- detectable from the row alone:
--   * the innovation changed  -> updated_at > classified_at
--   * the shifts changed      -> classified_corpus_hash <> the current hash
--   * it was never classified -> classified_at IS NULL
--
-- The corpus hash is sha256 over the (scope, slug, name, subtitle, from, to) of
-- every shift in the current publication, sorted. A rename, a re-framing or a
-- new shift all move it; republishing identical content does not. That is what
-- makes the hourly sweep free on a quiet hour and complete after a Monday.

ALTER TABLE public.innovations
    ADD COLUMN classified_at          timestamp with time zone,
    ADD COLUMN classified_corpus_hash text;

-- The sweep's driving predicate. Partial, because a classified-and-current row
-- is the overwhelming majority and never needs to be visited.
CREATE INDEX idx_innovations_unclassified
    ON public.innovations USING btree (id)
    WHERE state = 'active' AND classified_at IS NULL;

CREATE INDEX idx_innovations_classified_corpus
    ON public.innovations USING btree (classified_corpus_hash)
    WHERE state = 'active';

-- migrate:down

DROP INDEX IF EXISTS public.idx_innovations_classified_corpus;
DROP INDEX IF EXISTS public.idx_innovations_unclassified;

ALTER TABLE public.innovations
    DROP COLUMN IF EXISTS classified_corpus_hash,
    DROP COLUMN IF EXISTS classified_at;
