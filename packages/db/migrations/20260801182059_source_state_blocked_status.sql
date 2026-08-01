-- migrate:up

-- Separate "the host is refusing us" from "this source is broken".
--
-- All 11 sources sitting in `failed` are YouTube, and they share one cause:
-- YouTube blocks transcript and listing requests from datacenter IPs, which is
-- what Railway runs on. Recording that as a generic failure meant the
-- failed-source alert (threshold: 3) fired on every single run for a known
-- condition with a known remedy — which is how an operator learns to ignore
-- alerts. A blocked source is not a broken one: it needs a proxy credential,
-- not a fix, and it must not mask the next source that genuinely breaks.

ALTER TABLE public.source_state
    DROP CONSTRAINT IF EXISTS source_state_last_run_status_check;

ALTER TABLE public.source_state
    ADD CONSTRAINT source_state_last_run_status_check
    CHECK ((last_run_status = ANY (ARRAY[
        'ok'::text,       -- fetched cleanly
        'partial'::text,  -- some items fetched, some failed
        'failed'::text,   -- the source itself is broken; needs investigation
        'blocked'::text   -- the host refused us (cloud IP); needs a proxy
    ])));

-- Reclassify the known-blocked backlog so the next run starts from an honest
-- baseline rather than re-alerting on history. Scoped to youtube because that
-- is the only platform with a confirmed block; anything else stays 'failed'.
UPDATE public.source_state
   SET last_run_status = 'blocked'
 WHERE last_run_status = 'failed'
   AND platform = 'youtube';

-- migrate:down

UPDATE public.source_state
   SET last_run_status = 'failed'
 WHERE last_run_status = 'blocked';

ALTER TABLE public.source_state
    DROP CONSTRAINT IF EXISTS source_state_last_run_status_check;

ALTER TABLE public.source_state
    ADD CONSTRAINT source_state_last_run_status_check
    CHECK ((last_run_status = ANY (ARRAY['ok'::text, 'partial'::text, 'failed'::text])));
