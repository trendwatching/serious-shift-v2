#!/usr/bin/env python3
"""Resolve banked predictions in two conservative passes.

For months steps/evaluate.py has stated plainly that nothing resolves a
prediction, so accuracy defaults to 0.5 for everyone and credibility — a
factor in claim routing and hero-stat ranking — is near-constant. This step
turns the 5,000+ banked predictions into the calibration signal they were
collected to be.

TRIAGE (once per prediction, cheap tier): classify resolvable / vague /
unfalsifiable; author neutral resolution criteria, a resolve_by date from the
stated timeframe, and search terms for retrieval. The unresolvable share is a
finding about the corpus, not a failure.

RESOLVE (weekly, due predictions only): retrieve corpus claims ingested AFTER
the prediction was made by full-text search, hand them to a judge that may
abstain, and apply only high-confidence verdicts that cite evidence ids.
Everything else stays pending. `status` is written under the existing enum
(true / partially_true / false / expired), with the audit trail on the row
(resolution_method, evidence_claim_ids, resolved_at, note).

The judge sees only our own ingested evidence — no live web, no model
memory-as-evidence (the prompt forbids it, and the evidence-id requirement
enforces it mechanically: ids must exist in the retrieved set).

Usage:
  python -m serious_shift_pipeline.steps.resolve_predictions [--triage-only|--resolve-only]
      [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date

from ..core import db, llm, observability
from ..core.config import SYNTHESIS_MODEL
from ..core.observability import CostTracker, ErrorLog, RunLog
from ..prompts.evaluation import resolve_prompt, triage_prompt

_USE_BATCH = os.environ.get("SS_DISABLE_BATCH", "") not in ("1", "true", "yes")

TRIAGE_VALID = {"resolvable", "vague", "unfalsifiable"}
VERDICT_VALID = {"true", "partially_true", "false", "expired", "insufficient"}
#: Verdicts that need cited evidence to be applied. "expired" may rest on the
#: absence of evidence after the deadline, so it is exempt — but still needs
#: high confidence and a non-empty evidence set to look at.
EVIDENCE_REQUIRED = {"true", "partially_true", "false"}

EVIDENCE_LIMIT = 12


def _parse_date(value) -> date | None:
    try:
        text = str(value or "").strip()[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
    except ValueError:
        pass
    return None


# ── triage ────────────────────────────────────────────────────────────────────

def triage(conn, cost_tracker: CostTracker, error_log: ErrorLog,
           limit: int, dry_run: bool) -> dict:
    rows = db.query(conn, """
        SELECT p.id, p.prediction_id, p.claim_text, p.timeframe,
               COALESCE(s.date_published, p.created_at::date) AS made_on
        FROM predictions p LEFT JOIN sources s ON s.id = p.source_id
        WHERE p.status = 'pending' AND p.triage_status IS NULL
        ORDER BY p.id LIMIT %s""", (limit,))
    stats = {"examined": len(rows), "resolvable": 0, "vague": 0,
             "unfalsifiable": 0, "failed": 0}
    print(f"Triage: {len(rows)} untriaged pending predictions")
    if not rows or dry_run:
        return stats

    today = date.today().isoformat()
    reqs = [llm.Req(user=triage_prompt(r["claim_text"], r["timeframe"] or "",
                                       str(r["made_on"] or ""), today),
                    max_tokens=500, custom_id=f"p{r['id']}")
            for r in rows]
    results = _run_reqs(reqs)

    for row in rows:
        text, usage = results.get(f"p{row['id']}", (None, {"error": "no result"}))
        if usage and not usage.get("error"):
            cost_tracker.add(usage, thinker_name="RESOLVE_TRIAGE")
        verdict = _parse(text, usage, error_log, "triage", row["prediction_id"])
        if verdict is None:
            stats["failed"] += 1
            continue
        kind = verdict.get("triage")
        if kind not in TRIAGE_VALID:
            stats["failed"] += 1
            continue
        resolve_by = _parse_date(verdict.get("resolve_by"))
        criteria = (verdict.get("resolution_criteria") or "").strip() or None
        terms = (verdict.get("search_terms") or "").strip() or None
        if kind == "resolvable" and not (resolve_by and criteria and terms):
            # A "resolvable" without the machinery to resolve it is vague.
            kind = "vague"
        stats[kind] += 1
        db.execute(conn, """UPDATE predictions SET triage_status = %s,
            resolution_criteria = %s, resolve_by = %s, search_terms = %s
            WHERE id = %s""",
            (kind, criteria, resolve_by, terms, row["id"]))
    conn.commit()
    return stats


# ── resolution ────────────────────────────────────────────────────────────────

def _evidence_for(conn, row: dict) -> list[dict]:
    """Corpus claims ingested after the prediction was made, matched on the
    triage-authored search terms. Plain-SQL retrieval — the judge never
    searches, it only reads what this returns."""
    terms = " OR ".join((row["search_terms"] or "").split()[:6])
    if not terms:
        return []
    return db.query(conn, """
        SELECT c.id, c.claim_text AS text, c.statistic,
               t.name AS author, s.title AS source,
               s.date_published AS date, COALESCE(ps.url, s.url) AS url
        FROM claims c
        JOIN sources s  ON s.id = c.source_id
        JOIN thinkers t ON t.id = c.thinker_id
        LEFT JOIN sources ps ON ps.id = c.primary_source_id
        WHERE c.duplicate_of IS NULL
          AND c.created_at > %s
          AND c.thinker_id IS DISTINCT FROM %s
          AND to_tsvector('english', c.claim_text || ' ' || COALESCE(c.statistic, ''))
              @@ websearch_to_tsquery('english', %s)
        ORDER BY s.date_published DESC NULLS LAST
        LIMIT %s""",
        (row["made_at"], row["thinker_id"], terms, EVIDENCE_LIMIT))


def resolve(conn, cost_tracker: CostTracker, error_log: ErrorLog,
            limit: int, dry_run: bool) -> dict:
    rows = db.query(conn, """
        SELECT p.id, p.prediction_id, p.claim_text, p.resolution_criteria,
               p.resolve_by, p.search_terms, p.thinker_id, p.created_at AS made_at,
               COALESCE(s.date_published, p.created_at::date) AS made_on
        FROM predictions p LEFT JOIN sources s ON s.id = p.source_id
        WHERE p.status = 'pending' AND p.triage_status = 'resolvable'
          AND p.resolve_by <= current_date
        ORDER BY p.resolve_by LIMIT %s""", (limit,))
    stats = {"due": len(rows), "no_evidence": 0, "judged": 0, "applied": 0,
             "abstained": 0, "failed": 0}
    print(f"Resolve: {len(rows)} due resolvable predictions")
    if not rows or dry_run:
        return stats

    today = date.today().isoformat()
    evidence_by_id: dict[int, list[dict]] = {}
    reqs = []
    for row in rows:
        evidence = _evidence_for(conn, row)
        if not evidence:
            stats["no_evidence"] += 1
            continue
        evidence_by_id[row["id"]] = evidence
        reqs.append(llm.Req(
            user=resolve_prompt(row["claim_text"], str(row["made_on"] or ""),
                                row["resolution_criteria"] or "",
                                str(row["resolve_by"] or ""), today, evidence),
            model=SYNTHESIS_MODEL, max_tokens=600, custom_id=f"p{row['id']}"))
    results = _run_reqs(reqs)

    for row in rows:
        if row["id"] not in evidence_by_id:
            continue
        text, usage = results.get(f"p{row['id']}", (None, {"error": "no result"}))
        if usage and not usage.get("error"):
            cost_tracker.add(usage, thinker_name="RESOLVE_JUDGE")
        verdict = _parse(text, usage, error_log, "resolve", row["prediction_id"])
        if verdict is None:
            stats["failed"] += 1
            continue
        stats["judged"] += 1
        outcome = verdict.get("verdict")
        confidence = verdict.get("confidence")
        retrieved_ids = {e["id"] for e in evidence_by_id[row["id"]]}
        cited = [int(i) for i in (verdict.get("evidence_ids") or [])
                 if isinstance(i, (int, str)) and str(i).isdigit()
                 and int(i) in retrieved_ids]
        applies = (
            outcome in VERDICT_VALID and outcome != "insufficient"
            and confidence == "high"
            and (cited or outcome not in EVIDENCE_REQUIRED)
        )
        if not applies:
            stats["abstained"] += 1
            continue
        note = (verdict.get("note") or "")[:400]
        db.execute(conn, """UPDATE predictions SET status = %s,
            evaluation_notes = %s, resolution_method = 'judge',
            evidence_claim_ids = %s, resolved_at = now()
            WHERE id = %s AND status = 'pending'""",
            (outcome, note, cited or None, row["id"]))
        stats["applied"] += 1
    conn.commit()
    return stats


# ── shared plumbing ───────────────────────────────────────────────────────────

def _run_reqs(reqs: list) -> dict:
    if not reqs:
        return {}
    if _USE_BATCH:
        return llm.call_batch(reqs)
    out: dict[str, tuple[str | None, dict]] = {}
    for req in reqs:
        try:
            out[str(req.custom_id)] = llm.call(req)
        except Exception as exc:  # noqa: BLE001 — surfaced per-prediction
            out[str(req.custom_id)] = (None, {"error": repr(exc)})
    return out


def _parse(text, usage, error_log: ErrorLog, step: str, pid: str) -> dict | None:
    if text is None:
        error_log.record(step=step, thinker="PIPELINE",
                         exc=RuntimeError(str((usage or {}).get("error"))),
                         retry_attempted=False, outcome="skipped", prediction=pid)
        return None
    try:
        parsed = llm.parse_model_json(text)
        return parsed if isinstance(parsed, dict) else None
    except ValueError as exc:
        error_log.record(step=step, thinker="PIPELINE", exc=exc,
                         retry_attempted=False, outcome="skipped", prediction=pid)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage + resolve predictions")
    parser.add_argument("--triage-only", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--limit", type=int,
                        default=int(os.environ.get("SS_RESOLVE_LIMIT", "400")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")

    orchestrated = bool(os.environ.get("SS_RUN_ID"))
    run_id = os.environ.get("SS_RUN_ID") or observability.new_run_id("ingest")
    run = RunLog(run_id, "ingest")
    if not orchestrated:
        run.start()
    error_log = ErrorLog(run_id)
    cost_tracker = CostTracker()

    detail: dict = {}
    with db.connect() as conn:
        if not args.resolve_only:
            detail["triage"] = triage(conn, cost_tracker, error_log,
                                      args.limit, args.dry_run)
        if not args.triage_only:
            detail["resolve"] = resolve(conn, cost_tracker, error_log,
                                        args.limit, args.dry_run)

    run.add_usage(cost=cost_tracker, detail={"resolve_predictions": detail})
    if not orchestrated:
        run.finish(status="ok")
    print(f"\nResolution pass: {detail}")
    return 0


if __name__ == "__main__":
    main()
