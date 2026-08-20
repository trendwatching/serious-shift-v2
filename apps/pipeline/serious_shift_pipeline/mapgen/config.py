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
import os

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


def load_gates() -> dict:
    """packages/contracts/gates.json — publication-gate thresholds and the
    remediation skip list, or an empty mapping if unreadable (consumers fall
    back to their historical defaults). Not cached: skipped_issue_codes() reads
    it at call time so a remediation branch can carry a skip list and the next
    deploy drops it."""
    try:
        return json.loads((contracts_dir() / 'gates.json').read_text())
    except (ValueError, OSError, RuntimeError):
        return {}


_CONTRACT = _load_contract()

MODULE_ORDER = _CONTRACT.get('order') or {}

#: The canonical sectors, in the order the gate demands them. Read from the same
#: file the validator reads, so the two cannot disagree. Deliberately not counted
#: here: the count was "sixteen" in this comment for a week after the contract
#: dropped to 15, and a stale number in a comment is how the 17 Aug 2026 run came
#: to fail on a rule nobody had changed.
INDUSTRY_SECTORS = _CONTRACT.get('industry_sectors') or []

#: Claims routed per domain, and offered per key shift for sub-trend clustering.
#:
#: CLAIMS_PER_DOM has to scale with MAX_KTS_PER_DOM, and does not scale itself.
#: Phase 4 asks each key shift for up to CLAIMS_PER_KT from the domain's pool
#: through a SHARED top-up ledger, so demand is n_kts x CLAIMS_PER_KT against a
#: fixed supply: 900 against 200 at nine shifts, 1,500 at fifteen. The tail of
#: each sphere runs on its phase-3 assignments alone once the spares are gone,
#: and a shift that ends up with none is dropped from the work list entirely.
#: 350 keeps roughly the ratio nine shifts had.
CLAIMS_PER_DOM  = 350   # claims sent to Key Trend generation per domain
CLAIMS_PER_KT   = 100   # claims sent to sub-trend generation per KT

#: How many Key Trends each domain carries: a RANGE, not a floor, and spheres
#: are not required to match each other — the gate checks each one against this
#: range independently, so a sphere with thinner evidence simply carries fewer.
#:
#: The old ceiling was 9, chosen after the 2026-08-10 audit found a floor-only
#: prompt producing 51 shifts telling ~30 distinct stories. The ceiling rose to
#: 15 on the 18 Aug 2026 review. What keeps that from repeating the 2026-08-10
#: failure is not the number but the prompt: it asks for as many as the evidence
#: genuinely supports and still requires every pair to be distinguishable in one
#: sentence. Phase 3 truncates past MAX deterministically and the publication
#: gate rejects a count outside the range. Single source of truth —
#: prompts/map_data.py imports it.
MIN_KTS_PER_DOM = 7
MAX_KTS_PER_DOM = 15

#: How many sub-shifts a key shift carries. Also a range, from the same review.
#:
#: This used to be "exactly 5" in the generator and 4-5 in the gate, written out
#: as separate literals in three files that had no idea about each other
#: (phases/sub_trends.py, phases/editorial.py, validation.py). That is precisely
#: the shape of a writer/gate disagreement, so it lives here now and every one of
#: them imports it. MAX is what generation aims for; MIN is what publication
#: accepts, and the slack is what lets a colliding or bodyless child be dropped
#: rather than fail a whole run.
MIN_SUB_TRENDS = 3
MAX_SUB_TRENDS = 5

#: How many key shifts one sphere should expect to change names in one week.
#:
#: A TARGET, expressed to the model in the prompt, and deliberately NOT a gate.
#: The 18 Aug 2026 review was explicit: steer the drift, never fail a run for
#: exceeding it. A week where a capability landed or a market broke is allowed
#: to move the map, and a hard cap here would only teach the model to keep a
#: name the evidence had abandoned.
#:
#: What makes an unbounded budget safe is carryover.pin_slugs: a renamed shift
#: keeps its URL, so drift costs a label rather than a page's identity. The two
#: have to stay together — this number alone would be a wish.
#: Expressed as a SHARE of the sphere rather than a count, because 2 renames is
#: 29% of a seven-shift sphere and 13% of a fifteen-shift one — the same number
#: would silently tighten the steer as the map grew.
KT_CHANGE_SHARE = float(os.environ.get('SS_KT_CHANGE_SHARE', '0.25'))


def kt_change_budget(published: int) -> int:
    """How many renames to ask a sphere for, given how many shifts it publishes.

    Never zero: a sphere must always be allowed to correct one name that the
    evidence has genuinely abandoned.
    """
    return max(1, round(max(published, MIN_KTS_PER_DOM) * KT_CHANGE_SHARE))


#: Back-compat default for callers with no sphere in hand (the prompt builder's
#: keyword default). A real call passes the sphere's own budget.
KT_CHANGE_BUDGET = kt_change_budget(MIN_KTS_PER_DOM)

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
