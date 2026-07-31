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
  Phase 8: Hero-stat select  — per KT, the single strongest dated statistic (SQL, no API).
                               Runs here, before 4b, because the stat_band module is
                               built from hero_stat.value.
  Phase 4b: Editorial body   — 2 calls per KT; writes the ordered MODULE LIST that
                               composes the shift + sub-shift pages (see kt_modules /
                               st_modules — editing those two functions changes the
                               page composition for every shift)
  Phase 5: Thinker attrib    — 1 per KT
  Phase 6: Interrelatedness  — typed edges (KT↔KT, cross-domain)
  Phase 7: Synthesis insights — 4 calls (one per domain)
  Phase 9: Export            — write documents['map'] (served by the backend at /api/map),
                               merging any editor-authored module overrides

Usage (DATABASE_URL + ANTHROPIC_API_KEY in env)
  python -m serious_shift_pipeline.steps.generate_map_data
  python -m serious_shift_pipeline.steps.generate_map_data --dry-run      # claim counts only, no API
  python -m serious_shift_pipeline.steps.generate_map_data --phase1       # DB setup only, no API
  python -m serious_shift_pipeline.steps.generate_map_data --export-only  # re-export from existing data
  python -m serious_shift_pipeline.steps.generate_map_data --editorial-only  # regenerate modules only

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
from pathlib import Path

from ..core import db, llm, parallel
from ..prompts import (
    SYNTHESIS_MODEL,
    INSIGHTS_MODEL,
    prompt_domain_key_trends,
    prompt_sub_trends,
    prompt_kt_editorial,
    prompt_st_editorial,
    prompt_thinker_attribution,
    prompt_interrelatedness_batch,
    prompt_synthesis_insights,
)

def _load_module_order() -> dict:
    """Canonical module order per scope, from packages/contracts/shift_modules.json.

    Falls back to an empty mapping (export then preserves whatever order the
    modules were written in) so a missing contract file can never break a run.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / 'packages' / 'contracts' / 'shift_modules.json'
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text()).get('order') or {}
            except (ValueError, OSError):
                return {}
    return {}


MODULE_ORDER = _load_module_order()

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
        'horizon': '2028',
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
        'horizon': '2027',
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
        'horizon': '2026',
        'primary_claim_domains': ['consumer_behavior'],
        'secondary_claim_domains': ['education'],
        'tech_keywords': ['consumer', 'customer', 'brand', 'purchas', 'personali', 'experienc',
                          'agent', 'recommend', 'shop', 'loyalt', 'product', 'user', 'retail',
                          'delegat', 'trust'],
    },
    {
        'id':    'organisations',
        'name':  'Organisations',
        'label': 'AGI × Organisations',
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
        'horizon': '2026',
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
# Claude response parsing (prompts live in serious_shift_pipeline.prompts)
# ---------------------------------------------------------------------------

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
            INSERT INTO domains_v2 (id, name, label, short_description, description, sort_order, horizon)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, label = EXCLUDED.label,
              short_description = EXCLUDED.short_description,
              description = EXCLUDED.description, sort_order = EXCLUDED.sort_order,
              horizon = EXCLUDED.horizon
        """, (d['id'], d['name'], d['label'], d['short_description'], d['description'],
              d['sort_order'], d.get('horizon')))
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
            return extract_json(call_claude(prompt_domain_key_trends(d, domain_claims[d['id']], MIN_KTS_PER_DOM), api_key))
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
# Phase 4b — Editorial body for each Key Trend and its sub-trends
#
# Phases 3 and 4 name and cluster; this writes the prose the reader sees on the
# shift and sub-shift pages (From→To, what's changing / why now, human needs,
# consumer tension, horizon, industries, opportunity territories).
#
# Kept as its own phase, one call per Key Trend, for two reasons: a long
# editorial answer can never truncate the taxonomy it hangs off, and a parse
# failure here leaves the shift intact — the page just falls back to hero + dek,
# because the front end renders each section only when its field is present.
# ---------------------------------------------------------------------------

def _as_steps(timeline) -> list | None:
    """Normalise a {now,next,beyond} object into the [{label,text}] the map
    document carries. Tolerates a model that already returned a list."""
    if isinstance(timeline, list):
        return [t for t in timeline if isinstance(t, dict) and t.get('text')] or None
    if isinstance(timeline, dict):
        steps = [{'label': k.capitalize(), 'text': timeline[k]}
                 for k in ('now', 'next', 'beyond') if timeline.get(k)]
        return steps or None
    return None


def _as_pairs(items) -> list | None:
    """Normalise [{name,text}] lists (industries, opportunities, territories)."""
    if not isinstance(items, list):
        return None
    out = [{'name': i.get('name', ''), 'text': i.get('text', '')}
           for i in items if isinstance(i, dict) and i.get('name')]
    return out or None


def _as_strings(items) -> list | None:
    """Normalise a list of plain strings (signals, counter-signals)."""
    if not isinstance(items, list):
        return None
    out = [s.strip() for s in items if isinstance(s, str) and s.strip()]
    return out or None


#: A leading display figure: 200 · 25% · 3× · 2:1 · $4.2bn · 18-34.
_FIGURE_RE = re.compile(
    r'^[$€£]?\d[\d,.]*(?:\s?[-–]\s?\d[\d,.]*)?'          # 200 · 4.2 · 18-34
    r'(?:\s?(?:%|×|x\b|:\s?\d+))?'                        # % · × · :1
    r'(?:\s?(?:million|billion|trillion|bn|m|k))?',       # 4.2bn · 16 million
    re.IGNORECASE,
)


def _short_figure(text, limit: int = 14) -> str | None:
    """A numeral fit for the stat band, or None.

    `hero_stat.value` is prose lifted from a claim ("200 years of encyclical
    history, first time dedicated entirely to technology"), but the band renders
    it at ~99px on desktop, so only a short figure works. Take a leading figure
    if there is one and give up otherwise — an overflowing band is worse than no
    band, and the module is dropped when this returns nothing.
    """
    if not text:
        return None
    t = ' '.join(str(text).split())
    if len(t) <= limit:
        return t
    m = _FIGURE_RE.match(t)
    if m:
        figure = m.group(0).strip().rstrip('.,;:')
        if figure and len(figure) <= limit:
            return figure
    return None


def _jsonb(value) -> str | None:
    """Serialise for a `%s::jsonb` placeholder; empty/None stays SQL NULL so the
    front end treats the section as absent."""
    return json.dumps(value) if value else None


# ── The module template ─────────────────────────────────────────────────────
#
# A shift page is an ordered list of {type, data} modules. These two functions
# ARE the template: the order below is the order the reader sees, and a module is
# omitted when the model gave us nothing for it (the page then simply doesn't
# have that section). To add, drop or reorder a section for every shift at once,
# edit these lists — no frontend change is needed as long as the type is
# registered in apps/frontend/src/shift/modules.jsx.
#
# Canonical type list + data shapes: packages/contracts/shift_modules.json.

def _module(type_: str, data, required: tuple = ()) -> dict | None:
    """A module, or None when it has nothing to render.

    `required` names the keys the module cannot render without. A stat band with
    prose but no numeral, or a tension band with a label but no quote, is not a
    section — it is an empty box. With no `required` given the module survives as
    long as any one value is set, which is what peel_tabs and human_needs want
    (both render happily with only one side filled). Mirrors the `required` lists
    in packages/contracts/shift_modules.json.
    """
    if not data:
        return None
    if isinstance(data, dict):
        if required:
            if any(not data.get(k) for k in required):
                return None
        elif not any(v for v in data.values()):
            return None
    return {'type': type_, 'data': data}


def kt_modules(kt_row: dict, editorial: dict) -> list:
    """Module list for a key shift, in the design's reading order."""
    e = editorial or {}
    needs = e.get('human_needs') if isinstance(e.get('human_needs'), dict) else {}
    hero = kt_row.get('hero_stat') or {}

    candidates = [
        _module('dek', {'text': kt_row.get('subtitle') or ''}, ('text',)),
        _module('from_to', {'from': e.get('from') or '', 'to': e.get('to') or ''}, ('from', 'to')),
        _module('pull_quote', {'quote': e.get('pull_quote') or ''}, ('quote',)),
        _module('stat_band', {
            # The model is asked for a display figure; hero_stat.value is a
            # fallback and is usually prose, so it has to be reduced first.
            'value': (e.get('stat_value') or '').strip() or _short_figure(hero.get('value')) or '',
            'text': e.get('stat_text') or hero.get('value') or '',
            'source': hero.get('source') or hero.get('thinker') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': e.get('whats_changing') or '',
            'why_now': e.get('why_now') or '',
        }),
        # Resolved from the shift's sub-shifts at render time, so it carries no
        # data of its own — but it still has to sit in the order.
        {'type': 'sub_shift_list', 'data': {}},
        _module('human_needs', {
            'unlocked': needs.get('unlocked') or '',
            'threatened': needs.get('threatened') or '',
        }),
        _module('tension_band', {'quote': e.get('consumer_tension') or ''}, ('quote',)),
        _module('timeline', {'steps': _as_steps(e.get('timeline')) or []}, ('steps',)),
        _module('industries', {'items': _as_pairs(e.get('industries')) or []}, ('items',)),
        _module('territories', {'items': _as_pairs(e.get('opportunities')) or []}, ('items',)),
    ]
    return [m for m in candidates if m]


def st_modules(st_row: dict, editorial: dict) -> list:
    """Module list for a sub-shift, in the design's reading order."""
    e = editorial or {}
    needs = e.get('human_needs') if isinstance(e.get('human_needs'), dict) else {}
    stat = e.get('stat') if isinstance(e.get('stat'), dict) else {}

    candidates = [
        _module('lede', {'text': e.get('lede') or st_row.get('description') or ''}, ('text',)),
        _module('from_to_solid', {'from': e.get('from') or '', 'to': e.get('to') or ''}, ('from', 'to')),
        _module('tension_band', {'quote': e.get('quote') or '', 'label': 'The tension'}, ('quote',)),
        _module('stat_band', {
            'value': stat.get('value') or '',
            'text': stat.get('text') or '',
            'source': stat.get('source') or '',
        }, ('value',)),
        _module('peel_tabs', {
            'whats_changing': e.get('whats_changing') or '',
            'why_now': e.get('why_now') or '',
        }),
        _module('human_needs', {
            'unlocked': needs.get('unlocked') or '',
            'threatened': needs.get('threatened') or '',
        }),
        _module('signals', {'items': _as_strings(e.get('signals')) or []}, ('items',)),
        _module('counter_signals', {'items': _as_strings(e.get('counter_signals')) or []}, ('items',)),
        _module('timeline', {'steps': _as_steps(e.get('timeline')) or []}, ('steps',)),
        _module('territories', {'items': _as_pairs(e.get('territories')) or []}, ('items',)),
    ]
    return [m for m in candidates if m]


def phase4b_editorial(conn, api_key: str, domain_claims: dict, domain_kts: dict):
    """Writes the module list for every Key Trend and sub-trend."""
    print('\nPhase 4b — Writing editorial modules per Key Trend (parallel)…')

    pool = {c['id']: c for d in DOMAINS for c in domain_claims[d['id']]}
    by_id = {d['id']: d for d in DOMAINS}

    # The KT rows as stored — `hero_stat` (phase 8, which runs before this) and
    # `subtitle` both feed modules, so read them once rather than per KT.
    kt_rows = {r['id']: dict(r) for r in conn.execute(
        'SELECT id, subtitle, hero_stat FROM domain_key_trends').fetchall()}

    # Sub-trends grouped by parent in one query (rather than one query per KT).
    subs_by_kt: dict = {}
    for r in conn.execute("""
        SELECT id, kt_id, name, subtitle, description FROM domain_sub_trends
        ORDER BY kt_id, sort_order
    """).fetchall():
        subs_by_kt.setdefault(r['kt_id'], []).append(dict(r))

    # One work item per KT, carrying its claims and its already-written sub-trends.
    work = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            claims = [pool[cid] for cid in kt.get('_claim_ids', []) if cid in pool]
            if not claims:
                claims = domain_claims[d['id']][:CLAIMS_PER_KT]
            work.append((d['id'], kt, claims, subs_by_kt.get(kt['_db_id'], [])))

    if not work:
        print('  (no Key Trends to enrich)')
        return

    def generate(item):
        d_id, kt, claims, subs = item
        out = {}
        try:
            out['kt'] = extract_json(call_claude(
                prompt_kt_editorial(kt['name'], kt.get('subtitle', ''), by_id[d_id]['name'], claims),
                api_key))
        except (ValueError, Exception) as e:   # noqa: B014 - report and continue
            print(f'  ERROR kt editorial ({kt["name"][:30]}): {e}')
        if subs:
            try:
                out['st'] = extract_json(call_claude(
                    prompt_st_editorial(kt['name'], kt.get('subtitle', ''), subs, claims),
                    api_key))
            except (ValueError, Exception) as e:   # noqa: B014
                print(f'  ERROR st editorial ({kt["name"][:30]}): {e}')
        return out

    results = parallel.pmap(generate, work)

    kt_done = st_done = 0
    for (_d_id, kt, _claims, subs), result in zip(work, results):
        e = result.get('kt') or {}
        kt_row = kt_rows.get(kt['_db_id'], {'subtitle': kt.get('subtitle', ''), 'hero_stat': None})
        modules = kt_modules(kt_row, e)
        conn.execute(
            'UPDATE domain_key_trends SET modules=%s::jsonb, read_time=%s WHERE id=%s',
            (_jsonb(modules), e.get('read_time') or None, kt['_db_id']),
        )
        if e:
            kt_done += 1

        # Match editorial back to sub-trends by name (the prompt is told not to
        # rename them); anything unmatched still gets a module list built from the
        # row itself, so the sub-shift page is never empty.
        editorial_by_name = {
            str(se.get('name', '')).strip().lower(): se
            for se in ((result.get('st') or {}).get('sub_trends') or [])
            if isinstance(se, dict)
        }
        for sub in subs:
            se = editorial_by_name.get(sub['name'].strip().lower()) or {}
            conn.execute(
                'UPDATE domain_sub_trends SET modules=%s::jsonb WHERE id=%s',
                (_jsonb(st_modules(sub, se)), sub['id']),
            )
            if se:
                st_done += 1

    conn.commit()
    print(f'  ✓  {kt_done}/{len(work)} shifts and {st_done} sub-shifts given an editorial body.')


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
            'horizon':           d['horizon'],
            'key_trend_ids':     [f'kt-{r["id"]}' for r in kt_rows],
            'synthesis_insight_ids': [r['id'] for r in si_rows],
        })

    # ---- editor-authored module overrides ----
    # Keyed by URL slug so they survive the weekly TRUNCATE…RESTART IDENTITY of
    # the v2 tables. An override that matches nothing is reported rather than
    # silently ignored — that almost always means the shift was renamed.
    overrides = {
        (r['scope'], r['slug']): r['modules']
        for r in conn.execute(
            'SELECT scope, slug, modules FROM shift_module_overrides WHERE enabled'
        ).fetchall()
    }
    used_overrides: set = set()

    # ── Modules derived from data other phases already produced ──────────────
    # Thinker attribution (phase 5), interrelatedness (phase 6) and the claim
    # graph are all generated every run. Composing them into modules here — at
    # export, from rows that already exist — surfaces that work on the page
    # without another model call.
    RELATIONSHIP_LABELS = {
        'reinforces': 'Reinforces',
        'accelerated_by': 'Accelerated by',
        'accelerates': 'Accelerates',
        'tension_with': 'In tension with',
        'contradicts': 'Contradicts',
        'depends_on': 'Depends on',
        'enables': 'Enables',
    }

    def _voices_module(kt_row):
        pro = _attr(kt_row['proponents'])[1] or []
        sk = _attr(kt_row['skeptics'])[1] or []
        keep = lambda xs: [
            {'name': x.get('name', ''), 'quote': x.get('quote', '')}
            for x in xs if isinstance(x, dict) and x.get('name') and x.get('quote')
        ]
        pro, sk = keep(pro), keep(sk)
        if not pro and not sk:
            return None
        return {'type': 'voices', 'data': {'proponents': pro, 'skeptics': sk}}

    # Typed KT↔KT edges. domain_links stores ids as 'kt:<id>'.
    links_by_kt: dict = {}
    for r in conn.execute("""
        SELECT source_id, target_id, relationship, strength, reasoning
        FROM domain_links
        WHERE source_type = 'kt' AND target_type = 'kt'
        ORDER BY strength DESC NULLS LAST
    """).fetchall():
        for a, b in ((r['source_id'], r['target_id']), (r['target_id'], r['source_id'])):
            try:
                src = int(str(a).split(':')[-1])
                dst = int(str(b).split(':')[-1])
            except (ValueError, TypeError):
                continue
            links_by_kt.setdefault(src, []).append((dst, r['relationship'], r['reasoning']))

    claim_rows_by_st: dict = {}
    for r in conn.execute("""
        SELECT stc.sub_trend_id, c.claim_text, t.name AS thinker, s.title AS source,
               s.date_published, c.signal_strength, c.consumer_implication
        FROM domain_sub_trend_claims stc
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        LEFT JOIN sources s ON s.id = c.source_id
        WHERE c.duplicate_of IS NULL AND c.claim_text IS NOT NULL
        ORDER BY stc.sub_trend_id, COALESCE(c.claim_weight, 0) DESC
    """).fetchall():
        claim_rows_by_st.setdefault(r['sub_trend_id'], []).append({
            'text': r['claim_text'],
            'thinker': r['thinker'] or '',
            'source': r['source'] or '',
            'date': str(r['date_published'])[:10] if r['date_published'] else '',
            'strength': r['signal_strength'] or '',
            'implication': r['consumer_implication'] or '',
        })

    def _insert_after(modules: list, after_types: tuple, module) -> list:
        """Place a module directly after the last of `after_types` present, or
        append. Keeps the design's reading order stable as types come and go."""
        if not module:
            return modules
        idx = -1
        for i, m in enumerate(modules):
            if m.get('type') in after_types:
                idx = i
        out = list(modules)
        out.insert(idx + 1 if idx >= 0 else len(out), module)
        return out

    def _ordered(modules: list, scope: str) -> list:
        """Sort a module list into the canonical reading order.

        The order lives in packages/contracts/shift_modules.json, so a change to
        the page composition re-composes on the next --export-only rather than
        needing every shift regenerated. Unknown types keep their relative
        position at the end rather than being dropped.
        """
        order = MODULE_ORDER.get(scope) or []
        rank = {t: i for i, t in enumerate(order)}
        fallback = len(rank)
        return sorted(
            modules or [],
            key=lambda m: (rank.get(m.get('type'), fallback), 0),
        )

    def resolve_modules(scope: str, slug: str, generated):
        key = (scope, slug)
        if key in overrides:
            used_overrides.add(key)
            return overrides[key]
        return generated or []

    # ---- child-id lookups, pre-grouped (one query each, not one per parent) ----
    st_ids_by_kt: dict = {}
    for r in conn.execute(
        'SELECT kt_id, id FROM domain_sub_trends ORDER BY kt_id, sort_order'
    ).fetchall():
        st_ids_by_kt.setdefault(r['kt_id'], []).append(r['id'])

    claim_ids_by_st: dict = {}
    for r in conn.execute(
        'SELECT sub_trend_id, claim_id FROM domain_sub_trend_claims'
    ).fetchall():
        claim_ids_by_st.setdefault(r['sub_trend_id'], []).append(r['claim_id'])

    # ---- key_trends ----
    kt_rows_all = conn.execute("""
        SELECT kt.id, kt.slug, kt.domain_id,
               kt.name, kt.subtitle, kt.velocity, kt.sort_order,
               kt.proponents, kt.skeptics, kt.hero_stat,
               kt.modules, kt.read_time
        FROM domain_key_trends kt
        ORDER BY kt.domain_id, kt.sort_order
    """).fetchall()
    # URL slugs are derived from the name (that is what the front end routes on
    # and what an override is keyed by). Two shifts in one domain could slugify
    # the same, so disambiguate in a stable order — the query is ORDER BY
    # domain_id, sort_order, so the same input always yields the same slug.
    kt_slug_by_id: dict = {}
    _seen_kt: dict = {}
    for kt in kt_rows_all:
        base = slugify(kt['name'])
        n = _seen_kt.get((kt['domain_id'], base), 0) + 1
        _seen_kt[(kt['domain_id'], base)] = n
        kt_slug_by_id[kt['id']] = base if n == 1 else f'{base}-{n}'
    key_trends_j = []
    for kt in kt_rows_all:
        url_slug = kt_slug_by_id[kt['id']]
        key_trends_j.append({
            'id':          f'kt-{kt["id"]}',
            'db_id':       kt['id'],
            'domain_id':   kt['domain_id'],
            'name':        kt['name'],
            'subtitle':    kt['subtitle'],
            'description': kt['subtitle'],   # back-compat alias
            'velocity':    kt['velocity'] or 'rising',
            'hero_stat':   kt['hero_stat'],  # {value, thinker, source, year} or null
            'sub_trend_ids': [f'st-{i}' for i in st_ids_by_kt.get(kt['id'], [])],
            'proponents':  _attr(kt['proponents'])[0],
            'skeptics':    _attr(kt['skeptics'])[0],
            'proponents_detail': _attr(kt['proponents'])[1],
            'skeptics_detail':   _attr(kt['skeptics'])[1],
            'read_time':   kt['read_time'],
            # The ordered page composition. Empty until phase 4b has run, in
            # which case the front end projects a minimal list from the fields
            # above so the page still renders.
            'slug':    url_slug,
            'modules': resolve_modules('key_trend', url_slug, kt['modules']),
            '_kt_row': kt,   # dropped below; used to compose derived modules
        })

    # Compose the derived modules once every shift's slug is known (related
    # shifts need to link to siblings). An override replaces the whole list, so
    # it is left untouched — the editor's ordering wins.
    kt_title_by_id = {kt['id']: kt['name'] for kt in kt_rows_all}
    kt_domain_by_id = {kt['id']: kt['domain_id'] for kt in kt_rows_all}
    for entry in key_trends_j:
        row = entry.pop('_kt_row')
        if ('key_trend', entry['slug']) in used_overrides:
            continue
        mods = entry['modules']
        mods = _insert_after(mods, ('tension_band', 'timeline'), _voices_module(row))

        seen, items = set(), []
        for dst, rel, why in links_by_kt.get(row['id'], []):
            if dst in seen or dst == row['id'] or dst not in kt_slug_by_id:
                continue
            seen.add(dst)
            items.append({
                'title': kt_title_by_id.get(dst, ''),
                'href': f'/map/{kt_domain_by_id.get(dst, "")}/{kt_slug_by_id[dst]}',
                'relationship': RELATIONSHIP_LABELS.get(rel, (rel or '').replace('_', ' ').title()),
                'reasoning': why or '',
                'domain': kt_domain_by_id.get(dst, ''),
            })
            if len(items) == 6:
                break
        if items:
            mods = mods + [{'type': 'related_shifts', 'data': {'items': items}}]
        entry['modules'] = _ordered(mods, 'key_trend')

    # ---- sub_trends ----
    st_rows_all = conn.execute("""
        SELECT st.id, st.slug, st.kt_id, st.domain_id,
               st.name, st.subtitle, st.description, st.modules
        FROM domain_sub_trends st
        ORDER BY st.kt_id, st.sort_order
    """).fetchall()
    sub_trends_j = []
    _seen_st: dict = {}
    for st in st_rows_all:
        # A sub-shift slug is only unique beneath its parent, so the override key
        # is the two-segment URL path. Same stable disambiguation as above.
        base = slugify(st['name'])
        n = _seen_st.get((st['kt_id'], base), 0) + 1
        _seen_st[(st['kt_id'], base)] = n
        url_slug = f'{kt_slug_by_id.get(st["kt_id"], "")}/{base if n == 1 else f"{base}-{n}"}'
        sub_trends_j.append({
            'id':          f'st-{st["id"]}',
            'db_id':       st['id'],
            'key_trend_id': f'kt-{st["kt_id"]}',
            'domain_id':   st['domain_id'],
            'name':        st['name'],
            'subtitle':    st['subtitle'],
            'description': st['description'],
            'claim_ids':   [f'c_{i}' for i in claim_ids_by_st.get(st['id'], [])],
            'slug':    url_slug,
            'modules': resolve_modules('sub_trend', url_slug, st['modules']),
        })
        # The sourced claims behind this sub-shift, beside the written signals.
        if ('sub_trend', url_slug) not in used_overrides:
            evidence = claim_rows_by_st.get(st['id'], [])[:8]
            if evidence:
                sub_trends_j[-1]['modules'] = _insert_after(
                    sub_trends_j[-1]['modules'],
                    ('counter_signals', 'signals', 'peel_tabs'),
                    {'type': 'evidence', 'data': {'items': evidence}},
                )
        sub_trends_j[-1]['modules'] = _ordered(sub_trends_j[-1]['modules'], 'sub_trend')

    unmatched = sorted(f'{s}:{sl}' for (s, sl) in overrides.keys() - used_overrides)
    if unmatched:
        print(f'  ⚠  {len(unmatched)} module override(s) matched no shift '
              f'(renamed?): {", ".join(unmatched[:5])}'
              + (' …' if len(unmatched) > 5 else ''))

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


def load_kts_from_db(conn) -> dict:
    """Rebuild the {domain_id: [kt, …]} shape that the paid phases expect, from
    the Key Trends already stored. Used by --editorial-only so modules can be
    (re)generated for an existing map without a full rebuild."""
    domain_kts: dict = {d['id']: [] for d in DOMAINS}
    claim_ids: dict = {}
    for r in conn.execute("""
        SELECT st.kt_id, stc.claim_id
        FROM domain_sub_trends st
        JOIN domain_sub_trend_claims stc ON stc.sub_trend_id = st.id
    """).fetchall():
        claim_ids.setdefault(r['kt_id'], []).append(r['claim_id'])

    for r in conn.execute("""
        SELECT id, domain_id, name, subtitle, velocity
        FROM domain_key_trends ORDER BY domain_id, sort_order
    """).fetchall():
        if r['domain_id'] not in domain_kts:
            continue
        domain_kts[r['domain_id']].append({
            '_db_id': r['id'],
            '_claim_ids': claim_ids.get(r['id'], []),
            'name': r['name'],
            'subtitle': r['subtitle'] or '',
            'velocity': r['velocity'],
        })
    return domain_kts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',     action='store_true', help='Print claim counts only')
    parser.add_argument('--phase1',      action='store_true', help='DB setup + domain insert only (no API)')
    parser.add_argument('--export-only', action='store_true', help='Re-export from existing v2 data')
    parser.add_argument('--editorial-only', action='store_true',
                        help='Regenerate the editorial modules for existing Key Trends, then '
                             're-export. Does NOT reset the v2 tables or re-cluster.')
    parser.add_argument('--limit', type=int, default=0, metavar='N',
                        help='With --editorial-only: only process the first N Key Trends per '
                             'domain. Use a small N to smoke-test the path before paying for '
                             'the full set.')
    args = parser.parse_args()

    conn = get_conn()

    # ── Editorial-only ───────────────────────────────────────────────────────
    # Deliberately on this side of reset_v2_tables: the taxonomy is left exactly
    # as it is, so slugs (and therefore any authored module overrides) still match.
    if args.editorial_only:
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            print('ERROR: ANTHROPIC_API_KEY not set.')
            sys.exit(1)
        print('--editorial-only: regenerating modules for the existing map…')
        domain_kts = load_kts_from_db(conn)
        if args.limit:
            domain_kts = {k: v[:args.limit] for k, v in domain_kts.items()}
            print(f'  --limit {args.limit}: capped to the first {args.limit} shift(s) per domain.')
        total = sum(len(v) for v in domain_kts.values())
        if not total:
            print('ERROR: no Key Trends in the database — run a full rebuild first.')
            conn.close(); sys.exit(1)
        print(f'  {total} Key Trends found across {len(DOMAINS)} domains.')
        # Domain definitions are an idempotent upsert with no truncate, so they
        # are safe here — and necessary: horizon and the domain labels live on
        # domains_v2 and would otherwise stay unset on a database that has only
        # ever had the taxonomy phases run against it.
        phase1_domain_definitions(conn)
        domain_claims = phase2_claim_routing(conn)
        phase8_hero_stats(conn)          # stat_band module needs hero_stat first
        phase4b_editorial(conn, api_key, domain_claims, domain_kts)
        print('\nPhase 9 — Exporting map…')
        out = build_map_json_v2(conn)
        _write_map_document(conn, out)
        _write_synthesis_document(conn, out)
        n_mod = sum(len(kt.get('modules') or []) for kt in out['key_trends'])
        print("✓  map written → documents['map']")
        print(f'   {len(out["key_trends"])} KTs carrying {n_mod} modules · '
              f'{len(out["sub_trends"])} sub-trends')
        conn.close(); return

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

    # ── Hero stats (free, SQL) — must precede the editorial phase, whose
    #    stat_band module is built from hero_stat.value. ────────────────────────
    phase8_hero_stats(conn)

    # ── Phase 4b: editorial modules ──────────────────────────────────────────
    phase4b_editorial(conn, api_key, domain_claims, domain_kts)

    # ── Phase 5: thinker attribution ─────────────────────────────────────────
    phase5_thinker_attribution(conn, api_key, domain_claims, domain_kts)

    # ── Phase 6: interrelatedness ─────────────────────────────────────────────
    phase6_interrelatedness(conn, api_key, domain_kts)

    # ── Phase 7: synthesis insights ───────────────────────────────────────────
    phase7_synthesis(conn, api_key, domain_claims)

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
