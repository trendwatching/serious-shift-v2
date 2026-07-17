"""
Read queries over the Postgres data store.

This is the worked **template** for the SQLite→Postgres repoint and doubles as
the functional spec for the Rust backend's read API (apps/backend). Each
function returns plain data (list[dict] / dict / int) — presentation is the
caller's job, unlike the legacy query_vault.py which printed inline.

Conversions applied vs the SQLite original:
  * `?`            → `%s`
  * `name LIKE ?`  → `name ILIKE %s`  (case-insensitive, Postgres)
  * `IN (?,?,…)`   → `= ANY(%s)`      (pass a Python list; no dynamic placeholders)
  * f-string `WHERE domain='{domain}'` (injection) → parameterized `%s`
"""
from __future__ import annotations

from ..core import db

ACTIVE_CLAIMS = "c.duplicate_of IS NULL"

# signal_strength ordering, for "at least this strong" filters
SIGNAL_ORDER = {"noise": 0, "background": 1, "signal": 2, "strong_signal": 3}


def _signals_at_least(min_strength: str) -> list[str]:
    floor = SIGNAL_ORDER.get(min_strength, 2)
    return [k for k, v in SIGNAL_ORDER.items() if v >= floor]


# 1. THINKER PROFILE
def get_thinker_profile(conn, name: str) -> dict | None:
    t = db.query_one(conn, "SELECT * FROM thinkers WHERE name ILIKE %s", (f"%{name}%",))
    if not t:
        return None
    active = db.query_one(
        conn,
        f"SELECT COUNT(*) AS n FROM claims c WHERE c.thinker_id = %s AND {ACTIVE_CLAIMS}",
        (t["id"],),
    )["n"]
    total = db.query_one(
        conn, "SELECT COUNT(*) AS n FROM claims WHERE thinker_id = %s", (t["id"],)
    )["n"]
    predictions = db.query(
        conn,
        """SELECT prediction_id, claim_text, status, consensus_alignment, evaluation_date
           FROM predictions WHERE thinker_id = %s ORDER BY evaluation_date""",
        (t["id"],),
    )
    top_claims = db.query(
        conn,
        f"""SELECT claim_text, domain, claim_weight, freshness_score
            FROM claims c
            WHERE c.thinker_id = %s AND {ACTIVE_CLAIMS}
              AND c.signal_strength = ANY(%s)
            ORDER BY COALESCE(c.claim_weight, 0) DESC LIMIT 10""",
        (t["id"], ["strong_signal", "signal"]),
    )
    return {
        "thinker": t,
        "active_claims": active,
        "total_claims": total,
        "predictions": predictions,
        "top_claims": top_claims,
    }


# 2. CLAIMS BY DOMAIN
def get_claims_by_domain(conn, domain: str, min_signal_strength: str = "signal") -> list[dict]:
    return db.query(
        conn,
        f"""SELECT c.claim_text, c.claim_type, c.signal_strength, c.specificity,
                   c.claim_weight, t.name AS thinker, s.date_published
            FROM claims c
            JOIN thinkers t ON c.thinker_id = t.id
            LEFT JOIN sources s ON c.source_id = s.id
            WHERE c.domain = %s AND c.signal_strength = ANY(%s) AND {ACTIVE_CLAIMS}
            ORDER BY COALESCE(c.claim_weight, 0) DESC""",
        (domain, _signals_at_least(min_signal_strength)),
    )


# 3. CREDIBILITY LEADERBOARD
def get_credibility_leaderboard(conn) -> list[dict]:
    return db.query(
        conn,
        """SELECT name, credibility_score, prediction_accuracy, outlier_factor,
                  (SELECT COUNT(*) FROM predictions WHERE thinker_id = thinkers.id) AS pred_count,
                  (SELECT COUNT(*) FROM predictions WHERE thinker_id = thinkers.id AND status != 'pending') AS eval_count
           FROM thinkers ORDER BY credibility_score DESC""",
    )


# 4. PREDICTIONS EVALUABLE BY DATE
def get_predictions_evaluable_by(conn, date_str: str) -> list[dict]:
    return db.query(
        conn,
        """SELECT p.prediction_id, p.claim_text, p.evaluation_date, p.status,
                  p.consensus_alignment, t.name AS thinker
           FROM predictions p JOIN thinkers t ON p.thinker_id = t.id
           WHERE p.evaluation_date IS NOT NULL AND p.evaluation_date <= %s
           ORDER BY p.evaluation_date""",
        (date_str,),
    )


# 5. CONTRARIAN SIGNALS
def get_contrarian_signals(conn) -> list[dict]:
    return db.query(
        conn,
        """SELECT p.prediction_id, p.claim_text, p.consensus_alignment, p.domain,
                  t.name AS thinker, t.credibility_score
           FROM predictions p JOIN thinkers t ON p.thinker_id = t.id
           WHERE p.consensus_alignment <= 0.25 ORDER BY p.consensus_alignment""",
    )


# 6. CONSENSUS CLAIMS
def get_consensus_claims(conn) -> list[dict]:
    return db.query(
        conn,
        """SELECT p.prediction_id, p.claim_text, p.consensus_alignment, p.domain, t.name AS thinker
           FROM predictions p JOIN thinkers t ON p.thinker_id = t.id
           WHERE p.consensus_alignment >= 0.6 ORDER BY p.consensus_alignment DESC""",
    )


# 7. THINKER EVOLUTION
def get_thinker_evolution(conn, name: str) -> list[dict]:
    t = db.query_one(conn, "SELECT id, name FROM thinkers WHERE name ILIKE %s", (f"%{name}%",))
    if not t:
        return []
    return db.query(
        conn,
        f"""SELECT c.claim_text, c.claim_type, c.domain, c.claim_weight, s.date_published
            FROM claims c LEFT JOIN sources s ON c.source_id = s.id
            WHERE c.thinker_id = %s AND {ACTIVE_CLAIMS}
            ORDER BY s.date_published""",
        (t["id"],),
    )


# 8. CONCEPT DEEP DIVE
def get_concept_deep_dive(conn, concept_name: str) -> dict | None:
    c = db.query_one(conn, "SELECT * FROM concepts WHERE name ILIKE %s", (f"%{concept_name}%",))
    if not c:
        return None
    linked = db.query_one(
        conn,
        f"""SELECT COUNT(DISTINCT cc.claim_id) AS n FROM claim_concepts cc
            JOIN claims c ON cc.claim_id = c.id WHERE cc.concept_id = %s AND {ACTIVE_CLAIMS}""",
        (c["id"],),
    )["n"]
    thinkers = db.query(
        conn,
        """SELECT t.name, ct.stance FROM concept_thinkers ct
           JOIN thinkers t ON ct.thinker_id = t.id WHERE ct.concept_id = %s""",
        (c["id"],),
    )
    return {"concept": c, "linked_claims": linked, "thinkers": thinkers}


# 9. TENSION BREAKDOWN
def get_tension_breakdown(conn, tension_name: str) -> dict | None:
    return db.query_one(
        conn, "SELECT * FROM tensions WHERE name ILIKE %s", (f"%{tension_name}%",)
    )


# 10. KEYNOTE MATERIAL
def get_keynote_material(conn, domain: str | None = None, min_signal: str = "signal",
                         max_results: int = 20) -> list[dict]:
    sql = f"""SELECT c.claim_text, c.domain, c.claim_weight, c.freshness_score,
                     t.name AS thinker, t.credibility_score
              FROM claims c JOIN thinkers t ON c.thinker_id = t.id
              WHERE c.signal_strength = ANY(%s) AND {ACTIVE_CLAIMS}"""
    params: list = [_signals_at_least(min_signal)]
    if domain:
        sql += " AND c.domain = %s"
        params.append(domain)
    sql += """ ORDER BY COALESCE(c.claim_weight, 0) * COALESCE(c.freshness_score, 0.5) DESC
               LIMIT %s"""
    params.append(max_results)
    return db.query(conn, sql, params)


# 11. CLAIMS SINCE DATE
def get_claims_since(conn, date_str: str) -> list[dict]:
    return db.query(
        conn,
        f"""SELECT c.claim_text, c.domain, c.claim_weight, t.name AS thinker, s.date_published
            FROM claims c JOIN thinkers t ON c.thinker_id = t.id
            LEFT JOIN sources s ON c.source_id = s.id
            WHERE s.date_published >= %s AND {ACTIVE_CLAIMS}
            ORDER BY COALESCE(c.claim_weight, 0) DESC""",
        (date_str,),
    )


# 12. PREDICTION ACCURACY BY DOMAIN  (parameterized — fixes the original f-string injection)
def get_prediction_accuracy_by_domain(conn, domain: str | None = None) -> list[dict]:
    sql = "SELECT domain, status, COUNT(*) AS cnt FROM predictions"
    params: list = []
    if domain:
        sql += " WHERE domain = %s"
        params.append(domain)
    sql += " GROUP BY domain, status ORDER BY domain"
    return db.query(conn, sql, params)


# 13. SEARCH CLAIMS
def search_claims(conn, keyword: str) -> list[dict]:
    return db.query(
        conn,
        f"""SELECT c.claim_text, c.domain, c.claim_weight, c.signal_strength,
                   t.name AS thinker, s.date_published
            FROM claims c JOIN thinkers t ON c.thinker_id = t.id
            LEFT JOIN sources s ON c.source_id = s.id
            WHERE c.claim_text ILIKE %s AND {ACTIVE_CLAIMS}
            ORDER BY COALESCE(c.claim_weight, 0) DESC""",
        (f"%{keyword}%",),
    )


# 14. INDUSTRY-RELEVANT CLAIMS
INDUSTRY_KEYWORDS = {
    "healthcare": ["health", "medical", "drug", "disease", "patient", "diagnosis", "pharma"],
    "finance": ["bank", "financ", "invest", "trading", "wealth", "insurance"],
    "education": ["educat", "school", "student", "learn", "university", "teacher"],
    "retail": ["retail", "shop", "consumer", "purchase", "buy", "commerce", "brand"],
    "media": ["media", "content", "publish", "news", "journal", "advertis"],
    "legal": ["legal", "law", "court", "attorney", "regulat", "compliance"],
    "software": ["code", "software", "develop", "engineer", "program", "coding"],
}


def get_industry_relevant_claims(conn, industry: str) -> list[dict]:
    keywords = INDUSTRY_KEYWORDS.get(industry.lower(), [industry.lower()])
    # Match any keyword: claim_text ILIKE ANY(array_of_patterns)
    patterns = [f"%{k}%" for k in keywords]
    return db.query(
        conn,
        f"""SELECT c.claim_text, c.domain, c.claim_weight, t.name AS thinker, t.credibility_score
            FROM claims c JOIN thinkers t ON c.thinker_id = t.id
            WHERE c.claim_text ILIKE ANY(%s) AND {ACTIVE_CLAIMS}
            ORDER BY COALESCE(c.claim_weight, 0) DESC""",
        (patterns,),
    )


# DATABASE STATS
def get_db_stats(conn) -> dict:
    total = db.query_one(conn, "SELECT COUNT(*) AS n FROM claims")["n"]
    active = db.query_one(
        conn, f"SELECT COUNT(*) AS n FROM claims c WHERE {ACTIVE_CLAIMS}"
    )["n"]
    counts = {}
    for tbl in ["thinkers", "sources", "predictions", "concepts", "tensions", "claim_concepts"]:
        counts[tbl] = db.query_one(conn, f"SELECT COUNT(*) AS n FROM {tbl}")["n"]
    return {"claims_total": total, "claims_active": active,
            "claims_duplicate": total - active, **counts}
