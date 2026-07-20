-- migrate:up
-- =============================================================================
-- 0005 — Curated individual voices (editor-added).
--
-- Adds high-signal people as entities + their primary feed to scrape_sources.
-- Reuses the existing scrapers: Substacks/blogs via method='rss' (scrape_rss),
-- personal sites via method='scrape_index', LinkedIn/X via method='manual'.
-- reputation_tier reflects the editor's stated signal (1 = essential).
-- Additive only (no new tables); safe/idempotent via ON CONFLICT.
-- =============================================================================

INSERT INTO thinkers (name, entity_kind, reputation_tier, affiliation) VALUES
  ('Jaron Lanier',   'person', 1, 'Microsoft / independent'),
  ('Jack Clark',     'person', 1, 'Anthropic'),
  ('Ray Dalio',      'person', 2, 'Bridgewater Associates'),
  ('Salim Ismail',   'person', 2, 'OpenExO'),
  ('Thomas Marzano', 'person', 3, 'Independent'),
  ('Timothy B. Lee', 'person', 1, 'Understanding AI'),
  ('Brandon McCord', 'person', 4, 'Independent')
ON CONFLICT (name) DO NOTHING;

-- Jack Clark — Import AI (Substack). "Arguably the most influential AI newsletter."
INSERT INTO scrape_sources (thinker_id, platform, method, url, rss, note)
SELECT id, 'substack', 'rss', 'https://importai.substack.com', 'https://importai.substack.com/feed',
       'Import AI — mirror also at jack-clark.net'
FROM thinkers WHERE name = 'Jack Clark'
UNION ALL
-- Timothy B. Lee — Understanding AI (Substack custom domain). Highest-signal.
SELECT id, 'substack', 'rss', 'https://www.understandingai.org', 'https://www.understandingai.org/feed',
       'Understanding AI — technical + commercial implications'
FROM thinkers WHERE name = 'Timothy B. Lee'
UNION ALL
-- Ray Dalio — Principled Perspectives (Substack). Macro/geopolitics/investing.
SELECT id, 'substack', 'rss', 'https://raydalio.substack.com', 'https://raydalio.substack.com/feed',
       'Principled Perspectives'
FROM thinkers WHERE name = 'Ray Dalio'
UNION ALL
-- Jaron Lanier — personal site (essays, interviews, talks, papers). No RSS.
SELECT id, 'blog', 'scrape_index', 'https://www.jaronlanier.com', NULL,
       'Personal site — index scrape'
FROM thinkers WHERE name = 'Jaron Lanier'
UNION ALL
-- Salim Ismail — content spread across salimismail.com + OpenExO. No single feed.
SELECT id, 'blog', 'scrape_index', 'https://salimismail.com', NULL,
       'Content spread across salimismail.com + OpenExO / Exponential View'
FROM thinkers WHERE name = 'Salim Ismail'
UNION ALL
-- Thomas Marzano — primarily LinkedIn. Manual collection.
SELECT id, 'linkedin', 'manual', NULL, NULL,
       'Primarily LinkedIn (design/AI/experience innovation) + keynotes'
FROM thinkers WHERE name = 'Thomas Marzano'
UNION ALL
-- Brandon McCord — primarily X + podcasts; no essential standalone publication.
SELECT id, 'x', 'manual', NULL, NULL,
       'Primarily X/Twitter + podcast appearances; low cadence'
FROM thinkers WHERE name = 'Brandon McCord';

-- migrate:down
DELETE FROM scrape_sources WHERE thinker_id IN (
  SELECT id FROM thinkers WHERE name IN (
    'Jaron Lanier','Jack Clark','Ray Dalio','Salim Ismail',
    'Thomas Marzano','Timothy B. Lee','Brandon McCord'));
DELETE FROM thinkers WHERE name IN (
  'Jaron Lanier','Jack Clark','Ray Dalio','Salim Ismail',
  'Thomas Marzano','Timothy B. Lee','Brandon McCord');
