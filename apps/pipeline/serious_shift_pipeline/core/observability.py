"""
Cost tracking + append-only JSONL logs, shared by the scraper and extractor.
Ported unchanged from the legacy scripts except the logs dir is configurable
(SS_LOGS_DIR, default ./logs).
"""
from __future__ import annotations

import json
import os
import threading
import traceback as tb
from datetime import datetime

from .config import EXTRACTION_INPUT_RATE, EXTRACTION_OUTPUT_RATE

LOGS_DIR = os.environ.get("SS_LOGS_DIR", os.path.join(os.getcwd(), "logs"))


def _ensure_logs_dir() -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)


class ErrorLog:
    """Append-only structured error log; one JSON object per line."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._count = 0
        self._lock = threading.Lock()   # record() is called from worker threads
        self.path = os.path.join(LOGS_DIR, "error_log.jsonl")
        _ensure_logs_dir()

    def record(self, *, stage, thinker, exc, retry_attempted: bool,
               outcome: str = "skipped", **extra) -> None:
        entry = {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "thinker": thinker,
            "error_class": type(exc).__name__,
            "error_message": str(exc)[:500],
            "traceback": tb.format_exc(),
            "retry_attempted": retry_attempted,
            "outcome": outcome,
            **{k: str(v)[:200] for k, v in extra.items()},
        }
        line = json.dumps(entry) + "\n"
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
            self._count += 1

    @property
    def count(self) -> int:
        return self._count


class TokenLog:
    """Append-only token-usage log; one JSON line per run."""

    def __init__(self) -> None:
        self.path = os.path.join(LOGS_DIR, "token_log.jsonl")
        _ensure_logs_dir()

    def append(self, **entry) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


class CostTracker:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.by_thinker: dict = {}
        self._lock = threading.Lock()   # add() is called from worker threads

    def add(self, usage: dict, thinker_name: str = "unknown") -> None:
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        with self._lock:
            self.input_tokens += inp
            self.output_tokens += out
            self.calls += 1
            t = self.by_thinker.setdefault(thinker_name, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
            t["input_tokens"] += inp
            t["output_tokens"] += out
            t["calls"] += 1

    @property
    def cost(self) -> float:
        return self.input_tokens * EXTRACTION_INPUT_RATE + self.output_tokens * EXTRACTION_OUTPUT_RATE

    def thinker_cost(self, name: str) -> float:
        t = self.by_thinker.get(name, {})
        return t.get("input_tokens", 0) * EXTRACTION_INPUT_RATE + t.get("output_tokens", 0) * EXTRACTION_OUTPUT_RATE

    def by_thinker_serializable(self) -> dict:
        return {
            name: {**data, "cost_usd": round(
                data["input_tokens"] * EXTRACTION_INPUT_RATE
                + data["output_tokens"] * EXTRACTION_OUTPUT_RATE, 6)}
            for name, data in self.by_thinker.items()
        }

    def report(self) -> None:
        print(f"\n  API Calls:     {self.calls}")
        print(f"  Input tokens:  {self.input_tokens:,}")
        print(f"  Output tokens: {self.output_tokens:,}")
        print(f"  Estimated cost: ${self.cost:.4f}")
