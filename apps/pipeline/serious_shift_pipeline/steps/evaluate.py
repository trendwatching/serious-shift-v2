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

# Predictions evaluated as of the current cycle (prediction_id -> (status, notes)).
EVALUATIONS: dict[str, tuple[str, str]] = {
    "P014": ("false", 'Reality: Google ~25%, Microsoft ~30% AI-generated code. Far from "essentially all."'),
    "P013": ("false", "No AI system matches Nobel-level performance across biology, math, engineering simultaneously by end 2026."),
    "P025": ("partially_true", "Entry-level hiring in tech/consulting declined measurably in 2025-2026; major firms cite AI. But not dramatic enough to call fully true yet."),
    "P054": ("partially_true", "Call center automation accelerated significantly. Software engineering augmented but not displaced. Partially correct on sequencing."),
    "P028": ("partially_true", 'AI agents improved significantly (Claude Code, Codex) but still require heavy oversight for multi-step tasks. "Slop" is harsh but directionally correct.'),
    "P046": ("partially_true", "P&G study replicated. Additional evidence from consulting firms. But not yet broadly confirmed across industries."),
    "P057": ("partially_true", "Multi-agent orchestration emerging (Claude Code, Copilot agents) but still early. Shift visible but not complete."),
    "P044": ("partially_true", "GPT-5 and Claude 4 showed smaller gains than GPT-3->4 leap. Scaling continues but with diminishing capability jumps per compute dollar. LeCun directionally correct."),
}

_ACCURACY = {"true": 1.0, "partially_true": 0.5, "false": 0.0, "expired": 0.3}


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


def run(conn) -> dict[str, dict]:
    """Apply EVALUATIONS and recompute every thinker's credibility. Returns
    {thinker_name: score dict}."""
    for pid, (status, notes) in EVALUATIONS.items():
        db.execute(
            conn,
            "UPDATE predictions SET status = %s, evaluation_notes = %s WHERE prediction_id = %s",
            (status, notes, pid),
        )

    scores: dict[str, dict] = {}
    for t in db.query(conn, "SELECT id, name FROM thinkers"):
        preds = db.query(
            conn,
            "SELECT status, consensus_alignment FROM predictions WHERE thinker_id = %s",
            (t["id"],),
        )
        s = score_thinker([(p["status"], p["consensus_alignment"]) for p in preds])
        db.execute(
            conn,
            "UPDATE thinkers SET credibility_score = %s, prediction_accuracy = %s, outlier_factor = %s WHERE id = %s",
            (s["credibility"], s["accuracy"], s["outlier"], t["id"]),
        )
        scores[t["name"]] = s
    return scores


def main():
    with db.connect() as conn:
        scores = run(conn)
    for name, s in sorted(scores.items(), key=lambda kv: -kv[1]["credibility"]):
        print(f"  {name}: {s['credibility']}/100 (acc={s['accuracy']}, "
              f"outlier={s['outlier']}, {s['evaluable']}/{s['total']} eval)")


if __name__ == "__main__":
    main()
