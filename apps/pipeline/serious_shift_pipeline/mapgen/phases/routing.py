"""Phase 2 — route claims to domains (no API calls)."""
from __future__ import annotations

from ..config import CLAIMS_PER_DOM, DOMAINS
from ..routing import route_claims_for_domain


def phase2_claim_routing(conn) -> dict:
    """Returns {domain_id: [claim_dict, ...]} for Key Trend generation."""
    print('\nPhase 2 — Routing claims to domains (SQL heuristic, no API)…')
    domain_claims = {}
    for d in DOMAINS:
        claims = route_claims_for_domain(conn, d, limit=CLAIMS_PER_DOM)
        domain_claims[d['id']] = claims
        thinkers = len({c['thinker'] for c in claims})
        print(f"  {d['name']:<15}  {len(claims):3d} claims  |  {thinkers} thinkers")
    return domain_claims
