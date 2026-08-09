-- migrate:up

-- ── The sphere id becomes US spelling: organisations → organizations ───────
--
-- It was British on purpose. The id is the URL segment, the `shift_refs` key
-- and the `domains_v2` primary key, so renaming it 404s every published link —
-- and the comment in mapgen/config.py said as much for months.
--
-- What changed is that the cost landed on a reader instead of on us:
-- `/map/organizations` was a 404 you could reach by typing the name printed on
-- the page, while `/map/organisations` was the one that worked. The site had
-- not launched, so the link breakage is free, and this rides along with the
-- `/map` prefix drop — every URL moves once rather than twice.
--
-- Five foreign keys reference domains_v2(id) and NONE of them is
-- ON UPDATE CASCADE, so a plain UPDATE on the primary key fails. The row is
-- copied under the new id, children are repointed, and the old row is deleted
-- last — which also keeps the FKs satisfied at every point in between.
--
-- Every statement is guarded on the literal, so this is a no-op on a database
-- that has already been rebuilt from the renamed mapgen/config.py.

INSERT INTO public.domains_v2
       (id, name, label, short_description, description, sort_order, horizon, intro)
SELECT 'organizations', d.name, d.label, d.short_description, d.description,
       d.sort_order, d.horizon, d.intro
  FROM public.domains_v2 d
 WHERE d.id = 'organisations'
    ON CONFLICT (id) DO NOTHING;

-- FK'd children.
UPDATE public.domain_key_trends         SET domain_id = 'organizations' WHERE domain_id = 'organisations';
UPDATE public.domain_sub_trends         SET domain_id = 'organizations' WHERE domain_id = 'organisations';
UPDATE public.domain_synthesis_insights SET domain_id = 'organizations' WHERE domain_id = 'organisations';
UPDATE public.domain_flows              SET source_id = 'organizations' WHERE source_id = 'organisations';
UPDATE public.domain_flows              SET target_id = 'organizations' WHERE target_id = 'organisations';

-- Carries a sphere id but has no foreign key, so it would have been missed:
-- shift_module_visibility is the editor-authored table that survives the
-- weekly TRUNCATE, and shift_refs is what innovations join through.
UPDATE public.shift_module_visibility SET domain_id = 'organizations' WHERE domain_id = 'organisations';
UPDATE public.shift_refs              SET domain_id = 'organizations' WHERE domain_id = 'organisations';

DELETE FROM public.domains_v2 WHERE id = 'organisations';

-- migrate:down

INSERT INTO public.domains_v2
       (id, name, label, short_description, description, sort_order, horizon, intro)
SELECT 'organisations', d.name, d.label, d.short_description, d.description,
       d.sort_order, d.horizon, d.intro
  FROM public.domains_v2 d
 WHERE d.id = 'organizations'
    ON CONFLICT (id) DO NOTHING;

UPDATE public.domain_key_trends         SET domain_id = 'organisations' WHERE domain_id = 'organizations';
UPDATE public.domain_sub_trends         SET domain_id = 'organisations' WHERE domain_id = 'organizations';
UPDATE public.domain_synthesis_insights SET domain_id = 'organisations' WHERE domain_id = 'organizations';
UPDATE public.domain_flows              SET source_id = 'organisations' WHERE source_id = 'organizations';
UPDATE public.domain_flows              SET target_id = 'organisations' WHERE target_id = 'organizations';
UPDATE public.shift_module_visibility   SET domain_id = 'organisations' WHERE domain_id = 'organizations';
UPDATE public.shift_refs                SET domain_id = 'organisations' WHERE domain_id = 'organizations';

DELETE FROM public.domains_v2 WHERE id = 'organizations';
