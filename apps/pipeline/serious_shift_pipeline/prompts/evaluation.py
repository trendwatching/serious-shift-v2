"""
Prompt builders for prediction triage and resolution (steps/resolve_predictions).

Triage runs once per prediction on the cheap tier; resolution runs weekly on
the synthesis tier over corpus evidence only. Both return strict JSON; the
step applies verdicts conservatively (high confidence + cited evidence, else
the prediction stays pending).
"""
from __future__ import annotations

import json

from ._loader import load_and_render


def triage_prompt(claim_text: str, timeframe: str, made_on: str, today: str) -> str:
    return load_and_render(
        "evaluation/triage.txt",
        claim_text=claim_text,
        timeframe=timeframe or "none stated",
        made_on=made_on or "unknown",
        today=today,
    )


def resolve_prompt(claim_text: str, made_on: str, criteria: str,
                   resolve_by: str, today: str, evidence: list[dict]) -> str:
    lines = "\n".join(json.dumps(e, ensure_ascii=False, default=str) for e in evidence)
    return load_and_render(
        "evaluation/resolve.txt",
        claim_text=claim_text,
        made_on=made_on or "unknown",
        criteria=criteria,
        resolve_by=resolve_by or "none",
        today=today,
        evidence=lines or "(no evidence lines)",
    )
