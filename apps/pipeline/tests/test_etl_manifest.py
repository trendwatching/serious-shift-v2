"""
Regression test for the ETL's most expensive failure mode.

`scrape_sources` is the manifest the weekly cron reads to know what to fetch.
It is seeded by the migration, it does not exist in the legacy SQLite, and it
references `thinkers(id)` — so `TRUNCATE thinkers … CASCADE`, which the
documented import runs, used to delete all 120 rows with nothing to put them
back. The system stayed up, the cron kept running, and it fetched nothing,
permanently and without an error. Nothing caught it because nothing looked.

The test builds a throwaway SQLite that mimics the legacy shape (thinkers with
*different* ids to the seed, so the re-key is actually exercised) and asserts
the manifest is intact afterwards.

Gated like the other destructive integration tests: DATABASE_URL plus an
explicit SS_ALLOW_DESTRUCTIVE_TESTS opt-in, because it truncates core tables.
"""
import importlib.util
import os
import sqlite3

import pytest

from serious_shift_pipeline.core import db
from serious_shift_pipeline.paths import packages_dir

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
    ),
    pytest.mark.skipif(
        os.environ.get("SS_ALLOW_DESTRUCTIVE_TESTS", "") not in ("1", "true", "yes"),
        reason="truncates core tables; set SS_ALLOW_DESTRUCTIVE_TESTS=1 on a disposable database",
    ),
]


def _load_etl():
    """Import packages/db/etl/sqlite_to_postgres.py by path.

    It lives outside the installed package (it is an operational script, not
    pipeline code) so there is no module path to import it by.
    """
    path = packages_dir() / "db" / "etl" / "sqlite_to_postgres.py"
    spec = importlib.util.spec_from_file_location("_ss_etl", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_sqlite(tmp_path):
    """A minimal stand-in for serious-shift.db.

    Only `thinkers` is populated, and with ids that do not line up with the
    migration's seed — that is the whole point. If the restore re-keyed on id
    instead of name it would pass against a matching id space and fail in
    production.
    """
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE thinkers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            credibility_score REAL DEFAULT 50.0,
            entity_kind TEXT DEFAULT 'person',
            discovered INTEGER DEFAULT 0
        );
        CREATE TABLE sources (id INTEGER PRIMARY KEY, thinker_id INTEGER, title TEXT);
        CREATE TABLE claims (id INTEGER PRIMARY KEY, thinker_id INTEGER, duplicate_of INTEGER);
        """
    )
    # Deliberately high, non-contiguous ids: nothing here overlaps the seed's 1..87.
    conn.executemany(
        "INSERT INTO thinkers (id, name) VALUES (?, ?)",
        [(9001, "Sam Altman"), (9002, "Andrej Karpathy"), (9003, "Nobody In The Seed")],
    )
    conn.commit()
    conn.close()
    return path


def _manifest(conn):
    """(thinker_name, platform, url, params) for every manifest row."""
    return {
        (r["name"], r["platform"], r["url"], str(r["params"]))
        for r in db.query(
            conn,
            """SELECT t.name, s.platform, s.url, s.params
               FROM scrape_sources s JOIN thinkers t ON t.id = s.thinker_id""",
        )
    }


def test_import_preserves_the_scrape_manifest(legacy_sqlite):
    etl = _load_etl()

    with db.connect() as conn:
        before = _manifest(conn)
    assert before, (
        "no seeded scrape_sources to protect — apply packages/db migrations first"
    )

    etl.main_with_args(
        sqlite=str(legacy_sqlite),
        database_url=db.get_dsn(),
        truncate=True,
    )

    with db.connect() as conn:
        after = _manifest(conn)
        dangling = db.query_one(
            conn,
            """SELECT COUNT(*) AS n FROM scrape_sources s
               LEFT JOIN thinkers t ON t.id = s.thinker_id
               WHERE t.id IS NULL""",
        )["n"]

    assert after == before, (
        "the import changed the scrape manifest. Lost: "
        f"{sorted(before - after)}; gained: {sorted(after - before)}"
    )
    assert dangling == 0, f"{dangling} manifest rows point at a thinker that no longer exists"


def test_import_is_idempotent(legacy_sqlite):
    """A second import must not duplicate the manifest it just restored."""
    etl = _load_etl()
    for _ in range(2):
        etl.main_with_args(
            sqlite=str(legacy_sqlite), database_url=db.get_dsn(), truncate=True
        )

    with db.connect() as conn:
        rows = db.query_one(conn, "SELECT COUNT(*) AS n FROM scrape_sources")["n"]
        distinct = db.query_one(
            conn,
            """SELECT COUNT(*) AS n FROM (
                   SELECT DISTINCT thinker_id, platform, method, url, rss,
                          channel_url, handle, note, params
                   FROM scrape_sources) d""",
        )["n"]

    assert rows == distinct, f"{rows - distinct} duplicate manifest rows after a re-import"
