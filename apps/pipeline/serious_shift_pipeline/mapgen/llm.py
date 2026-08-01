"""Batched Claude calls for the map phases, with per-run cost accounting."""
from __future__ import annotations

import os

from ..core import config, llm, observability, parallel
from ..prompts import SYNTHESIS_MODEL


# Every map phase is a fan-out of independent prompts, and the weekly cron does
# not care about latency — so they go through the Batch API at half price.
# SS_DISABLE_BATCH=1 falls back to the synchronous path for local iteration,
# where waiting minutes for a batch is worse than paying double for one call.
_USE_BATCH = os.environ.get('SS_DISABLE_BATCH', '') not in ('1', 'true', 'yes')

# Generous ceiling: the largest observed map response is ~1.8k tokens, and
# staying under llm's streaming threshold keeps every call batchable. The old
# blanket 32000 forced streaming, which the Batch API does not accept.
MAP_MAX_TOKENS = 8192

# Spend for the whole map step. Previously every one of these ~270 calls threw
# its usage away (`text, _ = ...`), so the run report omitted most of the bill.
COST = observability.CostTracker(
    budget=config.Budget(per_phase_usd={'map': float(os.environ.get('SS_MAP_BUDGET_USD', '20'))}),
    phase='map',
)


def generate_json(items, prompt_of, *, model: str = SYNTHESIS_MODEL, default=None,
                  describe=lambda x: '') -> list:
    """One LLM call per item, parsed as JSON, returned in input order.

    Failures (batch error or unparseable JSON) yield `default` for that item
    rather than aborting — one bad response must not lose the phase.
    """
    items = list(items)
    if not items:
        return []

    reqs = [
        llm.Req(user=prompt_of(x), model=model, max_tokens=MAP_MAX_TOKENS, custom_id=f'i{i}')
        for i, x in enumerate(items)
    ]
    if _USE_BATCH:
        results = llm.call_batch(reqs)
    else:
        pairs = parallel.pmap(llm.call, reqs)
        results = {str(r.custom_id): pair for r, pair in zip(reqs, pairs)}

    out = []
    for i, x in enumerate(items):
        text, usage = results.get(f'i{i}', (None, {}))
        if usage and not usage.get('error'):
            COST.add(usage, 'map')
        if text is None:
            print(f'  ERROR ({describe(x)}): {usage.get("error", "no result")}')
            out.append(default() if callable(default) else default)
            continue
        try:
            out.append(llm.parse_model_json(text))
        except ValueError as e:
            print(f'  ERROR parsing JSON ({describe(x)}): {e}')
            out.append(default() if callable(default) else default)
    return out
