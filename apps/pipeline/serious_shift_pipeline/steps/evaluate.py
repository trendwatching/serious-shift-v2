"""
Evaluate predictions and recompute credibility scores (Postgres writer).

Converted from the legacy evaluate_predictions.py:
  * `sqlite3` + `?`            → `db.connect()` + `%s`
  * the Obsidian-markdown sync step (Step 3) is dropped — the vault is no
    longer the front end; the database is the source of truth.

The credibility formula is extracted into `score_thinker()` as a pure function
so it is unit-tested without a database (see tests/test_credibility.py).
"""
from __future__ import annotations

from ..core import db

_ACCURACY = {"true": 1.0, "partially_true": 0.5, "false": 0.0, "expired": 0.3}

#: Ceiling for the source-authority fallback. INVARIANT: an entity with no
#: evaluated predictions must never outrank the band where named people sit
#: (~50-54 while accuracy defaults to 0.5). Before this cap, `authority*100`
#: put anonymous arXiv co-authors and org accounts at 60-69 — above every
#: named thinker on the platform — and the ranking SQL dutifully preferred
#: their claims for hero statistics.
_ENTITY_FALLBACK_CAP = 45.0


def score_thinker(predictions: list[tuple[str, float | None]]) -> dict:
    """Compute credibility for one thinker from their predictions.

    `predictions` is a list of (status, consensus_alignment). Formula:
      accuracy = mean(status->score) over evaluable predictions (else 0.5)
      outlier  = 0.5 + (avg_consensus * 0.5)
      credibility = (accuracy*0.85 + outlier*0.15) * 100
    """
    total = len(predictions)
    evaluable = [(s, c) for s, c in predictions if s != "pending"]

    if evaluable:
        accuracy = sum(_ACCURACY.get(s, 0.5) for s, _ in evaluable) / len(evaluable)
    else:
        accuracy = 0.5

    avg_consensus = (sum((c or 0.0) for _, c in predictions) / total) if total else 0.5
    outlier = 0.5 + (avg_consensus * 0.5)
    credibility = ((accuracy * 0.85) + (outlier * 0.15)) * 100

    return {
        "credibility": round(credibility, 1),
        "accuracy": round(accuracy, 2),
        "outlier": round(outlier, 2),
        "total": total,
        "evaluable": len(evaluable),
    }


def evaluable_backlog(conn) -> dict:
    """Predictions whose evaluation date has passed but which are still pending.

    Nothing in the pipeline resolves a prediction. There was a hard-coded table
    of eight hand-written verdicts here; every id in it (P013-P057) was absent
    from the database, which starts at P070, so it updated zero rows on every
    run since. Removing it does not change behaviour — it just stops the step
    from looking like it evaluates something.

    The consequence is worth stating plainly, because it is invisible from the
    outside: `accuracy` defaults to 0.5 for every thinker, and accuracy carries
    85% of the credibility weight, so credibility currently varies only through
    the 15% outlier term. Ranking runs on a fraction of its intended signal
    until predictions are actually resolved — by a judge model, or by a human
    review surface writing `status` back.
    """
    return db.query_one(conn, """
        SELECT COUNT(*) FILTER (WHERE status = 'pending'
                                  AND evaluation_date <= current_date) AS due,
               COUNT(*) FILTER (WHERE status <> 'pending')             AS resolved,
               COUNT(*)                                                AS total
        FROM predictions""") or {"due": 0, "resolved": 0, "total": 0}


def run(conn) -> dict[str, dict]:
    """Recompute every thinker's credibility from whatever is resolved.
    Returns {thinker_name: score dict}."""
    # Mean source authority per entity — the reputability signal for entities
    # that have no evaluable predictions (papers, orgs, labs, discovered authors).
    authority_by_id = {
        r["thinker_id"]: r["a"]
        for r in db.query(conn, """
            SELECT thinker_id, AVG(authority) AS a
            FROM sources WHERE authority IS NOT NULL GROUP BY thinker_id""")
    }

    scores: dict[str, dict] = {}
    for t in db.query(conn, "SELECT id, name FROM thinkers"):
        preds = db.query(
            conn,
            "SELECT status, consensus_alignment FROM predictions WHERE thinker_id = %s",
            (t["id"],),
        )
        s = score_thinker([(p["status"], p["consensus_alignment"]) for p in preds])
        authority = authority_by_id.get(t["id"])

        # For entities with no evaluated predictions, a prediction-derived
        # credibility (~54) is meaningless — prefer the source-authority signal
        # when we have one so papers/orgs rank on merit relative to each other.
        # Scaled and capped below the person band (see _ENTITY_FALLBACK_CAP):
        # venue authority orders entities among themselves; it must never rank
        # an unevaluated byline above a named thinker with a track record.
        credibility = s["credibility"]
        if s["evaluable"] == 0 and authority is not None:
            credibility = round(min(_ENTITY_FALLBACK_CAP, float(authority) * 100.0 * 0.8), 1)

        db.execute(
            conn,
            """UPDATE thinkers SET credibility_score = %s, prediction_accuracy = %s,
                   outlier_factor = %s, authority_score = %s WHERE id = %s""",
            (credibility, s["accuracy"], s["outlier"],
             round(float(authority), 3) if authority is not None else None, t["id"]),
        )
        scores[t["name"]] = s
    return scores


def main():
    with db.connect() as conn:
        backlog = evaluable_backlog(conn)
        scores = run(conn)
    if backlog["due"]:
        print(f"  ⚠  {backlog['due']:,} predictions are past their evaluation date and "
              f"still pending ({backlog['resolved']:,}/{backlog['total']:,} resolved "
              f"overall). Credibility is running on the outlier term alone until "
              f"something resolves them.")
    for name, s in sorted(scores.items(), key=lambda kv: -kv[1]["credibility"]):
        print(f"  {name}: {s['credibility']}/100 (acc={s['accuracy']}, "
              f"outlier={s['outlier']}, {s['evaluable']}/{s['total']} eval)")


if __name__ == "__main__":
    main()
