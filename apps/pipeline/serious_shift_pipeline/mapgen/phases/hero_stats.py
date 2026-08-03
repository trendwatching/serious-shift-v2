"""Phase 8 — pick each Key Trend's hero statistic."""
from __future__ import annotations

import json


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


def select_hero_stat(conn, kt_id) -> dict | None:
    """Return the single strongest dated, attributable statistic among a Key
    Trend's claims, as {value, thinker, source, year} — or None if it has none.
    `source` is the rendered credit line, not the raw article title.
    Ranked by claim weight × thinker credibility; statistics come from the
    `claims.statistic` / `claims.has_statistic` fields (process_raw extracts them)."""
    row = conn.execute("""
        SELECT c.statistic, c.claim_text, t.name AS thinker,
               s.title AS source, s.date_published AS pub_date, s.url
        FROM domain_sub_trends st
        JOIN domain_sub_trend_claims stc ON stc.sub_trend_id = st.id
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        LEFT JOIN sources s ON s.id = c.source_id
        WHERE st.kt_id = %s
          AND c.has_statistic IS TRUE
          AND c.statistic IS NOT NULL
          AND s.url ~* '^https?://'
          AND c.duplicate_of IS NULL
        ORDER BY COALESCE(c.claim_weight,0)
                 * (GREATEST(COALESCE(t.credibility_score,50.0), 30.0) / 100.0) DESC,
                 c.id
        LIMIT 1
    """, (kt_id,)).fetchone()
    if not row:
        return None
    year = str(row['pub_date'])[:4] if row['pub_date'] else ''
    return {
        'value':   row['statistic'],
        'text':    row['claim_text'] or '',
        'thinker': row['thinker'] or '',
        'source':  _attribution(row['thinker'], row['source'], year),
        'year':    year,
        'url':     row['url'] or '',
    }


def phase8_hero_stats(conn):
    """Persist one hero statistic per Key Trend to domain_key_trends.hero_stat."""
    print('\nPhase 8 — Selecting hero statistics per Key Trend (SQL, no API)…')
    kt_ids = [r['id'] for r in conn.execute('SELECT id FROM domain_key_trends').fetchall()]
    n = 0
    for kt_id in kt_ids:
        hero = select_hero_stat(conn, kt_id)
        conn.execute('UPDATE domain_key_trends SET hero_stat=%s::jsonb WHERE id=%s',
                     (json.dumps(hero) if hero else None, kt_id))
        if hero:
            n += 1
    conn.commit()
    print(f'  ✓  {n}/{len(kt_ids)} Key Trends have a hero statistic.')
