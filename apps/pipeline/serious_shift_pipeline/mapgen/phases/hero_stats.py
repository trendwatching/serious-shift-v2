"""Phase 8 — pick each Key Trend's hero statistic.

Assignment is exclusive and topical. The previous version ran an independent
per-KT argmax over pools that (pre-2026-08-10) largely shared their contents,
so the domain's three strongest statistics became the hero of every shift they
leaked into — 51 shifts, ~6 distinct heroes, a teen-suicide figure fronting
ten pages including shopping and pricing. One claim now heroes exactly one
shift, and only when it shares vocabulary with the shift it fronts.
"""
from __future__ import annotations

import json

from ...core.matching import normalize
from ..modules import _short_figure, figure_echoes, stat_claim_key

#: Attributions render as a single small line under the statistic. A scraped
#: article title can be 200+ characters of pipe-separated newsletter sections,
#: which is not an attribution and swamps the band it sits in.
MAX_ATTRIBUTION = 90


def _attribution(thinker: str, title: str, year: str) -> str:
    """A short credit line for the stat band: who said it, and when.

    Prefers the named thinker over the source title. Titles are the fallback
    only, and are truncated — a roundup post's title is a table of contents,
    not a citation, and rendering it verbatim put a 200-character run of
    unrelated headlines under the hero figure on the live site.
    """
    who = (thinker or '').strip()
    if not who:
        who = (title or '').strip()
        if len(who) > MAX_ATTRIBUTION:
            who = who[:MAX_ATTRIBUTION].rsplit(' ', 1)[0].rstrip(' ,;:|-') + '…'
    return ', '.join(p for p in (who, year) if p)


def stat_matches_shift(kt_name: str | None, kt_subtitle: str | None,
                       stat_value: str | None, stat_text: str | None) -> bool:
    """The topical floor a hero statistic must clear to front a shift.

    At least one shared stemmed, non-stopword term between the shift's own
    framing and the statistic's text. Deliberately permissive — its job is to
    reject category errors (a suicide statistic on a shopping page), not to
    rank. `normalize` already drops domain-generic terms (ai, consumer, model…),
    so the shared term has to carry actual topic. The publication gate applies
    the same test (validation.py), so what this refuses to write, the gate
    would refuse to publish.
    """
    shift_terms = set(normalize(f'{kt_name or ""} {kt_subtitle or ""}'))
    stat_terms = set(normalize(f'{stat_value or ""} {stat_text or ""}'))
    return bool(shift_terms & stat_terms)


def _hero_candidates(conn) -> dict[int, list[dict]]:
    """Every (kt, statistic-claim) pairing, strongest first, one query."""
    rows = conn.execute("""
        SELECT DISTINCT ON (st.kt_id, c.id)
               st.kt_id, c.id AS claim_id, c.statistic, c.claim_text,
               t.name AS thinker, s.title AS source,
               -- A chased statistic fronts its shift with the ORIGIN's URL and
               -- date (claims.primary_source_id), not the newsletter that
               -- quoted it. Keying dedup on the primary URL also collapses two
               -- commentators quoting the same study into one hero.
               COALESCE(ps.date_published, s.date_published) AS pub_date,
               COALESCE(NULLIF(ps.url, ''), s.url) AS url,
               COALESCE(c.claim_weight, 0)
                 * (GREATEST(COALESCE(t.credibility_score, 50.0), 30.0) / 100.0)
                 AS score
        FROM domain_sub_trends st
        JOIN domain_sub_trend_claims stc ON stc.sub_trend_id = st.id
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        JOIN sources s  ON s.id = c.source_id
        LEFT JOIN sources ps ON ps.id = c.primary_source_id
                            AND ps.url ~* '^https?://'
        WHERE c.has_statistic IS TRUE
          AND c.statistic IS NOT NULL
          AND s.url ~* '^https?://'
          AND c.duplicate_of IS NULL
          -- An undated figure cannot front a page: the reader has no way to
          -- know if it is from last month or 2019. Same rule as the
          -- hero_stat_undated gate, so writer and gate cannot disagree.
          AND COALESCE(ps.date_published, s.date_published) IS NOT NULL
        ORDER BY st.kt_id, c.id
    """).fetchall()
    by_kt: dict[int, list[dict]] = {}
    for r in rows:
        by_kt.setdefault(r['kt_id'], []).append(dict(r))
    for candidates in by_kt.values():
        candidates.sort(key=lambda r: (-r['score'], r['claim_id']))
    return by_kt


def _as_hero(row: dict) -> dict:
    # No claim_id in the JSON: the publication gate re-derives provenance from
    # (value, url) against the document's own claims, so the same checks hold
    # on a served document where a DB identifier would never be available.
    year = str(row['pub_date'])[:4] if row['pub_date'] else ''
    return {
        'value':   row['statistic'],
        'text':    row['claim_text'] or '',
        'thinker': row['thinker'] or '',
        'source':  _attribution(row['thinker'], row['source'], year),
        'year':    year,
        'url':     row['url'] or '',
    }


def assign_heroes(kt_rows: list[dict],
                  by_kt: dict[int, list[dict]],
                  fronted: set[tuple[str, str]] | None = None) -> dict[int, dict | None]:
    """Greedy exclusive assignment: shifts with the fewest eligible candidates
    choose first, each claim heroes at most one shift, and a shift whose every
    candidate is either taken or off-topic gets None — no stat_band beats a
    recycled or unrelated one.

    Candidates are filtered to statistics that actually REDUCE to a display
    figure. `kt_modules` renders the band as `_short_figure(hero.value)` and
    drops the module when that returns None, so a hero picked from prose with no
    numeral in it satisfies this phase and then renders nothing: the 18 Aug 2026
    staging run reported 30/44 shifts with a hero and the gate found 16/44
    carrying a band, failing stat_coverage from the other side of the same
    exclusive assignment. A pick that cannot render is worse than no pick, since
    it also consumes the claim.

    `fronted` — the stat_claim_keys already carried by persisted sub-shift bands
    — is a PREFERENCE, not a filter. It was a hard exclusion, which inverted the
    gate: validation registers key shifts first and blames the SUB for
    re-fronting, so treating a child's band as senior prior art cost the parent
    its figure and left the collision in place anyway. Children's bands that
    still collide are ceded to their parent at export instead
    (`reconcile_fronted_stats`), which is the same parent-priority policy that
    remediated 2026-08-12 by hand.
    """
    fronted = fronted or set()
    eligible: dict[int, list[dict]] = {}
    for kt in kt_rows:
        rows = [
            row for row in by_kt.get(kt['id'], [])
            if _short_figure(row['statistic']) is not None
            and stat_matches_shift(kt['name'], kt['subtitle'],
                                   row['statistic'], row['claim_text'])
            # Never front a figure the shift's own fixed copy already states:
            # the subtitle is phase-3 prose no later pass can rewrite, so a
            # hero echoing it puts the same number on the page twice, forever.
            # The topicality test above wants VOCABULARY overlap; this rejects
            # only the FIGURE recurring — the two must never be merged.
            and not figure_echoes(row['statistic'],
                                  [('name', kt['name']),
                                   ('subtitle', kt['subtitle'])])
        ]
        # Stable partition, so strength order survives inside each half.
        rows.sort(key=lambda r: stat_claim_key(r['statistic'], r['url']) in fronted)
        eligible[kt['id']] = rows

    taken: set[int] = set()
    heroes: dict[int, dict | None] = {}
    for kt in sorted(kt_rows, key=lambda k: (len(eligible[k['id']]), k['id'])):
        pick = next((row for row in eligible[kt['id']]
                     if row['claim_id'] not in taken), None)
        heroes[kt['id']] = _as_hero(pick) if pick else None
        if pick:
            taken.add(pick['claim_id'])
    return heroes


def phase8_hero_stats(conn):
    """Persist one hero statistic per Key Trend to domain_key_trends.hero_stat."""
    print('\nPhase 8 — Selecting hero statistics per Key Trend (SQL, no API)…')
    kt_rows = [dict(r) for r in conn.execute(
        'SELECT id, name, subtitle FROM domain_key_trends').fetchall()]
    # Claims the children already front. Sub stat bands persist across targeted
    # regens, so they are prior art this assignment must not re-front.
    fronted = {
        stat_claim_key(r['value'], r['url'])
        for r in conn.execute("""
            SELECT m->'data'->>'value' AS value, m->'data'->>'url' AS url
            FROM domain_sub_trends, jsonb_array_elements(modules) m
            WHERE m->>'type' = 'stat_band'
              AND COALESCE(m->'data'->>'value', '') <> ''
        """).fetchall()
    }
    heroes = assign_heroes(kt_rows, _hero_candidates(conn), fronted)

    n = 0
    for kt in kt_rows:
        hero = heroes.get(kt['id'])
        conn.execute('UPDATE domain_key_trends SET hero_stat=%s::jsonb WHERE id=%s',
                     (json.dumps(hero) if hero else None, kt['id']))
        if hero:
            n += 1
    conn.commit()
    print(f'  ✓  {n}/{len(kt_rows)} Key Trends have a hero statistic '
          f'(exclusive, topical).')
