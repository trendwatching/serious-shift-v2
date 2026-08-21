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

from collections import Counter

from ..core.text import url_slug as slugify


def name_key(value: object) -> str:
    """The identity a name is deduplicated on — the same one the URL uses."""
    return slugify(str(value or '')) or ''


#: How many pages one family word may headline across the whole map. The
#: 2026-08-19 content review counted nine "…Blindspot"s, seven "…Premium"s and
#: six "…Arithmetic"s — every one a legal name by the exact-slug rule, and
#: together a map that reads like one author's tic. Two is the cap because a
#: pair can still be a deliberate rhyme; three is a pattern.
NAME_FAMILY_CAP = 2


def family_keys(value: object) -> set[str]:
    """The name patterns a name occupies: its head word, its tail word, and the
    joined tail bigram.

    The bigram is what makes "Deflation Blind Spot" and "Deflation Blindspot"
    the same family — the first registers {deflation, spot, blindspot} and the
    second {deflation, blindspot, deflationblindspot}; they collide on
    `blindspot` no matter how the model spaces it. Tokens shorter than four
    characters are dropped so "AI" or "of" never counts as a family.

    Deliberately no stemming: "Blindness" and "Blindspot" stay distinct. The
    british-spelling lint's calibration note applies here too — an overgreedy
    matcher produces false hits, gets distrusted, and gets switched off. Exact
    squeezed tokens keep the false-positive rate at zero and accept the
    residual.
    """
    tokens = [t for t in name_key(value).split('-') if t]
    keys = set()
    if len(tokens) >= 2 and len(tokens[-2] + tokens[-1]) >= 4:
        keys.add(tokens[-2] + tokens[-1])
    for token in (tokens[0], tokens[-1]) if tokens else ():
        if len(token) >= 4:
            keys.add(token)
    return keys


def family_counter(names) -> Counter:
    """Seed a family ledger from names that already exist on the map."""
    counts: Counter = Counter()
    for name in names:
        counts.update(family_keys(name))
    return counts


def breaches_family_cap(name: object, families: Counter,
                        cap: int = NAME_FAMILY_CAP) -> bool:
    """Whether taking `name` would push any of its families past `cap`."""
    return any(families[key] >= cap for key in family_keys(name))


def choose_unique(candidates: list[dict], want: int, claimed: set[str],
                  families: Counter | None = None,
                  family_cap: int = NAME_FAMILY_CAP,
                  min_want: int = 0,
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

    When a `families` Counter is passed, a candidate whose name would push any
    of its `family_keys` past `family_cap` is walked past exactly like a slug
    collider, and every kept name's families are counted. Pass the same Counter
    shift after shift (and sphere after sphere) and the cap holds map-wide.
    `families=None` disables the check entirely.

    `min_want` is the floor the family cap must yield to. On the 2026-08-19
    remediation run the cap starved the LAST families to choose: with ~200
    names already claimed, every candidate of a late shift echoed some family
    and the strict walk left it 0–2 children against a publication gate of 3 —
    a failed run, to avoid a name echo the gate itself treats as advisory. So
    the strict pass runs first, and only if it kept fewer than `min_want` does
    a second pass re-admit family-breaching (never exact-colliding) spares, in
    the model's own order, up to `min_want`. An echoing name on a publishable
    page beats a page that cannot publish.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for candidate in candidates:
        if len(kept) >= want:
            break
        name = str(candidate.get('name') or '').strip()
        key = name_key(name)
        if not key or key in claimed or (
                families is not None
                and breaches_family_cap(name, families, family_cap)):
            if name:
                dropped.append(candidate)
            continue
        claimed.add(key)
        if families is not None:
            families.update(family_keys(name))
        kept.append(candidate)

    if len(kept) < min_want:
        for candidate in dropped[:]:
            if len(kept) >= min_want:
                break
            name = str(candidate.get('name') or '').strip()
            key = name_key(name)
            if not key or key in claimed:
                continue  # exact twins stay out, whatever the floor
            claimed.add(key)
            if families is not None:
                families.update(family_keys(name))
            kept.append(candidate)
            dropped.remove(candidate)

    return kept, [str(c.get('name') or '').strip() for c in dropped]
