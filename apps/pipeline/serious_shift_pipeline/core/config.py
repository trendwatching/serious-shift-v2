"""Pipeline config — models + pricing, from env. No heavy imports so logging and
cost tracking don't pull in the Anthropic SDK."""
import os
import threading

# Extraction runs on the cheapest capable model: it is by far the highest-volume
# call (one per raw source file) and the task is structured extraction.
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "claude-haiku-4-5")

# USD per 1M tokens, (input, output), by model-id prefix. Prefix matching so a
# dated id ("claude-haiku-4-5-20251001") resolves to the same rates as the alias.
#
# Costing previously assumed every call was Haiku, which silently under-reported
# the Sonnet and Opus spend that is most of a run.
#
# Every model this pipeline can be pointed at must appear here. EXTRACTION_MODEL
# and INSIGHTS_MODEL are env-overridable, so an operator upgrading a stage to a
# newer model would otherwise silently fall through to the Sonnet fallback — and
# for an Opus- or Fable-tier model that under-reports the bill by 1.7x-3.3x,
# which is exactly the reporting error the per-model table was added to fix.
_RATES_PER_M = {
    "claude-haiku-4-5":  (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5":   (3.0, 15.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-opus-5":     (5.0, 25.0),
    "claude-fable-5":    (10.0, 50.0),
    "claude-mythos-5":   (10.0, 50.0),
}
_FALLBACK_PER_M = (3.0, 15.0)  # unknown model: assume Sonnet rather than free

# Cache reads are ~0.1x input, cache writes ~1.25x; Batch is half price overall.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25
BATCH_MULTIPLIER = 0.50


def rates_for(model: str | None) -> tuple[float, float]:
    """(input, output) USD per token for `model`."""
    name = model or EXTRACTION_MODEL
    for prefix, (inp, out) in _RATES_PER_M.items():
        if name.startswith(prefix):
            return inp / 1_000_000, out / 1_000_000
    return _FALLBACK_PER_M[0] / 1_000_000, _FALLBACK_PER_M[1] / 1_000_000


def cost_of(usage: dict) -> float:
    """USD for one call, from the usage dict core.llm returns."""
    inp_rate, out_rate = rates_for(usage.get("model"))
    cost = (
        (usage.get("input_tokens") or 0) * inp_rate
        + (usage.get("cache_read_input_tokens") or 0) * inp_rate * CACHE_READ_MULTIPLIER
        + (usage.get("cache_creation_input_tokens") or 0) * inp_rate * CACHE_WRITE_MULTIPLIER
        + (usage.get("output_tokens") or 0) * out_rate
    )
    return cost * BATCH_MULTIPLIER if usage.get("batch") else cost


class BudgetExceeded(RuntimeError):
    """Raised when a run or one phase passes its spend ceiling."""


class Budget:
    """Hard spend ceiling for a run.

    Distinct from the escalation threshold, which only *notifies* after the fact.
    This raises, so a runaway stops rather than being reported once the money is
    already spent. Thread-safe: charged from pmap workers.
    """

    def __init__(self, total_usd: float | None = None, per_phase_usd: dict | None = None):
        self.total = (
            total_usd if total_usd is not None
            else float(os.environ.get("SS_BUDGET_TOTAL_USD", "35.0"))
        )
        self.per_phase = per_phase_usd or {}
        self.spent = 0.0
        self.by_phase: dict[str, float] = {}
        self._lock = threading.Lock()

    def charge(self, phase: str, usd: float) -> None:
        with self._lock:
            self.spent += usd
            self.by_phase[phase] = self.by_phase.get(phase, 0.0) + usd
            if self.spent > self.total:
                raise BudgetExceeded(
                    f"run spend ${self.spent:.2f} exceeded ceiling ${self.total:.2f} "
                    f"(in phase {phase!r}); raise SS_BUDGET_TOTAL_USD to allow more")
            cap = self.per_phase.get(phase)
            if cap is not None and self.by_phase[phase] > cap:
                raise BudgetExceeded(
                    f"phase {phase!r} spend ${self.by_phase[phase]:.2f} exceeded its "
                    f"${cap:.2f} cap")
