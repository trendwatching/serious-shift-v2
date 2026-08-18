"""Phase 3 — generate each domain's Key Trends.

Domains run SEQUENTIALLY, threading an accumulated `taken` name ledger, so the
four calls cannot mint near-twins of each other — the same advisory-ledger
pattern phase 4 uses for sub-trend names. The count is a range
(MIN_KTS_PER_DOM–MAX_KTS_PER_DOM): the old floor-only ask ("prefer more trends
over fewer") produced 51 shifts telling ~30 distinct stories. Overshoot is
truncated deterministically here so the publication gate's kt_count check is a
backstop, not a tripwire; a short response gets a bounded retry (there was
none — only a warning that scrolled past).
"""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import MAX_KTS_PER_DOM, MIN_KTS_PER_DOM, prompt_domain_key_trends
from ...prompts import fmt_claims_block  # noqa: F401  (kept for prompt helpers)
from ..config import DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json

#: One re-ask for a domain that came back under MIN. Bounded: a second short
#: answer publishes short and the kt_count gate decides.
MAX_KT_ATTEMPTS = 2


def _valid_kts(result: object) -> list[dict]:
    raw = result.get('key_trends') if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    return [kt for kt in raw
            if isinstance(kt, dict) and kt.get('name') and kt.get('subtitle')]


def phase3_key_trends(conn, api_key: str, domain_claims: dict,
                      previous: dict | None = None) -> dict:
    """
    Returns {domain_id: [kt_dict_with_db_id, ...]}
    Writes MIN..MAX_KTS_PER_DOM Key Trends per domain to domain_key_trends.

    `previous` is the live published taxonomy from `carryover`. Each sphere is
    shown its OWN live shifts and asked to return them; every other sphere's
    live names go in `taken` instead, which forbids them. Those two blocks have
    to stay disjoint — `taken` forbids even echoing a name, so a sphere seeing
    its own names there would be told to return and to avoid the same words.
    """
    print('\nPhase 3 — Generating Key Trends per domain (sequential, shared name ledger)…')

    previous = previous or {}
    slug = _slugger()
    domain_kts: dict = {}
    taken: list[str] = []
    for d in DOMAINS:
        claims = domain_claims[d['id']]
        current = previous.get(d['id']) or []
        # Live names belonging to spheres this run has NOT reached yet. Without
        # this, Society can coin the name Organizations is about to be asked to
        # carry forward, three calls before Organizations is asked for it.
        reserved = [entry['name']
                    for dom_id, entries in previous.items() if dom_id != d['id']
                    for entry in entries]
        forbidden = sorted(set(taken) | set(reserved))
        kts: list[dict] = []
        for attempt in range(1, MAX_KT_ATTEMPTS + 1):
            [result] = generate_json(
                [d],
                lambda dom: prompt_domain_key_trends(
                    dom, claims, taken=forbidden, current=current),
                default=lambda: {'key_trends': []},
                describe=lambda dom: f"{dom['name']} (attempt {attempt})",
            )
            kts = _valid_kts(result)
            if len(kts) >= MIN_KTS_PER_DOM:
                break
            if attempt < MAX_KT_ATTEMPTS:
                print(f'  {d["name"]}: only {len(kts)} KTs '
                      f'(target {MIN_KTS_PER_DOM}–{MAX_KTS_PER_DOM}) — re-asking')
        if len(kts) < MIN_KTS_PER_DOM and current:
            # `generate_json` swallows a failed call into `default`, so a single
            # HTTP error here used to cost a sphere its shifts. That was survivable
            # while every run reminted the map anyway; against a published one it
            # means retiring 7–9 live URLs — and everything keyed to them — because
            # one batch timed out. Losing a week's refresh is the cheaper failure.
            print(f'  {d["name"]}: only {len(kts)} KTs after {MAX_KT_ATTEMPTS} '
                  f'attempts — carrying the published sphere forward unchanged '
                  f'rather than retiring {len(current)} live shift(s)')
            kts = [{'name': entry['name'], 'subtitle': entry.get('subtitle', ''),
                    'velocity': 'steady', 'claim_ids': []} for entry in current]
        elif len(kts) < MIN_KTS_PER_DOM:
            print(f'  {d["name"]}: only {len(kts)} KTs after {MAX_KT_ATTEMPTS} '
                  f'attempts — the kt_count gate will decide')
        # Deterministic truncation past MAX: the model lists its strongest
        # candidates first, and a sixth-through-Nth thin trend is exactly what
        # the range exists to prevent.
        kts = kts[:MAX_KTS_PER_DOM]

        written = []
        for j, kt in enumerate(kts, start=1):
            kt['_db_id'] = conn.execute("""
                INSERT INTO domain_key_trends
                  (slug, domain_id, name, subtitle, velocity, sort_order)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (slug(f'kt-{slugify(kt["name"])}'), d['id'],
                  kt['name'], kt.get('subtitle', ''), kt.get('velocity', 'rising'), j)).fetchone()['id']
            kt['_claim_ids'] = [int(cid) for cid in kt.get('claim_ids', [])
                                if isinstance(cid, (int, float)) and not isinstance(cid, bool)]
            written.append(kt)
            taken.append(str(kt['name']))
        domain_kts[d['id']] = written
        print(f'  ✓  {d["name"]}: {len(written)} KTs')

    conn.commit()
    return domain_kts
