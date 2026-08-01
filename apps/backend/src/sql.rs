//! Read queries. Each returns a single `json` scalar so the handler is trivial.
//! Shapes mirror the legacy export_to_json.py byte-for-byte (same columns,
//! same ordering) so the frontend contract is unchanged.
//!
//! The list endpoints take `$1` as a row limit. They are inspection surfaces
//! with no UI contract, and unbounded they answered ~8 MB per request against a
//! public URL — enough that a handful of concurrent calls is a denial of
//! service, and enough to make the whole table transit the wire to answer a
//! question about its first page. `?limit=` overrides; see `list_limit`.

pub const THINKERS: &str = r#"
SELECT coalesce(json_agg(row_to_json(q) ORDER BY q.credibility_score DESC NULLS LAST), '[]'::json)
FROM (
  SELECT t.*,
    (SELECT count(*) FROM predictions WHERE thinker_id = t.id)                        AS prediction_count,
    (SELECT count(*) FROM predictions WHERE thinker_id = t.id AND status <> 'pending') AS evaluated_count,
    (SELECT count(*) FROM claims      WHERE thinker_id = t.id)                        AS claim_count,
    (SELECT count(*) FROM sources     WHERE thinker_id = t.id)                        AS source_count
  FROM thinkers t
  ORDER BY t.credibility_score DESC NULLS LAST, t.id
  LIMIT $1
) q"#;

pub const SOURCES: &str = r#"
SELECT coalesce(json_agg(row_to_json(q) ORDER BY q.date_published DESC NULLS LAST), '[]'::json)
FROM (
  SELECT s.*, t.name AS thinker_name
  FROM sources s JOIN thinkers t ON s.thinker_id = t.id
  ORDER BY s.date_published DESC NULLS LAST, s.id
  LIMIT $1
) q"#;

pub const CLAIMS: &str = r#"
SELECT coalesce(json_agg(row_to_json(q) ORDER BY coalesce(q.claim_weight, 0) DESC), '[]'::json)
FROM (
  SELECT c.*, t.name AS thinker_name, t.credibility_score,
         s.title AS source_title, s.date_published AS source_date, s.source_depth
  FROM claims c
  JOIN thinkers t ON c.thinker_id = t.id
  LEFT JOIN sources s ON c.source_id = s.id
  ORDER BY coalesce(c.claim_weight, 0) DESC, c.id
  LIMIT $1
) q"#;

pub const PREDICTIONS: &str = r#"
SELECT coalesce(json_agg(row_to_json(q) ORDER BY q.evaluation_date NULLS LAST), '[]'::json)
FROM (
  SELECT p.*, t.name AS thinker_name, t.credibility_score, s.title AS source_title
  FROM predictions p
  JOIN thinkers t ON p.thinker_id = t.id
  LEFT JOIN sources s ON p.source_id = s.id
  ORDER BY p.evaluation_date NULLS LAST, p.id
  LIMIT $1
) q"#;

pub const STATS: &str = r#"
SELECT json_build_object(
  'thinkers',              (SELECT count(*) FROM thinkers),
  'sources',               (SELECT count(*) FROM sources),
  'claims',                (SELECT count(*) FROM claims),
  'predictions',           (SELECT count(*) FROM predictions),
  'evaluated_predictions', (SELECT count(*) FROM predictions WHERE status <> 'pending'),
  'avg_credibility',       (SELECT round(avg(credibility_score)::numeric, 1) FROM thinkers),
  'claims_by_domain',      (SELECT coalesce(json_object_agg(domain, c), '{}'::json)
                            FROM (SELECT domain, count(*) c FROM claims WHERE domain IS NOT NULL GROUP BY domain) d),
  'predictions_by_status', (SELECT coalesce(json_object_agg(status, c), '{}'::json)
                            FROM (SELECT status, count(*) c FROM predictions WHERE status IS NOT NULL GROUP BY status) p)
)"#;
