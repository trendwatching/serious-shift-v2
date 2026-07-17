"""
Live integration test against Postgres. Skipped unless DATABASE_URL is set
(CI sets it after applying packages/db migrations; locally, run Docker Postgres
from packages/db). Seeds a minimal graph and exercises representative queries.
"""
import os

import pytest

from serious_shift_pipeline.core import db
from serious_shift_pipeline.tools import queries

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture
def seeded():
    with db.connect() as conn:
        # Clean slate for the rows we touch (CASCADE handles dependents).
        db.execute(conn, "TRUNCATE thinkers, sources, claims, predictions RESTART IDENTITY CASCADE")
        tid = db.insert_returning_id(
            conn,
            "INSERT INTO thinkers (name, credibility_score) VALUES (%s, %s) RETURNING id",
            ("Test Thinker", 72.5),
        )
        sid = db.insert_returning_id(
            conn,
            "INSERT INTO sources (thinker_id, title, date_published) VALUES (%s, %s, %s) RETURNING id",
            (tid, "Test Source", "2026-05-01"),
        )
        db.execute(
            conn,
            """INSERT INTO claims (source_id, thinker_id, claim_text, domain, signal_strength, claim_weight)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (sid, tid, "Agents will reshape retail by 2027", "consumer_behavior", "strong_signal", 0.9),
        )
        db.execute(
            conn,
            """INSERT INTO predictions (prediction_id, thinker_id, claim_text, status, consensus_alignment)
               VALUES (%s, %s, %s, %s, %s)""",
            ("P999", tid, "AGI by 2030", "pending", 0.2),
        )
        yield conn


def test_profile_and_counts(seeded):
    prof = queries.get_thinker_profile(seeded, "Test")
    assert prof and prof["thinker"]["name"] == "Test Thinker"
    assert prof["active_claims"] == 1
    assert len(prof["predictions"]) == 1


def test_domain_and_search(seeded):
    rows = queries.get_claims_by_domain(seeded, "consumer_behavior", "signal")
    assert len(rows) == 1 and rows[0]["thinker"] == "Test Thinker"
    assert queries.search_claims(seeded, "retail")
    assert queries.get_industry_relevant_claims(seeded, "retail")


def test_contrarian_and_stats(seeded):
    assert queries.get_contrarian_signals(seeded)            # consensus 0.2 <= 0.25
    stats = queries.get_db_stats(seeded)
    assert stats["claims_total"] == 1 and stats["claims_active"] == 1
