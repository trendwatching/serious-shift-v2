"""
Prompt builder for raw-content extraction (steps/process_raw).

Extracts structured intelligence (source, claims, predictions, position changes)
from a primary source, with the thinker's known positions as context. Runs on the
default EXTRACTION_MODEL (Haiku 4.5) — the step calls llm.call_claude() without an
override, so the model lives in core/config.py, not here.
"""
from ._loader import load_and_render


def extraction_prompt(thinker: dict, meta: dict, raw_text: str,
                      context_claims: list, context_preds: list) -> str:
    context_text = "WHAT WE ALREADY KNOW ABOUT THIS THINKER'S POSITIONS:\n"
    for c in context_claims[:15]:
        context_text += f"  [{c['date_published']}] {c['claim_text'][:150]}\n"
    context_text += "\nTHEIR EXISTING PREDICTIONS:\n"
    for p in context_preds:
        context_text += f"  {p['prediction_id']}: {p['claim_text'][:100]} [{p['status']}]\n"

    return load_and_render(
        "extraction/raw.txt",
        thinker_name=thinker['name'],
        credibility_score=f"{thinker['credibility_score']:.1f}",
        source_title=meta.get('title', 'Unknown'),
        platform=meta.get('platform', 'unknown'),
        date=meta.get('date', 'unknown'),
        url=meta.get('url', ''),
        context=context_text,
        raw_content=raw_text[:12000],
    )
