-- migrate:up

-- Turn the dormant `innovations` stub into a real model, and give an innovation
-- a durable many-to-many mapping onto the key shifts it is an example of.
--
-- Four things this has to get right.
--
-- 1. THE UNIQUE KEY IS NULLABLE, SO THE UPSERT SILENTLY DOESN'T.
--
-- `source_innovation_id` carries a UNIQUE constraint but no NOT NULL. Postgres
-- treats NULLs as distinct in a unique index, so the ingest handler's
-- `ON CONFLICT (source_innovation_id) DO UPDATE` never fires for a payload that
-- omitted it — every retry of the same innovation inserts another row, forever,
-- and nothing ever reports a problem. The upstream database always sends the id;
-- requiring it is what makes the endpoint idempotent as documented.
--
-- SET NOT NULL will fail loudly if any NULL row exists. That is deliberate:
-- silently deleting ingested rows to make a migration pass is worse than
-- stopping. The route has never been enabled in any environment (INGEST_TOKEN
-- unset everywhere), so this table should be empty — check with
-- `SELECT count(*) FROM innovations` before applying.
--
-- 2. A FOREIGN KEY TO THE TAXONOMY WOULD BE DELETED EVERY MONDAY.
--
-- mapgen's `reset_v2_tables` runs
--   TRUNCATE domain_key_trends, domain_sub_trends, … RESTART IDENTITY CASCADE
-- on every synthesize run, so a key shift's primary key is recycled weekly and
-- means nothing across runs. A link table referencing domain_key_trends(id)
-- would be cascade-emptied on the first publication after it was populated.
--
-- The precedent is `shift_module_overrides`, which keys editor-authored module
-- lists on (scope, slug) precisely "so they survive the weekly TRUNCATE". This
-- migration promotes that idea to a real table — `shift_refs` — so the mapping
-- can be an actual foreign key to an actual row, while the identity it points at
-- is the URL slug that outlives the rebuild. `shift_refs` is upserted by the
-- publication step and never deleted, so a link survives a shift being renamed
-- and renamed back; a stale `last_published_at` is the signal that a link now
-- points at a shift no longer in the map.
--
-- 3. TAGS ARE THE QUERY KEY, SO THEY GET TABLES; THE REST STAYS JSONB.
--
-- The payload's eight tag facets are what filtering and any future tag-overlap
-- matching read, and a facet+slug pair needs to be one row shared by many
-- innovations rather than a string repeated in every jsonb blob. Everything else
-- upstream sends — source_urls, the raw cover_image descriptor, the whole
-- payload — is stored, never joined, and stays jsonb.
--
-- 4. COVER IMAGES CANNOT BE HOTLINKED.
--
-- The upstream cover URL is signed with an `exp`, and the app's CSP is
-- `img-src 'self' data:`, so a third-party image URL is both blocked by the
-- browser today and dead tomorrow. The bytes are mirrored at ingest into
-- `innovation_assets` and served from our own origin. Its own table, not a
-- bytea column on `innovations`, so the row every list query reads stays skinny
-- and the image bytes only move when an image is actually requested.
--
-- CREATE INDEX, not CONCURRENTLY: dbmate wraps each migration in a transaction,
-- which CONCURRENTLY cannot join. Every table here is new or empty.

-- ── innovations: require the identity, add the columns the API needs ─────────

ALTER TABLE public.innovations
    ALTER COLUMN source_innovation_id SET NOT NULL;

-- Backfill before the NOT NULLs below, so an already-ingested row with a null
-- title or url is repaired rather than blocking the migration.
UPDATE public.innovations
   SET title = coalesce(nullif(btrim(title), ''), 'Untitled innovation')
 WHERE title IS NULL OR btrim(title) = '';

UPDATE public.innovations
   SET article_url = ''
 WHERE article_url IS NULL;

ALTER TABLE public.innovations
    ALTER COLUMN title SET NOT NULL,
    ALTER COLUMN article_url SET NOT NULL,
    -- Ordered list of brands; element 1 is the primary brand the card shows.
    -- A typed array rather than a table: these are labels, never joined on.
    ADD COLUMN brands_list  text[] NOT NULL DEFAULT '{}',
    -- The body exactly as received. Lets a field upstream adds later be
    -- backfilled without asking for a re-send, and makes a bad transform
    -- diagnosable from the row itself.
    ADD COLUMN payload      jsonb  NOT NULL DEFAULT '{}'::jsonb,
    -- sha256 of the canonicalised payload: what lets a duplicate re-POST answer
    -- "unchanged" without a write.
    ADD COLUMN payload_hash text,
    ADD COLUMN state        text   NOT NULL DEFAULT 'active',
    ADD COLUMN cover_state  text   NOT NULL DEFAULT 'none',
    ADD COLUMN cover_error  text,
    ADD CONSTRAINT innovations_state_check
        CHECK (state = ANY (ARRAY['active'::text, 'withdrawn'::text])),
    ADD CONSTRAINT innovations_cover_state_check
        CHECK (cover_state = ANY (ARRAY['none'::text, 'stored'::text, 'failed'::text])),
    -- A backstop under the API's own check, so a future writer can't store a
    -- javascript: or file: URL the card would render as a link. The empty string
    -- is tolerated for the same reason idx_sources_url_unique is partial: a
    -- pre-existing row may have no canonical address, and inventing one for it
    -- would be worse than admitting it.
    ADD CONSTRAINT innovations_article_url_check
        CHECK (article_url = '' OR article_url ~ '^https?://');

-- Backfill the array from the jsonb the old handler wrote. The `brands` column
-- is deliberately left in place: dropping a column in the same migration that
-- adds its replacement makes `migrate:down` lossy.
UPDATE public.innovations
   SET brands_list = coalesce(
         (SELECT array_agg(value ORDER BY ordinality)
            FROM jsonb_array_elements_text(brands) WITH ORDINALITY AS t(value, ordinality)
           WHERE btrim(value) <> ''),
         '{}')
 WHERE jsonb_typeof(brands) = 'array';

-- Brand filtering is a plausible read path and an array needs GIN to serve it.
CREATE INDEX IF NOT EXISTS idx_innovations_brands
    ON public.innovations USING gin (brands_list);

-- The list endpoint pages on (created_at DESC, id DESC); the existing
-- idx_innovations_created covers only the leading column.
CREATE INDEX IF NOT EXISTS idx_innovations_feed
    ON public.innovations USING btree (created_at DESC, id DESC)
    WHERE state = 'active';

-- ── tags: normalised, closed facet list ─────────────────────────────────────
--
-- The facet list is closed on purpose. A facet upstream invents later does not
-- fail the ingest — the API preserves it in `payload` and reports it back as
-- `ignored_facets`, so taxonomy drift is visible without being an outage.

CREATE TABLE public.innovation_tags (
    id            bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    facet         text NOT NULL,
    slug          text NOT NULL,
    external_uuid uuid,
    first_seen_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT innovation_tags_facet_check CHECK (facet = ANY (ARRAY[
        'industry'::text, 'subindustry'::text, 'region'::text, 'country'::text,
        'audience'::text, 'season'::text, 'innovation-type'::text,
        'basic-human-need'::text])),
    CONSTRAINT innovation_tags_facet_slug_key UNIQUE (facet, slug)
);

-- Upstream's own identifier, when it sends one — a lookup path, not an
-- invariant. Deliberately NOT unique: (facet, slug) is our identity, and if
-- upstream ever reused a uuid across two facets a unique index would turn that
-- into a failed ingest. Same call as the closed facet list above — drift gets
-- reported, not enforced at the cost of an outage. Partial because `audience`
-- in the documented payload carries a slug and no uuid at all.
CREATE INDEX idx_innovation_tags_external
    ON public.innovation_tags USING btree (external_uuid)
    WHERE external_uuid IS NOT NULL;

CREATE TABLE public.innovation_tag_links (
    innovation_id bigint NOT NULL REFERENCES public.innovations(id)     ON DELETE CASCADE,
    tag_id        bigint NOT NULL REFERENCES public.innovation_tags(id) ON DELETE RESTRICT,
    PRIMARY KEY (innovation_id, tag_id)
);

-- The referencing side of the FK, which Postgres never indexes for us — and the
-- side every tag filter reads. Same gap the 20260803180000 migration closed for
-- seven other columns.
CREATE INDEX idx_itl_tag ON public.innovation_tag_links USING btree (tag_id);

-- ── shift_refs: the identity a link can safely point at ─────────────────────

CREATE TABLE public.shift_refs (
    id                bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    scope             text NOT NULL,
    -- key_trend: one path segment. sub_trend: 'parent/child' — the same
    -- two-segment key shift_module_overrides uses, because a sub-shift slug is
    -- only unique beneath its parent.
    slug              text NOT NULL,
    domain_id         text,
    title             text,
    first_seen_at     timestamp with time zone NOT NULL DEFAULT now(),
    last_published_at timestamp with time zone,
    CONSTRAINT shift_refs_scope_check
        CHECK (scope = ANY (ARRAY['key_trend'::text, 'sub_trend'::text])),
    CONSTRAINT shift_refs_scope_slug_key UNIQUE (scope, slug)
);

-- ── the many-to-many mapping ────────────────────────────────────────────────

CREATE TABLE public.innovation_shift_links (
    innovation_id bigint  NOT NULL REFERENCES public.innovations(id) ON DELETE CASCADE,
    shift_ref_id  bigint  NOT NULL REFERENCES public.shift_refs(id)  ON DELETE CASCADE,
    -- Who decided this link. 'auto' is reserved for a future tag-overlap
    -- suggester; recording provenance is what stops an automated pass silently
    -- overwriting an editor's decision.
    source        text    NOT NULL DEFAULT 'editor',
    confidence    real,
    sort_order    integer NOT NULL DEFAULT 0,
    note          text,
    enabled       boolean NOT NULL DEFAULT true,
    created_at    timestamp with time zone NOT NULL DEFAULT now(),
    updated_at    timestamp with time zone NOT NULL DEFAULT now(),
    -- The composite key is the point: one innovation on many shifts, one shift
    -- carrying many innovations, and a duplicate pair structurally impossible —
    -- which is what makes both the ingest path and the curation PUT idempotent
    -- without any extra bookkeeping.
    PRIMARY KEY (innovation_id, shift_ref_id),
    CONSTRAINT innovation_shift_links_source_check
        CHECK (source = ANY (ARRAY['ingest'::text, 'editor'::text, 'auto'::text])),
    CONSTRAINT innovation_shift_links_confidence_check
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

-- The hot read: shift → its innovations, once per snapshot rebuild.
CREATE INDEX idx_isl_shift
    ON public.innovation_shift_links USING btree (shift_ref_id) WHERE enabled;

-- The backend folds max(updated_at) into its cache version so an ETag changes
-- the moment a link does.
CREATE INDEX idx_isl_updated
    ON public.innovation_shift_links USING btree (updated_at DESC);

-- ── mirrored cover images ───────────────────────────────────────────────────

CREATE TABLE public.innovation_assets (
    innovation_id bigint  NOT NULL REFERENCES public.innovations(id) ON DELETE CASCADE,
    kind          text    NOT NULL DEFAULT 'cover',
    bytes         bytea   NOT NULL,
    mime          text    NOT NULL,
    byte_size     integer NOT NULL,
    sha256        text    NOT NULL,
    source_url    text    NOT NULL,
    fetched_at    timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (innovation_id, kind),
    CONSTRAINT innovation_assets_kind_check
        CHECK (kind = ANY (ARRAY['cover'::text])),
    CONSTRAINT innovation_assets_mime_check CHECK (mime = ANY (ARRAY[
        'image/jpeg'::text, 'image/png'::text, 'image/webp'::text,
        'image/avif'::text])),
    -- Mirrors the 5 MiB cap the fetcher enforces, so a bad write can't land a
    -- row the fetcher would have refused.
    CONSTRAINT innovation_assets_size_check
        CHECK (byte_size > 0 AND byte_size <= 5242880)
);

-- migrate:down

DROP TABLE IF EXISTS public.innovation_assets;
DROP TABLE IF EXISTS public.innovation_shift_links;
DROP TABLE IF EXISTS public.shift_refs;
DROP TABLE IF EXISTS public.innovation_tag_links;
DROP TABLE IF EXISTS public.innovation_tags;

DROP INDEX IF EXISTS public.idx_innovations_feed;
DROP INDEX IF EXISTS public.idx_innovations_brands;

ALTER TABLE public.innovations
    DROP CONSTRAINT IF EXISTS innovations_article_url_check,
    DROP CONSTRAINT IF EXISTS innovations_cover_state_check,
    DROP CONSTRAINT IF EXISTS innovations_state_check,
    DROP COLUMN IF EXISTS cover_error,
    DROP COLUMN IF EXISTS cover_state,
    DROP COLUMN IF EXISTS state,
    DROP COLUMN IF EXISTS payload_hash,
    DROP COLUMN IF EXISTS payload,
    DROP COLUMN IF EXISTS brands_list,
    ALTER COLUMN article_url DROP NOT NULL,
    ALTER COLUMN title DROP NOT NULL,
    ALTER COLUMN source_innovation_id DROP NOT NULL;
