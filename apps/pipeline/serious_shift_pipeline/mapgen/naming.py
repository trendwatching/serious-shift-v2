"""Making a name unique without asking the model again.

The name ledger the phases thread through their prompts is an *ask*, and asks
can fail. Until now that was the only mechanism: three re-asks, and if a
duplicate survived, the phase printed "publication will reject them" and let the
gate fail the entire run — after every paid phase had already been paid for.

Three things could happen at that point, and only one of them is acceptable:

  - publish the twin. Two pages a reader cannot tell apart, which is the exact
    defect the ledger exists to prevent (22 names over 58 pages, 2026-08-09).
  - mint a machine name. A "-2" in a URL nobody chose, and a name no editor
    would have written.
  - walk past the collider to the next candidate the model already returned.

The third is free. The model routinely returns more candidates than the five we
ask for, and every one of them is real editorial that has already been paid for.
Choosing among them is deterministic, costs nothing, and cannot fail — so it
belongs after the asks, not instead of them. The re-ask ladder still runs first,
because it produces better names; this is what happens when it does not.

Names are compared on `url_slug`, which is what the publication gate compares
(`duplicate_sub_shift_slug`, `sub_shift_shadows_shift`) and what a reader's URL
bar compares. Anything looser here and the two disagree again.
"""
from __future__ import annotations

from ..core.text import url_slug as slugify


def name_key(value: object) -> str:
    """The identity a name is deduplicated on — the same one the URL uses."""
    return slugify(str(value or '')) or ''


def choose_unique(candidates: list[dict], want: int, claimed: set[str],
                  ) -> tuple[list[dict], list[str]]:
    """The first `want` candidates whose names nobody else is already wearing.

    `claimed` is mutated: every kept name is added, so the caller can walk shift
    after shift and have each one see what all the previous ones took. Seed it
    with the key-shift names and a sub-shift can never be born wearing its own
    parent's name.

    Returns `(kept, dropped_names)`. `kept` may be shorter than `want` when the
    spares run out — publishing four children is explicitly allowed by the gate
    (`4 <= len(children) <= 5`, there so an editor can merge two), and four real
    names beat five with a twin among them.
    """
    kept: list[dict] = []
    dropped: list[str] = []
    for candidate in candidates:
        if len(kept) >= want:
            break
        name = str(candidate.get('name') or '').strip()
        key = name_key(name)
        if not key or key in claimed:
            if name:
                dropped.append(name)
            continue
        claimed.add(key)
        kept.append(candidate)
    return kept, dropped
