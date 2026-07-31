"""
Reputability gate + authority scoring — the hybrid quality bar for content that
isn't authored by a curated roster person.

Pure functions (no DB) so they're trivially unit-testable; `discover.py` and
`process_raw.py` load the curated venue-tier overrides / allowlist from the DB
and pass them in.

authority ∈ [0,1] blends:
  • venue tier   (reputable_venues; 1 = top → 1.0, unknown → ~0.4)
  • citations    (log-scaled; ~1000 cites → 1.0) when known
  • entity tier  (curated editor override on the primary author/org)
"""
from __future__ import annotations

import math

# Fallback venue tiers (substring match, lowercased) when the DB overrides table
# isn't consulted. 1 = most reputable.
DEFAULT_VENUE_TIERS: dict[str, int] = {
    "nature": 1, "science": 1, "pnas": 1,
    "neurips": 1, "icml": 1, "iclr": 1, "acl": 1, "cvpr": 1,
    "quarterly journal of economics": 1, "american economic review": 1, "econometrica": 1,
    "aaai": 2, "emnlp": 2, "nber": 2, "journal of economic perspectives": 2,
    "arxiv": 3, "ssrn": 3,
}

_TIER_SCORE = {1: 1.0, 2: 0.82, 3: 0.6, 4: 0.45, 5: 0.3}


def venue_tier(name: str | None, overrides: dict[str, int] | None = None) -> int:
    """Resolve a venue name to a tier. `overrides` (from reputable_venues) wins on
    exact (case-insensitive) match; otherwise a substring match against defaults;
    otherwise 4 (unknown-but-present)."""
    if not name:
        return 5
    key = name.strip().lower()
    if overrides:
        low = {k.lower(): v for k, v in overrides.items()}
        if key in low:
            return low[key]
    for frag, tier in DEFAULT_VENUE_TIERS.items():
        if frag in key:
            return tier
    return 4


def citation_component(cites: int | None) -> float | None:
    if cites is None:
        return None
    return max(0.0, min(1.0, math.log10(1 + max(0, cites)) / 3.0))  # 1000 → 1.0


def compute_authority(*, citation_count: int | None, tier: int,
                      entity_tier: int | None = None) -> float:
    """Blend venue tier, citations, and any editor entity tier into 0..1."""
    v = _TIER_SCORE.get(tier, 0.4)
    c = citation_component(citation_count)
    e = _TIER_SCORE.get(entity_tier) if entity_tier else None

    parts, weights = [v], [0.5]
    if c is not None:
        parts.append(c); weights.append(0.4)
    if e is not None:
        parts.append(e); weights.append(0.2)
    total_w = sum(weights)
    score = sum(p * w for p, w in zip(parts, weights)) / total_w
    return round(max(0.0, min(1.0, score)), 3)


def is_reputable(paper: dict, *, allowlist: set[str] | None = None,
                 venue_overrides: dict[str, int] | None = None,
                 min_citations: int = 0, min_authority: float = 0.35) -> tuple[bool, float]:
    """Decide whether a discovered paper clears the bar. Returns (passed, authority).

    Passes if ANY of:
      • an author or the venue is in the curated allowlist (always in), OR
      • citation_count ≥ min_citations AND authority ≥ min_authority, OR
      • authority ≥ min_authority (covers reputable venues with no citation data).
    """
    allow = {a.lower() for a in (allowlist or set())}
    authors = [a.lower() for a in paper.get("authors", [])]
    venue = (paper.get("venue") or "").lower()
    tier = venue_tier(paper.get("venue"), venue_overrides)
    authority = compute_authority(citation_count=paper.get("citation_count"), tier=tier)

    if allow and (venue in allow or any(a in allow for a in authors)):
        return True, max(authority, 0.6)

    cites = paper.get("citation_count")
    if cites is not None and cites >= min_citations and authority >= min_authority:
        return True, authority
    if authority >= min_authority:
        return True, authority
    return False, authority
