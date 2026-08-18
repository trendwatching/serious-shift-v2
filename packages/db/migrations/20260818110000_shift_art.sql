-- Generated shift artwork, and the briefs it is generated from.
--
-- Both are keyed on (scope, slug) — the same durable key `shift_refs` and
-- `shift_module_overrides` use, and for the same reason: domain_key_trends.id is
-- recycled by reset_v2_tables every week, so a row id is not an identity.
--
-- Art lives in Postgres rather than the frontend build because it has to go live
-- in the same publication as the map. The frontend's static art is baked into the
-- backend image at build time, so anything committed there lands minutes-to-hours
-- after the document that names it — which is exactly the drift this is meant to
-- end. `innovation_assets` already serves bytes from Postgres through the
-- backend, so this is an established shape here rather than a new one.
--
-- Briefs are a SEPARATE table on purpose. They are the model-written image
-- description, and if they lived in the v2 tables the weekly TRUNCATE would
-- regenerate every brief, changing every prompt, invalidating every prompt hash
-- and re-paying for all ~250 images every single week. Keyed durably and hashed
-- on their editorial inputs, an unchanged shift costs nothing.

-- migrate:up
CREATE TABLE public.shift_art_briefs (
    scope        text NOT NULL,
    slug         text NOT NULL,
    brief        text NOT NULL,
    input_sha256 text NOT NULL,
    model        text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT shift_art_briefs_pkey PRIMARY KEY (scope, slug),
    CONSTRAINT shift_art_briefs_scope_check
        CHECK (scope = ANY (ARRAY['key_trend'::text, 'sub_trend'::text])),
    CONSTRAINT shift_art_briefs_len_check
        CHECK (length(brief) BETWEEN 1 AND 4000)
);

CREATE TABLE public.shift_art (
    scope             text NOT NULL,
    slug              text NOT NULL,
    frame             text NOT NULL,
    bytes             bytea NOT NULL,
    mime              text NOT NULL DEFAULT 'image/jpeg',
    width             integer NOT NULL,
    height            integer NOT NULL,
    byte_size         integer NOT NULL,
    sha256            text NOT NULL,
    prompt_sha256     text NOT NULL,
    style             text NOT NULL,
    model             text NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT now(),
    last_published_at timestamptz,
    CONSTRAINT shift_art_pkey PRIMARY KEY (scope, slug, frame),
    CONSTRAINT shift_art_scope_check
        CHECK (scope = ANY (ARRAY['key_trend'::text, 'sub_trend'::text])),
    CONSTRAINT shift_art_frame_check
        CHECK (frame = ANY (ARRAY['hero'::text, 'wide'::text, 'og'::text, 'tile'::text])),
    CONSTRAINT shift_art_mime_check CHECK (mime = 'image/jpeg'::text),
    -- A 2 MB ceiling on a frame that should encode to ~150 KB. Not a design
    -- constraint, a runaway guard: this table is read on every page view.
    CONSTRAINT shift_art_size_check CHECK (byte_size > 0 AND byte_size <= 2097152)
);

-- JPEG is already compressed; the default EXTENDED storage would attempt LZ
-- compression on every row and every read for nothing.
ALTER TABLE public.shift_art ALTER COLUMN bytes SET STORAGE EXTERNAL;

-- The idempotency lookup: "is the art for this prompt already here?"
CREATE INDEX shift_art_prompt_sha256_idx ON public.shift_art (prompt_sha256);

-- migrate:down
DROP TABLE public.shift_art;
DROP TABLE public.shift_art_briefs;
