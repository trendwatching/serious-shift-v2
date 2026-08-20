"""
Prompt builder for ad-hoc single-URL ingest (tools/ingest).

Lighter-weight cousin of the extraction prompt: fewer fields, 5-15 claims, with
the thinker's existing positions/predictions as context for position-change flags.
"""
from ..core.config import INGEST_MODEL  # noqa: F401 — re-exported
from ._loader import load_and_render


def ingest_prompt(thinker_name: str, content: str, context: dict) -> str:
    context_text = "EXISTING POSITIONS:\n"
    for c in context["recent_claims"][:10]:
        context_text += f"  [{c['date_published']}] {c['claim_text'][:120]}\n"
    context_text += "\nACTIVE PREDICTIONS:\n"
    for p in context["predictions"]:
        context_text += f"  {p['prediction_id']}: {p['claim_text'][:100]} [{p['status']}]\n"

    return load_and_render(
        "ingest/single_url.txt",
        thinker_name=thinker_name,
        context=context_text,
        content=content[:8000],
    )
