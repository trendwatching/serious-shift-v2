"""Draw a handful of shifts locally so the team can look before the fleet pays.

Dev-only, and deliberately not wired into `mapgen`: it reads the *published* map
over HTTP, writes JPEGs to a directory, and touches neither Postgres nor the
document. Nothing here can affect a publication.

It exists because `generate-art.mjs` cannot show this direction. That script
splices the shift's title, arc and dek straight into the prompt; the real
pipeline writes an LLM image brief first (phase 10) and splices that. The brief
is where the metaphor is decided, so a sample without it is a sample of the old
behaviour.

    export $(grep -v '^#' ../frontend/.env.local | xargs)   # GEMINI_API_KEY
    python -m serious_shift_pipeline.mapgen.art.sample \\
        --slug silent-commerce --slug sovereignty-fracture --out /tmp/art

`--dry-run` writes the briefs and the assembled prompts and spends nothing on
images, which is the cheap way to read a prompt change end to end.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import requests

from ...prompts import prompt_art_brief
from ..llm import generate_json
from ..phases.art_briefs import (_context, _with_registers, briefs_from_result,
                                 register_for)
from . import gemini, raster
from .prompts import image_prompt
from .style import DERIVED, FRAMES, spec_for

#: The staging backend, which is what the .mjs defaults to as well.
DEFAULT_ORIGIN = 'https://backend-staging-1c16.up.railway.app'
SPHERES = ('society', 'economy', 'organizations', 'consumers')


def _get(origin: str, path: str) -> dict:
    response = requests.get(f'{origin}{path}', timeout=(10, 60))
    response.raise_for_status()
    return response.json()


def _tail(slug: object) -> str:
    return str(slug or '').rsplit('/', 1)[-1]


def _find(origin: str, wanted: set[str]) -> list[tuple[str, str]]:
    """(sphere, slug) for each wanted shift. The index does not carry modules."""
    found: list[tuple[str, str]] = []
    for sphere in SPHERES:
        body = _get(origin, f'/api/v1/map/{sphere}')
        domain = (body.get('domains') or [body])[0]
        for shift in domain.get('key_shifts') or domain.get('key_trends') or []:
            slug = _tail(shift.get('slug'))
            if slug in wanted:
                found.append((sphere, slug))
    return found


def _family(origin: str, sphere: str, slug: str) -> tuple[dict, list[dict]]:
    """The shift as phase 10 sees it, plus its sub-shifts.

    Sub slugs are rebuilt as `parent/child` rather than taken as returned: that
    is the form the published document uses, and the register is keyed on the
    slug — a sample drawn from a different slug string would preview a different
    composition from the one the real run produces.
    """
    body = _get(origin, f'/api/v1/map/{sphere}/{slug}')
    shift = body.get('shift') or body.get('key_shift') or body.get('key_trend') or body
    subs = []
    for sub in body.get('sub_shifts') or body.get('sub_trends') or []:
        subs.append({**sub, 'slug': f'{slug}/{_tail(sub.get("slug"))}'})
    return shift, subs


def _write(stem: Path, prompt: str, image: bytes | None, scope: str, frame: str) -> None:
    """The master and every crop that rides on it, exactly as the pipeline cuts
    them — so what the team looks at is what the site would serve."""
    stem.with_suffix('.prompt.txt').write_text(prompt, encoding='utf-8')
    if image is None:
        return
    from PIL import Image
    with Image.open(io.BytesIO(image)) as master:
        print(f'      master {frame}: {master.width}x{master.height}')
    for out in (frame, *DERIVED.get((scope, frame), ())):
        spec = spec_for(out)
        encoded, _ = raster.cover_crop(image, int(spec['width']), int(spec['height']),
                                       int(spec['quality']))
        stem.with_suffix(f'.{out}.jpg').write_bytes(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slug', action='append', required=True,
                        help='key shift slug, repeatable')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--origin', default=DEFAULT_ORIGIN)
    parser.add_argument('--dry-run', action='store_true',
                        help='write briefs and prompts, generate no images')
    parser.add_argument('--max-subs', type=int, default=5)
    args = parser.parse_args(argv)

    wanted = {_tail(s) for s in args.slug}
    families = _find(args.origin, wanted)
    missing = wanted - {slug for _, slug in families}
    if missing:
        print(f'not on the published map: {", ".join(sorted(missing))}', file=sys.stderr)
    if not families:
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    work = [(sphere, slug, *_family(args.origin, sphere, slug))
            for sphere, slug in families]
    for _, _, _, subs in work:
        del subs[args.max_subs:]

    print(f'writing briefs for {len(work)} famil(y/ies)…')
    results = generate_json(
        work,
        lambda item: prompt_art_brief(item[2].get('name', ''), item[2].get('subtitle', ''),
                                      _context(item[2]), _with_registers(item[3], item[1]),
                                      register_for(item[1])),
        default=lambda: {},
        describe=lambda item: str(item[1]),
    )

    briefs: dict[str, str] = {}
    jobs: list[tuple[str, str, str, str, str]] = []  # name, sphere, slug, scope, frame
    for (sphere, slug, _shift, subs), result in zip(work, results):
        # Parsed and filtered by the real phase, not by a copy of it — a sample
        # that showed briefs production would have rejected is a sample of the
        # wrong thing, which is how a "handwritten recipe card" got through.
        brief, sub_briefs = briefs_from_result(result, slug, subs)
        if brief:
            briefs[slug] = brief
            jobs += [(slug, sphere, slug, 'key_trend', frame)
                     for frame in ('hero', 'wide')]
        else:
            print(f'  {slug}: no usable brief for the key shift; subs continue')
        for sub_slug, sub_brief in sub_briefs:
            briefs[sub_slug] = sub_brief
            jobs += [(sub_slug, sphere, sub_slug, 'sub_trend', frame)
                     for frame in ('tile', 'wide')]

    (args.out / 'briefs.json').write_text(
        json.dumps(briefs, indent=2, ensure_ascii=False, sort_keys=True), encoding='utf-8')

    cost = 0.0
    for name, sphere, slug, scope, frame in jobs:
        prompt = image_prompt(sphere, frame, briefs[slug])
        stem = args.out / f'{name.replace("/", "__")}.{frame}'
        image = None
        if not args.dry_run:
            try:
                image = gemini.generate_image(prompt, str(FRAMES[frame]['aspect']))
            except gemini.GeminiError as exc:
                print(f'  {name} {frame}: {exc}')
            else:
                cost += gemini.COST_PER_IMAGE
        print(f'  {stem.name}{"" if image else " (prompt only)"}')
        _write(stem, prompt, image, scope, frame)

    print(f'{len(briefs)} brief(s), {len(jobs)} image(s), ${cost:.2f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
