"""
Serious Shift tone of voice — the single source of truth for how generated
content reads. Every content-producing prompt (keynote, key trends, sub-trends,
synthesis insights, and the backend's /api/personalize) embeds this block.

The text itself lives in `packages/prompts/voice.txt` and is shared verbatim with
the Rust backend (which embeds the same file via include_str!). Edit the voice
THERE and it changes everywhere. `VOICE` is loaded once at import.
"""
from ._loader import load

VOICE = load("voice.txt")
