"""Connection + slug-uniqueness helpers shared by the phases."""
from __future__ import annotations

from ..core import db


def get_conn():
    return db.raw_connect()




def _slugger():
    """A fresh unique-slug maker: suffixes -2, -3, … on collision within a phase."""
    used: set = set()

    def make(base: str) -> str:
        s, n = base, 2
        while s in used:
            s = f'{base}-{n}'; n += 1
        used.add(s)
        return s
    return make

# ---------------------------------------------------------------------------

DROP_V2_ORDER = [
    'domain_synthesis_insight_claims',
    'domain_synthesis_insights',
    'domain_links',
    'domain_sub_trend_claims',
    'domain_sub_trends',
    'domain_key_trends',
    'domain_flows',
    'domains_v2',
]


def reset_v2_tables(conn):
    """Clear all v2 tables before a rebuild. The schema itself is owned by the
    packages/db migrations, so we TRUNCATE rather than drop/recreate."""
    conn.execute('TRUNCATE ' + ', '.join(DROP_V2_ORDER) + ' RESTART IDENTITY CASCADE')
    conn.commit()
    print('  ✓  v2 tables reset.')
