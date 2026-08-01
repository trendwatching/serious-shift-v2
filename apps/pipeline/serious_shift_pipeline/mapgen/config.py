"""Tuning constants, the module-order contract, and the fixed domain table.

Domains are hardcoded rather than generated: they are the product's top-level
information architecture, not something the model should be free to reshape.
"""
from __future__ import annotations

import json

from ..paths import contracts_dir

def _load_module_order() -> dict:
    """Canonical module order per scope, from packages/contracts. Empty mapping
    if unreadable, in which case the export preserves whatever order the modules
    were written in."""
    try:
        path = contracts_dir() / 'shift_modules.json'
        return json.loads(path.read_text()).get('order') or {}
    except (ValueError, OSError, RuntimeError):
        return {}


MODULE_ORDER = _load_module_order()

CLAIMS_PER_DOM  = 200   # claims sent to Key Trend generation per domain
CLAIMS_PER_KT   = 100   # claims sent to sub-trend generation per KT
MIN_KTS_PER_DOM = 8     # ask the model for at least this many Key Trends per domain

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
