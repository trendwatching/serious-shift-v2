-- migrate:up

-- ── The sphere's "what's shifting right now" paragraph ─────────────────────
--
-- domains_v2 already carries two descriptions and neither is this one.
-- `short_description` is the evergreen one-line deck under the sphere title;
-- `description` is long-form framing that only seo.rs reads, for meta tags.
-- `intro` is a present-tense read on the current map, which is a third job.
--
-- Authored in mapgen/config.py, never here: domains_v2 is inside
-- dbutil.DROP_V2_ORDER and is TRUNCATE … RESTART IDENTITY CASCADE'd on every
-- synthesize run, so a value written straight into the table survives until the
-- following Monday and no longer.

ALTER TABLE public.domains_v2
    ADD COLUMN intro text NOT NULL DEFAULT '';


-- ── Which modules a page shows, by scope and sphere ────────────────────────
--
-- The sibling of `shift_module_overrides`, and deliberately at a different
-- grain. An override answers "what is on THIS page" with a whole hand-authored
-- module array keyed by URL slug. This answers "which module types does this
-- SPHERE show" with one boolean, keyed by (scope, domain_id, module_type).
-- Cramming both grains into one table would mean a nullable slug, a nullable
-- domain, and a CHECK to keep them apart — a worse thing to reason about than
-- two tables with one precedence rule between them.
--
-- The default matrix lives in packages/contracts/shift_modules.json and is
-- mirrored as a const in apps/backend/src/module_policy.rs. Rows here are
-- deviations from it, applied by the backend when it builds a route fragment —
-- which is what lets an editor flip a flag and see the change within
-- DOC_CACHE_TTL instead of at the next weekly publication.
--
-- Hiding is presentation only. The publication always carries every module it
-- generated and validate_map() still requires them, so a flag can never make a
-- run unpublishable and un-hiding never needs a republish.
--
-- NO FOREIGN KEY TO domains_v2, for the reason given above: the cascade would
-- delete every editor decision the first Monday after it was made. Same reason
-- shift_refs exists. An unknown domain_id is reported by the exporter, not
-- enforced by the schema.
--
-- NO `enabled` COLUMN. `visible` IS the payload, and deleting the row is how you
-- revert to the contract default — the same "delete the row to go back to
-- generated" idiom shift_module_overrides already uses.

CREATE TABLE public.shift_module_visibility (
    scope       text NOT NULL,
    -- A sphere id ('society' | 'economy' | 'consumers' | 'organizations'), or
    -- '*' meaning every sphere. An exact match beats '*'; '*' beats the
    -- contract default.
    domain_id   text NOT NULL,
    module_type text NOT NULL,
    visible     boolean NOT NULL,
    note        text,
    updated_at  timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, domain_id, module_type),
    CONSTRAINT shift_module_visibility_scope_check
        CHECK (scope = ANY (ARRAY['key_trend'::text, 'sub_trend'::text])),
    CONSTRAINT shift_module_visibility_domain_check
        CHECK (domain_id <> '' AND domain_id = lower(domain_id)),
    CONSTRAINT shift_module_visibility_type_check
        CHECK (module_type <> '' AND module_type ~ '^[a-z][a-z0-9_]*$')
);

-- The backend folds max(updated_at) into its snapshot version, so an ETag
-- changes the moment a flag does.
CREATE INDEX idx_smv_updated
    ON public.shift_module_visibility USING btree (updated_at DESC);

-- migrate:down

DROP TABLE IF EXISTS public.shift_module_visibility;

ALTER TABLE public.domains_v2
    DROP COLUMN IF EXISTS intro;
