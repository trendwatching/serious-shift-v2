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
from ..naming import breaches_family_cap, family_counter, family_keys, name_key

#: One re-ask for a domain that came back under MIN. Bounded: a second short
#: answer publishes short and the kt_count gate decides.
MAX_KT_ATTEMPTS = 2


def _valid_kts(result: object) -> list[dict]:
    raw = result.get('key_trends') if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    return [kt for kt in raw
            if isinstance(kt, dict) and kt.get('name') and kt.get('subtitle')]


def _select_kts(kts: list[dict], want: int, current_keys: set[str],
                reserved: set[str], accepted: set[str],
                families) -> tuple[list[dict], list[str]]:
    """The first `want` candidates that keep the map's names distinct.

    A candidate is walked past — the same spare-walking `choose_unique` does
    for sub-shifts — when its name is already accepted this run, or when it is
    NEW and would either reuse another sphere's live name (`reserved`) or push
    a name family past its cap ("Cognition Stake" in Society and "Cognition
    Bleed" in Consumers were both legal by exact equality; the 2026-08-19
    review named three such pairs).

    A CARRIED name — one this sphere is publishing right now — is exempt from
    the family test: continuity beats the lint, and retiring a live label is a
    deliberate act, not a side-effect. Its families are pre-counted by the
    caller, so keeping it never double-counts.
    """
    kept: list[dict] = []
    dropped: list[str] = []
    for kt in kts:
        if len(kept) >= want:
            break
        name = str(kt.get('name') or '').strip()
        key = name_key(name)
        if not key or key in accepted:
            if name:
                dropped.append(name)
            continue
        if key not in current_keys and (
                key in reserved or breaches_family_cap(name, families)):
            dropped.append(name)
            continue
        accepted.add(key)
        if key not in current_keys:
            families.update(family_keys(name))
        kept.append(kt)
    return kept, dropped


def _print_arena_mix(domain_name: str, kts: list[dict], claims: list) -> None:
    """The sphere's topical mix, printed so an operator can see clustering.

    Report-only, deliberately no gate: the only machine-readable topic signal
    is `claims.domain`, and "government-related" spans two of its buckets while
    missing others — a gate that cannot measure the defect it polices would be
    a second opinion, not an invariant. The prompt's ARENA SPREAD test is the
    fix; this line is how the operator sees whether it worked (the 2026-08-19
    review counted 5 of Society's 10 shifts on one governmental note).
    """
    by_id = {c['id']: str(c.get('claim_domain') or '?') for c in claims
             if isinstance(c, dict) and 'id' in c}
    counts: dict[str, int] = {}
    for kt in kts:
        buckets = {by_id[cid] for cid in kt.get('_claim_ids') or [] if cid in by_id}
        for bucket in buckets or {'?'}:
            counts[bucket] = counts.get(bucket, 0) + 1
    if counts:
        mix = ', '.join(f'{k}:{v}' for k, v in
                        sorted(counts.items(), key=lambda kv: -kv[1]))
        print(f'     {domain_name} claim-domain mix (shifts drawing on each): {mix}')


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
    # One family ledger for the whole map, pre-counting every live published
    # name once (carried names are exempt from the cap and must not count
    # again when their sphere returns them). Threaded through `_select_kts`
    # sphere after sphere, exactly like the `taken` name ledger.
    live_by_key: dict[str, str] = {}
    for entries in previous.values():
        for entry in entries:
            key = name_key(entry['name'])
            if key:
                live_by_key.setdefault(key, entry['name'])
    families = family_counter(live_by_key.values())
    accepted: set[str] = set()
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
        # Deterministic selection up to MAX: the model lists its strongest
        # candidates first, and a sixth-through-Nth thin trend is exactly what
        # the range exists to prevent. Selection rather than bare truncation,
        # so a family collider is replaced by the next spare instead of kept —
        # and never rejected when it is a name this sphere already publishes.
        current_keys = {name_key(entry['name']) for entry in current}
        reserved_keys = {name_key(name) for name in reserved} - current_keys
        kts, family_dropped = _select_kts(
            kts, MAX_KTS_PER_DOM, current_keys, reserved_keys, accepted, families)
        if family_dropped:
            print(f'  {d["name"]}: {len(family_dropped)} candidate name(s) walked '
                  f'past for echoing an existing name family: '
                  f'{", ".join(family_dropped[:4])}'
                  + (' …' if len(family_dropped) > 4 else ''))

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
        _print_arena_mix(str(d['name']), written, claims)

    conn.commit()
    return domain_kts
