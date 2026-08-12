"""Tuning constants, the module-order contract, and the fixed domain table.

Domains are hardcoded rather than generated: they are the product's top-level
information architecture, not something the model should be free to reshape.

They are hardcoded *here*, and not in the database, for a second reason that is
easy to trip over: `domains_v2` is inside `dbutil.DROP_V2_ORDER`, so every
synthesize run TRUNCATEs it with RESTART IDENTITY CASCADE and re-upserts it from
this table. Sphere copy authored directly in the DB would vanish the following
Monday. If editor-authored sphere copy is ever wanted, it needs a durable side
table keyed by domain_id, the way `shift_module_overrides` is.

Three text fields, three jobs, all four spheres:
  short_description  the one-line deck under the sphere title, on the deck panel
                     and the listing page. Evergreen.
  intro              the "WHAT'S SHIFTING RIGHT NOW" paragraph on the deck panel.
                     A present-tense read on the current map, so it is the field
                     that dates fastest and the one an editor will want to touch.
  description        long-form framing. Read only by seo.rs, for meta tags.
"""
from __future__ import annotations

import json

from ..paths import contracts_dir

def _load_contract() -> dict:
    """packages/contracts/shift_modules.json, or an empty mapping if unreadable.

    An unreadable contract degrades rather than raises: the export then preserves
    whatever order the modules were written in, and the industries module — which
    cannot be made canonical without the sector list — is simply omitted.
    """
    try:
        return json.loads((contracts_dir() / 'shift_modules.json').read_text())
    except (ValueError, OSError, RuntimeError):
        return {}


_CONTRACT = _load_contract()

MODULE_ORDER = _CONTRACT.get('order') or {}

#: The sixteen sectors, in the order the gate demands them. Read from the same
#: file the validator reads, so the two cannot disagree.
INDUSTRY_SECTORS = _CONTRACT.get('industry_sectors') or []

CLAIMS_PER_DOM  = 200   # claims sent to Key Trend generation per domain
CLAIMS_PER_KT   = 100   # claims sent to sub-trend generation per KT

#: How many Key Trends each domain carries: a RANGE, not a floor. The old
#: floor-only prompt ("at least 8 … prefer more trends over fewer") produced
#: 51 shifts telling ~30 distinct stories — the 2026-08-10 audit found an
#: evaluation cluster of seven shifts and a jobs cluster of six. 7–9 per
#: domain gives 28–36 total, which is insight granularity rather than
#: database granularity. Phase 3 truncates past MAX deterministically and the
#: publication gate rejects a count outside the range. This is the single
#: source of truth — prompts/map_data.py imports it.
MIN_KTS_PER_DOM = 7
MAX_KTS_PER_DOM = 9

DOMAINS = [
    {
        'id':    'society',
        'name':  'Society',
        'label': 'AI × Society',
        'short_description': (
            'Belonging, trust and truth when anything can be generated and '
            'nobody has to be present.'
        ),
        'intro': (
            'As AI moves deeper into everyday life, institutions, '
            'relationships, identities and power structures begin to shift, '
            'especially once intelligent machines become social participants '
            'themselves.'
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
        'label': 'AI × Economy',
        'short_description': (
            'Where value, work and money move once capability stops being scarce.'
        ),
        'intro': (
            'Intelligence is becoming an economic resource in its own right, '
            'transforming how value is created, who or what produces it, who '
            'owns it and how wealth is distributed.'
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
        'label': 'AI × Consumers',
        'short_description': (
            'Identity, taste and desire in a market where software does the shopping.'
        ),
        'intro': (
            'What people need may remain remarkably constant. AI radically '
            'changes how those needs are understood and fulfilled, and '
            'increasingly acts, chooses and buys on people’s behalf.'
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
        # US spelling, including the id. It stayed British for a long time
        # because it is the URL segment, the shift_refs key and the domains_v2
        # primary key — renaming it 404s every published link. That was worth
        # paying once: /map/organizations was a 404 a reader could reach by
        # typing the name they see on the page. Migrated together with the
        # `/map` prefix drop, so every URL moved once rather than twice.
        'id':    'organizations',
        'name':  'Organizations',
        'label': 'AI × Organizations',
        'short_description': (
            'How institutions decide, hire and defend themselves when speed is free.'
        ),
        'intro': (
            'From individual tasks to entire workflows, AI is rebuilding the '
            'organization around autonomy, changing how companies operate, '
            'innovate, compete and ultimately what a company even is.'
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
    {'source': 'society',       'target': 'consumers',     'strength': 'high',   'description': 'Cultural shifts in identity, trust, and meaning drive consumer expectations and behavioral norms.'},
    {'source': 'economy',       'target': 'consumers',     'strength': 'high',   'description': 'Economic disruption — displacement, inequality, new income models — redefines consumer purchasing power and priorities.'},
    {'source': 'economy',       'target': 'organizations', 'strength': 'high',   'description': 'Macro-economic pressures, labor cost dynamics, and capital flows directly determine organizational strategy.'},
    {'source': 'consumers',     'target': 'organizations', 'strength': 'high',   'description': 'Shifting consumer expectations and agent-mediated purchase patterns force organizational redesign.'},
    {'source': 'organizations', 'target': 'economy',       'strength': 'medium', 'description': 'Corporate adoption of AI at scale drives productivity, employment patterns, and market concentration.'},
]
