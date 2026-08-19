"""Assemble the single JSON document the frontend reads.

Pinned by tests/test_map_export_golden.py: this is the one output whose exact
shape the UI depends on.
"""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlparse

from ..core.text import url_slug as slugify
from .art.store import publish_art
from .carryover import load_published_taxonomy, pin_slugs
from .config import DOMAINS, MODULE_ORDER
from .modules import (conform_modules, figure_echoes, scrub_module_tree,
                      stat_band_from_hero, stat_claim_key)
from .validation import EVIDENCE_REUSE_SHARE, require_valid_map


def _attr(stored):
    """Parse stored proponents/skeptics JSON into (names, detail[{name, quote}]).
    Accepts the new [{name, quote}] form or a legacy [name] list."""
    items = json.loads(stored) if stored else []
    names, detail = [], []
    for x in items:
        if isinstance(x, dict):
            names.append(x.get('name', ''))
            item = {'name': x.get('name', ''), 'quote': x.get('quote', '')}
            for field in ('source', 'date', 'url'):
                if x.get(field):
                    item[field] = x[field]
            detail.append(item)
        else:
            names.append(str(x))
            detail.append({'name': str(x), 'quote': ''})
    return names, detail


def _http_url(value) -> str:
    """A publishable HTTP(S) URL, or an empty string."""
    try:
        parsed = urlparse(str(value or '').strip())
        return parsed.geturl() if parsed.scheme in {'http', 'https'} and parsed.netloc else ''
    except ValueError:
        return ''


def assign_sub_tails(st_rows: list, kt_slugs: dict) -> tuple[dict, list[str]]:
    """The last segment of each sub-shift's URL: `{parent}/{tail}`.

    The path is two segments, but the TAIL is deduplicated GLOBALLY and against
    every key-shift slug — not per parent, which is what this did until
    18 Aug 2026.

    That was a writer/gate disagreement, and the expensive kind. Validation has
    always rejected a repeated tail (`duplicate_sub_shift_slug`) and a tail that
    shadows a shift (`sub_shift_shadows_shift`), both unrepairable. Deduplicating
    per parent meant the exporter could hand the gate a document the gate was
    guaranteed to refuse — and it refused it only after every paid phase had run.
    Conforming here is the repo's own lesson: conform at export, not at
    generation.

    Pure and separate from `build_map_json_v2` so the rule can be tested without
    a database; the golden export fixture only runs against a populated one.

    Returns `({sub_id: tail}, suffixed_tails)`.
    """
    seen: dict = {slug: 1 for slug in kt_slugs.values()}
    tails: dict = {}
    suffixed: list[str] = []
    for st in st_rows:
        base = slugify(st['name'])
        n = seen.get(base, 0) + 1
        seen[base] = n
        tail = base if n == 1 else f'{base}-{n}'
        if n > 1:
            suffixed.append(tail)
        tails[st['id']] = tail
    return tails, suffixed


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
            # The "what's shifting right now" paragraph on the sphere panel.
            # Carried on every domain row, but only the per-sphere fragment
            # serves it — the index fragment every visitor fetches on first
            # paint stays deliberately lean.
            'intro':             d['intro'],
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
        def keep(xs):
            items = []
            for x in xs:
                if not isinstance(x, dict) or not x.get('name') or not x.get('quote'):
                    continue
                source_url = _http_url(x.get('url'))
                if not source_url:
                    continue
                item = {'name': x.get('name', ''), 'quote': x.get('quote', ''), 'url': source_url}
                if x.get('source'):
                    item['source'] = x['source']
                if x.get('date'):
                    item['date'] = x['date']
                items.append(item)
            return items
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
        ORDER BY strength DESC NULLS LAST, id
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
               s.date_published, s.url, c.signal_strength, c.consumer_implication
        FROM domain_sub_trend_claims stc
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        LEFT JOIN sources s ON s.id = c.source_id
        WHERE c.duplicate_of IS NULL AND c.claim_text IS NOT NULL
        ORDER BY stc.sub_trend_id, COALESCE(c.claim_weight, 0) DESC, c.id
    """).fetchall():
        source_url = _http_url(r['url'])
        if not source_url:
            continue
        claim_rows_by_st.setdefault(r['sub_trend_id'], []).append({
            'text': r['claim_text'],
            'thinker': r['thinker'] or '',
            'source': r['source'] or '',
            'date': str(r['date_published'])[:10] if r['date_published'] else '',
            'url': source_url,
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
        """Sort a module list into the canonical reading order, and scrub it.

        The order lives in packages/contracts/shift_modules.json, so a change to
        the page composition re-composes on the next --export-only rather than
        needing every shift regenerated. Unknown types keep their relative
        position at the end rather than being dropped.

        This is also the one point every module list passes through — generated,
        derived and override-authored alike, after the derived ones have been
        inserted — so it is where the identifier scrub and the contract caps
        belong. Doing it here rather than only at generation is what lets an
        --export-only run correct copy that was written before a cap existed, or
        under one that disagreed with the gate: 75 issues on one run, none of
        them needing a single new model call to fix.
        """
        order = MODULE_ORDER.get(scope) or []
        rank = {t: i for i, t in enumerate(order)}
        fallback = len(rank)
        return sorted(
            conform_modules(scrub_module_tree(modules or [])),
            key=lambda m: (rank.get(m.get('type'), fallback), 0),
        )

    def resolve_modules(scope: str, slug: str, generated):
        """(modules, authored). `authored` marks a hand-written override.

        The backend needs to know, because it filters modules by sphere when it
        builds a route fragment and an authored list is exempt from that filter.
        Publishing the fact beside the list is cheaper and more honest than
        having the backend re-query `shift_module_overrides`: the flag then
        cannot disagree with the composition it describes.
        """
        key = (scope, slug)
        if key in overrides:
            used_overrides.add(key)
            return overrides[key], True
        return (generated or []), False

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
    # URL slugs are derived from the name — that is what the front end routes on
    # and what an override is keyed by. Two shifts could slugify the same, so
    # disambiguate in a stable order: the query is ORDER BY domain_id,
    # sort_order, so the same input always yields the same slug.
    #
    # GLOBALLY unique, not per domain. The URL carries the sphere, so per-domain
    # would be enough to route — but `shift_refs` and `shift_module_overrides`
    # are both keyed on (scope, slug) with no domain, so two spheres each
    # producing a "Moat Migration" gave both the slug `moat-migration` and the
    # publication died on a unique-constraint violation *after* passing the whole
    # editorial gate. An override keyed that way would also have silently applied
    # to the wrong sphere.
    #
    # Slugs are also CARRIED FORWARD from the live publication wherever the same
    # shift is still here — see carryover.pin_slugs. Deriving purely from the
    # name was what made every rename move a page and leave its artwork, its
    # overrides and its inbound links behind. Pinning happens here rather than in
    # phase 3 because this is the one function every publish path passes through
    # (full rebuild, --editorial-only, --export-only) and because the taxonomy is
    # only final here: the targeted repair pass can re-cluster after phase 4.
    kt_slug_by_id, slug_report = pin_slugs(list(kt_rows_all),
                                           load_published_taxonomy(conn))
    if slug_report['renames']:
        print(f'  ↻ {len(slug_report["renames"])} shift(s) renamed; each keeps its '
              f'URL so its artwork and links survive:')
        for was, now in slug_report['renames']:
            print(f'      {was!r} → {now!r}')
    if slug_report['retired']:
        print(f'  ⚠ {slug_report["retired"]} published shift(s) are not in this map')
    key_trends_j = []
    for kt in kt_rows_all:
        url_slug = kt_slug_by_id[kt['id']]
        kt_modules, kt_authored = resolve_modules('key_trend', url_slug, kt['modules'])
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
            'modules': kt_modules,
            # Stripped from every response by INTERNAL_SHIFT_FIELDS; read only by
            # the backend's snapshot builder, to exempt this page from the
            # per-sphere module visibility filter.
            'authored': kt_authored,
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

        # Phase 8 runs after phase 4b, so the persisted band can be a hero ago.
        # Re-derived, never trusted; dropped outright when the current hero has
        # no figure in it, because that band would render as an empty box.
        band = stat_band_from_hero(entry['hero_stat'])
        mods = [m for m in mods if not (isinstance(m, dict) and m.get('type') == 'stat_band')]
        if band:
            mods = mods + [band]

        seen, items = set(), []
        for dst, rel, why in links_by_kt.get(row['id'], []):
            if dst in seen or dst == row['id'] or dst not in kt_slug_by_id:
                continue
            seen.add(dst)
            items.append({
                'title': kt_title_by_id.get(dst, ''),
                'href': f'/{kt_domain_by_id.get(dst, "")}/{kt_slug_by_id[dst]}',
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
    st_tail_by_id, _suffixed = assign_sub_tails(list(st_rows_all), kt_slug_by_id)
    for st in st_rows_all:
        url_slug = f'{kt_slug_by_id.get(st["kt_id"], "")}/{st_tail_by_id[st["id"]]}'
        st_modules, st_authored = resolve_modules('sub_trend', url_slug, st['modules'])
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
            'modules': st_modules,
            'authored': st_authored,   # see the key-shift note above
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

    # A numeric suffix in a live URL is a name nobody chose. It used to be
    # applied silently; two pages sharing a name is an editorial problem and the
    # only person who can fix it needs to be told it happened.
    if _suffixed:
        print(f'  ⚠  {len(_suffixed)} sub-shift(s) needed a numeric suffix — two '
              f'pages share a name: {", ".join(_suffixed[:5])}'
              + (' …' if len(_suffixed) > 5 else ''))

    reuse_report = reconcile_evidence_reuse(sub_trends_j)
    if reuse_report['claims_trimmed']:
        print(f"  ↳ {reuse_report['claims_trimmed']} over-reaching claim citation(s) "
              f"trimmed — no claim anchors more than {reuse_report['cap']} pages.")

    # A page must not restate the figure it fronts — its fixed copy can't move,
    # so the fronted half cedes. Runs BEFORE the cross-page dedup so a doomed
    # hero never claims seniority over a sub-shift band it would then not use.
    echo_report = reconcile_self_echo(key_trends_j, sub_trends_j)
    if echo_report['shift_heroes_dropped'] or echo_report['sub_bands_dropped']:
        gone = echo_report['shift_heroes_dropped'] + echo_report['sub_bands_dropped']
        print(f"  ↳ {len(gone)} fronted statistic(s) dropped for restating the "
              f"page's own name or subtitle: {', '.join(gone[:5])}"
              + (' …' if len(gone) > 5 else ''))

    # One claim, one page — settled here rather than asked of the writers.
    stat_report = reconcile_fronted_stats(key_trends_j, sub_trends_j)
    if stat_report['sub_bands_ceded'] or stat_report['sub_bands_deduped']:
        print(f"  ↳ {stat_report['sub_bands_ceded']} sub-shift stat band(s) ceded to "
              f"their parent shift, {stat_report['sub_bands_deduped']} deduplicated "
              f"between sub-shifts — one claim fronts one page.")
    if stat_report['shift_heroes_dropped']:
        print(f"  ⚠  {len(stat_report['shift_heroes_dropped'])} shift(s) lost a hero "
              f"statistic to a duplicate figure: "
              f"{', '.join(stat_report['shift_heroes_dropped'][:5])}")

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

    # Claims stay in the document — the publication gate cross-references every
    # citation against them — but slimmed: no credibility score and no
    # signal_strength. Neither is rendered anywhere, both were exposed
    # unauthenticated through the deprecated /api/map blob, and the scores are
    # decorative until predictions get resolved (accuracy defaults to 0.5 for
    # everyone). Ranking still uses credibility_score DB-side; publishing it
    # was the only part that had to stop.
    claims_j = []
    if all_cids:
        rows = conn.execute("""
            SELECT c.id, c.claim_text, c.consumer_implication,
                   t.name AS thinker,
                   s.title AS source_title, s.date_published, s.url AS source_url
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
                'source_title':      r['source_title'] or '',
                'source_date':       r['date_published'] or '',
                'source_url':        _http_url(r['source_url']),
                'consumer_implication': r['consumer_implication'] or '',
            })

    # The `thinkers` block is gone from the document: /api/thinkers reads the
    # table directly, no frontend code reads the document copy, and shipping
    # every thinker's credibility_score in an unauthenticated blob was the
    # exposure main.rs's /api/map deprecation note complains about.

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

    # `links`, `domain_flows`, `by_thinker` and `by_velocity` are no longer
    # published: no public fragment ever served them, no frontend code read
    # them, and their producers (phases 5/6) are dormant. `synthesis_insights`
    # stays because the sphere fragment serves it and useData.js shape-checks
    # the key — it is simply an empty list while phase 7 is dormant.

    return {
        'updated':             today,
        'architecture':        'domain-first-v2',
        'domains':             domains_j,
        'key_trends':          key_trends_j,
        'sub_trends':          sub_trends_j,
        'claims':              claims_j,
        'synthesis_insights':  insights_j,
    }



#: A sub-shift below this has too little behind it to be worth publishing, so a
#: reuse trim stops rather than hollow one out.
MIN_CLAIMS_PER_SUB_ON_TRIM = 2


def reconcile_evidence_reuse(sub_trends: list) -> dict:
    """Keep a claim on the pages that most need it, and take it off the rest.

    "The same evidence cannot anchor more than N pages" is a routing fact, and
    routing is decided in phase 4. The targeted repair only rewrites editorial
    prose, so it re-published the same claim_ids every time: on the 18 Aug 2026
    run this was the LAST issue standing, survived a repair pass that fixed all
    four of its neighbours, and would have failed the map on its own. Marking it
    repairable (this morning) was not enough — nothing downstream could actually
    repair it.

    Which page cedes is decided by how much else it has to stand on: holders are
    ranked by their own claim count, fewest first, so a page resting on three
    claims keeps the evidence and a page with five gives it up. Ties break on
    document order. A page is never trimmed below
    MIN_CLAIMS_PER_SUB_ON_TRIM — the next-richest holder cedes instead, and if
    none can, the claim is left over the cap for the gate to reject rather than
    quietly gutting a page to pass.
    """
    cap = max(3, round(EVIDENCE_REUSE_SHARE * len(sub_trends)))
    holders: dict[str, list[int]] = {}
    for index, sub in enumerate(sub_trends):
        # Only routing padding is trimmable: a claim the page's own editorial
        # CITES cannot be un-routed here, because the citation would be left
        # pointing outside the page's evidence and the prose would be making a
        # point with its source removed. Blind trimming did exactly that on the
        # first attempt — it fixed evidence_reuse and broke editorial_provenance
        # on two pages instead. A cited claim over the cap is a clustering
        # decision, and only phase 4 can take it back.
        cited = set()
        for module in sub.get('modules') or []:
            if isinstance(module, dict) and module.get('type') == 'peel_tabs':
                for value in (module.get('data') or {}).get('evidence_ids') or []:
                    cited.add(f'c_{value}' if str(value).isdigit() else str(value))
        for value in sub.get('claim_ids') or []:
            if str(value) not in cited:
                holders.setdefault(str(value), []).append(index)

    total_holders: dict[str, int] = {}
    for sub in sub_trends:
        for value in sub.get('claim_ids') or []:
            total_holders[str(value)] = total_holders.get(str(value), 0) + 1

    trimmed = 0
    for value, indexes in sorted(holders.items()):
        indexes = indexes[:]  # local

        # Re-read the length each time: an earlier claim's trim may already have
        # taken pages off this one, and the counter has to be per-claim — a
        # single running total let the second over-reaching claim exit
        # immediately on the first claim's arithmetic.
        over = total_holders.get(value, 0) - cap
        if over <= 0:
            continue
        ranked = sorted(indexes, key=lambda i: (len(sub_trends[i]['claim_ids']), i))
        for index in reversed(ranked):          # richest page cedes first
            if over <= 0:
                break
            claims = sub_trends[index]['claim_ids']
            if len(claims) - 1 < MIN_CLAIMS_PER_SUB_ON_TRIM:
                continue
            sub_trends[index]['claim_ids'] = [c for c in claims if str(c) != value]
            over -= 1
            trimmed += 1
    return {'claims_trimmed': trimmed, 'cap': cap}


def reconcile_fronted_stats(key_trends: list, sub_trends: list) -> dict:
    """Apply the gate's own statistic dedup, in the gate's own order, by
    stripping the loser. Parent priority.

    One claim may front one page. `validate_map` enforces that by registering
    every key shift's `hero_stat` first and every sub-shift's `stat_band` after,
    so the SUB is always the one blamed for a cross-form collision. Nothing
    upstream honoured that order: phase 8 treated persisted child bands as
    senior and skipped the claim, and two distinct claim rows quoting the same
    figure from the same article still collided because the key is
    (figure, source), not the claim id.

    The 2026-08-12 remediation established that editorial regeneration CANNOT
    converge these — ~$4.50 of targeted regen re-formed the same pairs, because
    the avoid-list is advisory and both pages genuinely rest on the same
    evidence. So this is settled deterministically at export, where the whole
    document is visible, rather than asked for at generation. Every publish path
    passes through here, including --export-only.

    Prose defects (spelling, crutch, meta-language) do regen away and are left
    to the repair pass; only fronted-statistic identity is resolved here.
    """
    seen: dict[tuple, str] = {}
    dropped: list[str] = []
    ceded = deduped = 0

    for index, shift in enumerate(key_trends):
        hero = shift.get('hero_stat')
        if not isinstance(hero, dict) or not hero.get('value'):
            continue
        key = stat_claim_key(hero.get('value'), hero.get('url'))
        if key in seen:
            # A parent cannot cede to another parent — there is no second place
            # to put a hero — so the later shift loses both the field and the
            # band derived from it, and renders as a shift without a statistic.
            shift['hero_stat'] = None
            shift['modules'] = [m for m in shift.get('modules') or []
                                if not (isinstance(m, dict) and m.get('type') == 'stat_band')]
            dropped.append(shift.get('slug') or f'key_trends[{index}]')
        else:
            seen[key] = f'key_trends[{index}]'

    for index, sub in enumerate(sub_trends):
        kept = []
        for module in sub.get('modules') or []:
            if not (isinstance(module, dict) and module.get('type') == 'stat_band'):
                kept.append(module)
                continue
            data = module.get('data') or {}
            if not data.get('value'):
                kept.append(module)
                continue
            key = stat_claim_key(data.get('value'), data.get('url'))
            owner = seen.get(key)
            if owner is None:
                seen[key] = f'sub_trends[{index}]'
                kept.append(module)
                continue
            # Dropped, not blanked: `sub_modules` requires value+url, so a band
            # with the figure removed is not a band.
            if owner.startswith('key_trends'):
                ceded += 1
            else:
                deduped += 1
        sub['modules'] = kept

    return {'shift_heroes_dropped': dropped,
            'sub_bands_ceded': ceded, 'sub_bands_deduped': deduped}


def reconcile_self_echo(key_trends: list, sub_trends: list) -> dict:
    """Drop a fronted statistic the page's own fixed copy already states.

    A hero whose figure sits in the shift's name or subtitle puts the same
    number on the page twice, and the copy half of that pair cannot move: the
    subtitle is phase-3/4 prose the repair pass never rewrites, and there is no
    safe deterministic edit that removes a number from a sentence. So — same
    policy as `reconcile_fronted_stats` above — the movable half cedes: the
    hero (and the band derived from it) is stripped, and the page renders as a
    shift without a statistic rather than a shift that says one thing twice.

    Phase 8 now avoids picking such heroes at all, so on a fresh run this is a
    no-op. It exists because --export-only republishes persisted picks without
    re-running phase 8, and a pick made before the avoidance landed (all 32
    subtitle echoes on the 2026-08-19 live map) must not survive an export.
    """
    heroes_dropped: list[str] = []
    bands_dropped: list[str] = []

    for index, shift in enumerate(key_trends):
        hero = shift.get('hero_stat')
        if not isinstance(hero, dict) or not hero.get('value'):
            continue
        if figure_echoes(hero.get('value'),
                         [('name', shift.get('name')),
                          ('subtitle', shift.get('subtitle'))]):
            shift['hero_stat'] = None
            shift['modules'] = [m for m in shift.get('modules') or []
                                if not (isinstance(m, dict) and m.get('type') == 'stat_band')]
            heroes_dropped.append(shift.get('slug') or f'key_trends[{index}]')

    for index, sub in enumerate(sub_trends):
        kept = []
        for module in sub.get('modules') or []:
            if (isinstance(module, dict) and module.get('type') == 'stat_band'
                    and (module.get('data') or {}).get('value')
                    and figure_echoes(module['data'].get('value'),
                                      [('name', sub.get('name')),
                                       ('subtitle', sub.get('subtitle')),
                                       ('description', sub.get('description'))])):
                bands_dropped.append(sub.get('slug') or f'sub_trends[{index}]')
                continue
            kept.append(module)
        sub['modules'] = kept

    return {'shift_heroes_dropped': heroes_dropped, 'sub_bands_dropped': bands_dropped}


def _write_map_document(conn, out):
    """Validate and atomically promote a candidate, rotating the last good map."""
    require_valid_map(out)
    encoded = json.dumps(out, default=str)  # Postgres date/datetime → ISO string
    conn.execute("""
        INSERT INTO documents (key, body, updated_at)
        SELECT 'map:previous', body, updated_at FROM documents WHERE key = 'map'
        ON CONFLICT (key) DO UPDATE SET
          body = EXCLUDED.body,
          updated_at = EXCLUDED.updated_at
    """)
    conn.execute("""INSERT INTO documents (key, body) VALUES ('map', %s::jsonb)
        ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
        (encoded,))
    _publish_shift_refs(conn, out)
    # Art is stamped and pruned inside the SAME transaction as the document that
    # names it, which is what makes "the art goes live with the map" true rather
    # than nearly true. Nothing links to art but this document, so a row it no
    # longer names is a row nothing can reach.
    live = {('key_trend', str(shift.get('slug') or ''))
            for shift in out.get('key_trends') or []}
    live |= {('sub_trend', str(sub.get('slug') or ''))
             for sub in out.get('sub_trends') or []}
    pruned = publish_art(conn, live - {('key_trend', ''), ('sub_trend', '')})
    if pruned:
        print(f'  ⚠  {pruned} art brief(s) pruned for shifts no longer published')
    conn.commit()


def _publish_shift_refs(conn, out: dict) -> None:
    """Record the identity of every shift this document publishes.

    `shift_refs` is what an innovation's mapping points at, and it exists because
    `domain_key_trends.id` cannot be pointed at: `reset_v2_tables` TRUNCATEs the
    v2 taxonomy with RESTART IDENTITY on every run, so those keys are recycled
    weekly. The durable identity is the URL slug — the same key
    `shift_module_overrides` uses, and for the same reason.

    A shift that leaves the map keeps its row with a now-stale
    `last_published_at`, so a link survives a shift being renamed and renamed
    back, and that staleness is what the warning below detects. Runs in the same
    transaction as the document promotion above: the identities and the document
    they came from must not be able to disagree.

    Rows used to be upserted and *never* deleted, which meant the table only
    grew: 676 rows describing 306 published shifts, 370 of them stale. The
    reconciliation below keeps the property that matters — a ref anything points
    at is immortal — and drops the rest, which carry no information beyond "this
    slug existed once" and are read by nothing.
    """
    rows = [
        ('key_trend', kt.get('slug'), kt.get('domain_id'), kt.get('name'))
        for kt in out.get('key_trends') or []
    ] + [
        ('sub_trend', st.get('slug'), st.get('domain_id'), st.get('name'))
        for st in out.get('sub_trends') or []
    ]
    rows = [r for r in rows if r[1]]
    if not rows:
        return

    scopes, slugs, domains, titles = (list(column) for column in zip(*rows))
    # statement_timestamp(), not now() and not clock_timestamp(). now() is the
    # *transaction* timestamp, so two publications sharing a transaction would
    # each look current to the other and the staleness check below would find
    # nothing. clock_timestamp() is volatile and can be re-evaluated per row,
    # which would spread this publication's shifts across several stamps.
    # statement_timestamp() is fixed for this one statement and advances for the
    # next — exactly one stamp per publication.
    conn.execute("""
        INSERT INTO shift_refs (scope, slug, domain_id, title, last_published_at)
        SELECT scope, slug, domain_id, title, statement_timestamp()
          FROM unnest(%s::text[], %s::text[], %s::text[], %s::text[])
               AS t(scope, slug, domain_id, title)
        ON CONFLICT (scope, slug) DO UPDATE SET
          domain_id = EXCLUDED.domain_id,
          title = EXCLUDED.title,
          last_published_at = EXCLUDED.last_published_at
    """, (scopes, slugs, domains, titles))
    print(f'  ✓  {len(rows)} shift identities published.')

    # Reconcile: drop refs this publication did not carry AND that nothing
    # points at.
    #
    # `NOT EXISTS` covers disabled links too, not just enabled ones. A disabled
    # auto link is an editor's veto, and the tombstone is what stops the next
    # classifier sweep resurrecting it — deleting its ref would cascade the
    # tombstone away and quietly overturn the veto. The FK is ON DELETE CASCADE,
    # so this is not theoretical.
    #
    # No grace window. A stale ref with no link carries nothing a grace window
    # could protect: `classify` only considers refs from the latest publication,
    # `first_seen_at` is written and read by nobody, and if the slug comes back
    # the upsert above simply recreates the row.
    pruned = conn.execute("""
        DELETE FROM shift_refs sr
         WHERE sr.last_published_at IS DISTINCT FROM
               (SELECT max(last_published_at) FROM shift_refs)
           AND NOT EXISTS (SELECT 1 FROM innovation_shift_links l
                            WHERE l.shift_ref_id = sr.id)
    """).rowcount
    if pruned:
        print(f'  ✓  {pruned} stale shift identity/identities pruned '
              f'(nothing linked to them).')

    # A curated innovation whose shift was renamed is the one failure here that
    # is otherwise silent: the link is still in the DB, the page just stops
    # showing it. Reported the same way an unmatched module override is.
    #
    # "Not in this publication" is `last_published_at` older than the newest one
    # in the table — which is the stamp the statement above just wrote.
    stranded = conn.execute("""
        SELECT sr.scope, sr.slug, count(*) AS links
          FROM innovation_shift_links l
          JOIN shift_refs sr ON sr.id = l.shift_ref_id
         WHERE l.enabled
           AND (sr.last_published_at IS NULL
                OR sr.last_published_at < (SELECT max(last_published_at) FROM shift_refs))
         GROUP BY sr.scope, sr.slug
         ORDER BY sr.scope, sr.slug
    """).fetchall()
    if stranded:
        names = [f'{r["scope"]}:{r["slug"]}' for r in stranded]
        total = sum(r['links'] for r in stranded)
        print(f'  ⚠  {total} innovation link(s) point at {len(names)} shift(s) not in '
              f'this publication (renamed?): {", ".join(names[:5])}'
              + (' …' if len(names) > 5 else ''))


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
