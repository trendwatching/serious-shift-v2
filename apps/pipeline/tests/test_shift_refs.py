"""
The durable half of the innovation↔shift mapping.

An innovation is linked to a shift by a foreign key into `shift_refs`, not into
`domain_key_trends`, because `reset_v2_tables` TRUNCATEs the v2 taxonomy with
RESTART IDENTITY on every synthesize run — a link keyed on a recycled primary key
would be cascade-deleted the first Monday after it was made, and nothing would
report it.

Two things therefore have to hold, and both are tested here: the new tables stay
out of the weekly truncate, and publication records the identity of every shift it
publishes so links have something to point at.
"""
from __future__ import annotations

import os

import pytest

from serious_shift_pipeline.mapgen.dbutil import DROP_V2_ORDER
from serious_shift_pipeline.mapgen.export import _publish_shift_refs

# Every table the mapping depends on. If one of these is ever added to the
# weekly TRUNCATE, curated links silently vanish once a week.
DURABLE_TABLES = [
    "innovations",
    "innovation_tags",
    "innovation_tag_links",
    "innovation_assets",
    "innovation_shift_links",
    "shift_refs",
]


def test_the_mapping_tables_are_not_in_the_weekly_truncate():
    clashes = sorted(set(DURABLE_TABLES) & set(DROP_V2_ORDER))
    assert not clashes, (
        f"{clashes} would be TRUNCATEd on every synthesize run, deleting curated "
        "innovation links weekly"
    )
    # The one it *is* safe to point at, restated so the reason stays visible.
    assert "domain_key_trends" in DROP_V2_ORDER


DOCUMENT = {
    "key_trends": [
        {"slug": "trust-machines", "domain_id": "society", "name": "Trust Machines"},
        {"slug": "capability-arrives", "domain_id": "work", "name": "Capability Arrives"},
        # No slug: unaddressable, so it cannot be linked to and is skipped.
        {"slug": "", "domain_id": "society", "name": "Nameless"},
    ],
    "sub_trends": [
        {
            "slug": "trust-machines/proof-of-human",
            "domain_id": "society",
            "name": "Proof of Human",
        }
    ],
}


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
def test_publication_records_every_addressable_shift_identity():
    """Rolled back, so this is safe against any database with the schema."""
    from serious_shift_pipeline.core import db

    conn = db.raw_connect()
    try:
        _publish_shift_refs(conn, DOCUMENT)
        rows = conn.execute(
            "SELECT scope, slug, domain_id, title, last_published_at FROM shift_refs"
            " WHERE slug IN ('trust-machines','capability-arrives','trust-machines/proof-of-human','')"
            " ORDER BY scope, slug"
        ).fetchall()
        got = [(r["scope"], r["slug"]) for r in rows]
        assert got == [
            ("key_trend", "capability-arrives"),
            ("key_trend", "trust-machines"),
            ("sub_trend", "trust-machines/proof-of-human"),
        ], "a sub-shift keeps its parent/child slug; a slugless shift is skipped"
        assert all(r["last_published_at"] is not None for r in rows)
        assert next(r for r in rows if r["slug"] == "trust-machines")["title"] == "Trust Machines"

        # Publishing again is an upsert, not a duplicate — the identity is
        # (scope, slug), which is what makes a link survive the rebuild.
        _publish_shift_refs(conn, DOCUMENT)
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM shift_refs WHERE slug = 'trust-machines'"
            ).fetchone()["n"]
            == 1
        )
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
def test_a_link_to_a_renamed_shift_is_reported(capsys):
    """The silent failure: the shift gets renamed, the link stays valid, and the
    page just stops showing the innovation. Publication has to say so."""
    from serious_shift_pipeline.core import db

    conn = db.raw_connect()
    try:
        _publish_shift_refs(conn, DOCUMENT)
        ref_id = conn.execute(
            "SELECT id FROM shift_refs WHERE scope='key_trend' AND slug='trust-machines'"
        ).fetchone()["id"]
        innovation_id = conn.execute(
            """INSERT INTO innovations (source_innovation_id, article_url, title, payload)
               VALUES (-1, 'https://example.com/x', 'An example', '{}'::jsonb)
               ON CONFLICT (source_innovation_id) DO UPDATE SET title = EXCLUDED.title
               RETURNING id"""
        ).fetchone()["id"]
        conn.execute(
            """INSERT INTO innovation_shift_links (innovation_id, shift_ref_id, source)
               VALUES (%s, %s, 'editor') ON CONFLICT DO NOTHING""",
            (innovation_id, ref_id),
        )

        # The next publication drops that shift — as a rename does, since the slug
        # is the identity.
        renamed = {
            "key_trends": [
                {"slug": "trust-machines-v2", "domain_id": "society", "name": "Trust Machines"}
            ],
            "sub_trends": [],
        }
        capsys.readouterr()
        _publish_shift_refs(conn, renamed)
        out = capsys.readouterr().out
        assert "innovation link(s) point at" in out
        assert "key_trend:trust-machines" in out
    finally:
        conn.rollback()
        conn.close()
