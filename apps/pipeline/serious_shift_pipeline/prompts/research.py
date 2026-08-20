"""
Prompt builder for per-shift deep research (steps/research).

The research call runs sync on the synthesis tier with SERVER tools
(web_search / web_fetch) — the API executes the searching and fetching inside
one request. The model's output is only a pointer list: steps/research.py
re-fetches every cited URL itself and verifies each quote against our own
stored copy before anything enters the evidence pack.
"""
from __future__ import annotations

from ._loader import load_and_render


def sphere_scan_prompt(*, sphere: str, sphere_description: str, lens: str,
                       sectors: list[str], today: str) -> str:
    """Discovery sweep for one sphere × lens — the breadth pass the map's
    shifts are named from (phase 3 clusters these claims)."""
    return load_and_render(
        "research/sphere_scan.txt",
        sphere=sphere,
        sphere_description=sphere_description,
        lens=lens,
        sectors=", ".join(sectors),
        today=today,
    )


def shift_research_prompt(*, shift_name: str, subtitle: str, sphere: str,
                          sphere_description: str, sectors: list[str],
                          today: str, context: str = "") -> str:
    return load_and_render(
        "research/shift_research.txt",
        shift_name=shift_name,
        subtitle=subtitle or "(no subtitle yet — a candidate shift)",
        sphere=sphere,
        sphere_description=sphere_description,
        sectors=", ".join(sectors),
        today=today,
        context=context,
    )
