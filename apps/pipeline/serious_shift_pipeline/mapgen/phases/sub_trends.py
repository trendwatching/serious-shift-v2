"""Phase 4 — generate sub-trends under each Key Trend."""
from __future__ import annotations

import math

from ...core.matching import normalize
from ...core.text import url_slug as slugify
from ...prompts import prompt_sub_trends
from ..config import CLAIMS_PER_KT, DOMAINS, MAX_SUB_TRENDS, MIN_SUB_TRENDS
from ..dbutil import _slugger
from ..naming import (breaches_family_cap, choose_unique, family_counter,
                      family_keys, name_key)
from ..llm import generate_json

#: Aim for the maximum; publish anything from the minimum up. Both come from
#: mapgen.config so the generator and the gate cannot disagree — they were
#: separate literals in three files until 18 Aug 2026.

#: Re-asks for a shift whose taxonomy came back short. Cheap — it is one call per
#: shift, and only the shortfall is retried.
MAX_CLUSTER_ATTEMPTS = 3


#: The contract requires two independently routed evidence items per sub-shift,
#: and the editorial prompt must cite two of its own claims. A sub-shift given
#: fewer than this is unpublishable the moment it is created — no retry can fix
#: it, because the evidence to cite does not exist.
MIN_CLAIMS_PER_SUB = 2

#: The smallest pool a KT can cluster a PUBLISHABLE set of sub-shifts from:
#: MIN_CLAIMS_PER_SUB per child at the minimum child count, plus citation
#: headroom. Derived rather than written down, because it was 12 — sized for
#: five children — and would have stayed sized for five. Pools below this are
#: filled from zero-overlap spares: a thin on-topic pool beats an unpublishable
#: one.
MIN_POOL_PER_KT = MIN_SUB_TRENDS * MIN_CLAIMS_PER_SUB + 6


def _pool_idf(pool: list[dict]) -> dict[str, float]:
    """IDF over the domain pool's claim texts (same shape as matching.Corpus)."""
    df: dict[str, int] = {}
    for claim in pool:
        for term in set(normalize(claim.get('claim_text') or '')):
            df[term] = df.get(term, 0) + 1
    n = len(pool)
    return {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}


def _topical_top_up(kt: dict, full_pool: list[dict], preferred_ids: set[int],
                    ledger: set[int], remaining: int,
                    idf: dict[str, float]) -> list[dict]:
    """Spares for a KT's pool, chosen for the KT rather than for the domain.

    The old top-up took the head of the domain pool, so every KT in a domain
    received the same ~80 highest-weighted claims — which is how one suicide
    statistic became the hero of ten shifts and the same six anecdotes carried
    the whole map. Spares are now ranked by IDF-weighted token overlap with the
    KT's own name+subtitle, and a claim consumed as top-up by one KT is off the
    table for its siblings (`ledger`). Phase-3 assignments are never stolen.

    Zero-overlap spares are used only to reach MIN_POOL_PER_KT — a claim with
    nothing lexically in common with the shift has no business informing its
    editorial, let alone becoming its hero stat.
    """
    kt_terms = set(normalize(f"{kt.get('name') or ''} {kt.get('subtitle') or ''}"))
    scored: list[tuple[float, int, dict]] = []
    for claim in full_pool:
        cid = claim['id']
        if cid in preferred_ids or cid in ledger:
            continue
        overlap = sum(idf.get(t, 0.0) for t in kt_terms & set(normalize(claim.get('claim_text') or '')))
        scored.append((overlap, cid, claim))
    scored.sort(key=lambda item: (-item[0], item[1]))

    chosen = [claim for overlap, _, claim in scored if overlap > 0][:remaining]
    floor = max(0, min(remaining, MIN_POOL_PER_KT - len(preferred_ids)) - len(chosen))
    if floor:
        chosen += [claim for overlap, _, claim in scored if overlap <= 0][:floor]
    ledger.update(claim['id'] for claim in chosen)
    return chosen


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

    # The repair path re-clusters a few shifts into a map the rest of which
    # already exists — everything ledgered below must therefore be seeded from
    # the database, not just from this call's own work list. On the full run
    # the tables were just reset, so both seeds are empty and nothing changes.
    routed_elsewhere = {
        r['claim_id'] for r in
        conn.execute('SELECT DISTINCT claim_id FROM domain_sub_trend_claims').fetchall()
    }
    existing_names = {
        str(r['name']).strip() for r in
        conn.execute('SELECT name FROM domain_sub_trends UNION '
                     'SELECT name FROM domain_key_trends').fetchall()
        if str(r['name'] or '').strip()
    }

    # Build the per-KT claim pool (pure, no I/O), one work item per KT.
    # Top-up is topical and exclusive: ranked by overlap with the KT's own
    # framing, and a spare consumed by one KT never pads a sibling's pool.
    work = []  # (domain_id, kt, preferred_claims)
    starved: list[str] = []
    for d in DOMAINS:
        full_pool = domain_claims[d['id']]
        idf = _pool_idf(full_pool)
        topup_ledger: set[int] = set(routed_elsewhere)
        shifts = domain_kts.get(d['id'], [])
        # A FAIR SHARE of the spares, not a greedy grab.
        #
        # Every shift used to be offered up to CLAIMS_PER_KT from one shared
        # ledger, so demand was n_kts x 100 against a pool of a few hundred and
        # the first two or three shifts in a sphere consumed all the spares.
        # That was survivable at nine shifts and starves the tail at fifteen:
        # the last shifts run on their phase-3 assignments alone, their children
        # fall under MIN_CLAIMS_PER_SUB, and the editorial then has nothing
        # citable — which the gate reports as missing modules, three steps away
        # from the actual cause.
        share = max(MIN_POOL_PER_KT, len(full_pool) // max(len(shifts), 1))
        for kt in shifts:
            preferred_ids = set(kt.get('_claim_ids', []))
            preferred = sorted(
                (all_domain_claims[cid] for cid in preferred_ids if cid in all_domain_claims),
                key=lambda c: c['id'])
            remaining = min(CLAIMS_PER_KT, share) - len(preferred)
            if remaining > 0:
                preferred += _topical_top_up(kt, full_pool, preferred_ids,
                                             topup_ledger, remaining, idf)
            if preferred:
                work.append((d['id'], kt, preferred))
            else:
                # Previously this shift just vanished from `work` — no error, no
                # warning. It surfaced much later as `sub_shift_count: found 0`,
                # and the repair pass re-ran phase 4 against the same exhausted
                # pool and re-failed. Say it here, where the cause is visible.
                starved.append(f'{d["id"]}/{kt.get("name")}')

    if starved:
        print(f'  ⚠  {len(starved)} key shift(s) got no routed claims and will have '
              f'no sub-shifts — the domain pool is exhausted: {", ".join(starved[:5])}'
              + (' …' if len(starved) > 5 else ''))

    # One call per Key Trend, re-requesting any that did not come back with a
    # publishable taxonomy. The contract is *exactly* five sub-shifts per shift;
    # a shift that gets none has no sub-shift pages at all and fails the gate for
    # the whole run, so it is worth a second and third ask.
    # Seeded with every KEY SHIFT name, so a sub-shift cannot be born wearing its
    # own parent's — or another shift's — name. Sub-shift names are added as
    # collisions are resolved below; the calls themselves run concurrently, so no
    # single call can see what its siblings are inventing at the same moment.
    # That is the whole reason the duplicates happened.
    # Matched case-insensitively, shown to the model in its original casing.
    display: dict[str, str] = {}
    for name in existing_names:
        display.setdefault(name.lower(), name)
    for _, kt, _ in work:
        name = str(kt.get('name') or '').strip()
        if name:
            display.setdefault(name.lower(), name)
    taken: set[str] = set(display)

    prompt_of = lambda item: prompt_sub_trends(  # noqa: E731 — matches the call below
        item[1]['name'], item[1].get('subtitle', ''), item[2],
        taken=[display[key] for key in sorted(taken)])
    describe = lambda item: item[1]['name'][:30]  # noqa: E731

    def usable(item, result) -> bool:
        # The MINIMUM, not the maximum. This predicate decides whether to spend
        # another paid attempt, and a shift that already has enough to publish
        # is not worth three of them.
        return len(_validated_sub_trends(result, {c['id'] for c in item[2]})) >= MIN_SUB_TRENDS

    results = generate_json(work, prompt_of, default=lambda: {'sub_trends': []},
                            describe=describe)
    for attempt in range(2, MAX_CLUSTER_ATTEMPTS + 1):
        pending = [i for i, (item, r) in enumerate(zip(work, results)) if not usable(item, r)]
        if not pending:
            break
        print(f'    {len(pending)} shift(s) short of {MIN_SUB_TRENDS} sub-trends — '
              f'attempt {attempt}/{MAX_CLUSTER_ATTEMPTS}')
        retried = generate_json([work[i] for i in pending], prompt_of,
                                default=lambda: {'sub_trends': []}, describe=describe)
        for index, result in zip(pending, retried):
            if usable(work[index], result):
                results[index] = result

    # ── Collision pass ────────────────────────────────────────────────────
    #
    # Walk the results in a fixed order, claiming names as we go. A shift whose
    # sub-trends collide with anything already claimed — exactly, or by pushing
    # a name FAMILY past its cap (nine "…Blindspot"s were all exact-unique) —
    # is re-asked with the accumulated list, which is the only point at which a
    # call can know what every other call produced. Deterministic order so a
    # rerun makes the same decisions; validation.py hard-fails exact twins that
    # survive, and choose_unique below resolves family breaches by walking to a
    # spare.
    for attempt in range(1, MAX_CLUSTER_ATTEMPTS + 1):
        families = family_counter(display[key] for key in sorted(taken))
        clashing = []
        for index, (item, result) in enumerate(zip(work, results)):
            names = [str(sub.get('name') or '').strip()
                     for sub in (result.get('sub_trends') or [])]
            keys = [n.lower() for n in names if n]
            breach = False
            batch = family_counter(())
            for name in names:
                if breaches_family_cap(name, families + batch):
                    breach = True
                    break
                batch.update(family_keys(name))
            if any(k in taken for k in keys) or len(set(keys)) != len(keys) or breach:
                clashing.append(index)
                continue
            for name, key in zip(names, keys):
                taken.add(key)
                display.setdefault(key, name)
        if not clashing:
            break
        if attempt == MAX_CLUSTER_ATTEMPTS:
            print(f'    {len(clashing)} shift(s) still carry a duplicate name after '
                  f'{MAX_CLUSTER_ATTEMPTS} asks — resolving deterministically below')
            break
        print(f'    {len(clashing)} shift(s) reused a name — re-asking with '
              f'{len(taken)} taken (attempt {attempt}/{MAX_CLUSTER_ATTEMPTS})')
        retried = generate_json([work[i] for i in clashing], prompt_of,
                                default=lambda: {'sub_trends': []}, describe=describe)
        for index, result in zip(clashing, retried):
            if usable(work[index], result):
                results[index] = result

    # Serial: write sub-trends + claim links. Velocity is phase 3's call and is
    # not revisited here — phase 3 sees the whole domain and can grade trends
    # against each other; this phase sees one KT and anchored on the prompt's
    # example value every time it was asked.
    # Seeded with what the table already holds: on the full run that is
    # nothing (reset), on the repair path it is every other shift's children.
    slug = _slugger({r['slug'] for r in
                     conn.execute('SELECT slug FROM domain_sub_trends').fetchall()})
    # The authoritative uniqueness pass. The asks above are a quality mechanism
    # and may still leave a collision; this cannot, because it chooses rather
    # than requests. Seeded with every key-shift name so no child is born
    # wearing its parent's, and carried across shifts so each sees what the
    # previous ones took.
    claimed: set[str] = {name_key(name) for name in existing_names}
    claimed |= {name_key(kt.get('name')) for _, kt, _ in work}
    claimed.discard('')
    # The family ledger, seeded the same way: what the map already wears counts
    # toward every cap, so a run against a published map cannot re-grow the
    # "…Blindspot" monotone one legal name at a time. Deduplicated on name_key
    # first — existing_names already contains this run's key trends, and a name
    # counted twice would saturate its families on its own.
    seed_names: dict[str, str] = {}
    for name in list(existing_names) + [str(kt.get('name') or '') for _, kt, _ in work]:
        key = name_key(name)
        if key:
            seed_names.setdefault(key, name)
    chosen_families = family_counter(seed_names.values())
    promoted = 0
    short: list[str] = []
    for (d_id, kt, claims), result in zip(work, results):
        # Choose BEFORE truncating. Truncating first threw away the spare that
        # would have replaced a collider, which is what left the run with a
        # duplicate the gate then rejected.
        allowed = {claim['id'] for claim in claims}
        candidates = _validated_sub_trends(result, allowed)
        chosen, dropped = choose_unique(candidates, MAX_SUB_TRENDS, claimed,
                                        families=chosen_families)
        promoted += len(dropped)
        if len(chosen) < MIN_SUB_TRENDS:
            short.append(kt['name'])
        sub_trends = _top_up_claims(chosen, allowed)
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
        print(f'  ✓  {kt["name"][:48]}: {len(sub_trends)} sub-trends')

    if promoted or short:
        print(f'    {promoted} colliding name(s) replaced from spare candidates; '
              f'{len(short)} shift(s) publishing fewer than {MIN_SUB_TRENDS} '
              f'rather than a duplicate'
              + (f' ({", ".join(n[:28] for n in short[:4])})' if short else ''))

    conn.commit()
