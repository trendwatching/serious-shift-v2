"""
Serious Shift tone of voice — the single source of truth for how generated
content reads. Every content-producing prompt (key trends, sub-trends, editorial
modules, synthesis insights) embeds this block.

The text itself lives in `packages/prompts/voice.txt`. The backend no longer
embeds it — it is a read-only API and makes no model calls — so the pipeline is
the only consumer. Edit the voice THERE and it changes everywhere. `VOICE` is
loaded once at import.
"""
from ._loader import load

VOICE = load("voice.txt")
