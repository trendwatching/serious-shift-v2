"""Server-free Postgres-SQL validation for the keynote generator's queries.
Drives the per-Key-Trend evidence + intro + load queries with a capturing fake
db and parses every emitted SQL as Postgres."""
import sqlglot

from serious_shift_pipeline.core import db
from serious_shift_pipeline.steps import generate_keynote as gk


class _Capture:
    def __init__(self):
        self.sqls = []

    def query(self, conn, sql, params=None):
        self.sqls.append(sql)
        return []

    def query_one(self, conn, sql, params=None):
        self.sqls.append(sql)
        return {"thinkers": 10, "sources": 200, "claims": 1700, "predictions": 60}


def test_keynote_queries_are_valid_postgres(monkeypatch):
    cap = _Capture()
    monkeypatch.setattr(db, "query", cap.query)
    monkeypatch.setattr(db, "query_one", cap.query_one)

    gk.load_key_trends(object())
    gk.kt_evidence(object(), 1)
    gk._intro(object())

    assert cap.sqls, "no SQL captured"
    for sql in cap.sqls:
        sqlglot.parse_one(sql, dialect="postgres")
        assert "?" not in sql
