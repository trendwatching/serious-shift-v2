"""
Orchestration: load the manifest, fan out across thinkers, own the watermark.

The watermark is updated here and nowhere else. Handlers report what they
fetched; this decides what that means for `source_state`, so the invariant has
one place to be wrong rather than eight.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime

from ...core import db, observability, parallel
from ...core.observability import ErrorLog, RunLog
from ...core.redaction import redact_secrets
from .handlers import _run_scraper, handle_manual, is_ip_block
from .watermark import (
    FALLBACK_SINCE, get_since_for_source, get_thinker_id, update_source_state,
)


class Log:
    """In-run scrape tally. Printed as it goes, persisted at the end to
    `pipeline_runs.detail['scrape']` by the caller.

    It used to also write a `scrape_log.json` next to the working directory,
    carrying the same stats/sources/proxy figures. That was the pre-Postgres
    mechanism and it survived the migration by accident: on Railway the file is
    written to a container filesystem that is discarded when the cron job ends,
    so the only copy anyone could actually read was already the database row.
    Two sinks for one fact, one of them unreadable in production.
    """

    def __init__(self):
        self.stats = {'found': 0, 'fetched': 0, 'skipped': 0, 'failed': 0}
        self.entries = []
        self.source_results = []
        self.proxy_requests = 0
        self.proxy_cost_usd = 0.0
        self._lock = threading.Lock()   # log() is called from worker threads

    def log(self, action, thinker, platform, title='', url='', error=''):
        with self._lock:
            self.entries.append({
                'action': action,
                'thinker': thinker,
                'platform': platform,
                'title': title[:80],
            })
            self.stats[action] = self.stats.get(action, 0) + 1

    def proxy_request(self):
        """Record one proxied YouTube HTTP operation without logging its URL."""
        try:
            unit_cost = float(os.environ.get('YOUTUBE_PROXY_COST_USD_PER_REQUEST', '0'))
        except ValueError:
            unit_cost = 0.0
        with self._lock:
            self.proxy_requests += 1
            self.proxy_cost_usd += max(0.0, unit_cost)

    def source_result(self, *, thinker, platform, status, item_count,
                      duration_seconds, proxied=False):
        with self._lock:
            self.source_results.append({
                'thinker': thinker,
                'platform': platform,
                'status': status,
                'item_count': item_count,
                'duration_seconds': round(duration_seconds, 3),
                'proxied': bool(proxied),
            })

    def summary(self):
        print(f"\n{'='*50}\nSCRAPE SUMMARY\n{'='*50}")
        for k, v in self.stats.items():
            print(f"  {k}: {v}")
        total = len(self.source_results)
        successful = sum(item['status'] == 'ok' for item in self.source_results)
        if total:
            print(f"  source success: {successful}/{total} ({successful / total:.1%})")
        if self.proxy_requests:
            print(f"  proxy requests: {self.proxy_requests} "
                  f"(estimated ${self.proxy_cost_usd:.4f})")



def load_thinker_sources(conn, name_filter=None):
    """Load the scrape manifest from the DB as [{name, sources:[{platform, method,
    url, rss, channel_url, handle, note}, …]}, …] — replaces scraper_config.json."""
    rows = db.query(conn, """
        SELECT t.name, ss.platform, ss.method, ss.url, ss.rss, ss.channel_url, ss.handle, ss.note, ss.params
        FROM scrape_sources ss JOIN thinkers t ON t.id = ss.thinker_id
        ORDER BY t.name, ss.id""")
    by_name: dict = {}
    for r in rows:
        entry = by_name.setdefault(r["name"], {"name": r["name"], "sources": []})
        entry["sources"].append({k: r[k] for k in
                                 ("platform", "method", "url", "rss", "channel_url", "handle", "note", "params")})
    thinkers = list(by_name.values())
    if name_filter:
        thinkers = [t for t in thinkers if name_filter.lower() in t["name"].lower()]
    return thinkers


def scrape_thinker(cfg, mode, global_since, until, log, conn, auto_since, error_log):
    """
    Orchestrate fetching for one thinker across all their sources.

    If auto_since=True, per-source since is read from source_state.
      global_since acts as the fallback for sources with no prior run.
    If auto_since=False, global_since is used for every source.

    Failure handling
      Each source gets one retry (10 s delay). If both attempts fail,
      the error is logged to error_log and the run continues with the
      next source. source_state is ALWAYS updated — even on failure —
      so last_run_status reflects what happened and broken sources are
      visible via a query.

    Watermark invariant
      update_source_state is called after every attempt (success or fail).
      On failure, newest_date=None so last_item_date does not regress.
    """
    name = cfg['name']
    print(f"\n{'='*50}\nSCRAPING: {name} ({mode})\n{'='*50}")

    thinker_id = get_thinker_id(conn, name)
    if thinker_id is None:
        print(f"  WARNING: '{name}' not found in thinkers table — skipping source_state updates.")

    for src in cfg.get('sources', []):
        method   = src.get('method', 'manual')
        platform = src.get('platform', method)
        # Stable per-source identifier for the watermark key. Use `or` (not
        # dict.get defaults): a manifest row has all of url/channel_url/rss/handle
        # as keys, but most are NULL — e.g. a YouTube source sets only
        # channel_url, so `src.get('url', …)` would return None, not fall through.
        src_url  = (src.get('url') or src.get('channel_url') or src.get('rss')
                    or src.get('handle') or 'unknown')

        # Determine effective since for this source
        if auto_since and thinker_id is not None:
            since = get_since_for_source(
                conn, thinker_id, platform, src_url, global_since
            )
        else:
            since = global_since

        print(f"\n  Source: {platform} | {src_url} | since={since}")

        if method == 'manual':
            handle_manual(name, src, log)
            # Manual sources have no watermark — nothing to update
            continue

        newest_date, count, status = None, 0, 'ok'
        last_exc = None
        source_started = time.monotonic()

        for attempt in range(2):
            try:
                newest_date, count = _run_scraper(
                    method, name, src, since, until, mode, log, error_log
                )
                last_exc = None   # success — clear any previous attempt error
                break
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    print(
                        f"  ⚠  attempt 1 failed "
                        f"({type(exc).__name__}: {redact_secrets(exc)[:120]}). "
                        f"Retrying in 10 s…"
                    )
                    time.sleep(10)

        if last_exc is not None:
            # A host refusing our IP is a configuration gap, not a broken
            # source. Recording both as 'failed' meant the failed-source alert
            # fired every run for a known cause with a known remedy, which is
            # how a real breakage gets lost in the noise.
            blocked = is_ip_block(last_exc)
            status = 'blocked' if blocked else 'failed'
            newest_date, count = None, 0
            if blocked:
                print(f"  ⛔  {platform} | {src_url[:60]} is blocking this IP. "
                      f"Set YOUTUBE_PROXY_URL or WEBSHARE_PROXY_USERNAME/"
                      f"WEBSHARE_PROXY_PASSWORD to fetch it from a cloud host.")
            else:
                print(f"  ✗  {platform} | {src_url[:60]} failed after retry: "
                      f"{redact_secrets(last_exc)}")
            error_log.record(
                step='scrape',
                thinker=name,
                exc=last_exc,
                retry_attempted=True,
                outcome='blocked' if blocked else 'skipped',
                platform=platform,
                source_url=src_url,
            )

        log.source_result(
            thinker=name,
            platform=platform,
            status=status,
            item_count=count,
            duration_seconds=time.monotonic() - source_started,
            proxied=(platform == 'youtube' and bool(
                os.environ.get('YOUTUBE_PROXY_URL')
                or os.environ.get('WEBSHARE_PROXY_USERNAME')
            )),
        )

        # Update watermark — ALWAYS called, success or failure.
        # On failure: newest_date=None → last_item_date does not change.
        # last_run_status='failed' makes broken sources queryable.
        if thinker_id is not None:
            update_source_state(
                conn, thinker_id, platform, src_url,
                newest_date, count, status,
            )
            if count:
                print(f"  ✓ Watermark updated: {newest_date} ({count} new items)")
            elif status == 'failed':
                print("  ✗ status=failed written to source_state")
            else:
                print("  — No new items; watermark unchanged")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Serious Shift Scraper v3')
    parser.add_argument('--thinker', help='Scrape specific thinker by name')
    parser.add_argument('--all', action='store_true', help='Scrape all thinkers')
    parser.add_argument('--mode', choices=['historical', 'live'], default='live',
                        help='historical=full archive via sitemap; live=recent RSS (default)')
    parser.add_argument('--since', default=None,
                        help='Override watermark globally. Use for backfills. '
                             'Format: YYYY-MM-DD. Without this flag, per-source '
                             'watermarks from source_state are used.')
    parser.add_argument('--until', default=datetime.now().strftime('%Y-%m-%d'),
                        help='Upper date bound (default: today)')
    args = parser.parse_args()

    if not args.thinker and not args.all:
        parser.error("Specify --thinker 'Name' or --all")

    # auto_since=True  unless user explicitly passed --since
    auto_since   = args.since is None
    global_since = args.since or FALLBACK_SINCE

    conn = db.raw_connect()      # source_state + scrape_sources live in packages/db migrations

    log = Log()
    thinkers = load_thinker_sources(conn, None if args.all else args.thinker)
    if not thinkers:
        print(f"Thinker not found: {args.thinker}")
        conn.close()
        sys.exit(1)

    # Orchestrated runs inherit SS_RUN_ID so scrape errors file under the same
    # run as the extraction that follows them; standalone, this step owns a run
    # row of its own.
    orchestrated = bool(os.environ.get('SS_RUN_ID'))
    run_id     = os.environ.get('SS_RUN_ID') or observability.new_run_id('ingest')
    run        = RunLog(run_id, 'ingest')
    if not orchestrated:
        run.start()
    error_log  = ErrorLog(run_id)
    mode_label = 'auto-since' if auto_since else f'since={global_since}'
    print(f"Run ID: {run_id}")
    print(f"Mode: {args.mode} | {mode_label} | until={args.until}")
    print(f"Thinkers: {len(thinkers)}")

    # Scrape thinkers concurrently — this is network-bound. Each worker gets its
    # own DB connection (psycopg connections aren't shared across threads); the
    # shared Log/ErrorLog are lock-guarded. Raw files write to per-source paths.
    def scrape_one(t):
        wconn = db.raw_connect()
        try:
            scrape_thinker(t, args.mode, global_since, args.until,
                           log, wconn, auto_since, error_log)
        except Exception as exc:  # noqa: BLE001 — one thinker failing must not stop the rest
            error_log.record(step='scrape', thinker=t.get('name', '?'), exc=exc,
                             retry_attempted=False, outcome='skipped')
            print(f"  ✗  {t.get('name', '?')} failed: {type(exc).__name__}: "
                  f"{redact_secrets(exc)[:100]}")
        finally:
            wconn.close()

    parallel.pmap(scrape_one, thinkers)

    conn.close()
    log.summary()

    source_total = len(log.source_results)
    source_ok = sum(item['status'] == 'ok' for item in log.source_results)
    run.add_usage(detail={'scrape': {
        **log.stats,
        'errors': error_log.count,
        'source_success_rate': round(source_ok / source_total, 4) if source_total else None,
        'sources': log.source_results,
        'proxy_requests': log.proxy_requests,
        'proxy_cost_usd': round(log.proxy_cost_usd, 6),
    }})
    if not orchestrated:
        run.finish(status='ok')

    print(f"\n  Errors: {error_log.count}"
          + (f" — query pipeline_errors WHERE run_id = '{run_id}'" if error_log.count else ""))
