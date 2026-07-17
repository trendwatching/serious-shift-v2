#!/usr/bin/env python3
"""
Ad-hoc single-URL ingest (Postgres). Fetches a URL, extracts claims (Claude if a
key is set, else heuristics), and writes to the DB. Complements the batch
scraper/process_raw path for one-off additions.

Converted from ingest_pipeline.py: sqlite3+`?`→db.connect()+`%s`;
last_insert_rowid()→RETURNING id; Anthropic urllib call→llm.call_claude;
`LIKE`→`ILIKE`. The web fetch still uses urllib (that's scraping, not the API).

Usage:
  DATABASE_URL=... [ANTHROPIC_API_KEY=...] python -m serious_shift_pipeline.tools.ingest \
      --url URL --thinker "Sam Altman"
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime

from ..core import db, llm

INGEST_MODEL = "claude-sonnet-4-6"


def fetch_content(url):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:15000]
    except Exception as e:
        print(f"  Fetch failed: {e}")
        return None


def get_thinker_context(conn, thinker_id):
    claims = db.query(conn, """
        SELECT c.claim_text, c.domain, s.date_published
        FROM claims c LEFT JOIN sources s ON c.source_id = s.id
        WHERE c.thinker_id = %s ORDER BY s.date_published DESC LIMIT 20
    """, (thinker_id,))
    predictions = db.query(conn, """
        SELECT prediction_id, claim_text, status, consensus_alignment
        FROM predictions WHERE thinker_id = %s
    """, (thinker_id,))
    return {"recent_claims": claims, "predictions": predictions}


def extract_with_api(content, thinker_name, context):
    context_text = "EXISTING POSITIONS:\n"
    for c in context["recent_claims"][:10]:
        context_text += f"  [{c['date_published']}] {c['claim_text'][:120]}\n"
    context_text += "\nACTIVE PREDICTIONS:\n"
    for p in context["predictions"]:
        context_text += f"  {p['prediction_id']}: {p['claim_text'][:100]} [{p['status']}]\n"

    prompt = f"""Extract structured intelligence from this content.

THINKER: {thinker_name}

{context_text}

CONTENT:
{content[:8000]}

Return JSON:
{{
  "source": {{ "title": "...", "date": "YYYY-MM-DD", "summary": "3 sentences", "consumer_implication": "1 sentence", "source_type": "article/interview/talk/podcast/blog_post", "signal_strength": "high/medium/low", "novelty": "new_thinking/repeating_position/position_shift" }},
  "claims": [
    {{ "claim_text": "One specific claim", "claim_type": "prediction/analysis/opinion/fact", "domain": "labor/consumer_behavior/technology_capability/economy/agi_timeline/regulation/existential_risk/enterprise", "consumer_implication": "How this affects consumers", "specificity": 3, "quote": "direct quote if available" }}
  ],
  "predictions": [
    {{ "claim_text": "Falsifiable prediction", "timeframe": "By YYYY", "domain": "...", "specificity": 4, "consensus_alignment": 0.5, "evaluation_date": "YYYY-MM-DD" }}
  ],
  "position_changes": [
    {{ "previous_position": "What they said before", "new_position": "What they say now" }}
  ]
}}

Extract 5-15 claims. Flag any position changes compared to existing positions above.
If the thinker is REPEATING an existing position, set novelty to "repeating_position".
If they say something genuinely new, set novelty to "new_thinking"."""

    text, _ = llm.call_claude(prompt, model=INGEST_MODEL, max_tokens=4096)
    return llm.parse_model_json(text)


def extract_heuristic(content, thinker_name):
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", content) if len(s.strip()) > 40]
    claims = []
    for s in sentences[:15]:
        if any(w in s.lower() for w in ["ai ", "artificial", "machine learn", "model", "agent", "automat"]):
            claims.append({
                "claim_text": s[:200], "claim_type": "analysis",
                "domain": "technology_capability", "consumer_implication": "",
                "specificity": 2, "quote": "",
            })
    return {
        "source": {
            "title": content[:60].strip(), "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": content[:300], "consumer_implication": "",
            "source_type": "article", "signal_strength": "medium",
            "novelty": "repeating_position",
        },
        "claims": claims[:10], "predictions": [], "position_changes": [],
    }


DOMAIN_VALID = {"labor", "consumer_behavior", "technology_capability", "economy", "agi_timeline",
                "regulation", "existential_risk", "enterprise", "education", "geopolitics"}


def write_to_db(conn, thinker_id, url, extracted):
    src = extracted["source"]
    signal_map = {"high": "signal", "medium": "signal", "low": "background"}
    novelty = src.get("novelty") if src.get("novelty") in {"new_thinking", "repeating_position", "position_shift"} else "repeating_position"

    filename = f"{src.get('date', 'unknown')} - ingested - {src.get('title', 'unknown')[:40]}.md"
    source_id = db.insert_returning_id(conn, """INSERT INTO sources
        (thinker_id, title, date_published, source_type, url, summary,
         consumer_implication, signal_strength, novelty, keynote_impact, confidence, filename)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'strengthens_existing','informed_prediction',%s) RETURNING id""",
        (thinker_id, src.get("title", ""), db.normalize_date(src.get("date")),
         src.get("source_type", "article"), url, src.get("summary", ""),
         src.get("consumer_implication", ""), signal_map.get(src.get("signal_strength", ""), "signal"),
         novelty, filename))

    claim_count = 0
    for cl in extracted.get("claims", []):
        domain = cl.get("domain", "technology_capability")
        if domain not in DOMAIN_VALID:
            domain = "technology_capability"
        db.execute(conn, """INSERT INTO claims (source_id, thinker_id, claim_text, claim_type,
            domain, consumer_implication, signal_strength, specificity, quote)
            VALUES (%s,%s,%s,%s,%s,%s,'signal',%s,%s)""",
            (source_id, thinker_id, cl["claim_text"], cl.get("claim_type", "analysis"), domain,
             cl.get("consumer_implication", ""), cl.get("specificity", 3), cl.get("quote", "")))
        claim_count += 1

    conn.commit()
    return source_id, claim_count


def main():
    parser = argparse.ArgumentParser(description="Ingest a single source URL into the DB")
    parser.add_argument("--url", required=True)
    parser.add_argument("--thinker", required=True)
    args = parser.parse_args()

    use_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    with db.connect() as conn:
        thinker = db.query_one(conn, "SELECT id, name FROM thinkers WHERE name ILIKE %s",
                               (f"%{args.thinker}%",))
        if not thinker:
            sys.exit(f"Thinker '{args.thinker}' not found in database.")
        print(f"Thinker: {thinker['name']} (id={thinker['id']})")

        print(f"Fetching: {args.url}")
        content = fetch_content(args.url)
        if not content:
            sys.exit("Could not fetch content.")
        print(f"  Fetched {len(content)} chars")

        if use_api:
            print("Extracting with Claude API (with historical context)…")
            extracted = extract_with_api(content, thinker["name"], get_thinker_context(conn, thinker["id"]))
        else:
            print("Extracting with heuristics (no API key)…")
            extracted = extract_heuristic(content, thinker["name"])

        source_id, claim_count = write_to_db(conn, thinker["id"], args.url, extracted)
        print(f"\nIngested: source_id={source_id}, {claim_count} claims")

        for pc in extracted.get("position_changes", []):
            print(f"  POSITION CHANGE — prev: {pc.get('previous_position', 'N/A')} | "
                  f"new: {pc.get('new_position', 'N/A')}")


if __name__ == "__main__":
    main()
