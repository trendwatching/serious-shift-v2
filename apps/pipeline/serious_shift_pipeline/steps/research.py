#!/usr/bin/env python3
"""Per-shift deep research → span-verified evidence pack.

The 2026-08-20 pivot: content is produced by researching each shift on the
live web, not by scraping a thinker roster. One synthesis-tier request with
SERVER tools (web_search / web_fetch) researches a shift and returns a
pointer list of evidence items. Trust stays deterministic:

  * the model only points — this step RE-FETCHES every cited URL itself
    (steps/scraper/content.fetch_article_text) and stores the document
    (full text, sha256, dates) in `sources`;
  * every quote must locate verbatim in OUR stored copy
    (claim_integrity.locate_quote) or the item is dropped;
  * every statistic must verify against our copy (statistic_verifies);
  * survivors become `claims` rows with span anchors, bundled into an
    `evidence_packs` row whose `coverage` self-audit (kinds, hosts, primary
    share, newest date) is what the coverage gates read.

Usage:
  python -m serious_shift_pipeline.steps.research --shift <slug> [--dry-run]
  python -m serious_shift_pipeline.steps.research --name "Silent Commerce" \
      --subtitle "..." --sphere consumers
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from urllib.parse import urlparse

from ..core import claim_integrity, db, llm, observability
from ..core.config import SYNTHESIS_MODEL
from ..core.observability import CostTracker, ErrorLog, RunLog
from ..core.text import url_slug
from ..mapgen.config import DOMAINS, INDUSTRY_SECTORS
from ..prompts.research import shift_research_prompt

MAX_SEARCHES = int(os.environ.get("SS_RESEARCH_MAX_SEARCHES", "25"))
MAX_FETCHES = int(os.environ.get("SS_RESEARCH_MAX_FETCHES", "40"))
#: Soft per-shift spend note (the run-level Budget still hard-stops).
SHIFT_USD_NOTE = float(os.environ.get("SS_RESEARCH_SHIFT_USD", "2.50"))
MAX_ITEMS = 30

DOMAIN_VALID = {"agi_timeline", "labor", "consumer_behavior", "technology_capability",
                "economy", "regulation", "existential_risk", "enterprise",
                "education", "geopolitics"}
KIND_VALID = {"support", "counter", "context"}


def research_tools() -> list[dict]:
    return [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES},
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": MAX_FETCHES,
         "max_content_tokens": 20000},
    ]


def clean_items(raw) -> tuple[list[dict], list[str]]:
    """Validate/normalize the model's pointer list. Pure; heavily tested."""
    items, rejects, seen = [], [], set()
    if not isinstance(raw, list):
        return [], ["response is not a JSON array"]
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            rejects.append(f"[{i}] not an object")
            continue
        url = str(item.get("url") or "").strip()
        quote = str(item.get("quote") or "").strip()
        finding = str(item.get("finding") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            rejects.append(f"[{i}] bad url {url[:60]!r}")
            continue
        if not quote or len(quote) > 400 or not finding:
            rejects.append(f"[{i}] missing/oversized quote or finding")
            continue
        key = (url, claim_integrity.normalize_text(quote))
        if key in seen:
            rejects.append(f"[{i}] duplicate of an earlier item")
            continue
        seen.add(key)
        kind = item.get("kind") if item.get("kind") in KIND_VALID else "context"
        domain = item.get("domain") if item.get("domain") in DOMAIN_VALID \
            else "technology_capability"
        sector = item.get("sector") if item.get("sector") in INDUSTRY_SECTORS else None
        items.append({
            "url": url, "host": parsed.netloc.removeprefix("www."),
            "title": str(item.get("title") or "")[:300],
            "publisher": str(item.get("publisher") or parsed.netloc)[:200],
            "author": (str(item.get("author")) if item.get("author") else None),
            "date": str(item.get("date") or "")[:10] or None,
            "quote": quote, "finding": finding[:500],
            "statistic": (str(item.get("statistic"))[:500]
                          if item.get("statistic") else None),
            "kind": kind, "sector": sector,
            "primary": bool(item.get("primary")), "domain": domain,
        })
        if len(items) >= MAX_ITEMS:
            break
    return items, rejects


def salvage_item_array(text: str) -> list | None:
    """Recover the complete items of a TRUNCATED JSON array response.

    Items are independent evidence pointers, so a response cut mid-item
    should cost exactly the partial tail, not the whole sweep. Walks '}'
    positions backwards from the end, closing the array after each, and
    returns the first parse that yields a non-empty list."""
    start = text.find("[")
    if start == -1:
        return None
    body = text[start:]
    pos = len(body)
    for _attempt in range(60):
        pos = body.rfind("}", 1, pos)
        if pos == -1:
            return None
        try:
            parsed = json.loads(body[:pos + 1] + "]")
        except ValueError:
            continue
        return parsed if isinstance(parsed, list) and parsed else None
    return None


def coverage_of(stored: list[dict], dropped: dict) -> dict:
    hosts = Counter(item["host"] for item in stored)
    return {
        "items": len(stored),
        "kinds": dict(Counter(item["kind"] for item in stored)),
        "hosts": len(hosts),
        "top_host_share": (max(hosts.values()) / len(stored)) if stored else 0,
        "primary_share": (sum(1 for i in stored if i["primary"]) / len(stored))
                         if stored else 0,
        "with_statistic": sum(1 for i in stored if i["statistic"]),
        "sectors": sorted({i["sector"] for i in stored if i["sector"]}),
        "newest": max((i["date"] or "" for i in stored), default=""),
        "dropped": dropped,
    }


def _field(obj, key):
    """Attribute or dict-key access: the SDK returns typed objects on the
    non-streaming path and plain dicts inside stream-accumulated blocks."""
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def norm_url(url: str) -> str:
    """Loose URL identity for matching a cited URL to a fetched one across
    redirects/formatting: host without www + path without trailing slash."""
    parsed = urlparse(str(url or "").strip())
    return (parsed.netloc.removeprefix("www.") + parsed.path.rstrip("/")).lower()


_CANONICAL = re.compile(r"^canonical:\s*(\S+)", re.M)


def api_fetched_docs(msg) -> dict[str, str]:
    """{normalized url: text} for every successful web_fetch the API executed
    inside the research call. This is the FALLBACK copy for pages our own
    re-fetch cannot read (PDFs, bot-walled hosts): the quote still has to
    locate verbatim in whatever copy we store, so verification stays
    deterministic — only the fetcher changes. Indexed by both the fetched URL
    and the canonical URL in the document front matter (probed live: the two
    often differ, and the model cites the canonical)."""
    out: dict[str, str] = {}
    for block in _field(msg, "content") or []:
        if _field(block, "type") != "web_fetch_tool_result":
            continue
        result = _field(block, "content")
        url = _field(result, "url")
        text = _field(_field(_field(result, "content"), "source"), "data")
        if not (url and isinstance(text, str) and len(text) >= 300):
            continue
        out[norm_url(str(url))] = text
        canonical = _CANONICAL.search(text[:600])
        if canonical:
            out[norm_url(canonical.group(1))] = text
    return out


def _upsert_author(conn, name: str):
    """Lightweight author/publisher row — the thinkers table survives as an
    authors registry; the roster semantics are gone."""
    db.execute(conn, """INSERT INTO thinkers (name, entity_kind, discovered)
        VALUES (%s, 'publication', TRUE) ON CONFLICT (name) DO NOTHING""",
        (name[:200],))
    row = db.query_one(conn, "SELECT id FROM thinkers WHERE name = %s", (name[:200],))
    return row["id"] if row else None


def _store_document(conn, item: dict, text: str, pub_date) -> int:
    existing = db.query_one(
        conn, "SELECT id FROM sources WHERE url = %s AND url <> ''", (item["url"],))
    if existing:
        return existing["id"]
    author_id = _upsert_author(conn, item["author"] or item["publisher"])
    return db.insert_returning_id(conn, """INSERT INTO sources
        (thinker_id, title, date_published, source_type, platform, url,
         full_text, content_sha256, signal_strength, novelty, keynote_impact,
         confidence)
        VALUES (%s,%s,%s,'article',%s,%s,%s,%s,'signal','repeating_position',
                'background','data_backed') RETURNING id""",
        (author_id, item["title"] or item["publisher"],
         pub_date or db.normalize_date(item["date"]),
         "primary" if item["primary"] else "research",
         item["url"], text, hashlib.sha256(text.encode("utf-8")).hexdigest()))


def build_pack(conn, shift: dict, run_id: str, cost_tracker: CostTracker,
               error_log: ErrorLog, dry_run: bool = False,
               prompt: str | None = None) -> dict | None:
    """Research one shift end-to-end; returns the coverage dict or None.
    `prompt` overrides the per-shift template (the sphere scan reuses this
    whole verify-and-store path with its own discovery prompt)."""
    if prompt is None:
        sphere = next((d for d in DOMAINS if d["id"] == shift["sphere"]), None)
        if sphere is None:
            print(f"  unknown sphere {shift['sphere']!r}")
            return None
        prompt = shift_research_prompt(
            shift_name=shift["name"], subtitle=shift.get("subtitle", ""),
            sphere=str(sphere["name"]),
            sphere_description=str(sphere["short_description"]),
            sectors=list(INDUSTRY_SECTORS), today=date.today().isoformat(),
            context=shift.get("context", ""))
    if dry_run:
        print(prompt[:1200])
        return None

    # One poisoned fetch (the API 400s on e.g. a corrupt PDF it fetched) or a
    # truncated final array must cost ONE attempt, never the sweep and never
    # the run — the first live run died exactly this way, twice.
    msg = None
    for attempt in (1, 2):
        try:
            msg, usage = llm.call_raw(llm.Req(
                user=prompt if attempt == 1 else prompt +
                "\nNOTE: a previous attempt failed on an unreadable PDF; "
                "prefer HTML pages this pass.",
                model=SYNTHESIS_MODEL, max_tokens=20000,
                tools=research_tools(), betas=["web-fetch-2025-09-10"],
                custom_id=f"research-{shift['slug']}-a{attempt}"))
            cost_tracker.add(usage, thinker_name=f"RESEARCH:{shift['slug']}")
            break
        except Exception as exc:  # noqa: BLE001 — contained per shift, retried once
            error_log.record(step="research", thinker=shift["slug"], exc=exc,
                             retry_attempted=(attempt == 1), outcome="retried"
                             if attempt == 1 else "skipped")
            msg = None
    if msg is None:
        return None
    api_docs = api_fetched_docs(msg)
    text = llm.msg_text(msg)
    try:
        parsed = llm.parse_model_json(text)
    except ValueError as exc:
        parsed = salvage_item_array(text)
        if parsed is None:
            error_log.record(step="research", thinker=shift["slug"], exc=exc,
                             retry_attempted=False, outcome="skipped")
            return None
        print(f"  {shift['slug']}: salvaged {len(parsed)} items from a "
              f"truncated response")
    items, rejects = clean_items(parsed)

    from .scraper.content import fetch_article_text
    stored_items, item_ids = [], []
    dropped = {"pointer_rejects": len(rejects), "fetch_failed": 0,
               "quote_not_found": 0, "statistic_unverified": 0,
               "api_copy_used": 0}
    # Resolve ONE stored copy per URL. We have up to two candidates: our own
    # re-fetch and the copy the API's web_fetch read during research (PDFs and
    # bot-walled hosts only exist in the latter; dynamic pages can differ
    # between the two). The rule is unchanged — every quote must locate
    # verbatim in the stored document — so per URL we store whichever copy
    # verifies MORE of the quotes cited against it, preferring our own fetch
    # on a tie.
    by_url: dict[str, list[dict]] = {}
    for item in items:
        by_url.setdefault(item["url"], []).append(item)

    docs: dict[str, tuple[str, object] | None] = {}
    for url, url_items in by_url.items():
        own: tuple[str, object] | None = None
        try:
            fetched_text, pub_date = fetch_article_text(url)
            if fetched_text and len(fetched_text) >= 300:
                own = (fetched_text, pub_date)
        except Exception as exc:  # noqa: BLE001 — one dead link is routine
            error_log.record(step="research_fetch", thinker=shift["slug"],
                             exc=exc, retry_attempted=False,
                             outcome="skipped", source_url=url)
        api_text = api_docs.get(norm_url(url))
        candidates: list[tuple[bool, tuple[str, object]]] = []
        if own:
            candidates.append((True, own))
        if api_text:
            candidates.append(
                (False, (api_text, db.normalize_date(url_items[0]["date"]))))
        if not candidates:
            docs[url] = None
            continue

        def quote_hits(text: str) -> int:
            return sum(1 for it in url_items
                       if claim_integrity.locate_quote(it["quote"], text))

        is_own, best = max(candidates, key=lambda c: (quote_hits(c[1][0]), c[0]))
        if not is_own:
            dropped["api_copy_used"] += 1
        docs[url] = best

    for item in items:
        doc = docs.get(item["url"])
        if doc is None:
            dropped["fetch_failed"] += 1
            continue
        doc_text, pub_date = doc
        span = claim_integrity.locate_quote(item["quote"], doc_text)
        if span is None:
            dropped["quote_not_found"] += 1
            continue
        if item["statistic"] and not claim_integrity.statistic_verifies(
                item["statistic"], doc_text):
            dropped["statistic_unverified"] += 1
            item = dict(item, statistic=None)
        source_id = _store_document(conn, item, doc_text, pub_date)
        author_id = _upsert_author(conn, item["author"] or item["publisher"])
        claim_id = db.insert_returning_id(conn, """INSERT INTO claims
            (source_id, thinker_id, claim_text, claim_type, domain,
             consumer_implication, signal_strength, specificity, quote,
             has_statistic, statistic, quote_start, quote_end)
            VALUES (%s,%s,%s,'evidence',%s,'', 'signal',3,%s,%s,%s,%s,%s)
            RETURNING id""",
            (source_id, author_id, item["finding"], item["domain"],
             item["quote"], bool(item["statistic"]), item["statistic"],
             span[0], span[1]))
        item_ids.append(claim_id)
        stored_items.append(item)

    coverage = coverage_of(stored_items, dropped)
    db.execute(conn, """INSERT INTO evidence_packs (shift_slug, run_id, item_ids, coverage)
        VALUES (%s,%s,%s,%s::jsonb)
        ON CONFLICT (shift_slug, run_id)
        DO UPDATE SET item_ids = EXCLUDED.item_ids, coverage = EXCLUDED.coverage""",
        (shift["slug"], run_id, item_ids, json.dumps(coverage)))
    conn.commit()
    print(f"  {shift['slug']}: {coverage['items']} items "
          f"({coverage['kinds']}), {coverage['hosts']} hosts, "
          f"{coverage['primary_share']:.0%} primary, newest {coverage['newest']}, "
          f"dropped {dropped}")
    return coverage


#: The two discovery lenses each sphere is swept through. Two calls per
#: sphere: one watching the market, one watching the evidence — together they
#: supply the claims phase 3 names the sphere's shifts from.
SCAN_LENSES = {
    "market": ("products and launches changing behavior, adoption and usage "
               "numbers, consumer spending, company and funding moves"),
    "signals": ("research findings and primary data releases, policy and "
                "regulation, international developments outside the US, and "
                "credible criticism, failures or slowdowns"),
}


def sphere_scan(conn, run_id: str, cost_tracker: CostTracker,
                error_log: ErrorLog, dry_run: bool = False) -> dict:
    """Discovery sweep: every sphere × lens through the build_pack verify-and-
    store path. The resulting claims are what phase 2 routes and phase 3
    clusters into named shifts — this replaces the scraped corpus as the
    map's raw material."""
    from ..prompts.research import sphere_scan_prompt
    results: dict[str, dict] = {}
    for domain in DOMAINS:
        for lens_key, lens in SCAN_LENSES.items():
            slug = f"scan-{domain['id']}-{lens_key}"
            prompt = sphere_scan_prompt(
                sphere=str(domain["name"]),
                sphere_description=str(domain["short_description"]),
                lens=lens, sectors=list(INDUSTRY_SECTORS),
                today=date.today().isoformat())
            coverage = build_pack(
                conn, {"slug": slug, "name": str(domain["name"]),
                       "subtitle": lens, "sphere": domain["id"]},
                run_id, cost_tracker, error_log, dry_run=dry_run,
                prompt=prompt)
            results[slug] = coverage or {}
    total = sum(c.get("items", 0) for c in results.values())
    print(f"\nSphere scan complete: {total} verified evidence claims "
          f"across {len(results)} sweeps")
    return results


def _shift_from_map(conn, slug: str) -> dict | None:
    row = db.query_one(conn, "SELECT body FROM documents WHERE key = 'map'")
    if not row:
        return None
    body = row["body"]
    for kt in body.get("key_trends", []):
        if kt.get("slug") == slug:
            return {"slug": slug, "name": kt.get("name", slug),
                    "subtitle": kt.get("subtitle", ""),
                    "sphere": kt.get("domain_id", "")}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep-research one shift into an evidence pack")
    parser.add_argument("--shift", help="slug of a published shift")
    parser.add_argument("--name")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--sphere", choices=[d["id"] for d in DOMAINS])
    parser.add_argument("--sphere-scan", action="store_true",
                        help="discovery sweep: every sphere x lens (the "
                             "synthesize stage's first step)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")

    orchestrated = bool(os.environ.get("SS_RUN_ID"))
    run_id = os.environ.get("SS_RUN_ID") or observability.new_run_id("synthesize")
    run = RunLog(run_id, "synthesize")
    if not orchestrated:
        run.start()
    cost_tracker = CostTracker()
    error_log = ErrorLog(run_id)

    detail: dict = {}
    try:
        with db.connect() as conn:
            if args.sphere_scan:
                detail = sphere_scan(conn, run_id, cost_tracker, error_log,
                                     dry_run=args.dry_run)
            else:
                if args.shift:
                    shift = _shift_from_map(conn, args.shift)
                    if not shift:
                        sys.exit(f"ERROR: no published shift with slug {args.shift!r}")
                elif args.name and args.sphere:
                    shift = {"slug": url_slug(args.name), "name": args.name,
                             "subtitle": args.subtitle, "sphere": args.sphere}
                else:
                    sys.exit("ERROR: pass --sphere-scan, --shift SLUG, or --name and --sphere.")
                coverage = build_pack(conn, shift, run_id, cost_tracker, error_log,
                                      dry_run=args.dry_run)
                detail = {shift["slug"]: coverage or {}}
    finally:
        # Book spend even on a crash — the first live run paid for ~14
        # research calls and recorded $0.00 because this line was never
        # reached.
        run.add_usage(cost=cost_tracker, detail={"research": detail})
    if not orchestrated:
        run.finish(status="ok")
    if cost_tracker.cost > SHIFT_USD_NOTE:
        print(f"  note: shift research cost ${cost_tracker.cost:.2f} "
              f"exceeds the ${SHIFT_USD_NOTE:.2f} guide")
    return 0


if __name__ == "__main__":
    main()
