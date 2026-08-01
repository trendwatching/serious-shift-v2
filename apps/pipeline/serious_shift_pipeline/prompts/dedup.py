"""
Prompt builder for claim deduplication (steps/deduplicate).

Given a batch of ambiguous claim pairs, asks Claude to judge each DUPLICATE or
UNIQUE. The step parses the "N: DUPLICATE/UNIQUE" lines back out.
"""
from ._loader import load_and_render

DEDUP_MODEL = "claude-haiku-4-5"


def dedup_prompt(batch: list) -> str:
    """`batch` is a list of (id_a, text_a, id_b, text_b) tuples."""
    lines = []
    for idx, (id_a, text_a, id_b, text_b) in enumerate(batch):
        lines += [f"Pair {idx + 1}:", f"  A [{id_a}]: {text_a[:200]}", f"  B [{id_b}]: {text_b[:200]}"]
    return load_and_render("dedup/pairs.txt", pairs="\n".join(lines))
