"""Phase 4b — editorial prose for Key Trends and their sub-trends."""
from __future__ import annotations

from ...prompts import prompt_kt_editorial, prompt_st_editorial
from ..config import CLAIMS_PER_KT, DOMAINS
from ..llm import generate_json
from ..modules import _jsonb, _short_figure, kt_modules, st_modules


KT_REQUIRED = {
    'from', 'to', 'pull_quote', 'whats_changing', 'why_now',
    'human_needs', 'timeline', 'industries', 'opportunities',
}
ST_REQUIRED = {
    'lede', 'from', 'to', 'quote', 'whats_changing', 'why_now',
    'human_needs', 'signals', 'counter_signals', 'timeline', 'territories',
}

#: Fields where any one of several keys will do. `consumer_tension` is the
#: pre-August-2026 name for `tension`; a body that used the old key is complete,
#: and re-requesting it would spend a call to change a spelling.
KT_REQUIRED_ANY: tuple[tuple[str, ...], ...] = (('tension', 'consumer_tension'),)
ST_REQUIRED_ANY: tuple[tuple[str, ...], ...] = ()

#: Sub-objects that have to be filled on both sides. `human_needs` is rendered as
#: a card pair, so a body carrying only `unlocked` produces a coloured rectangle
#: with a label and no copy — which is what shipped before this check existed.
BOTH_SIDES = (('human_needs', ('unlocked', 'threatened')),)

#: How many times to ask for one body. A model that omits a field or overruns a
#: word cap usually gets it right on a second look, and re-requesting only the
#: failures is a handful of calls rather than another full phase.
MAX_EDITORIAL_ATTEMPTS = 3

def _complete_editorial(
    value: object,
    required: set[str],
    any_of: tuple[tuple[str, ...], ...] = (),
) -> bool:
    """Whether a body has everything the page needs.

    Length is deliberately *not* checked here. It was, briefly, and it made
    things worse: a shift carries sixteen sector notes, so judging the whole body
    on the longest of them failed 46 of 49 shifts on the first pass and still 41
    after three attempts — the retries could not converge because the thing being
    retried was not the thing that was wrong. Overruns are now trimmed per field
    in `modules.clamp_words`, where one long note is one note's problem, and this
    predicate is back to asking only what it can usefully re-request: are the
    fields there, and are the citations real.
    """
    if not isinstance(value, dict):
        return False
    if not all(value.get(field) for field in required):
        return False
    if not all(any(value.get(field) for field in group) for group in any_of):
        return False
    for key, sides in BOTH_SIDES:
        nested = value.get(key)
        if not isinstance(nested, dict) or not all(nested.get(s) for s in sides):
            return False
    return True


def _cited(editorial: object, key: str = 'evidence_ids') -> set[int]:
    """The claim ids an editorial body cites, ignoring anything non-numeric."""
    raw = editorial.get(key) if isinstance(editorial, dict) else []
    return {
        int(value) for value in raw or []
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _generate_until_complete(items, prompt_of, is_complete, *, describe, label):
    """Generate one body per item, then re-request only the ones that failed.

    Incomplete or overlong bodies used to be written as a NULL module list, which
    turned one absent field into nine missing modules and a publication the gate
    could never accept. Retrying the failures costs a few calls; not retrying
    them cost the entire run.
    """
    results = generate_json(items, prompt_of, default=dict, describe=describe)
    for attempt in range(2, MAX_EDITORIAL_ATTEMPTS + 1):
        pending = [i for i, (item, r) in enumerate(zip(items, results))
                   if not is_complete(item, r)]
        if not pending:
            break
        print(f'    {label}: {len(pending)} incomplete or overlong — '
              f'attempt {attempt}/{MAX_EDITORIAL_ATTEMPTS}')
        retried = generate_json([items[i] for i in pending], prompt_of,
                                default=dict, describe=describe)
        for index, result in zip(pending, retried):
            if is_complete(items[index], result):
                results[index] = result
    still = sum(1 for item, r in zip(items, results) if not is_complete(item, r))
    if still:
        print(f'    {label}: {still} still incomplete after '
              f'{MAX_EDITORIAL_ATTEMPTS} attempts')
    return results


def _sub_is_complete(sub, editorial, claims_by_sub) -> bool:
    allowed = {claim['id'] for claim in claims_by_sub.get(sub['id'], [])}
    cited = _cited(editorial)
    return (_complete_editorial(editorial, ST_REQUIRED, ST_REQUIRED_ANY)
            and len(cited) >= 2 and cited <= allowed)


def _generate_sub_editorial(items, *, describe):
    """One call per shift covering all five of its sub-shifts, retried per sub.

    A shift's response covers five sub-shifts at once, and asking for five
    eleven-field bodies inside one response means a partial answer is the normal
    case, not the exception. So the retry has to merge: keep the sub-shifts that
    came back usable, re-ask only for the shift's remaining ones, and fold each
    new arrival in.

    Judging the *shift* pass/fail instead — which is what a naive predicate
    does — makes every shift fail while any one of its five is short, so nothing
    is ever kept and the retries are three batches of pure waste. That is not
    hypothetical: it is what the first version of this did.
    """
    accumulated: list[dict] = [{'sub_trends': []} for _ in items]

    def missing(index: int) -> list:
        item = items[index]
        have = {
            str(se.get('name', '')).strip().lower()
            for se in accumulated[index]['sub_trends'] if isinstance(se, dict)
        }
        return [sub for sub in item[3] if sub['name'].strip().lower() not in have]

    for attempt in range(1, MAX_EDITORIAL_ATTEMPTS + 1):
        pending = [i for i in range(len(items)) if missing(i)]
        if not pending:
            break
        if attempt > 1:
            short = sum(len(missing(i)) for i in pending)
            print(f'    sub-shift editorial: {short} sub-shift(s) across '
                  f'{len(pending)} shift(s) short — attempt {attempt}/{MAX_EDITORIAL_ATTEMPTS}')
        # Ask only for the sub-shifts still outstanding, so a retry is a smaller
        # request as well as a rarer one. Each request carries its own shortfall
        # rather than being looked up by identity later.
        requests = [(items[i], missing(i)) for i in pending]
        results = generate_json(
            requests,
            lambda pair: prompt_st_editorial(
                pair[0][1]['name'], pair[0][1].get('subtitle', ''), pair[1], pair[0][4]),
            default=dict, describe=lambda pair: describe(pair[0]),
        )
        for index, result in zip(pending, results):
            item = items[index]
            by_name = {
                str(se.get('name', '')).strip().lower(): se
                for se in ((result or {}).get('sub_trends') or []) if isinstance(se, dict)
            }
            for sub in missing(index):
                se = by_name.get(sub['name'].strip().lower())
                if _sub_is_complete(sub, se, item[4]):
                    accumulated[index]['sub_trends'].append(se)

    short = sum(len(missing(i)) for i in range(len(items)))
    if short:
        print(f'    sub-shift editorial: {short} sub-shift(s) still incomplete '
              f'after {MAX_EDITORIAL_ATTEMPTS} attempts')
    return accumulated


def _verified_stat(editorial: dict, claims: list[dict]) -> dict | None:
    """Attach provenance from our database, never from model-authored text."""
    raw = editorial.get('stat') if isinstance(editorial, dict) else None
    if not isinstance(raw, dict):
        return None
    raw_claim_id = raw.get('claim_id')
    if isinstance(raw_claim_id, bool) or not isinstance(raw_claim_id, (int, float, str)):
        return None
    try:
        claim_id = int(raw_claim_id)
    except (TypeError, ValueError):
        return None
    claim = next((item for item in claims if item.get('id') == claim_id), None)
    value = _short_figure(claim.get('statistic')) if claim else None
    url = str(claim.get('source_url') or '') if claim else ''
    if not claim or not claim.get('has_statistic') or not value or not url.startswith(('http://', 'https://')):
        return None
    source = claim.get('thinker') or claim.get('source_title') or ''
    date = str(claim.get('date_published') or '')[:4]
    return {
        'value': value,
        'text': claim.get('claim_text') or '',
        'source': ', '.join(part for part in (source, date) if part),
        'url': url,
    }

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

    claim_ids_by_sub: dict = {}
    for r in conn.execute("""
        SELECT sub_trend_id, claim_id
        FROM domain_sub_trend_claims
        ORDER BY sub_trend_id, claim_id
    """).fetchall():
        claim_ids_by_sub.setdefault(r['sub_trend_id'], []).append(r['claim_id'])

    # One work item per KT, carrying its claims and its already-written sub-trends.
    work = []
    for d in DOMAINS:
        for kt in domain_kts.get(d['id'], []):
            subs = subs_by_kt.get(kt['_db_id'], [])
            claims_by_sub = {
                sub['id']: [pool[cid] for cid in claim_ids_by_sub.get(sub['id'], []) if cid in pool]
                for sub in subs
            }
            # Parent editorial may cite only evidence that is actually published
            # on one of its children. Earlier selection pools can contain claims
            # discarded during single-owner routing; exposing those to the model
            # creates citations readers cannot inspect anywhere on the shift.
            #
            # The shift's citable pool is exactly the union of its children's
            # routed claims — because that is precisely what the publication gate
            # checks it against ("2–6 citations from its routed child evidence").
            #
            # It used to fall back to the whole domain pool when a shift had no
            # `_claim_ids`, which let the model cite perfectly real claims that
            # belonged to no child of this shift. Those bodies passed the phase's
            # own completeness check and then failed the gate — 46 of 49 shifts on
            # one run — because the prompt was offered a wider set than the
            # validator would accept. Offer the narrower one and the two agree.
            claims = [
                claim for claim in (
                    pool[cid] for sub in subs
                    for cid in claim_ids_by_sub.get(sub['id'], []) if cid in pool
                )
            ][:CLAIMS_PER_KT]
            if not claims:
                # No child evidence at all: nothing citable exists, so the shift
                # cannot carry an editorial body. Skip rather than prompt for one
                # that is guaranteed to be rejected.
                print(f'  ⚠  {kt["name"][:40]}: no routed child evidence — skipping editorial')
                continue
            work.append((d['id'], kt, claims, subs, claims_by_sub))

    if not work:
        print('  (no Key Trends to enrich)')
        return

    # Two independent calls per Key Trend (its own editorial, and its sub-trends'),
    # so they go out as two batches and are merged back by index.
    def describe(item):
        return item[1]['name'][:30]

    def kt_is_complete(item, result):
        allowed = {claim['id'] for claim in item[2]}
        cited = _cited(result)
        return (_complete_editorial(result, KT_REQUIRED, KT_REQUIRED_ANY)
                and len(cited) >= 2 and cited <= allowed)

    kt_results = _generate_until_complete(
        work,
        lambda item: prompt_kt_editorial(
            item[1]['name'], item[1].get('subtitle', ''), str(by_id[item[0]]['name']), item[2]),
        kt_is_complete, describe=describe, label='shift editorial',
    )
    with_subs = [item for item in work if item[3]]
    st_results = _generate_sub_editorial(with_subs, describe=describe)
    st_by_kt = {id(item): r for item, r in zip(with_subs, st_results)}
    results = [
        {'kt': kt_r or {}, 'st': st_by_kt.get(id(item)) or {}}
        for item, kt_r in zip(work, kt_results)
    ]

    kt_done = st_done = 0
    for (_d_id, kt, _claims, subs, claims_by_sub), result in zip(work, results):
        e = result.get('kt') or {}
        kt_row = kt_rows.get(kt['_db_id'], {'subtitle': kt.get('subtitle', ''), 'hero_stat': None})
        kt_ids = {claim['id'] for claim in _claims}
        kt_citations = _cited(e)
        complete_kt = (_complete_editorial(e, KT_REQUIRED, KT_REQUIRED_ANY)
                       and len(kt_citations) >= 2 and kt_citations <= kt_ids)
        modules = kt_modules(kt_row, e) if complete_kt else []
        conn.execute(
            'UPDATE domain_key_trends SET modules=%s::jsonb, read_time=%s WHERE id=%s',
            (_jsonb(modules), e.get('read_time') or None, kt['_db_id']),
        )
        if complete_kt:
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
            allowed = claims_by_sub.get(sub['id'], [])
            allowed_ids = {claim['id'] for claim in allowed}
            cited = _cited(se)
            complete_st = (_complete_editorial(se, ST_REQUIRED, ST_REQUIRED_ANY)
                           and len(cited) >= 2 and cited <= allowed_ids)
            if complete_st:
                se = dict(se)
                se['stat'] = _verified_stat(se, allowed)
            conn.execute(
                'UPDATE domain_sub_trends SET modules=%s::jsonb WHERE id=%s',
                (_jsonb(st_modules(sub, se)) if complete_st else None, sub['id']),
            )
            if complete_st:
                st_done += 1

    conn.commit()
    expected_subs = sum(len(item[3]) for item in work)
    print(f'  ✓  {kt_done}/{len(work)} shifts and {st_done}/{expected_subs} sub-shifts given a validated editorial body.')
