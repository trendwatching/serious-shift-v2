#!/usr/bin/env python3
"""
generate_map_data — domain-first rebuild of the Serious Shift trend map (Postgres).

Architecture (Content Logic, June 2026 — scenario layer removed):
  4 DOMAINS  →  ≥8 KEY TRENDS per domain  →  3-5 SUB-TRENDS per KT  →  CLAIMS

Key Trends attach directly to a domain; there is no intermediate scenario layer.

Pipeline
  Phase 1: Domain definitions — hardcoded, inserts into domains_v2 table (no API)
  Phase 2: Claim routing     — SQL heuristic maps claims.domain → strategic domain (no API)
  Phase 3: KT gen            — 4 calls (one per domain), ≥8 fresh KTs from the domain pool
  Phase 4: Sub-trend gen     — M calls (one per KT)
  Phase 5: Thinker attrib    — 1 per KT
  Phase 6: Interrelatedness  — typed edges (KT↔KT, cross-domain)
  Phase 7: Synthesis insights — 4 calls (one per domain)
  Phase 8: Hero-stat select  — per KT, the single strongest dated statistic (SQL, no API)
  Phase 9: Export            — write documents['map'] (served by the backend at /api/map)

Usage (DATABASE_URL + ANTHROPIC_API_KEY in env)
  python -m serious_shift_pipeline.steps.generate_map_data
  python -m serious_shift_pipeline.steps.generate_map_data --dry-run      # claim counts only, no API
  python -m serious_shift_pipeline.steps.generate_map_data --phase1       # DB setup only, no API
  python -m serious_shift_pipeline.steps.generate_map_data --export-only  # re-export from existing data

v2 tables (schema owned by packages/db migrations):
  domains_v2                  4 domain rows, hand-coded
  domain_key_trends           ≥8 per domain, AI-generated (replaces hardcoded SECTION_CONFIG)
  domain_sub_trends           3-5 per KT, AI-generated
  domain_sub_trend_claims     junction
  domain_synthesis_insights   3-5 per domain, AI-generated
  domain_synthesis_insight_claims  junction
  domain_links                typed edges for new node set
  domain_flows                domain-to-domain directional influence
"""

import json
import os
import re
import sys
import argparse
import random
from datetime import date

from ..core import db, llm, parallel
from ..core.voice import VOICE

# ── Model assignment ─────────────────────────────────────────
# Editorial synthesis (Key Trends, sub-trends, attribution) runs on Sonnet 4.6.
SYNTHESIS_MODEL = 'claude-sonnet-4-6'
# Synthesis insights — the most editorially demanding, lowest-volume phase — runs on Opus 4.7.
INSIGHTS_MODEL  = 'claude-opus-4-7'

CLAIMS_PER_DOM  = 200   # claims sent to Key Trend generation per domain
CLAIMS_PER_KT   = 100   # claims sent to sub-trend generation per KT
MIN_KTS_PER_DOM = 8     # ask the model for at least this many Key Trends per domain

# ---------------------------------------------------------------------------
# Domain definitions  (Phase 1 — hardcoded, never generated)
# ---------------------------------------------------------------------------
DOMAINS = [
    {
        'id':    'society',
        'name':  'Society',
        'label': 'AGI × Society / World',
        'short_description': (
            'How AGI rewrites the social contract — from democratic governance '
            'and cultural authority to what it means to be human.'
        ),
        'description': (
            "AGI doesn't arrive into a neutral world — it arrives into one already "
            "fracturing along lines of trust, meaning, and identity. This domain maps the "
            "broadest stakes: what happens to democratic governance, cultural authority, and "
            "our sense of what it means to be human when intelligence is no longer a scarce, "
            "exclusively human asset. From geopolitical realignment and institutional "
            "legitimacy crises to the redefinition of creativity, consciousness, and community, "
            "AGI × Society is where the deepest and most contested transformation plays out — "
            "the one brands and organizations are least prepared to address."
        ),
        'sort_order': 1,
        # claims.domain values that belong primarily to this strategic domain
        'primary_claim_domains': ['agi_timeline', 'existential_risk', 'geopolitics', 'regulation', 'education'],
        'secondary_claim_domains': ['labor'],
        # keyword filter for technology_capability claims → this domain
        'tech_keywords': ['governance', 'democrac', 'society', 'cultur', 'trust', 'identit',
                          'wellbe', 'consciou', 'civil', 'politic', 'public', 'power',
                          'authoritar', 'right', 'war', 'geopolit'],
    },
    {
        'id':    'economy',
        'name':  'Economy',
        'label': 'AGI × Economy',
        'short_description': (
            'How AGI restructures who creates value, who captures it, and what happens '
            'to the rest — the new K-shaped reality.'
        ),
        'description': (
            "The intelligence economy is not a better version of the knowledge economy — "
            "it is its replacement. This domain tracks the structural rewiring of how value "
            "is created, captured, and distributed when AI can perform most cognitive work at "
            "near-zero marginal cost. The K-shaped economy is accelerating: productivity gains "
            "concentrate at the top while displacement spreads below. From corporate profit "
            "capture and the collapse of knowledge-worker premiums to new models of ownership, "
            "taxation, and redistribution, AGI × Economy asks the oldest question in capitalism: "
            "who gets the surplus, and what do the rest do next?"
        ),
        'sort_order': 2,
        'primary_claim_domains': ['economy', 'labor'],
        'secondary_claim_domains': ['geopolitics'],
        'tech_keywords': ['gdp', 'produc', 'wage', 'capital', 'invest', 'wealth', 'market',
                          'profit', 'growth', 'fiscal', 'tax', 'trade', 'inequal', 'unempl',
                          'k-shaped', 'redistribu', 'ubi'],
    },
    {
        'id':    'consumers',
        'name':  'Consumers',
        'label': 'AGI × Consumer Behavior',
        'short_description': (
            'How AGI transforms the way people make decisions, seek fulfilment, and '
            'relate to brands — human needs, now AI-mediated.'
        ),
        'description': (
            "The consumer isn't disappearing — they're delegating. As AI agents take over "
            "search, filtering, purchasing, and personalization at scale, the rules of brand "
            "relationships are being rewritten from scratch. This domain maps the AGI-driven "
            "shifts in how people make decisions, form preferences, and seek fulfilment — "
            "structured through the lens of human needs, because AGI reshapes how those needs "
            "are met, not the needs themselves. Trust migrates from brands to agents. "
            "Authenticity commands a premium. Emotional connection becomes harder to fake and "
            "more valuable to find. The consumer is still human. That's precisely what's "
            "changing everything."
        ),
        'sort_order': 3,
        'primary_claim_domains': ['consumer_behavior'],
        'secondary_claim_domains': ['education'],
        'tech_keywords': ['consumer', 'customer', 'brand', 'purchas', 'personali', 'experienc',
                          'agent', 'recommend', 'shop', 'loyalt', 'product', 'user', 'retail',
                          'delegat', 'trust'],
    },
    {
        'id':    'organisations',
        'name':  'Organizations',
        'label': 'AGI × Organizations',
        'short_description': (
            'How firms and institutions adapt — or fail to — when AI can perform, '
            'plan, and decide faster than any hierarchy was built to handle.'
        ),
        'description': (
            "Most organizations were designed for a world of scarce intelligence and "
            "predictable processes. Neither assumption holds. This domain tracks what happens "
            "to firms, institutions, and professional structures when AI can perform, plan, and "
            "decide at speeds no human hierarchy was built to absorb. From workforce redesign "
            "and agentic process automation to the institutional inertia that turns competitive "
            "advantage into competitive liability, AGI × Organizations is where strategic "
            "ambition and operational reality collide most visibly. The question is no longer "
            "whether to reorganize around AI, it's whether organizations can move fast enough "
            "to matter."
        ),
        'sort_order': 4,
        'primary_claim_domains': ['enterprise'],
        'secondary_claim_domains': ['regulation', 'education'],
        'tech_keywords': ['enterpris', 'organiz', 'corporat', 'firm', 'workforc', 'employe',
                          'manag', 'strateg', 'leader', 'institutio', 'business', 'ceo',
                          'exec', 'automat', 'workforce', 'agentic'],
    },
]

# Preset domain flows (directional influence arrows between domains)
DOMAIN_FLOWS_PRESET = [
    {'source': 'society',       'target': 'economy',       'strength': 'high',   'description': 'Societal legitimacy crises and governance failures shape economic confidence and policy responses.'},
    {'source': 'society',       'target': 'consumers',     'strength': 'high',   'description': 'Cultural shifts in identity, trust, and meaning drive consumer expectations and behavioural norms.'},
    {'source': 'economy',       'target': 'consumers',     'strength': 'high',   'description': 'Economic disruption — displacement, inequality, new income models — redefines consumer purchasing power and priorities.'},
    {'source': 'economy',       'target': 'organisations', 'strength': 'high',   'description': 'Macro-economic pressures, labour cost dynamics, and capital flows directly determine organisational strategy.'},
    {'source': 'consumers',     'target': 'organisations', 'strength': 'high',   'description': 'Shifting consumer expectations and agent-mediated purchase patterns force organisational redesign.'},
    {'source': 'organisations', 'target': 'economy',       'strength': 'medium', 'description': 'Corporate adoption of AI at scale drives productivity, employment patterns, and market concentration.'},
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_conn():
    return db.raw_connect()


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def _slugger():
    """A fresh unique-slug maker: suffixes -2, -3, … on collision within a phase."""
    used: set = set()

    def make(base: str) -> str:
        s, n = base, 2
        while s in used:
            s = f'{base}-{n}'; n += 1
        used.add(s)
        return s
    return make


# ---------------------------------------------------------------------------
# v2 map tables — schema owned by packages/db migrations. This step only
# TRUNCATEs them before a rebuild (reset_v2_tables); it never creates them.
# ---------------------------------------------------------------------------

DROP_V2_ORDER = [
    'domain_synthesis_insight_claims',
    'domain_synthesis_insights',
    'domain_links',
    'domain_sub_trend_claims',
    'domain_sub_trends',
    'domain_key_trends',
    'domain_flows',
    'domains_v2',
]


def reset_v2_tables(conn):
    """Clear all v2 tables before a rebuild. The schema itself is owned by the
    packages/db migrations, so we TRUNCATE rather than drop/recreate."""
    conn.execute('TRUNCATE ' + ', '.join(DROP_V2_ORDER) + ' RESTART IDENTITY CASCADE')
    conn.commit()
    print('  ✓  v2 tables reset.')


# ---------------------------------------------------------------------------
# API call + JSON extraction (reused from v1)
# ---------------------------------------------------------------------------

def call_claude(prompt: str, api_key: str = None, retries: int = 3,
                model: str = SYNTHESIS_MODEL) -> str:
    # api_key is accepted for call-site compatibility; the SDK reads
    # ANTHROPIC_API_KEY from the environment.
    text, _ = llm.call_claude(prompt, model=model, max_tokens=32000, retries=retries)
    return text


def extract_json(text: str):
    stripped = text.strip()
    fence = re.search(r'```(?:json)?\s*(.*?)\s*```', stripped, re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    for sc, ec in [('{', '}'), ('[', ']')]:
        idx = stripped.find(sc)
        if idx == -1:
            continue
        depth, in_str, escape = 0, False, False
        for i in range(idx, len(stripped)):
            ch = stripped[i]
            if escape:
                escape = False; continue
            if ch == '\\':
                escape = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if in_str:
                continue
            if ch == sc:
                depth += 1
            elif ch == ec:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[idx:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f'No JSON found:\n{text[:1500]}')


# ---------------------------------------------------------------------------
# Claim routing (Phase 2 — SQL heuristic, no API)
# ---------------------------------------------------------------------------

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
        SELECT c.id, c.claim_text, c.consumer_implication,
               c.signal_strength, c.specificity, c.domain AS claim_domain,
               t.name AS thinker, t.credibility_score,
               s.title AS source_title, s.date_published
        FROM claims c
        JOIN thinkers t ON c.thinker_id = t.id
        LEFT JOIN sources s ON c.source_id = s.id
        WHERE c.signal_strength IN ('signal','strong_signal')
          AND c.duplicate_of IS NULL
    """
    ORDER = """
        ORDER BY COALESCE(c.claim_weight,0) * COALESCE(c.freshness_score,0.5)
                 * (GREATEST(COALESCE(t.credibility_score,50.0), 30.0) / 100.0) DESC
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
    seeded, seeded_ids, t_seen = [], set(), set()
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


# ---------------------------------------------------------------------------
# Claude prompts
# ---------------------------------------------------------------------------

def fmt_claims_block(claims: list, max_per: int = None) -> str:
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

def prompt_domain_key_trends(domain: dict, claims: list) -> str:
    cb = fmt_claims_block(claims, max_per=180)
    return f"""{VOICE}

You are synthesising trend intelligence for Serious Shift — a consumer trend platform tracking AGI-driven shifts.

STRATEGIC DOMAIN: {domain['name']}
DOMAIN DESCRIPTION: {domain['description'][:400]}

TASK
From the evidence below, identify at least {MIN_KTS_PER_DOM} distinct KEY TRENDS for this domain. Each Key Trend is a named signal — a shift already underway in {domain['name']}, grounded in the claims. Together they map the most important things happening in this domain. Prefer more trends over fewer: surface every distinct shift the evidence supports, but never invent one the claims do not back.

RULES FOR KEY TREND NAMES
- 1–2 words. Short, intriguing, memorable. The name creates curiosity; the subtitle delivers the meaning. Alliteration works well but is not required.
- Right: "Synthetic Trust", "Delegated Desire", "Proof Premium", "Silent Commerce", "Branded Brands"
- Wrong: "AI Changes Consumer Behavior" (descriptive, not a name), "The Rise of Authenticity" (generic), "Trust Issues" (category label)
- Every Key Trend must be distinct from the others — no overlapping trends.

RULES FOR SUBTITLES (mandatory — the name is never shown without one)
- One complete, specific sentence. Super descriptive: explain exactly what the trend is. The subtitle carries the meaning the name deliberately withholds; if it is vague, the name has failed.
- Write it as a journalist writes a subheading, not as a marketer.
- Right: "When consumers rely on AI recommendations over brand reputation"

RULES FOR CLAIM ASSIGNMENT
- Assign each claim_id to the single Key Trend it best supports
- Every claim that clearly fits a Key Trend should be assigned
- Claims that don't fit cleanly may be omitted

Assign a velocity to each Key Trend:
- "breakout" = explosive growth, tipping point imminent
- "accelerating" = clear momentum, adoption growing fast
- "rising" = real signal, still building
- "steady" = established, not accelerating

EVIDENCE ({len(claims)} claims from the {domain['name']} domain):
{cb}

Return ONLY valid JSON — no preamble, no markdown fences:
{{
  "key_trends": [
    {{
      "name": "Key trend name here",
      "subtitle": "One specific sentence explaining exactly what this trend is",
      "velocity": "accelerating",
      "claim_ids": [123, 456, 789]
    }},
    ...
  ]
}}"""


# ── Phase 5: Sub-trend clustering per KT ───────────────────────────────────

def prompt_sub_trends(kt_name: str, kt_subtitle: str, claims: list) -> str:
    cb = fmt_claims_block(claims, max_per=90)
    return f"""{VOICE}

You are synthesising trend intelligence for Serious Shift — a consumer trend platform tracking AGI-driven shifts.

KEY TREND: {kt_name}
FRAMING: {kt_subtitle}

TASK
Identify 3–5 coherent SUB-TRENDS that emerge from the evidence below. Each sub-trend is a distinct, named micro-pattern that a brand strategist or consumer researcher would recognise as real.

RULES FOR SUB-TREND NAMES
- 1–2 words. Short, intriguing, memorable (NOT "AI Adoption", "Trust Issues", "Changing Behavior"). Alliteration welcome, not required.

RULES FOR SUBTITLES (mandatory)
- One complete, specific sentence that fully explains what the sub-trend is. Journalist subheading, not marketing copy.

RULES FOR DESCRIPTIONS
- Exactly 2 sentences. Strict.
- Sentence 1: what is happening. Sentence 2: what it means for consumers or brands.
- Sentence 2 must name the implication, not restate the observation. If sentence 2 could have been sentence 1 reworded, rewrite it.
- No filler phrases. No em dashes; use periods and commas only.

RULES FOR CLAIM ASSIGNMENT
- Assign each claim_id to the single sub-trend it best supports
- Every claim that clearly fits should be assigned

Also assign a velocity to the Key Trend itself:
- "breakout" | "accelerating" | "rising" | "steady"

EVIDENCE ({len(claims)} claims):
{cb}

Return ONLY valid JSON — no preamble, no markdown fences:
{{
  "key_trend_velocity": "accelerating",
  "sub_trends": [
    {{
      "name": "1-2 word name",
      "subtitle": "One specific sentence explaining exactly what this sub-trend is",
      "description": "Sentence one: what is happening. Sentence two: the implication for consumers or brands.",
      "claim_ids": [123, 456, 789]
    }},
    ...
  ]
}}"""


# ── Phase 6: Thinker attribution ────────────────────────────────────────────

def prompt_thinker_attribution(node_type: str, node_name: str, thinker_groups: dict) -> str:
    lines = []
    for thinker, clms in thinker_groups.items():
        lines.append(f'\n[{thinker}]')
        for c in clms[:8]:
            text = c['claim_text'] if isinstance(c, dict) else c
            lines.append(f'  - {text[:200]}')
    return f"""You are analysing thinker stances for Serious Shift.

NODE TYPE: {node_type}
NODE NAME: {node_name}

TASK
Based on the claims below (grouped by thinker), identify:
- 2–3 PROPONENTS: thinkers whose claims most strongly support or accelerate this {node_type}
- 2–3 SKEPTICS: thinkers whose claims question, complicate, or push back on it

For each thinker, include one direct quote or close paraphrase from THEIR evidence
that demonstrates why they are a proponent or skeptic. Without the quote the
attribution is unverifiable. Cite nothing they did not say.

THINKER CLAIMS:
{''.join(lines)}

Return ONLY valid JSON:
{{
  "proponents": [{{"name": "Name A", "quote": "short quote from their evidence"}}],
  "skeptics":   [{{"name": "Name C", "quote": "short quote from their evidence"}}]
}}"""


def parse_thinker_attribution(raw) -> dict:
    """Return {'proponents': [{name, quote}], 'skeptics': [...]}. Accepts either the
    new object form or a bare name list (back-compat)."""
    result = {'proponents': [], 'skeptics': []}
    if not isinstance(raw, dict):
        return result
    for k in ('proponents', 'skeptics'):
        for x in raw.get(k, []) or []:
            if isinstance(x, dict) and x.get('name'):
                result[k].append({'name': str(x['name']), 'quote': str(x.get('quote', ''))})
            elif isinstance(x, str) and x:
                result[k].append({'name': x, 'quote': ''})
    return result


def _collect_by_thinker(claims: list, max_per: int = 8) -> dict:
    grouped = {}
    for c in claims:
        t = c.get('thinker', '')
        if not t:
            continue
        grouped.setdefault(t, [])
        if len(grouped[t]) < max_per:
            grouped[t].append(c)
    return grouped


# ── Phase 7: Interrelatedness ───────────────────────────────────────────────

def prompt_interrelatedness_batch(pairs: list) -> str:
    lines = [
        f"  Pair ({p['id_a']}, {p['id_b']}): [{p['type_a']}] {p['name_a']} | [{p['type_b']}] {p['name_b']}"
        for p in pairs
    ]
    return f"""You are mapping relationships between trend nodes in Serious Shift.

RELATIONSHIP TYPES (pick exactly one per pair):
- "reinforces"       — one makes the other more likely/stronger
- "contradicts"      — the two pull in opposite directions
- "prerequisite_for" — one must happen for the other to occur
- "competes_with"    — compete for same resources/attention/adoption
- "accelerated_by"   — one is sped up by presence of the other
- "none"             — no meaningful relationship

STRENGTH: 0.0–1.0 (omit pairs with strength < 0.4 or relationship = "none")
DIRECTIONALITY: source_id → target_id

PAIRS:
{chr(10).join(lines)}

Return ONLY valid JSON list:
[
  {{
    "source_id": "scn:1",
    "target_id": "scn:3",
    "relationship": "reinforces",
    "strength": 0.8,
    "reasoning": "One sentence."
  }},
  ...
]
(Omit pairs with relationship="none" or strength < 0.4)"""


def parse_interrelatedness_batch(raw) -> list:
    VALID = {'reinforces','contradicts','prerequisite_for','competes_with','accelerated_by'}
    if isinstance(raw, dict):
        for k in ('links','relationships','edges','results','data'):
            if k in raw and isinstance(raw[k], list):
                raw = raw[k]; break
        else:
            raw = []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            src = item.get('source_id')
            tgt = item.get('target_id')
            rel = item.get('relationship','')
            str_ = float(item.get('strength',0))
            rsn = str(item.get('reasoning',''))
            if src is None or tgt is None or str_ < 0.4 or rel not in VALID:
                continue
            result.append({'source_id': str(src), 'target_id': str(tgt),
                           'relationship': rel, 'strength': str_, 'reasoning': rsn})
        except (TypeError, ValueError):
            continue
    return result


# ── Phase 8: Synthesis insights per domain ──────────────────────────────────

def prompt_synthesis_insights(domain_name: str, domain_desc: str, claims: list) -> str:
    cb = fmt_claims_block(claims, max_per=50)
    return f"""{VOICE}

You are the synthesis intelligence layer of Serious Shift.

DOMAIN: {domain_name}
DESCRIPTION: {domain_desc[:300]}

TASK
Generate 3–4 SYNTHESIS INSIGHTS — emergent ideas arising from combining multiple thinkers' claims. These must NOT be directly stated by any single thinker; they emerge from the pattern of evidence.

RULES
- Each insight combines at least 2 different thinkers from OPPOSING camps (a proponent and a skeptic), not thinkers who already agree.
- It must NOT be something any single thinker already wrote. Synthesis test: could this appear in any one thinker's writing? If yes, rewrite it. It should feel surprising but inevitable once read.
- Name: 4–8 words, surprising but inevitable. Right register: "The Collapse of the Awareness Economy", "When Speed Becomes the New Inequality".
- Description: 2–3 sentences, forward-looking, {domain_name}-specific, written as if you are the first person to have seen this clearly.
- contributing_claim_ids: 3–8 claim IDs that together generate the insight

EVIDENCE:
{cb}

Return ONLY valid JSON:
{{
  "insights": [
    {{
      "name": "Insight name here",
      "description": "Two to three sentences.",
      "contributing_claim_ids": [123, 456, 789]
    }},
    ...
  ]
}}"""


def parse_synthesis_insights(raw) -> list:
    if isinstance(raw, dict):
        raw = raw.get('insights', [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get('name','').strip()
        desc = item.get('description','').strip()
        ids  = [int(c) for c in item.get('contributing_claim_ids',[])
                if isinstance(c, (int,float)) and not isinstance(c, bool)]
        if name and desc and ids:
            result.append({'name': name, 'description': desc, 'contributing_claim_ids': ids})
    return result


# ---------------------------------------------------------------------------
# Phase 1 — Domain definitions (hardcoded write to DB)
# ---------------------------------------------------------------------------

def phase1_domain_definitions(conn):
    print('\nPhase 1 — Writing domain definitions to DB…')
    for d in DOMAINS:
        conn.execute("""
            INSERT INTO domains_v2 (id, name, label, short_description, description, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, label = EXCLUDED.label,
              short_description = EXCLUDED.short_description,
              description = EXCLUDED.description, sort_order = EXCLUDED.sort_order
        """, (d['id'], d['name'], d['label'], d['short_description'], d['description'], d['sort_order']))
    for f in DOMAIN_FLOWS_PRESET:
        conn.execute("""
            INSERT INTO domain_flows (source_id, target_id, strength, description)
            VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
        """, (f['source'], f['target'], f['strength'], f['description']))
    conn.commit()
    print(f'  ✓  {len(DOMAINS)} domains + {len(DOMAIN_FLOWS_PRESET)} domain flows written.')


# ---------------------------------------------------------------------------
# Phase 2 — Claim routing (SQL heuristic, no API)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Phase 3 — Key Trend generation per domain (4 API calls)
# ---------------------------------------------------------------------------

def phase3_key_trends(conn, api_key: str, domain_claims: dict) -> dict:
    """
    Returns {domain_id: [kt_dict_with_db_id, ...]}
    Writes ≥MIN_KTS_PER_DOM Key Trends per domain to domain_key_trends.
    """
    print('\nPhase 3 — Generating Key Trends per domain (parallel)…')

    # Parallel: one independent LLM call per domain.
    def generate(d):
        try:
            return extract_json(call_claude(prompt_domain_key_trends(d, domain_claims[d['id']]), api_key))
        except ValueError as e:
            print(f'  ERROR parsing JSON for {d["name"]}: {e}')
            return {'key_trends': []}

    results = parallel.pmap(generate, DOMAINS)

    # Serial: assign slugs + write (single connection, deterministic order).
    slug = _slugger()
    domain_kts: dict = {}
    for d, result in zip(DOMAINS, results):
        kts = result.get('key_trends', [])
        if len(kts) < MIN_KTS_PER_DOM:
            print(f'  {d["name"]}: only {len(kts)} KTs (target {MIN_KTS_PER_DOM})')
        written = []
        for j, kt in enumerate(kts, start=1):
            kt['_db_id'] = conn.execute("""
                INSERT INTO domain_key_trends
                  (slug, domain_id, name, subtitle, velocity, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'kt-{slugify(kt["name"])}'), d['id'],
                  kt['name'], kt.get('subtitle', ''), kt.get('velocity', 'rising'), j)).fetchone()['id']
            kt['_claim_ids'] = [int(cid) for cid in kt.get('claim_ids', [])
                                if isinstance(cid, (int, float))]
            written.append(kt)
        domain_kts[d['id']] = written
        print(f'  ✓  {d["name"]}: {len(written)} KTs')

    conn.commit()
    return domain_kts


# ---------------------------------------------------------------------------
# Phase 4 — Sub-trend clustering (M API calls)
# ---------------------------------------------------------------------------

def phase4_sub_trends(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    """Writes to domain_sub_trends + domain_sub_trend_claims."""
    print('\nPhase 4 — Clustering sub-trends per Key Trend (parallel)…')

    all_domain_claims = {c['id']: c for d in DOMAINS for c in domain_claims[d['id']]}

    # Build the per-KT claim pool (pure, no I/O), one work item per KT.
    work = []  # (domain_id, kt, preferred_claims)
    for d in DOMAINS:
        full_pool = domain_claims[d['id']]
        for kt in domain_kts.get(d['id'], []):
            preferred_ids = set(kt.get('_claim_ids', []))
            preferred = [all_domain_claims[cid] for cid in preferred_ids if cid in all_domain_claims]
            remaining = CLAIMS_PER_KT - len(preferred)
            if remaining > 0:
                preferred += [c for c in full_pool if c['id'] not in preferred_ids][:remaining]
            if preferred:
                work.append((d['id'], kt, preferred))

    # Parallel: one LLM call per KT.
    def generate(item):
        _d_id, kt, preferred = item
        try:
            return extract_json(call_claude(prompt_sub_trends(kt['name'], kt.get('subtitle', ''), preferred), api_key))
        except ValueError as e:
            print(f'  ERROR ({kt["name"][:30]}): {e}')
            return {'sub_trends': []}

    results = parallel.pmap(generate, work)

    # Serial: write sub-trends + claim links, refine KT velocity.
    slug = _slugger()
    for (d_id, kt, _), result in zip(work, results):
        velocity = result.get('key_trend_velocity', kt.get('velocity', 'rising'))
        conn.execute('UPDATE domain_key_trends SET velocity=%s WHERE id=%s', (velocity, kt['_db_id']))
        sub_trends = result.get('sub_trends', [])
        for i, st in enumerate(sub_trends, start=1):
            st_db_id = conn.execute("""
                INSERT INTO domain_sub_trends
                  (slug, kt_id, domain_id, name, subtitle, description, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'st-{slugify(st["name"])}'), kt['_db_id'], d_id,
                  st['name'], st.get('subtitle', ''), st['description'], i)).fetchone()['id']
            for cid in st.get('claim_ids', []):
                try:
                    conn.execute("""INSERT INTO domain_sub_trend_claims (sub_trend_id, claim_id)
                                    VALUES (%s,%s) ON CONFLICT DO NOTHING""", (st_db_id, int(cid)))
                except Exception:
                    pass
        print(f'  ✓  {kt["name"][:48]}: {len(sub_trends)} sub-trends, vel={velocity}')

    conn.commit()


# ---------------------------------------------------------------------------
# Phase 5 — Thinker attribution (per Key Trend)
# ---------------------------------------------------------------------------

def phase5_thinker_attribution(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    print('\nPhase 5 — Thinker attribution (parallel)…')

    # Build per-KT thinker groups (pure), one work item per KT.
    work = []  # (kt, groups)
    for d in DOMAINS:
        claims = domain_claims[d['id']]
        for kt in domain_kts.get(d['id'], []):
            preferred_ids = set(kt.get('_claim_ids', []))
            kt_claims = [c for c in claims if c['id'] in preferred_ids] or claims[:60]
            groups = _collect_by_thinker(kt_claims, max_per=8)
            if groups:
                work.append((kt, groups))

    # Parallel: one LLM call per KT.
    def attribute(item):
        kt, groups = item
        try:
            return parse_thinker_attribution(
                extract_json(call_claude(prompt_thinker_attribution('key_trend', kt['name'], groups), api_key)))
        except Exception:
            return {'proponents': [], 'skeptics': []}

    results = parallel.pmap(attribute, work)

    # Serial: write attribution.
    for (kt, _), attr in zip(work, results):
        conn.execute('UPDATE domain_key_trends SET proponents=%s, skeptics=%s WHERE id=%s',
                     (json.dumps(attr['proponents']), json.dumps(attr['skeptics']), kt['_db_id']))
    conn.commit()
    print(f'  ✓  {len(work)} Key Trends attributed')


# ---------------------------------------------------------------------------
# Phase 6 — Interrelatedness
# ---------------------------------------------------------------------------

def phase6_interrelatedness(conn, api_key: str, domain_kts: dict):
    print('\nPhase 6 — Interrelatedness (typed edges, parallel)…')
    MAX_BATCHES = 30

    # Gather KT nodes, build cross-domain pairs, batch them.
    kt_nodes = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            kt_nodes.append({'id': f'kt:{kt["_db_id"]}', 'name': kt['name'],
                             'desc': kt.get('subtitle', '')[:120], 'domain': d['id']})
    kt_pairs = [
        {'id_a': a['id'], 'name_a': a['name'], 'desc_a': a['desc'], 'type_a': 'key_trend',
         'id_b': b['id'], 'name_b': b['name'], 'desc_b': b['desc'], 'type_b': 'key_trend'}
        for i, a in enumerate(kt_nodes) for b in kt_nodes[i + 1:]
        if a['domain'] != b['domain']
    ]
    random.shuffle(kt_pairs)
    kt_pairs = kt_pairs[:200]
    batches = [kt_pairs[i:i + 25] for i in range(0, len(kt_pairs), 25)][:MAX_BATCHES]

    # Parallel: one LLM call per batch.
    def run_batch(batch):
        try:
            return parse_interrelatedness_batch(extract_json(call_claude(prompt_interrelatedness_batch(batch), api_key)))
        except Exception as e:
            print(f'  WARNING: {e}')
            return []

    results = parallel.pmap(run_batch, batches)

    # Serial: write links.
    n = 0
    for links in results:
        for lnk in links:
            try:
                conn.execute("""
                    INSERT INTO domain_links
                      (source_type, source_id, target_type, target_id, relationship, strength, reasoning)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
                """, (lnk['source_id'].split(':')[0], lnk['source_id'],
                      lnk['target_id'].split(':')[0], lnk['target_id'],
                      lnk['relationship'], lnk['strength'], lnk['reasoning']))
                n += 1
            except Exception:
                pass
    conn.commit()
    print(f'  ✓  {len(batches)} batches → {n} links')


# ---------------------------------------------------------------------------
# Phase 7 — Synthesis insights per domain (4 API calls)
# ---------------------------------------------------------------------------

def phase7_synthesis(conn, api_key: str, domain_claims: dict):
    print('\nPhase 7 — Synthesis insights per domain (parallel)…')

    # Parallel: one LLM call per domain (Opus).
    def generate(d):
        claims = domain_claims[d['id']][:50]
        if not claims:
            return d, []
        try:
            return d, parse_synthesis_insights(extract_json(
                call_claude(prompt_synthesis_insights(d['name'], d['description'], claims),
                            api_key, model=INSIGHTS_MODEL)))
        except Exception as e:
            print(f'  WARNING ({d["name"]}): {e}')
            return d, []

    results = parallel.pmap(generate, DOMAINS)

    # Serial: write insights + claim links.
    slug = _slugger()
    for d, insights in results:
        n_written = 0
        for ins in insights:
            row = conn.execute("""
                INSERT INTO domain_synthesis_insights (slug, domain_id, name, description)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id
            """, (slug(f'si-{d["id"]}-{slugify(ins["name"])}'), d['id'], ins['name'], ins['description'])).fetchone()
            si_id = row['id'] if row else None
            if si_id:
                for cid in ins['contributing_claim_ids']:
                    try:
                        conn.execute("""INSERT INTO domain_synthesis_insight_claims (insight_id, claim_id)
                                        VALUES (%s,%s) ON CONFLICT DO NOTHING""", (si_id, cid))
                    except Exception:
                        pass
                n_written += 1
        print(f'  ✓  {d["name"]}: {n_written} insights')
    conn.commit()


# ---------------------------------------------------------------------------
# Phase 8 — Hero-stat selection (per KT, SQL — no API)
# ---------------------------------------------------------------------------

def select_hero_stat(conn, kt_id) -> dict:
    """Return the single strongest dated, attributable statistic among a Key
    Trend's claims, as {value, thinker, source, year} — or None if it has none.
    Ranked by claim weight × thinker credibility; statistics come from the
    `claims.statistic` / `claims.has_statistic` fields (process_raw extracts them)."""
    row = conn.execute("""
        SELECT c.statistic, t.name AS thinker,
               s.title AS source, s.date_published AS pub_date
        FROM domain_sub_trends st
        JOIN domain_sub_trend_claims stc ON stc.sub_trend_id = st.id
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        LEFT JOIN sources s ON s.id = c.source_id
        WHERE st.kt_id = %s
          AND c.has_statistic IS TRUE
          AND c.statistic IS NOT NULL
          AND c.duplicate_of IS NULL
        ORDER BY COALESCE(c.claim_weight,0)
                 * (GREATEST(COALESCE(t.credibility_score,50.0), 30.0) / 100.0) DESC
        LIMIT 1
    """, (kt_id,)).fetchone()
    if not row:
        return None
    return {
        'value':   row['statistic'],
        'thinker': row['thinker'] or '',
        'source':  row['source'] or '',
        'year':    str(row['pub_date'])[:4] if row['pub_date'] else '',
    }


def phase8_hero_stats(conn):
    """Persist one hero statistic per Key Trend to domain_key_trends.hero_stat."""
    print('\nPhase 8 — Selecting hero statistics per Key Trend (SQL, no API)…')
    kt_ids = [r['id'] for r in conn.execute('SELECT id FROM domain_key_trends').fetchall()]
    n = 0
    for kt_id in kt_ids:
        hero = select_hero_stat(conn, kt_id)
        conn.execute('UPDATE domain_key_trends SET hero_stat=%s::jsonb WHERE id=%s',
                     (json.dumps(hero) if hero else None, kt_id))
        if hero:
            n += 1
    conn.commit()
    print(f'  ✓  {n}/{len(kt_ids)} Key Trends have a hero statistic.')


# ---------------------------------------------------------------------------
# Phase 9 — Export map.json
# ---------------------------------------------------------------------------

def _attr(stored):
    """Parse stored proponents/skeptics JSON into (names, detail[{name, quote}]).
    Accepts the new [{name, quote}] form or a legacy [name] list."""
    items = json.loads(stored) if stored else []
    names, detail = [], []
    for x in items:
        if isinstance(x, dict):
            names.append(x.get('name', ''))
            detail.append({'name': x.get('name', ''), 'quote': x.get('quote', '')})
        else:
            names.append(str(x))
            detail.append({'name': str(x), 'quote': ''})
    return names, detail


def build_map_json_v2(conn) -> dict:
    today = date.today().isoformat()

    # ---- domains ----
    # Key Trends attach directly to a domain; we read them here to populate each
    # domain's key_trend_ids (in sort order) for the front-end's domain → KT drill-down.
    d_rows = conn.execute('SELECT * FROM domains_v2 ORDER BY sort_order').fetchall()
    domains_j = []
    for d in d_rows:
        kt_rows = conn.execute(
            'SELECT id FROM domain_key_trends WHERE domain_id=%s ORDER BY sort_order',
            (d['id'],)
        ).fetchall()
        si_rows = conn.execute(
            'SELECT id FROM domain_synthesis_insights WHERE domain_id=%s ORDER BY id',
            (d['id'],)
        ).fetchall()
        domains_j.append({
            'id':                d['id'],
            'name':              d['name'],
            'label':             d['label'],
            'short_description': d['short_description'],
            'description':       d['description'],
            'key_trend_ids':     [f'kt-{r["id"]}' for r in kt_rows],
            'synthesis_insight_ids': [r['id'] for r in si_rows],
        })

    # ---- key_trends ----
    kt_rows_all = conn.execute("""
        SELECT kt.id, kt.slug, kt.domain_id,
               kt.name, kt.subtitle, kt.velocity, kt.sort_order,
               kt.proponents, kt.skeptics, kt.hero_stat
        FROM domain_key_trends kt
        ORDER BY kt.domain_id, kt.sort_order
    """).fetchall()
    key_trends_j = []
    for kt in kt_rows_all:
        st_rows = conn.execute(
            'SELECT id FROM domain_sub_trends WHERE kt_id=%s ORDER BY sort_order',
            (kt['id'],)
        ).fetchall()
        key_trends_j.append({
            'id':          f'kt-{kt["id"]}',
            'db_id':       kt['id'],
            'domain_id':   kt['domain_id'],
            'name':        kt['name'],
            'subtitle':    kt['subtitle'],
            'description': kt['subtitle'],   # back-compat alias
            'velocity':    kt['velocity'] or 'rising',
            'hero_stat':   kt['hero_stat'],  # {value, thinker, source, year} or null
            'sub_trend_ids': [f'st-{r["id"]}' for r in st_rows],
            'proponents':  _attr(kt['proponents'])[0],
            'skeptics':    _attr(kt['skeptics'])[0],
            'proponents_detail': _attr(kt['proponents'])[1],
            'skeptics_detail':   _attr(kt['skeptics'])[1],
        })

    # ---- sub_trends ----
    st_rows_all = conn.execute("""
        SELECT st.id, st.slug, st.kt_id, st.domain_id, st.name, st.subtitle, st.description
        FROM domain_sub_trends st
        ORDER BY st.kt_id, st.sort_order
    """).fetchall()
    sub_trends_j = []
    for st in st_rows_all:
        c_rows = conn.execute(
            'SELECT claim_id FROM domain_sub_trend_claims WHERE sub_trend_id=%s',
            (st['id'],)
        ).fetchall()
        sub_trends_j.append({
            'id':          f'st-{st["id"]}',
            'db_id':       st['id'],
            'key_trend_id': f'kt-{st["kt_id"]}',
            'domain_id':   st['domain_id'],
            'name':        st['name'],
            'subtitle':    st['subtitle'],
            'description': st['description'],
            'claim_ids':   [f'c_{r["claim_id"]}' for r in c_rows],
        })

    # ---- claims ----
    all_cids: set = set()
    for st in sub_trends_j:
        for cid_str in st['claim_ids']:
            try:
                all_cids.add(int(cid_str.replace('c_', '')))
            except ValueError:
                pass
    # Also add synthesis insight claims
    for row in conn.execute('SELECT DISTINCT claim_id FROM domain_synthesis_insight_claims').fetchall():
        all_cids.add(row['claim_id'])

    claims_j = []
    if all_cids:
        rows = conn.execute("""
            SELECT c.id, c.claim_text, c.consumer_implication, c.signal_strength,
                   t.name AS thinker, t.credibility_score,
                   s.title AS source_title, s.date_published
            FROM claims c
            JOIN thinkers t ON c.thinker_id = t.id
            LEFT JOIN sources s ON c.source_id = s.id
            WHERE c.id = ANY(%s)
        """, (list(all_cids),)).fetchall()
        for r in rows:
            claims_j.append({
                'id':                f'c_{r["id"]}',
                'text':              r['claim_text'] or '',
                'thinker':           r['thinker'] or '',
                'thinker_credibility': round(r['credibility_score'] or 50.0, 1),
                'source_title':      r['source_title'] or '',
                'source_date':       r['date_published'] or '',
                'signal_strength':   r['signal_strength'] or '',
                'consumer_implication': r['consumer_implication'] or '',
            })

    # ---- thinkers ----
    thinkers_j = [
        {
            'name': r['name'],
            'credibility_score': round(r['credibility_score'] or 50.0, 1),
            'prediction_accuracy': round(r['prediction_accuracy'] or 0.0, 3) if r['prediction_accuracy'] else None,
            'image_url': r['image_url'],
            'bio': r['bio'],
        }
        for r in conn.execute(
            'SELECT name, credibility_score, prediction_accuracy, image_url, bio '
            'FROM thinkers ORDER BY credibility_score DESC NULLS LAST'
        ).fetchall()
    ]

    # ---- synthesis insights ----
    si_rows = conn.execute("""
        SELECT si.id, si.slug, si.domain_id, si.name, si.description
        FROM domain_synthesis_insights si ORDER BY si.domain_id, si.id
    """).fetchall()
    insights_j = []
    for si in si_rows:
        cids = [r['claim_id'] for r in conn.execute(
            'SELECT claim_id FROM domain_synthesis_insight_claims WHERE insight_id=%s', (si['id'],)
        ).fetchall()]
        insights_j.append({
            'id':          si['id'],
            'name':        si['name'],
            'description': si['description'],
            'domain_id':   si['domain_id'],
            'contributing_claim_ids': cids,
            'ai_generated': True,
        })

    # ---- links ----
    link_rows = conn.execute("""
        SELECT source_type, source_id, target_type, target_id,
               relationship, strength, reasoning
        FROM domain_links ORDER BY strength DESC
    """).fetchall()
    links_j = [
        {
            'source_type': r['source_type'],
            'source_id':   r['source_id'],
            'target_type': r['target_type'],
            'target_id':   r['target_id'],
            'relationship': r['relationship'],
            'strength':    round(r['strength'], 3),
            'reasoning':   r['reasoning'] or '',
        }
        for r in link_rows
    ]

    # ---- domain_flows ----
    flow_rows = conn.execute('SELECT * FROM domain_flows ORDER BY id').fetchall()
    flows_j = [
        {
            'source': r['source_id'], 'target': r['target_id'],
            'strength': r['strength'], 'description': r['description'] or '',
        }
        for r in flow_rows
    ]

    # ---- index: by_thinker ----
    claim_to_thinker = {c['id'].replace('c_',''): c['thinker'] for c in claims_j}
    by_thinker: dict = {}
    def _add_t(t, etype, eid, ename):
        by_thinker.setdefault(t, [])
        for e in by_thinker[t]:
            if e['type'] == etype and e['id'] == eid:
                return
        by_thinker[t].append({'type': etype, 'id': eid, 'name': ename})

    for st in sub_trends_j:
        for cid_str in st['claim_ids']:
            t = claim_to_thinker.get(cid_str.replace('c_',''), '')
            if t: _add_t(t, 'sub_trend', st['id'], st['name'])
    for kt in key_trends_j:
        for t in kt['proponents'] + kt['skeptics']:
            _add_t(t, 'key_trend', kt['id'], kt['name'])

    # ---- index: by_velocity ----
    by_velocity: dict = {}
    for kt in key_trends_j:
        v = kt.get('velocity', 'rising')
        by_velocity.setdefault(v, [])
        by_velocity[v].append(kt['id'])

    return {
        'updated':             today,
        'architecture':        'domain-first-v2',
        'domains':             domains_j,
        'key_trends':          key_trends_j,
        'sub_trends':          sub_trends_j,
        'claims':              claims_j,
        'thinkers':            thinkers_j,
        'synthesis_insights':  insights_j,
        'links':               links_j,
        'domain_flows':        flows_j,
        'by_thinker':          by_thinker,
        'by_velocity':         by_velocity,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write_map_document(conn, out):
    """Store the assembled map as documents['map'] — served by the backend at /api/map."""
    conn.execute("""INSERT INTO documents (key, body) VALUES ('map', %s::jsonb)
        ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
        (json.dumps(out, default=str),))  # default=str: Postgres date/datetime → ISO string
    conn.commit()


def _write_synthesis_document(conn, out):
    """Store synthesis insights (grouped by domain) as documents['synthesis'] —
    served by the backend at /api/synthesis, rendered as the domain closing section."""
    doc = {
        'updated': out.get('updated'),
        'domains': [{'id': d['id'], 'name': d['name'], 'label': d['label']} for d in out.get('domains', [])],
        'synthesis_insights': out.get('synthesis_insights', []),
    }
    conn.execute("""INSERT INTO documents (key, body) VALUES ('synthesis', %s::jsonb)
        ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
        (json.dumps(doc, default=str),))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',     action='store_true', help='Print claim counts only')
    parser.add_argument('--phase1',      action='store_true', help='DB setup + domain insert only (no API)')
    parser.add_argument('--export-only', action='store_true', help='Re-export from existing v2 data')
    args = parser.parse_args()

    conn = get_conn()

    # ── Export-only ──────────────────────────────────────────────────────────
    if args.export_only:
        print('--export-only: reading existing v2 data…')
        out = build_map_json_v2(conn)
        _write_map_document(conn, out)
        _write_synthesis_document(conn, out)
        print("✓  map written → documents['map']")
        print(f'   {len(out["domains"])} domains · {len(out["key_trends"])} KTs · '
              f'{len(out["sub_trends"])} sub-trends · {len(out["links"])} links')
        conn.close(); return

    # ── Always reset v2 tables ───────────────────────────────────────────────
    reset_v2_tables(conn)

    # ── Phase 1 (free) ───────────────────────────────────────────────────────
    phase1_domain_definitions(conn)

    if args.dry_run or args.phase1:
        # Show claim counts per domain
        print('\nPhase 2 preview — claim counts per domain (dry run):')
        for d in DOMAINS:
            claims = route_claims_for_domain(conn, d, limit=CLAIMS_PER_DOM)
            thinkers = len({c['thinker'] for c in claims})
            print(f'  {d["name"]:<15}  {len(claims):3d} claims  |  {thinkers} thinkers')
        if args.phase1:
            print('\n--phase1: stopping after DB setup. Run without --phase1 to continue.')
        else:
            print('\n--dry-run: stopping. No API calls made.')
        conn.close(); return

    # ── Need API key for paid phases ─────────────────────────────────────────
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('ERROR: ANTHROPIC_API_KEY not set.')
        sys.exit(1)

    # ── Phase 2: claim routing (free, SQL) ───────────────────────────────────
    domain_claims = phase2_claim_routing(conn)

    # ── Phase 3: Key Trend generation per domain ─────────────────────────────
    domain_kts = phase3_key_trends(conn, api_key, domain_claims)

    # ── Phase 4: sub-trend clustering ────────────────────────────────────────
    phase4_sub_trends(conn, api_key, domain_claims, domain_kts)

    # ── Phase 5: thinker attribution ─────────────────────────────────────────
    phase5_thinker_attribution(conn, api_key, domain_claims, domain_kts)

    # ── Phase 6: interrelatedness ─────────────────────────────────────────────
    phase6_interrelatedness(conn, api_key, domain_kts)

    # ── Phase 7: synthesis insights ───────────────────────────────────────────
    phase7_synthesis(conn, api_key, domain_claims)

    # ── Phase 8: hero-stat selection ──────────────────────────────────────────
    phase8_hero_stats(conn)

    # ── Phase 9: export ───────────────────────────────────────────────────────
    print('\nPhase 9 — Exporting map…')
    out = build_map_json_v2(conn)
    _write_map_document(conn, out)
    _write_synthesis_document(conn, out)
    conn.close()

    print("\n✓  map → documents['map']")
    print(f'   {len(out["domains"])} domains · {len(out["key_trends"])} KTs · '
          f'{len(out["sub_trends"])} sub-trends')
    print(f'   {len(out["claims"])} claims · {len(out["synthesis_insights"])} insights · '
          f'{len(out["links"])} links')
    print('\nDone.')


if __name__ == '__main__':
    main()
