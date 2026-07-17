#!/usr/bin/env python3
"""
Data-driven keynote generation (Postgres).

One narrative section per **Key Trend** (Content Logic, June 2026). The hardcoded
ten-theme SECTION_CONFIG is gone: sections are now generated from the Key Trends
that `generate_map_data` writes to `domain_key_trends`, one 200-300 word narrative
per trend, driven by the claims linked to that trend's sub-trends. This keeps the
keynote and the map perfectly in sync — change the map's trends, the keynote follows.

Writes the result to the `documents` table (key='keynote'); the backend serves it
at /api/keynote.
"""
import argparse
import json
import os

from ..core import db, llm, parallel
from ..core.voice import VOICE
from .generate_map_data import _attr  # parse stored proponents/skeptics → (names, detail)

KEYNOTE_MODEL = "claude-sonnet-4-6"


def load_key_trends(conn):
    """Every Key Trend, in map order, with its domain name and attribution."""
    return db.query(conn, """
        SELECT kt.id, kt.name, kt.subtitle, kt.domain_id, kt.velocity,
               kt.hero_stat, kt.proponents, kt.skeptics,
               d.name AS domain_name, d.sort_order AS domain_sort
        FROM domain_key_trends kt
        JOIN domains_v2 d ON d.id = kt.domain_id
        ORDER BY d.sort_order, kt.sort_order
    """)


def kt_evidence(conn, kt_id, limit=18):
    """Claims linked to a Key Trend (via its sub-trends), strongest first,
    statistics surfaced ahead of the rest. Deduped by claim id in Python so the
    query can rank on a computed score without DISTINCT-on-expression limits."""
    rows = db.query(conn, """
        SELECT c.id, c.claim_text, c.consumer_implication, c.signal_strength,
               c.specificity, c.has_statistic, c.statistic,
               c.claim_weight, c.freshness_score,
               t.name AS thinker, t.credibility_score
        FROM domain_sub_trends st
        JOIN domain_sub_trend_claims stc ON stc.sub_trend_id = st.id
        JOIN claims c   ON c.id = stc.claim_id
        JOIN thinkers t ON t.id = c.thinker_id
        WHERE st.kt_id = %s
          AND c.duplicate_of IS NULL
        ORDER BY c.has_statistic DESC,
                 COALESCE(c.claim_weight,0) * COALESCE(c.freshness_score,0.5)
                 * (GREATEST(COALESCE(t.credibility_score,50.0), 30.0) / 100.0) DESC
    """, (kt_id,))
    seen, deduped = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        deduped.append(r)
        if len(deduped) >= limit:
            break
    return deduped


def format_evidence(kt, evidence):
    lines = []
    stats = [c for c in evidence if c["has_statistic"] and c["statistic"]]
    if stats:
        lines.append("STATISTICS (dated, attributable — lead with one of these):")
        for c in stats[:6]:
            lines.append(f"  {c['statistic']}  — {c['thinker']}")
    lines.append("\nCLAIMS (strongest first):")
    for c in evidence:
        lines.append(f"  [{c['thinker']}, cred:{c['credibility_score']:.0f}] (spec:{c['specificity']}) {c['claim_text'][:220]}")
        if c.get("consumer_implication"):
            lines.append(f"    Consumer: {c['consumer_implication'][:160]}")
    pro = _attr(kt["proponents"])[1]
    skep = _attr(kt["skeptics"])[1]
    if pro or skep:
        lines.append("\nOPPOSING CAMPS (real disagreement — surface the tension):")
        for p in pro:
            lines.append(f"  PROPONENT {p['name']}: {p['quote']}" if p.get("quote") else f"  PROPONENT {p['name']}")
        for s in skep:
            lines.append(f"  SKEPTIC {s['name']}: {s['quote']}" if s.get("quote") else f"  SKEPTIC {s['name']}")
    return "\n".join(lines)


def generate_section_with_api(kt, evidence):
    prompt = f"""{VOICE}

Write one section of the Serious Shift keynote, in the voice above. Each section is
one Key Trend — a shift already underway that reshapes how people live and buy.

KEY TREND: {kt['name']}
WHAT IT MEANS: {kt['subtitle']}
DOMAIN: {kt['domain_name']}

EVIDENCE FROM DATABASE:
{format_evidence(kt, evidence)}

FORMAT
- 200-300 words MAXIMUM. 3-5 short paragraphs, none longer than 4 sentences.
- Open with the single most striking dated statistic from the evidence.
- Every fact MUST come from the evidence above. Do not invent anything.
- If opposing camps are listed, name the disagreement — do not flatten it to consensus.
- Cite thinkers by last name only in the body.
- End the body with one concrete "so what" for a brand or consumer.
- After the body, add this EXACT line on its own paragraph (the one place scores appear):
  Key thinkers: [every thinker you cited, each with their credibility score from the evidence, separated by middots]
  Example: Key thinkers: Mollick (53.9) · Altman (52.8) · Hassabis (53.2)

Return ONLY the section body text followed by the Key thinkers line. No title. No preamble."""
    text, _ = llm.call_claude(prompt, model=KEYNOTE_MODEL, max_tokens=1024)
    return text


def generate_section_fallback(kt, evidence):
    """No-API degrade path: stitch the strongest evidence into prose."""
    parts = []
    stats = [c for c in evidence if c["has_statistic"] and c["statistic"]]
    if stats:
        parts.append(f"{stats[0]['statistic']} ({stats[0]['thinker']}).")
    for c in evidence[:4]:
        parts.append(f"{c['claim_text'][:180]} ({c['thinker']}, {c['credibility_score']:.1f}).")
    return "\n\n".join(parts) or kt["subtitle"]


def _intro(conn):
    """Dynamic standfirst — counts straight from the DB, no stale hardcoded numbers."""
    row = db.query_one(conn, """
        SELECT (SELECT count(*) FROM thinkers) AS thinkers,
               (SELECT count(*) FROM sources)  AS sources,
               (SELECT count(*) FROM claims WHERE duplicate_of IS NULL) AS claims,
               (SELECT count(*) FROM predictions) AS predictions
    """)
    return (f"{row['thinkers']} thinkers. {row['sources']} sources. {row['claims']:,} claims. "
            f"{row['predictions']} tracked predictions. Every claim weighted by the thinker's "
            "track record. Not opinions. Scored intelligence.\n\n"
            "We track what they said, when they said it, and whether they were right. The ones "
            "who got it wrong drop in the rankings. The ones who got it right rise. This is "
            "accountability applied to prediction.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show evidence without generating")
    args = parser.parse_args()

    use_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print("=" * 60)
    print("KEYNOTE GENERATION — ONE NARRATIVE PER KEY TREND")
    print("=" * 60)

    with db.connect() as conn:
        key_trends = load_key_trends(conn)
        print(f"{len(key_trends)} Key Trends to narrate\n")

        # Gather each Key Trend's evidence serially (fast DB reads)…
        evidence_by_kt = [kt_evidence(conn, kt["id"]) for kt in key_trends]

        if args.dry_run:
            for kt, evidence in zip(key_trends, evidence_by_kt):
                print(f"{kt['name']} — {kt['subtitle']}  [{kt['domain_name']}]: "
                      f"{len(evidence)} claims")
                print(format_evidence(kt, evidence)[:600])
            return

        # …then write all the narratives concurrently (the slow API calls).
        def narrate(pair):
            kt, evidence = pair
            if not use_api:
                return generate_section_fallback(kt, evidence)
            try:
                return generate_section_with_api(kt, evidence)
            except Exception as e:  # noqa: BLE001 — degrade to fallback on API failure
                print(f"  {kt['name']}: API failed ({e}); using fallback.")
                return generate_section_fallback(kt, evidence)

        bodies = parallel.pmap(narrate, list(zip(key_trends, evidence_by_kt)))

        sections = [
            {
                "number": str(i),
                "title": kt["name"],
                "subtitle": kt["subtitle"],
                "domain": kt["domain_name"],
                "domain_id": kt["domain_id"],
                "hero_stat": kt["hero_stat"],
                "body": body,
                "claims_used": len(evidence),
            }
            for i, (kt, evidence, body) in enumerate(zip(key_trends, evidence_by_kt, bodies), 1)
        ]

        output = {"intro": _intro(conn), "sections": sections}
        db.execute(conn, """INSERT INTO documents (key, body) VALUES ('keynote', %s::jsonb)
            ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()""",
            (json.dumps(output, default=str),))  # default=str: any date/datetime → ISO string
        print(f"\nKeynote written to documents['keynote'] ({len(sections)} sections)")


if __name__ == "__main__":
    main()
