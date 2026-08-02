"""Claim routing: pick which claims each domain's generation sees.

Selection is capped, so ORDER BY must be fully deterministic — a tie at the
cut-off used to change *which* claims reached the model between runs.
"""
from __future__ import annotations

from .config import CLAIMS_PER_DOM


def route_claims_for_domain(conn, domain: dict, limit: int = CLAIMS_PER_DOM) -> list:
    """
    Pull the top `limit` high-signal claims for a strategic domain.

    Priority ladder:
      1. Claims whose claims.domain is in domain['primary_claim_domains']
      2. Claims whose claims.domain is in domain['secondary_claim_domains']
      3. technology_capability claims whose text matches domain['tech_keywords']

    Within each tier, rank by claim_weight × freshness_score × credibility.
    Returns list of plain dicts.
    """
    primary   = domain['primary_claim_domains']
    secondary = domain['secondary_claim_domains']
    keywords  = domain['tech_keywords']

    # No DISTINCT: c.id (PK) is selected and the joins are 1:1 (one thinker, at
    # most one source per claim), so rows are already unique — and DISTINCT would
    # forbid ordering by the computed score expression below.
    SELECT = """
        SELECT c.id, c.claim_text, c.quote, c.consumer_implication,
               c.signal_strength, c.specificity, c.domain AS claim_domain,
               t.name AS thinker, t.credibility_score, t.discovered AS thinker_discovered,
               s.title AS source_title, s.date_published
        FROM claims c
        JOIN thinkers t ON c.thinker_id = t.id
        LEFT JOIN sources s ON c.source_id = s.id
        WHERE c.signal_strength IN ('signal','strong_signal')
          AND c.duplicate_of IS NULL
    """
    ORDER = """
        ORDER BY COALESCE(c.claim_weight,0) * COALESCE(c.freshness_score,0.5)
                 * (GREATEST(COALESCE(t.credibility_score,50.0), 30.0) / 100.0) DESC,
                 c.id
        LIMIT %s
    """

    # Tier 1: primary domains
    p_ph = ','.join(['%s'] * len(primary))
    tier1 = [dict(r) for r in conn.execute(
        f"{SELECT} AND c.domain IN ({p_ph}) {ORDER}", (*primary, limit)
    ).fetchall()]

    seen = {r['id'] for r in tier1}
    remaining = limit - len(tier1)

    # Tier 2: secondary domains
    tier2 = []
    if remaining > 0 and secondary:
        s_ph = ','.join(['%s'] * len(secondary))
        excl = f"AND c.id NOT IN ({','.join(str(i) for i in seen)})" if seen else ''
        tier2 = [dict(r) for r in conn.execute(
            f"{SELECT} AND c.domain IN ({s_ph}) {excl} {ORDER}", (*secondary, remaining)
        ).fetchall()]
        seen |= {r['id'] for r in tier2}
        remaining -= len(tier2)

    # Tier 3: technology_capability with keyword filter
    tier3 = []
    if remaining > 0 and keywords:
        kw_cond = ' OR '.join(f"LOWER(c.claim_text) LIKE '%{kw}%'" for kw in keywords)
        excl = f"AND c.id NOT IN ({','.join(str(i) for i in seen)})" if seen else ''
        tier3 = [dict(r) for r in conn.execute(
            f"{SELECT} AND c.domain = 'technology_capability' AND ({kw_cond}) {excl} {ORDER}",
            (remaining,)
        ).fetchall()]

    claims = tier1 + tier2 + tier3
    # Ensure thinker diversity: at least 5 distinct voices
    return _diversify(claims, min_thinkers=5, total=limit)


def _diversify(candidates: list, min_thinkers: int = 5, total: int = 100) -> list:
    """Guarantee at least min_thinkers distinct thinkers in the returned list."""
    if not candidates:
        return candidates
    available = {c['thinker'] for c in candidates}
    quota = min(min_thinkers, len(available))
    seeded: list = []
    seeded_ids: set = set()
    t_seen: set = set()
    for c in candidates:
        if len(t_seen) >= quota:
            break
        if c['thinker'] not in t_seen:
            seeded.append(c); seeded_ids.add(c['id']); t_seen.add(c['thinker'])
    result = seeded[:]
    for c in candidates:
        if len(result) >= total:
            break
        if c['id'] not in seeded_ids:
            result.append(c)
    return result
