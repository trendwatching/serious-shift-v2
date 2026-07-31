"""
Serious Shift prompt registry — the single place where every Claude request is
built. Each submodule holds the prompt text for one pipeline area plus the model
that request runs on; response parsing and orchestration live in the steps.

  voice       — VOICE tone-of-voice block, embedded by every content prompt
  map_data    — trend-map generation (key trends, sub-trends, attribution, links, insights)
  keynote     — one narrative section per Key Trend
  extraction  — structured extraction from raw sources (process_raw)
  dedup       — DUPLICATE/UNIQUE judgement for claim pairs
  ingest      — ad-hoc single-URL extraction

Import from the package root, e.g.:
  from ..prompts import VOICE, prompt_domain_key_trends, SYNTHESIS_MODEL
"""
from .voice import VOICE
from .map_data import (
    SYNTHESIS_MODEL,
    INSIGHTS_MODEL,
    MIN_KTS_PER_DOM,
    fmt_claims_block,
    prompt_domain_key_trends,
    prompt_sub_trends,
    prompt_kt_editorial,
    prompt_st_editorial,
    prompt_thinker_attribution,
    prompt_interrelatedness_batch,
    prompt_synthesis_insights,
)
from .keynote import KEYNOTE_MODEL, keynote_section_prompt
from .extraction import extraction_prompt
from .dedup import DEDUP_MODEL, dedup_prompt
from .ingest import INGEST_MODEL, ingest_prompt

__all__ = [
    "VOICE",
    "SYNTHESIS_MODEL",
    "INSIGHTS_MODEL",
    "MIN_KTS_PER_DOM",
    "fmt_claims_block",
    "prompt_domain_key_trends",
    "prompt_sub_trends",
    "prompt_kt_editorial",
    "prompt_st_editorial",
    "prompt_thinker_attribution",
    "prompt_interrelatedness_batch",
    "prompt_synthesis_insights",
    "KEYNOTE_MODEL",
    "keynote_section_prompt",
    "extraction_prompt",
    "DEDUP_MODEL",
    "dedup_prompt",
    "INGEST_MODEL",
    "ingest_prompt",
]
