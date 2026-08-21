-- Prediction resolution: make the 5,087 banked predictions resolvable.
--
-- steps/evaluate.py has admitted for months that "nothing in the pipeline
-- resolves a prediction", leaving accuracy at 0.5 for every thinker and
-- credibility_score — a factor in claim routing and hero-stat ranking —
-- effectively constant. Resolution is a two-pass loop (steps/resolve_predictions):
--
--  * TRIAGE (cheap model, once per prediction): is this resolvable at all?
--    Writes triage_status, machine-authored resolution_criteria, a resolve_by
--    date derived from the stated timeframe, and search_terms for evidence
--    retrieval. The unresolvable share is itself a finding, not a failure.
--  * RESOLVE (weekly, due predictions only): corpus evidence ingested AFTER
--    the prediction was made is retrieved by full-text search and put to a
--    judge that may abstain. Only a high-confidence verdict with cited
--    evidence writes `status`; everything else stays pending. The audit trail
--    (method, evidence ids, timestamp) lives on the row.
--
-- forecast_prob is captured going forward (extraction v2) so calibration can
-- graduate from shrunk accuracy to a real Brier score; it stays NULL for the
-- backlog, which asserted rather than quantified.

-- migrate:up
ALTER TABLE public.predictions
    ADD COLUMN triage_status text
        CONSTRAINT predictions_triage_status_check
        CHECK (triage_status IN ('resolvable', 'vague', 'unfalsifiable')),
    ADD COLUMN resolution_criteria text,
    ADD COLUMN resolve_by date,
    ADD COLUMN search_terms text,
    ADD COLUMN forecast_prob double precision
        CONSTRAINT predictions_forecast_prob_check
        CHECK (forecast_prob > 0.0 AND forecast_prob < 1.0),
    ADD COLUMN resolution_method text
        CONSTRAINT predictions_resolution_method_check
        CHECK (resolution_method IN ('judge', 'deterministic', 'human')),
    ADD COLUMN resolved_at timestamp with time zone,
    ADD COLUMN evidence_claim_ids bigint[];

CREATE INDEX predictions_due_idx
    ON public.predictions (resolve_by)
    WHERE status = 'pending' AND triage_status = 'resolvable';

-- migrate:down
DROP INDEX public.predictions_due_idx;
ALTER TABLE public.predictions
    DROP COLUMN evidence_claim_ids,
    DROP COLUMN resolved_at,
    DROP COLUMN resolution_method,
    DROP COLUMN forecast_prob,
    DROP COLUMN search_terms,
    DROP COLUMN resolve_by,
    DROP COLUMN resolution_criteria,
    DROP COLUMN triage_status;
