"""
Prompt builders for the domain-first trend-map generator (see mapgen/).

Each function loads a shared template from packages/prompts/map/ and renders it
with values computed in code. Response parsing (parse_thinker_attribution, …)
stays in the step — these functions only build requests.
"""
import os

from ._loader import load_and_render
from .voice import VOICE

# ── Model assignment ─────────────────────────────────────────
# Editorial synthesis (Key Trends, sub-trends, attribution) runs on Sonnet 4.6.
SYNTHESIS_MODEL = 'claude-sonnet-4-6'
# Synthesis insights — the most editorially demanding, lowest-volume phase — runs on Opus 4.7.
INSIGHTS_MODEL = os.environ.get('INSIGHTS_MODEL', 'claude-sonnet-4-6')

# Default number of Key Trends to ask for per domain (the step may override).
MIN_KTS_PER_DOM = 8


def fmt_claims_block(claims: list, max_per: int | None = None) -> str:
    if max_per:
        claims = claims[:max_per]
    lines = []
    for c in claims:
        cred = f"{c['credibility_score']:.0f}" if c['credibility_score'] else '?'
        text = (c['claim_text'] or '')[:220]
        lines.append(f"[id:{c['id']}] [{c['thinker']}, cred:{cred}] [{c['signal_strength']}] {text}")
        if c.get('consumer_implication'):
            lines.append(f"  → implication: {c['consumer_implication'][:120]}")
    return '\n'.join(lines)


# ── Phase 3: Key Trend generation per domain ───────────────────────────────

def prompt_domain_key_trends(domain: dict, claims: list, min_kts: int = MIN_KTS_PER_DOM) -> str:
    return load_and_render(
        "map/key_trends.txt",
        voice=VOICE,
        domain_name=domain['name'],
        domain_description=domain['description'][:400],
        min_kts=min_kts,
        claim_count=len(claims),
        evidence=fmt_claims_block(claims, max_per=180),
    )


# ── Phase 5: Sub-trend clustering per KT ───────────────────────────────────

def prompt_sub_trends(kt_name: str, kt_subtitle: str, claims: list) -> str:
    return load_and_render(
        "map/sub_trends.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        claim_count=len(claims),
        evidence=fmt_claims_block(claims, max_per=90),
    )


# ── Editorial body for the shift / sub-shift reading views ──────────────────
#
# The taxonomy phases above only name and cluster. These two write the prose the
# reader actually sees. They are deliberately separate calls, one per Key Trend,
# so that a long editorial answer can never truncate the taxonomy it hangs off —
# and so a failure here degrades a page to hero + dek instead of losing the shift.

def prompt_kt_editorial(kt_name: str, kt_subtitle: str, domain_name: str, claims: list) -> str:
    return load_and_render(
        "map/kt_editorial.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        domain_name=domain_name,
        claim_count=len(claims),
        evidence=fmt_claims_block(claims, max_per=90),
    )


def prompt_st_editorial(kt_name: str, kt_subtitle: str, sub_trends: list, claims: list) -> str:
    listing = '\n'.join(
        f"- {st['name']}: {st.get('subtitle') or st.get('description', '')}"
        for st in sub_trends
    )
    return load_and_render(
        "map/st_editorial.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        sub_trends=listing,
        claim_count=len(claims),
        evidence=fmt_claims_block(claims, max_per=90),
    )


# ── Phase 6: Thinker attribution ────────────────────────────────────────────

def prompt_thinker_attribution(node_type: str, node_name: str, thinker_groups: dict) -> str:
    lines = []
    for thinker, clms in thinker_groups.items():
        lines.append(f'\n[{thinker}]')
        for c in clms[:8]:
            text = c['claim_text'] if isinstance(c, dict) else c
            lines.append(f'  - {text[:200]}')
    return load_and_render(
        "map/thinker_attribution.txt",
        node_type=node_type,
        node_name=node_name,
        thinker_claims=''.join(lines),
    )


# ── Phase 7: Interrelatedness ───────────────────────────────────────────────

def prompt_interrelatedness_batch(pairs: list) -> str:
    lines = [
        f"  Pair ({p['id_a']}, {p['id_b']}): [{p['type_a']}] {p['name_a']} | [{p['type_b']}] {p['name_b']}"
        for p in pairs
    ]
    return load_and_render("map/interrelatedness.txt", pairs='\n'.join(lines))


# ── Phase 8: Synthesis insights per domain ──────────────────────────────────

def prompt_synthesis_insights(domain_name: str, domain_desc: str, claims: list) -> str:
    return load_and_render(
        "map/synthesis_insights.txt",
        voice=VOICE,
        domain_name=domain_name,
        domain_description=domain_desc[:300],
        evidence=fmt_claims_block(claims, max_per=50),
    )
