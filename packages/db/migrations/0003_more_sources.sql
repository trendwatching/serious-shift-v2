-- migrate:up
-- Fill the two remaining scrape gaps. The 0002 manifest already covers 67/69
-- thinkers with a scrapable feed (blog/rss/youtube); Geoffrey Hinton and Yann
-- LeCun publish mainly on X/Facebook (not scrapable), so we add their academic
-- publication indexes as low-cadence scrape_index sources. (Everyone else's
-- canonical feed — Marginal Revolution, Stratechery, Exponential View, etc. —
-- is already in 0002, so there is nothing useful to add for them.)

INSERT INTO scrape_sources (thinker_id, platform, method, url, rss, channel_url, handle, note)
SELECT id, 'blog', 'scrape_index', 'https://www.cs.toronto.edu/~hinton/papers.html', NULL, NULL, NULL,
       'Academic publications index (low cadence; primary commentary is on X).'
FROM thinkers WHERE name = 'Geoffrey Hinton';

INSERT INTO scrape_sources (thinker_id, platform, method, url, rss, channel_url, handle, note)
SELECT id, 'blog', 'scrape_index', 'http://yann.lecun.com/exdb/publis/', NULL, NULL, NULL,
       'Academic publications index (low cadence; primary commentary is on X/Facebook).'
FROM thinkers WHERE name = 'Yann LeCun';

-- migrate:down
DELETE FROM scrape_sources
 WHERE url IN ('https://www.cs.toronto.edu/~hinton/papers.html',
               'http://yann.lecun.com/exdb/publis/');
