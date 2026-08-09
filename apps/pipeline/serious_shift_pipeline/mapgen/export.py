"""Assemble the single JSON document the frontend reads.

Pinned by tests/test_map_export_golden.py: this is the one output whose exact
shape the UI depends on.
"""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlparse

from ..core.text import url_slug as slugify
from .config import DOMAINS, MODULE_ORDER
from .modules import conform_modules, scrub_module_tree
from .validation import require_valid_map


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
    kt_slug_by_id: dict = {}
    _seen_kt: dict = {}
    for kt in kt_rows_all:
        base = slugify(kt['name'])
        n = _seen_kt.get(base, 0) + 1
        _seen_kt[base] = n
        kt_slug_by_id[kt['id']] = base if n == 1 else f'{base}-{n}'
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
    _seen_st: dict = {}
    for st in st_rows_all:
        # A sub-shift slug is only unique beneath its parent, so the override key
        # is the two-segment URL path. Same stable disambiguation as above.
        base = slugify(st['name'])
        n = _seen_st.get((st['kt_id'], base), 0) + 1
        _seen_st[(st['kt_id'], base)] = n
        url_slug = f'{kt_slug_by_id.get(st["kt_id"], "")}/{base if n == 1 else f"{base}-{n}"}'
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
                'thinker_credibility': round(r['credibility_score'] or 50.0, 1),
                'source_title':      r['source_title'] or '',
                'source_date':       r['date_published'] or '',
                'source_url':        _http_url(r['source_url']),
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
            'FROM thinkers ORDER BY credibility_score DESC NULLS LAST, id'
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
        FROM domain_links ORDER BY strength DESC, id
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
    claim_to_thinker = {str(c['id']).replace('c_', ''): c['thinker'] for c in claims_j}
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
