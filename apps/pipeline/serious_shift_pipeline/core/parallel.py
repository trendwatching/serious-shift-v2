"""
Bounded, order-preserving parallel map for the pipeline's I/O-bound work.

The expensive pipeline steps are network/API bound (scraping, Claude calls), so a
thread pool gives a large speedup with no extra processes. Usage pattern across
the steps: run the API/network calls concurrently with `pmap`, then do the DB
writes serially on the main thread's connection (psycopg connections are not
shared across threads).

Concurrency is capped by SS_MAX_WORKERS (default 8) so we stay within API rate
limits and don't open too many sockets at once.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor


def max_workers(default: int = 8) -> int:
    try:
        return max(1, int(os.environ.get("SS_MAX_WORKERS", default)))
    except (TypeError, ValueError):
        return default


def pmap(fn, items, workers: int | None = None) -> list:
    """Apply `fn` to each item concurrently; return results in input order.

    Bounded by `workers` (default SS_MAX_WORKERS). For 0–1 items it runs inline
    (no threads). Exceptions propagate when the result list is materialised, so
    if a batch should survive individual failures, have `fn` catch its own
    errors and return a sentinel (the steps do this and filter afterwards).
    """
    items = list(items)
    if not items:
        return []
    n = max(1, min(workers or max_workers(), len(items)))
    if n == 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(fn, items))
