#!/usr/bin/env python3
"""
Claim deduplication (Postgres). Marks duplicates via claims.duplicate_of without
deleting; keeps the highest-quality claim as primary.

Converted from deduplicate_claims.py:
  * sqlite3 + `?`        → db.connect() + `%s`
  * PRAGMA / ALTER TABLE → dropped (duplicate_of exists in the migrations)
  * urllib + CERT_NONE   → Anthropic SDK (llm.call_claude)
The word-overlap heuristic, union-find grouping, and primary selection are unchanged.

Usage:
  DATABASE_URL=... python -m serious_shift_pipeline.steps.deduplicate           # dry run
  DATABASE_URL=... python -m serious_shift_pipeline.steps.deduplicate --execute [--use-api]
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict

from ..core import db, llm

DEDUP_MODEL = "claude-sonnet-4-6"

STOPWORDS = frozenset([
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "because", "but", "and", "or", "if", "while",
    "about", "up", "out", "off", "over", "this", "that", "these", "those",
    "it", "its", "he", "she", "they", "them", "his", "her", "their",
    "what", "which", "who", "whom", "we", "you", "i", "me", "my", "your",
    "also", "like", "new", "get", "make", "one", "two", "many", "much",
    "well", "even", "still", "already", "now", "said", "says", "say",
    "think", "things", "thing", "way", "need", "going", "really", "us",
])


def significant_words(text):
    tokens = re.findall(r"[a-z]+", text.lower())
    return set(t for t in tokens if t not in STOPWORDS and len(t) > 2)


def word_overlap(words_a, words_b):
    if not words_a or not words_b:
        return 0.0
    smaller = min(len(words_a), len(words_b))
    return len(words_a & words_b) / smaller if smaller > 0 else 0.0


def pick_primary(claims_in_group):
    def score(c):
        return (c.get("claim_weight") or 0.0, c.get("specificity") or 3,
                c.get("full_text_len") or 0, -c["id"])
    return max(claims_in_group, key=score)["id"]


def api_check_duplicates(pairs):
    """Send ambiguous pairs to Claude; return set of (id_a, id_b) judged duplicate."""
    duplicates = set()
    for i in range(0, len(pairs), 20):
        batch = pairs[i:i + 20]
        prompt_lines = []
        for idx, (id_a, text_a, id_b, text_b) in enumerate(batch):
            prompt_lines += [f"Pair {idx + 1}:", f"  A [{id_a}]: {text_a[:200]}", f"  B [{id_b}]: {text_b[:200]}"]
        prompt = (
            "For each pair of claims below, respond with ONLY the pair number and "
            "DUPLICATE or UNIQUE. Mark DUPLICATE only if a reader would learn nothing "
            "new from reading both — they make the same core argument even if worded differently.\n\n"
            + "\n".join(prompt_lines)
            + "\n\nRespond as: 1: DUPLICATE or 1: UNIQUE (one per line, nothing else)."
        )
        try:
            text, _ = llm.call_claude(prompt, model=DEDUP_MODEL, max_tokens=1024)
            for line in text.strip().split("\n"):
                m = re.match(r"(\d+)\s*:\s*(DUPLICATE|UNIQUE)", line.strip(), re.IGNORECASE)
                if m and m.group(2).upper() == "DUPLICATE":
                    pi = int(m.group(1)) - 1
                    if 0 <= pi < len(batch):
                        duplicates.add((batch[pi][0], batch[pi][2]))
        except Exception as e:  # noqa: BLE001 — one batch failing shouldn't abort the run
            print(f"    API batch failed: {e}")
    return duplicates


def main():
    parser = argparse.ArgumentParser(description="Deduplicate claims")
    parser.add_argument("--execute", action="store_true", help="Write changes")
    parser.add_argument("--use-api", action="store_true", help="Use Claude for ambiguous pairs")
    args = parser.parse_args()
    dry_run = not args.execute
    if dry_run:
        print("*** DRY RUN — no changes ***\n    Use --execute to apply.\n")

    with db.connect() as conn:
        print("  Column claims.duplicate_of: managed by migrations")
        claims = db.query(conn, """
            SELECT c.id, c.thinker_id, c.domain, c.claim_text, c.specificity,
                   c.signal_strength, t.name AS thinker, c.claim_weight,
                   LENGTH(COALESCE(s.full_text, '')) AS full_text_len
            FROM claims c
            JOIN thinkers t ON c.thinker_id = t.id
            LEFT JOIN sources s ON c.source_id = s.id
            WHERE c.duplicate_of IS NULL
            ORDER BY c.thinker_id, c.domain
        """)
        print(f"\n  Claims to scan: {len(claims)}")

        groups = defaultdict(list)
        for c in claims:
            groups[(c["thinker_id"], c["domain"] or "technology_capability")].append(c)
        print(f"  Thinker+domain groups: {len(groups)}")

        exact_dupes, overlap_candidates, total_pairs = [], [], 0
        for group_claims in groups.values():
            n = len(group_claims)
            if n < 2:
                continue
            words_cache = {c["id"]: significant_words(c["claim_text"]) for c in group_claims}
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = group_claims[i], group_claims[j]
                    total_pairs += 1
                    text_a, text_b = a["claim_text"].strip(), b["claim_text"].strip()
                    if text_a == text_b or (abs(len(text_a) - len(text_b)) < 10 and text_a[:50] == text_b[:50]):
                        exact_dupes.append((a["id"], b["id"]))
                        continue
                    if word_overlap(words_cache[a["id"]], words_cache[b["id"]]) > 0.60:
                        overlap_candidates.append((a["id"], text_a, b["id"], text_b))

        print(f"  Pairs compared: {total_pairs:,}")
        print(f"  Exact/near-exact duplicates: {len(exact_dupes)}")
        print(f"  High-overlap candidates: {len(overlap_candidates)}")

        api_confirmed = set()
        if args.use_api and overlap_candidates:
            print(f"\n  Sending {len(overlap_candidates)} pairs to Claude…")
            api_confirmed = api_check_duplicates(overlap_candidates)
            print(f"  API confirmed duplicates: {len(api_confirmed)}")
        elif overlap_candidates:
            for id_a, text_a, id_b, text_b in overlap_candidates:
                if word_overlap(significant_words(text_a), significant_words(text_b)) > 0.75:
                    api_confirmed.add((id_a, id_b))
            print(f"  High-confidence overlap duplicates (>75%): {len(api_confirmed)}")

        # Union-find to merge transitive duplicates
        all_pairs = set(exact_dupes) | api_confirmed
        print(f"\n  Total duplicate pairs: {len(all_pairs)}")
        parent: dict = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        for a, b in all_pairs:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        dupe_groups = defaultdict(set)
        for a, b in all_pairs:
            root = find(a)
            dupe_groups[root].update({a, b})

        claims_by_id = {c["id"]: c for c in claims}
        total_marked, primary_counts = 0, {}
        for members in dupe_groups.values():
            member_data = [claims_by_id[m] for m in members if m in claims_by_id]
            if len(member_data) < 2:
                continue
            primary_id = pick_primary(member_data)
            non_primary = [m["id"] for m in member_data if m["id"] != primary_id]
            primary_counts[primary_id] = len(non_primary)
            total_marked += len(non_primary)
            if not dry_run:
                for cid in non_primary:
                    db.execute(conn, "UPDATE claims SET duplicate_of = %s WHERE id = %s", (primary_id, cid))

        total = len(claims)
        pct = total_marked / total * 100 if total else 0
        print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
        print(f"  Total claims scanned: {total}")
        print(f"  Duplicate groups found: {len(dupe_groups)}")
        print(f"  Claims marked as duplicates: {total_marked}")
        print(f"  Duplication rate: {pct:.1f}%")
        print(f"  Unique claims remaining: {total - total_marked}")
        if dry_run:
            print("\n  Run with --execute to apply. Add --use-api for semantic matching.")


if __name__ == "__main__":
    main()
