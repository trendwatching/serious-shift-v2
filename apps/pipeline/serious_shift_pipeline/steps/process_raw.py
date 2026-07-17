#!/usr/bin/env python3
"""
Raw content processor — extracts structured intelligence via Claude, writes to Postgres.

Converted from the legacy process_raw.py:
  * sqlite3 + `?`           → db.connect() + `%s`
  * last_insert_rowid()     → INSERT ... RETURNING id
  * `name LIKE ?`           → `name ILIKE %s`
  * INSERT + IntegrityError → INSERT ... ON CONFLICT DO NOTHING
  * urllib + CERT_NONE      → Anthropic SDK (llm.call_claude)
  * Obsidian markdown notes → dropped (the DB is the source of truth)

Usage:
  DATABASE_URL=... ANTHROPIC_API_KEY=... python -m serious_shift_pipeline.steps.process_raw
  ... --thinker "Ethan Mollick" | --file path.txt | --dry-run | --cost-cap 400
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from datetime import datetime

from ..core import db, llm, parallel
from ..core.observability import CostTracker, ErrorLog, TokenLog

RAW_DIR = os.environ.get("RAW_CONTENT_DIR", os.path.join(os.getcwd(), "raw_content"))

CONCEPT_KEYWORDS = {
    "AGI as Gradual Arrival": ["agi", "gradual", "whoosh", "already here", "singularity", "timeline", "superintelligen", "human-level"],
    "AI Agents as Senior Employees": ["agent", "autonomous", "multi-week", "senior employee", "c-suite", "automat", "copilot", "delegate", "orchestrat", "agentic"],
    "The Consumer Trust Shift": ["trust", "trusted", "loyalty", "emotional bond", "most trusted", "consumer trust"],
    "Industrial Policy for the Intelligence Age": ["policy", "robot tax", "wealth fund", "four-day", "new deal", "ubi", "regulation", "governance"],
    "AGI as Science Accelerant": ["science", "discovery", "drug", "protein", "alphafold", "cure", "research", "nobel", "pharma"],
    "Vibe Coding and Software 3.0": ["vibe cod", "software 3", "agentic engineer", "coding", "developer", "code gen"],
    "White-Collar Displacement Inversion": ["white-collar", "job loss", "displace", "automat", "employ", "hiring", "workforce", "entry-level", "junior job"],
    "The Jagged Frontier": ["jagged", "frontier", "bottleneck", "salient", "uneven", "unpredictable"],
    "Centaur and Cyborg Collaboration": ["centaur", "cyborg", "human-ai", "collaboration", "teammate", "augment"],
    "Mass Intelligence and Institutional Redesign": ["mass intelligence", "institutional", "scarce intelligence", "abundant intelligence"],
    "AI Companionship and Emotional Labor": ["companion", "emotional", "relationship", "bonding", "loneliness", "psychosis", "scai", "conscious"],
    "The Containment Problem": ["containment", "contain", "coming wave", "control", "humanist superintelligence"],
    "Open Source vs Closed AI": ["open source", "open-source", "llama", "closed", "proprietary", "regulatory capture"],
    "Existential Risk and Consumer Awareness": ["existential", "extinction", "x-risk", "catastroph", "doom"],
    "The Exponential Gap": ["exponential gap", "exponential age", "linear adaptation", "exponential", "accelerat"],
    "Enterprise AI vs Consumer AI Divergence": ["enterprise", "copilot", "consumer ai", "distribution", "good enough", "market share"],
    "AI and the Collapse of the Attention Economy": ["attention economy", "ad-supported", "crawl-to-referral", "free internet", "traffic", "publisher"],
    "The Knowledge Compilation Paradigm": ["knowledge base", "wiki", "obsidian", "second brain", "rag", "knowledge manage"],
    "AI-Generated Entertainment": ["gaming", "entertainment", "creative", "generative game", "content creation", "media"],
}

DOMAIN_VALID = {"agi_timeline", "labor", "consumer_behavior", "technology_capability", "economy",
                "regulation", "existential_risk", "enterprise", "education", "geopolitics"}

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_thinker(conn, name):
    return db.query_one(conn, "SELECT * FROM thinkers WHERE name ILIKE %s", (f"%{name}%",))


def get_thinker_context(conn, thinker_id):
    claims = db.query(conn, """SELECT c.claim_text, c.domain, s.date_published
        FROM claims c LEFT JOIN sources s ON c.source_id = s.id
        WHERE c.thinker_id = %s ORDER BY s.date_published DESC LIMIT 20""", (thinker_id,))
    preds = db.query(conn, """SELECT prediction_id, claim_text, status, consensus_alignment
        FROM predictions WHERE thinker_id = %s""", (thinker_id,))
    return claims, preds


def get_next_prediction_id(conn):
    r = db.query_one(conn, "SELECT prediction_id FROM predictions ORDER BY id DESC LIMIT 1")
    if r:
        return int(re.search(r"\d+", r["prediction_id"]).group()) + 1
    return 70


def link_claims_to_concepts(conn, claim_ids, full_text):
    text_lower = full_text.lower()
    for concept_name, keywords in CONCEPT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            r = db.query_one(conn, "SELECT id FROM concepts WHERE name = %s", (concept_name,))
            if r:
                for cid in claim_ids:
                    db.execute(conn, """INSERT INTO claim_concepts (claim_id, concept_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING""", (cid, r["id"]))

# ── raw file parsing / processed markers ───────────────────────────────────────

def parse_raw_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    meta, body = {}, content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
            body = parts[2].strip()
    return meta, body


def is_processed(filepath):
    return os.path.exists(filepath + ".processed")


def mark_processed(filepath):
    with open(filepath + ".processed", "w") as f:
        f.write(datetime.now().isoformat())

# ── extraction ──────────────────────────────────────────────────────────────

def extract_with_claude(raw_text, meta, thinker, context_claims, context_preds, cost_tracker):
    context_text = "WHAT WE ALREADY KNOW ABOUT THIS THINKER'S POSITIONS:\n"
    for c in context_claims[:15]:
        context_text += f"  [{c['date_published']}] {c['claim_text'][:150]}\n"
    context_text += "\nTHEIR EXISTING PREDICTIONS:\n"
    for p in context_preds:
        context_text += f"  {p['prediction_id']}: {p['claim_text'][:100]} [{p['status']}]\n"

    text_for_api = raw_text[:12000]
    prompt = f"""You are extracting structured intelligence from a primary source.

THINKER: {thinker['name']}
CREDIBILITY SCORE: {thinker['credibility_score']:.1f}
SOURCE: {meta.get('title', 'Unknown')} ({meta.get('platform', 'unknown')}, {meta.get('date', 'unknown')})
URL: {meta.get('url', '')}

{context_text}

RAW CONTENT:
{text_for_api}

Extract the following as JSON:

{{
  "source": {{
    "title": "",
    "date_published": "",
    "source_type": "",
    "platform": "",
    "summary": "",
    "consumer_implication": "",
    "signal_strength": "strong_signal/signal/background/noise",
    "novelty": "new_thinking/repeating_position/position_shift",
    "keynote_impact": "new_slide/strengthens_existing/contradicts_current/obsoletes_section/background",
    "confidence": "speculation/informed_prediction/data_backed"
  }},
  "claims": [
    {{
      "claim_text": "",
      "claim_type": "prediction/analysis/opinion/fact/recommendation",
      "domain": "agi_timeline/labor/consumer_behavior/technology_capability/economy/regulation/existential_risk/enterprise/education/geopolitics",
      "consumer_implication": "",
      "signal_strength": "strong_signal/signal/background/noise",
      "specificity": 3,
      "quote": "",
      "has_statistic": false,
      "statistic": ""
    }}
  ],
  "predictions": [
    {{
      "claim_text": "",
      "timeframe": "",
      "domain": "",
      "specificity": 4,
      "consensus_alignment": 0.5,
      "evaluation_date": ""
    }}
  ],
  "position_changes": [
    {{
      "topic": "",
      "previous_position": "",
      "new_position": "",
      "significance": "minor/moderate/major"
    }}
  ]
}}

RULES:
- Extract EVERY distinct claim. One idea per claim. Aim for 10-30 claims.
- US English spelling throughout (behavior, organization, analyze — not behaviour/organisation/analyse).
- signal_strength — assign explicitly, do not leave to interpretation:
  - strong_signal: a clear, distinct, specific claim worth surfacing on its own
  - signal: meaningful, but not the loudest signal
  - background: context only, not a signal
  - noise: discard-level
- has_statistic: true ONLY when the claim contains a specific, dated, attributable number.
  When true, put that number and its attribution in "statistic", e.g.
  "34% of US consumers used an AI tool to shortlist a purchase, Q1 2025 (Webb)".
  Otherwise has_statistic=false and statistic="".
- consumer_implication must answer specifically: "how does this affect how people buy, live,
  work, or expect things?" A vague answer fails the requirement.
- Only create predictions for specific, falsifiable future statements.
- Set novelty to "position_shift" if content contradicts existing positions above;
  "repeating_position" if restating known views.
- Be aggressive with extraction. More is better.

Return ONLY the JSON. No commentary."""

    text, usage = llm.call_claude(prompt)
    cost_tracker.add(usage, thinker_name=thinker["name"])
    return llm.parse_model_json(text)

# ── DB writer ─────────────────────────────────────────────────────────────────

_TYPE_VALID = {"article", "interview", "talk", "podcast", "blog_post", "essay", "paper",
               "video", "social_media", "policy_paper", "book"}


def write_to_database(conn, thinker, meta, raw_text, extracted):
    src = extracted["source"]
    thinker_id = thinker["id"]
    url = meta.get("url", "")
    date_pub = db.normalize_date(src.get("date_published") or meta.get("date"))
    title = src.get("title", meta.get("title", "Unknown"))

    if url:
        existing = db.query_one(conn, "SELECT id FROM sources WHERE url = %s AND url <> ''", (url,))
        if existing:
            print(f"    Source already in DB (id={existing['id']}). Skipping DB write.")
            return existing["id"], 0, 0

    filename = f"{date_pub} - {thinker['name'].split()[-1]} - {re.sub(r'[^a-zA-Z0-9 -]', '', title)[:50].strip()}.md"
    source_id = db.insert_returning_id(conn, """INSERT INTO sources
        (thinker_id, title, date_published, source_type, url, summary, full_text,
         consumer_implication, signal_strength, novelty, keynote_impact, confidence, filename)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (thinker_id, title, date_pub,
         src.get("source_type") if src.get("source_type") in _TYPE_VALID else "article",
         url, src.get("summary", "")[:2000], raw_text[:50000],
         src.get("consumer_implication", "")[:1000],
         src.get("signal_strength") if src.get("signal_strength") in {"noise", "background", "signal", "strong_signal"} else "signal",
         src.get("novelty") if src.get("novelty") in {"new_thinking", "repeating_position", "position_shift"} else "repeating_position",
         src.get("keynote_impact") if src.get("keynote_impact") in {"new_slide", "strengthens_existing", "contradicts_current", "obsoletes_section", "background"} else "strengthens_existing",
         src.get("confidence") if src.get("confidence") in {"speculation", "informed_prediction", "data_backed"} else "informed_prediction",
         filename))

    claim_ids = []
    for cl in extracted.get("claims", []):
        domain = cl.get("domain", "technology_capability")
        if domain not in DOMAIN_VALID:
            domain = "technology_capability"
        has_stat = bool(cl.get("has_statistic", False))
        cid = db.insert_returning_id(conn, """INSERT INTO claims
            (source_id, thinker_id, claim_text, claim_type, domain, consumer_implication,
             signal_strength, specificity, quote, has_statistic, statistic)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (source_id, thinker_id, cl["claim_text"], cl.get("claim_type", "analysis"), domain,
             cl.get("consumer_implication", ""),
             cl.get("signal_strength") if cl.get("signal_strength") in {"noise", "background", "signal", "strong_signal"} else "signal",
             cl.get("specificity", 3), cl.get("quote", ""),
             has_stat, (cl.get("statistic") or "")[:500] if has_stat else None))
        claim_ids.append(cid)

    full_text = " ".join(cl["claim_text"] for cl in extracted.get("claims", []))
    link_claims_to_concepts(conn, claim_ids, full_text)

    pred_count = 0
    next_id = get_next_prediction_id(conn)
    for pred in extracted.get("predictions", []):
        pid = f"P{next_id:03d}"
        domain = pred.get("domain", "technology_capability")
        if domain not in DOMAIN_VALID:
            domain = "technology_capability"
        claim_id = db.insert_returning_id(conn, """INSERT INTO claims
            (source_id, thinker_id, claim_text, claim_type, domain, signal_strength, specificity)
            VALUES (%s,%s,%s,'prediction',%s,'strong_signal',%s) RETURNING id""",
            (source_id, thinker_id, pred["claim_text"], domain, pred.get("specificity", 4)))
        db.execute(conn, """INSERT INTO predictions
            (prediction_id, claim_id, thinker_id, source_id, claim_text, timeframe, domain,
             specificity, falsifiable, status, consensus_alignment, evaluation_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,'pending',%s,%s)""",
            (pid, claim_id, thinker_id, source_id, pred["claim_text"], pred.get("timeframe", ""),
             domain, pred.get("specificity", 4), pred.get("consensus_alignment", 0.5),
             db.normalize_date(pred.get("evaluation_date"))))
        pred_count += 1
        next_id += 1

    conn.commit()
    return source_id, len(claim_ids), pred_count

# ── per-file orchestration ──────────────────────────────────────────────────

def prepare_file(filepath, conn, error_log=None):
    """Serial, fast DB-read phase: skip-filters + load the thinker's context.
    Returns a work dict ready for extraction, or None if the file is skipped.
    (DB reads stay on the main thread; the slow Claude call runs in parallel.)"""
    if is_processed(filepath):
        return None

    file_size = os.path.getsize(filepath)
    if file_size < 1500:
        thinker_dir = os.path.basename(os.path.dirname(filepath)).replace("_", " ")
        if error_log is not None:
            error_log.record(stage="size_filter", thinker=thinker_dir,
                             exc=ValueError("file_too_small"), retry_attempted=False,
                             outcome="skipped", reason="file_too_small", file_bytes=str(file_size))
        return None

    meta, body = parse_raw_file(filepath)
    if len(body) < 100:
        return None

    # Already ingested? Skip BEFORE the (paid) Claude extraction. The scraper's
    # per-source watermark already limits re-fetches, but raw_content is ephemeral
    # on cloud hosts, so the DB is the durable "have we seen this URL" record.
    url = meta.get("url", "")
    if url and db.query_one(conn, "SELECT 1 AS x FROM sources WHERE url = %s AND url <> ''", (url,)):
        print(f"    SKIP: already in DB — {os.path.basename(filepath)}")
        mark_processed(filepath)
        return None

    thinker_name = meta.get("thinker") or os.path.basename(os.path.dirname(filepath)).replace("_", " ")
    thinker = get_thinker(conn, thinker_name)
    if not thinker:
        print(f"    SKIP: Thinker '{thinker_name}' not found in DB ({os.path.basename(filepath)})")
        return None

    context_claims, context_preds = get_thinker_context(conn, thinker["id"])
    return {
        "filepath": filepath,
        "thinker": thinker,
        "thinker_name": thinker_name,
        "meta": meta,
        "body": body[:30000],
        "context_claims": context_claims,
        "context_preds": context_preds,
    }


def write_prepared(conn, prep, extracted):
    """Serial DB-write phase for one extracted file. Returns (claims, preds)."""
    source_id, _claim_count, _pred_count = write_to_database(
        conn, prep["thinker"], prep["meta"], prep["body"], extracted
    )
    mark_processed(prep["filepath"])
    claims = len(extracted.get("claims", []))
    preds = len(extracted.get("predictions", []))
    changes = len(extracted.get("position_changes", []))
    print(f"    OK {os.path.basename(prep['filepath'])}: "
          f"{claims} claims, {preds} predictions, {changes} position changes (source {source_id})")
    return claims, preds


def _find_files(args):
    if args.file:
        return [args.file] if os.path.exists(args.file) else []
    if args.thinker:
        pattern = os.path.join(RAW_DIR, args.thinker.replace(" ", "_"), "*.txt")
    else:
        pattern = os.path.join(RAW_DIR, "**", "*.txt")
    files = sorted(glob.glob(pattern, recursive=not args.thinker))
    return [f for f in files if not os.path.basename(f).startswith("_MANUAL")]


def main():
    parser = argparse.ArgumentParser(description="Process raw content with Claude API")
    parser.add_argument("--thinker")
    parser.add_argument("--file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cost-cap", type=float, default=400.0, metavar="USD")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")

    files = _find_files(args)
    unprocessed = [f for f in files if not is_processed(f)]
    print("=" * 60)
    print("SERIOUS SHIFT RAW CONTENT PROCESSOR")
    print("=" * 60)
    print(f"Files found: {len(files)}\nUnprocessed: {len(unprocessed)}")

    if args.dry_run:
        for f in unprocessed:
            print(f"  {f}")
        return 0
    if not unprocessed:
        print("Nothing to process.")
        return 0

    run_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    run_at = datetime.now().isoformat()
    error_log = ErrorLog(run_id)
    token_log = TokenLog()
    cost_tracker = CostTracker()
    total_claims = total_preds = processed_count = skipped_count = 0
    cost_cap_hit = False

    # Process in chunks: read+extract a chunk in parallel, write it serially, then
    # check the cost cap. Chunking bounds how far we can overshoot the cap (at most
    # one chunk of in-flight calls) while still parallelising the slow Claude calls.
    _MARK_FAILED = object()
    chunk_size = parallel.max_workers() * 3
    done = 0

    with db.connect() as conn:
        for start in range(0, len(unprocessed), chunk_size):
            chunk = unprocessed[start:start + chunk_size]

            # 1. Serial reads → work items (skips return None and drop out).
            preps = [p for p in (prepare_file(f, conn, error_log) for f in chunk) if p]

            # 2. Parallel Claude extraction (the slow part). Errors become a sentinel
            #    so one bad file doesn't sink the chunk.
            def extract(prep):
                try:
                    return extract_with_claude(prep["body"], prep["meta"], prep["thinker"],
                                               prep["context_claims"], prep["context_preds"], cost_tracker)
                except Exception as exc:  # noqa: BLE001 — recorded below; run continues
                    return (_MARK_FAILED, exc)

            extracted_list = parallel.pmap(extract, preps)

            # 3. Serial writes.
            for prep, extracted in zip(preps, extracted_list):
                if isinstance(extracted, tuple) and extracted and extracted[0] is _MARK_FAILED:
                    exc = extracted[1]
                    print(f"  ✗  {os.path.basename(prep['filepath'])} failed: "
                          f"{type(exc).__name__}: {str(exc)[:100]}")
                    error_log.record(stage="extract", thinker=prep["thinker_name"], exc=exc,
                                     retry_attempted=False, outcome="skipped", source_file=prep["filepath"])
                    skipped_count += 1
                    continue
                try:
                    claims, preds = write_prepared(conn, prep, extracted)
                    conn.commit()
                except Exception as exc:  # noqa: BLE001 — logged; run continues
                    conn.rollback()
                    print(f"  ✗  {os.path.basename(prep['filepath'])} write failed: {str(exc)[:100]}")
                    error_log.record(stage="write", thinker=prep["thinker_name"], exc=exc,
                                     retry_attempted=False, outcome="skipped", source_file=prep["filepath"])
                    skipped_count += 1
                    continue
                total_claims += claims
                total_preds += preds
                if claims > 0:
                    processed_count += 1

            done += len(chunk)
            print(f"\n  ── PROGRESS: {done}/{len(unprocessed)} files  |  "
                  f"cost so far: ${cost_tracker.cost:.4f} / ${args.cost_cap:.2f} cap ──\n")

            if cost_tracker.cost >= args.cost_cap:
                msg = f"COST CAP REACHED: ${cost_tracker.cost:.4f} >= ${args.cost_cap:.2f}."
                print(f"\n  ⛔  {msg} Halting after {done} files.")
                error_log.record(stage="cost_cap_halt", thinker="PIPELINE", exc=RuntimeError(msg),
                                 retry_attempted=False, outcome="halted",
                                 files_attempted=str(done), cost_usd=str(round(cost_tracker.cost, 4)))
                cost_cap_hit = True
                break

    token_log.append(
        run_id=run_id, run_at=run_at, total_files_processed=processed_count,
        total_input_tokens=cost_tracker.input_tokens, total_output_tokens=cost_tracker.output_tokens,
        total_cost_usd=round(cost_tracker.cost, 6),
        by_thinker=cost_tracker.by_thinker_serializable(),
        by_stage={"extract": {"input_tokens": cost_tracker.input_tokens,
                              "output_tokens": cost_tracker.output_tokens,
                              "cost_usd": round(cost_tracker.cost, 6)}})

    print(f"\n{'='*60}\nPROCESSING COMPLETE\n{'='*60}")
    print(f"  Files processed:  {processed_count}/{len(unprocessed)}")
    print(f"  Files skipped:    {skipped_count}")
    print(f"  Claims extracted: {total_claims}")
    print(f"  Predictions:      {total_preds}")
    cost_tracker.report()
    print(f"\n  Errors: {error_log.count}" + ("" if not error_log.count else f" — see {error_log.path}"))
    if cost_cap_hit:
        print(f"  Run halted at cost cap (${args.cost_cap:.2f}). Re-run to continue.")
    return total_claims


if __name__ == "__main__":
    main()
