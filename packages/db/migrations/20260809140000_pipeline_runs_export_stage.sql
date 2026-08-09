-- migrate:up

-- ── `export` becomes a stage in its own right ──────────────────────────────
--
-- `mapgen.cli --export-only` republishes documents['map'] from the v2 tables.
-- It is the documented recovery from a failed publication — free, no API calls,
-- and the thing anyone reaches for after fixing a validation issue.
--
-- It opened no `pipeline_runs` row at all. So the history said "last
-- synthesize: failed" while the map serving on the site was fresh and correct,
-- which is the worst kind of wrong: it reads as an outage during the one window
-- where someone is already anxious about the content.
--
-- It cannot borrow the `synthesize` stage. A re-export costs nothing and
-- processes no claims, so recording it as a synthesis would drag every
-- cost-per-run and claims-per-run average toward zero, and the escalation rule
-- that compares a stage against its own previous run would start measuring
-- generation against re-publication. `ingest` and `full` are wrong for the same
-- reasons in the other direction.

ALTER TABLE public.pipeline_runs
  DROP CONSTRAINT IF EXISTS pipeline_runs_stage_check;

ALTER TABLE public.pipeline_runs
  ADD CONSTRAINT pipeline_runs_stage_check
  CHECK (stage = ANY (ARRAY['ingest'::text, 'synthesize'::text,
                            'full'::text, 'export'::text]));

-- migrate:down

-- Rows written under the new stage would violate the narrower constraint, so
-- they are folded into `synthesize` rather than deleted: a re-export IS a
-- publication, and losing the record of one is worse than mislabelling it.
UPDATE public.pipeline_runs SET stage = 'synthesize' WHERE stage = 'export';

ALTER TABLE public.pipeline_runs
  DROP CONSTRAINT IF EXISTS pipeline_runs_stage_check;

ALTER TABLE public.pipeline_runs
  ADD CONSTRAINT pipeline_runs_stage_check
  CHECK (stage = ANY (ARRAY['ingest'::text, 'synthesize'::text, 'full'::text]));
