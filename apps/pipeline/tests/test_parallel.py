"""Tests for the bounded order-preserving parallel map."""
import threading
import time

from serious_shift_pipeline.core import parallel


def test_pmap_preserves_order():
    # Even with varied per-item delays, results come back in input order.
    def slow(x):
        time.sleep(0.02 if x % 2 == 0 else 0.001)
        return x * 10
    assert parallel.pmap(slow, range(12), workers=4) == [x * 10 for x in range(12)]


def test_pmap_empty_and_single():
    assert parallel.pmap(lambda x: x, []) == []
    assert parallel.pmap(lambda x: x + 1, [41]) == [42]


def test_pmap_runs_concurrently():
    # 8 items each sleeping 50ms finish in well under the 400ms serial time.
    start = time.perf_counter()
    parallel.pmap(lambda _: time.sleep(0.05), range(8), workers=8)
    assert time.perf_counter() - start < 0.25


def test_pmap_actually_uses_threads():
    seen = set()
    lock = threading.Lock()
    def record(_):
        with lock:
            seen.add(threading.get_ident())
        time.sleep(0.02)
    parallel.pmap(record, range(8), workers=4)
    assert len(seen) > 1  # more than one worker thread was used


def test_max_workers_env(monkeypatch):
    monkeypatch.setenv("SS_MAX_WORKERS", "3")
    assert parallel.max_workers() == 3
    monkeypatch.setenv("SS_MAX_WORKERS", "garbage")
    assert parallel.max_workers(5) == 5
