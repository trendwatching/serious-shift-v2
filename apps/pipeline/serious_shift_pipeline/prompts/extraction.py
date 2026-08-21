"""
Prompt builder for raw-content extraction (steps/process_raw).

Extracts structured intelligence (source, claims, predictions, position changes)
from a primary source, with the thinker's known positions as context. Runs on the
default EXTRACTION_MODEL (Haiku 4.5) — the step calls llm.call()/llm.call_batch() without an
override, so the model lives in core/config.py, not here.
"""
from ._loader import load_and_render


def primary_origin_prompt(claim_text: str, statistic: str, context: str) -> str:
    """Provenance audit for one statistic-bearing claim (steps/primary_chase).
    Cheap-tier model; the response is a strict JSON verdict and the only URL it
    may return is one already present verbatim in the passage."""
    return load_and_render(
        "extraction/primary_origin.txt",
        claim_text=claim_text,
        statistic=statistic,
        context=context,
    )


def extraction_prompt(thinker: dict, meta: dict, raw_text: str,
                      context_claims: list, context_preds: list,
                      part: tuple[int, int] | None = None) -> str:
    """`raw_text` is one extraction unit — the whole source, or one chunk of a
    long source (process_raw splits at ~SS_EXTRACTION_CHUNK_CHARS; it used to
    truncate at 12k chars here, which silently discarded two thirds of a
    typical podcast transcript). `part=(j, n)` marks chunk j of n so the model
    knows the text is a slice, not the full source."""
    context_text = "WHAT WE ALREADY KNOW ABOUT THIS THINKER'S POSITIONS:\n"
    for c in context_claims[:15]:
        context_text += f"  [{c['date_published']}] {c['claim_text'][:150]}\n"
    context_text += "\nTHEIR EXISTING PREDICTIONS:\n"
    for p in context_preds:
        context_text += f"  {p['prediction_id']}: {p['claim_text'][:100]} [{p['status']}]\n"
    if part and part[1] > 1:
        context_text += (
            f"\nNOTE: the text below is part {part[0]} of {part[1]} of one long "
            "source; the other parts are extracted separately. Work only from "
            "the text below and do not guess at content outside it.\n")

    return load_and_render(
        "extraction/raw.txt",
        thinker_name=thinker['name'],
        credibility_score=f"{thinker['credibility_score']:.1f}",
        source_title=meta.get('title', 'Unknown'),
        platform=meta.get('platform', 'unknown'),
        date=meta.get('date', 'unknown'),
        url=meta.get('url', ''),
        context=context_text,
        raw_content=raw_text,
    )
