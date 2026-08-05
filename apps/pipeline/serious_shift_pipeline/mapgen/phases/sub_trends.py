"""Phase 4 — generate sub-trends under each Key Trend."""
from __future__ import annotations

from ...core.text import url_slug as slugify
from ...prompts import prompt_sub_trends
from ..config import CLAIMS_PER_KT, DOMAINS
from ..dbutil import _slugger
from ..llm import generate_json

#: The publication contract requires exactly this many sub-shifts per shift.
#: Fewer means missing pages and a failed gate; more is truncated deterministically
#: rather than left for the validator to reject.
REQUIRED_SUB_TRENDS = 5

#: Re-asks for a shift whose taxonomy came back short. Cheap — it is one call per
#: shift, and only the shortfall is retried.
MAX_CLUSTER_ATTEMPTS = 3


#: The contract requires two independently routed evidence items per sub-shift,
#: and the editorial prompt must cite two of its own claims. A sub-shift given
#: fewer than this is unpublishable the moment it is created — no retry can fix
#: it, because the evidence to cite does not exist.
MIN_CLAIMS_PER_SUB = 2


def _top_up_claims(sub_trends: list[dict], allowed_claim_ids: set[int]) -> list[dict]:
    """Give every sub-shift at least `MIN_CLAIMS_PER_SUB` routed claims.

    The model assigns claims unevenly: on one run 20 of 245 sub-shifts came back
    with one claim or none, out of a parent pool of up to a hundred. Each of those
    then failed publication three ways at once — no evidence module, no citable
    provenance, and therefore no editorial body at all, which is 9 missing modules
    per sub-shift and 180 of the run's 285 issues.

    Ownership stays single: a claim already assigned to a sibling is never reused.
    Topping up from the parent's unassigned remainder is a routing decision, not
    an editorial one, so it belongs here rather than in a prompt.
    """
    taken = {cid for st in sub_trends for cid in st.get('claim_ids') or []}
    spare = [cid for cid in sorted(allowed_claim_ids) if cid not in taken]
    for st in sub_trends:
        ids = list(st.get('claim_ids') or [])
        while len(ids) < MIN_CLAIMS_PER_SUB and spare:
            ids.append(spare.pop(0))
        st['claim_ids'] = ids
    return sub_trends


def _validated_sub_trends(result: object, allowed_claim_ids: set[int]) -> list[dict]:
    """Keep model taxonomy only when it satisfies the publication contract.

    Claim assignment is single-owner within a parent. Unknown IDs and repeated
    IDs are dropped instead of being over-routed into generic sibling pages.
    Structural defects remain visible to the publication validator, which can
    trigger the one bounded repair pass.
    """
    raw = result.get('sub_trends') if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return []
    seen: set[int] = set()
    out = []
    for item in raw:
        if not isinstance(item, dict) or not all(item.get(k) for k in ('name', 'subtitle', 'description')):
            continue
        ids = []
        for value in item.get('claim_ids') or []:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            claim_id = int(value)
            if claim_id in allowed_claim_ids and claim_id not in seen:
                seen.add(claim_id)
                ids.append(claim_id)
        out.append({**item, 'claim_ids': ids[:8]})
    return out


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

    # One call per Key Trend, re-requesting any that did not come back with a
    # publishable taxonomy. The contract is *exactly* five sub-shifts per shift;
    # a shift that gets none has no sub-shift pages at all and fails the gate for
    # the whole run, so it is worth a second and third ask.
    prompt_of = lambda item: prompt_sub_trends(  # noqa: E731 — matches the call below
        item[1]['name'], item[1].get('subtitle', ''), item[2])
    describe = lambda item: item[1]['name'][:30]  # noqa: E731

    def usable(item, result) -> bool:
        return len(_validated_sub_trends(result, {c['id'] for c in item[2]})) >= REQUIRED_SUB_TRENDS

    results = generate_json(work, prompt_of, default=lambda: {'sub_trends': []},
                            describe=describe)
    for attempt in range(2, MAX_CLUSTER_ATTEMPTS + 1):
        pending = [i for i, (item, r) in enumerate(zip(work, results)) if not usable(item, r)]
        if not pending:
            break
        print(f'    {len(pending)} shift(s) short of {REQUIRED_SUB_TRENDS} sub-trends — '
              f'attempt {attempt}/{MAX_CLUSTER_ATTEMPTS}')
        retried = generate_json([work[i] for i in pending], prompt_of,
                                default=lambda: {'sub_trends': []}, describe=describe)
        for index, result in zip(pending, retried):
            if usable(work[index], result):
                results[index] = result

    # Serial: write sub-trends + claim links, refine KT velocity.
    slug = _slugger()
    for (d_id, kt, claims), result in zip(work, results):
        velocity = result.get('key_trend_velocity', kt.get('velocity', 'rising'))
        conn.execute('UPDATE domain_key_trends SET velocity=%s WHERE id=%s', (velocity, kt['_db_id']))
        # Truncate rather than publish a sixth: the contract is exact, and a
        # deterministic cut here beats a validation failure the repair pass then
        # has to spend a call undoing.
        allowed = {claim['id'] for claim in claims}
        sub_trends = _top_up_claims(
            _validated_sub_trends(result, allowed)[:REQUIRED_SUB_TRENDS], allowed)
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
