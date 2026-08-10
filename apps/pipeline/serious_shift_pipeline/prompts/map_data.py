"""
Prompt builders for the domain-first trend-map generator (see mapgen/).

Each function loads a shared template from packages/prompts/map/ and renders it
with values computed in code. Response parsing (parse_thinker_attribution, …)
stays in the step — these functions only build requests.
"""
import json
import os

from ._loader import load_and_render
from .voice import VOICE

# ── Model assignment ─────────────────────────────────────────
# Editorial synthesis (Key Trends, sub-trends, attribution) runs on Sonnet 4.6.
SYNTHESIS_MODEL = 'claude-sonnet-4-6'
# Synthesis insights — the most editorially demanding, lowest-volume phase — runs on Opus 4.7.
INSIGHTS_MODEL = os.environ.get('INSIGHTS_MODEL', 'claude-sonnet-4-6')

# Single source of truth for how many Key Trends a domain carries — a range,
# owned by mapgen (which also gates on it at publication).
from ..mapgen.config import MAX_KTS_PER_DOM, MIN_KTS_PER_DOM  # noqa: E402


def fmt_claims_block(claims: list, max_per: int | None = None) -> str:
    if max_per:
        claims = claims[:max_per]
    lines = []
    for c in claims:
        # JSON Lines keeps attribution attached to the exact claim. The previous
        # prose formatter discarded URL, date, quote, claim type and confidence,
        # then asked the model for dated sourced prose it could not verify.
        item = {
            'id': c.get('id'),
            'claim': str(c.get('claim_text') or '')[:500],
            'claim_type': c.get('claim_type') or '',
            'signal': c.get('signal_strength') or '',
            'specificity': c.get('specificity'),
            'thinker': c.get('thinker') or '',
            # No credibility score. It is not usable in copy, the SQL already
            # ranks by it before a claim reaches this block, and offering it here
            # is how "(cred:54)" ended up inside a published sentence.
            'implication': str(c.get('consumer_implication') or '')[:300],
            'quote': str(c.get('quote') or '')[:600],
            'has_statistic': bool(c.get('has_statistic')),
            'statistic': str(c.get('statistic') or '')[:240],
            'source_title': str(c.get('source_title') or '')[:240],
            'source_date': str(c.get('date_published') or '')[:10],
            'source_url': c.get('source_url') or '',
            'source_type': c.get('source_type') or '',
            'source_confidence': c.get('source_confidence') or '',
        }
        lines.append(json.dumps(item, ensure_ascii=False, separators=(',', ':')))
    return '\n'.join(lines)


# ── Phase 3: Key Trend generation per domain ───────────────────────────────

def prompt_domain_key_trends(domain: dict, claims: list,
                             min_kts: int = MIN_KTS_PER_DOM,
                             max_kts: int = MAX_KTS_PER_DOM,
                             taken: list[str] | None = None) -> str:
    """`taken` carries the Key Trend names other domains already claimed this
    run, so the four phase-3 calls (now sequential) cannot mint near-twins of
    each other — the same advisory-ledger pattern `prompt_sub_trends` uses."""
    return load_and_render(
        "map/key_trends.txt",
        voice=VOICE,
        domain_name=domain['name'],
        domain_description=domain['description'][:400],
        min_kts=min_kts,
        max_kts=max_kts,
        taken='\n'.join(f'- {name}' for name in sorted(taken or [])) or '- (none yet)',
        claim_count=len(claims),
        evidence=fmt_claims_block(claims, max_per=180),
    )


# ── Phase 5: Sub-trend clustering per KT ───────────────────────────────────

def prompt_sub_trends(kt_name: str, kt_subtitle: str, claims: list,
                      taken: list[str] | None = None) -> str:
    """`taken` is every name already spoken for anywhere in the map.

    Without it each of the ~51 calls invents five memorable two-word names from
    overlapping evidence with no sight of the others, which is precisely how the
    2026-08-09 crawl found 22 names spread over 58 pages — "Provenance Premium"
    on seven of them. The list is advisory to the model and enforced by
    validation.py; the caller re-asks with a longer list when a collision
    survives.
    """
    return load_and_render(
        "map/sub_trends.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        claim_count=len(claims),
        taken='\n'.join(f'- {name}' for name in sorted(taken or [])) or '- (none yet)',
        evidence=fmt_claims_block(claims, max_per=90),
    )


# ── Editorial body for the shift / sub-shift reading views ──────────────────
#
# The taxonomy phases above only name and cluster. These two write the prose the
# reader actually sees. They are deliberately separate calls, one per Key Trend,
# so that a long editorial answer can never truncate the taxonomy it hangs off —
# and so a failure here degrades a page to hero + dek instead of losing the shift.

def _fmt_avoid(avoid: list | None) -> str:
    """The "already the centerpiece elsewhere" ledger, rendered like `taken`."""
    return '\n'.join(f'- {entry}' for entry in (avoid or [])) or '- (none yet)'


def prompt_kt_editorial(kt_name: str, kt_subtitle: str, domain_name: str,
                        claims: list, avoid: list | None = None) -> str:
    return load_and_render(
        "map/kt_editorial.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        domain_name=domain_name,
        claim_count=len(claims),
        avoid=_fmt_avoid(avoid),
        evidence=fmt_claims_block(claims, max_per=90),
    )


def prompt_st_editorial(kt_name: str, kt_subtitle: str, sub_trends: list,
                        claims_by_sub: dict, avoid: list | None = None) -> str:
    sections = []
    total = 0
    for st in sub_trends:
        claims = claims_by_sub.get(st['id'], [])
        total += len(claims)
        sections.append(
            f"SUB-TREND: {st['name']}\n"
            f"FRAMING: {st.get('subtitle') or st.get('description', '')}\n"
            f"ALLOWED EVIDENCE:\n{fmt_claims_block(claims, max_per=20) or '(none)'}"
        )
    return load_and_render(
        "map/st_editorial.txt",
        voice=VOICE,
        kt_name=kt_name,
        kt_subtitle=kt_subtitle,
        avoid=_fmt_avoid(avoid),
        sub_trend_evidence='\n\n'.join(sections),
        claim_count=total,
    )


# ── Phase 6: Thinker attribution ────────────────────────────────────────────

def prompt_thinker_attribution(node_type: str, node_name: str, thinker_groups: dict) -> str:
    """Render the attribution prompt with quotes and summaries kept apart.

    The two are labelled differently because only one of them is the thinker's
    words. `claim_text` is our extractor's paraphrase; `quote` is the verbatim
    span it was drawn from. Feeding only paraphrases — which is what this did —
    made it impossible for the model to return a real quote, while the UI
    rendered whatever came back inside quotation marks under the person's name.

    Quotes are NOT truncated: the parser accepts a returned quote only if it
    matches one of these verbatim, so a clipped source line could never match.
    """
    lines = []
    for thinker, clms in thinker_groups.items():
        lines.append(f'\n[{thinker}]')
        for c in clms[:8]:
            if not isinstance(c, dict):
                lines.append(f'  SUMMARY: {str(c)[:200]}')
                continue
            lines.append(f"  SUMMARY: {(c.get('claim_text') or '')[:200]}")
            quote = (c.get('quote') or '').strip()
            if quote:
                lines.append(f'  QUOTE: {quote}')
    return load_and_render(
        "map/thinker_attribution.txt",
        node_type=node_type,
        node_name=node_name,
        thinker_claims='\n'.join(lines),
    )


# ── Phase 7: Interrelatedness ───────────────────────────────────────────────

def prompt_interrelatedness_batch(pairs: list) -> str:
    lines = [
        f"  Pair ({p['id_a']}, {p['id_b']}): [{p['type_a']}] {p['name_a']} | [{p['type_b']}] {p['name_b']}"
        for p in pairs
    ]
    # `voice` matters here even though this prompt only picks a relationship
    # kind. Its `reasoning` string is published verbatim into the related_shifts
    # module (export.py), so it is reader-facing copy and has to follow the same
    # US-spelling rule as everything else — the one published surface the voice
    # block never reached.
    #
    # (That second line said "# type: its ..." until mypy read it as a PEP 484
    # type comment and reported the whole file as a syntax error.)
    return load_and_render("map/interrelatedness.txt", voice=VOICE, pairs='\n'.join(lines))


# ── Phase 8: Synthesis insights per domain ──────────────────────────────────

def prompt_synthesis_insights(domain_name: str, domain_desc: str, claims: list) -> str:
    return load_and_render(
        "map/synthesis_insights.txt",
        voice=VOICE,
        domain_name=domain_name,
        domain_description=domain_desc[:300],
        evidence=fmt_claims_block(claims, max_per=50),
    )
