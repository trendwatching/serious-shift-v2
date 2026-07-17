"""
Server-free validation of every read query.

Drives each function in queries.py through a capturing fake DB layer, collects
the emitted SQL, and asserts it parses as valid Postgres (sqlglot). This catches
dialect mistakes (bad placeholders, sqlite-isms) without a running database;
the live behaviour is covered by test_queries_integration.py in CI.
"""
import sqlglot

from serious_shift_pipeline.core import db
from serious_shift_pipeline.tools import queries


class _Capture:
    """Records SQL passed to db.* and returns benign stand-in rows."""

    def __init__(self):
        self.sqls: list[str] = []

    def query(self, conn, sql, params=None):
        self.sqls.append(sql)
        return []

    def query_one(self, conn, sql, params=None):
        self.sqls.append(sql)
        # Provide the keys the query functions read off single-row results.
        return {"id": 1, "n": 0, "name": "x"}


def _drive_all(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(db, "query", cap.query)
    monkeypatch.setattr(db, "query_one", cap.query_one)

    conn = object()  # never touched — db.* is faked
    queries.get_thinker_profile(conn, "altman")
    queries.get_claims_by_domain(conn, "labor", "signal")
    queries.get_credibility_leaderboard(conn)
    queries.get_predictions_evaluable_by(conn, "2026-06-04")
    queries.get_contrarian_signals(conn)
    queries.get_consensus_claims(conn)
    queries.get_thinker_evolution(conn, "hassabis")
    queries.get_concept_deep_dive(conn, "abundance")
    queries.get_tension_breakdown(conn, "inequality")
    queries.get_keynote_material(conn, domain="economy")
    queries.get_keynote_material(conn, domain=None)
    queries.get_claims_since(conn, "2026-01-01")
    queries.get_prediction_accuracy_by_domain(conn, "labor")
    queries.get_prediction_accuracy_by_domain(conn, None)
    queries.search_claims(conn, "agents")
    queries.get_industry_relevant_claims(conn, "healthcare")
    queries.get_db_stats(conn)
    return cap.sqls


def test_every_query_is_valid_postgres(monkeypatch):
    sqls = _drive_all(monkeypatch)
    assert len(sqls) >= 18, f"expected to capture all queries, got {len(sqls)}"
    for sql in sqls:
        # Raises on invalid Postgres syntax.
        sqlglot.parse_one(sql, dialect="postgres")


def test_no_sqlite_paramstyle_leaks(monkeypatch):
    sqls = _drive_all(monkeypatch)
    for sql in sqls:
        assert "?" not in sql, f"SQLite '?' placeholder leaked into: {sql[:80]}"
