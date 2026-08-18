"""Generate each shift's artwork and attach its URLs to the candidate map.

WHERE THIS RUNS, and why it matters: inside `_publish_candidate`, AFTER the gate
passes and BEFORE `_write_map_document`. Slugs are only final at export — the
targeted repair pass can re-cluster sub-shifts and mint new names — and art is
keyed by slug, so generating any earlier would key images to slugs that no longer
exist by the time the document is written.

THE ONE RULE: `generate_and_attach` never raises. Art is decoration; the taxonomy
is content. A Gemini outage, an expired key, a decode error, a spend ceiling —
each of them must cost this week's new images and nothing else. The map publishes
regardless, reusing whatever is already in `shift_art` and falling back to the
deterministic vector posters in heroes.json for anything missing, which the
frontend treats as a finished design rather than a placeholder.
"""
from __future__ import annotations

import os
import time

from ...core import parallel
from . import gemini, raster, store
from .prompts import image_prompt, prompt_sha256
from .style import FRAMES, OG, STYLE_NAME

#: Off switch. The lever to pull at 2am without deploying anything.
ENABLED = os.environ.get('SS_ART', '1') != '0'
#: Regenerate even where the prompt hash matches.
FORCE = os.environ.get('SS_ART_FORCE', '') == '1'
#: Matches the .mjs pool. Workers do network + Pillow only; DB writes stay on
#: the main thread, because psycopg connections are not thread-safe.
WORKERS = int(os.environ.get('SS_ART_WORKERS', '4'))
#: A runaway guard, not a budget. The 18 Aug 2026 decision was "no cap, generate
#: everything"; this exists so a bug cannot spend without bound.
BUDGET_USD = float(os.environ.get('SS_ART_BUDGET_USD', '60'))
#: Stop dispatching after this long. A 25-minute run silently becoming a
#: 90-minute one is its own kind of outage.
DEADLINE_SECONDS = float(os.environ.get('SS_ART_DEADLINE_SECONDS', '2400'))
#: Rows committed per batch. Bounds peak memory to a few tens of MB rather than
#: holding every encoded variant.
CHUNK = 16


def _sub_parent(sub: dict) -> str:
    return str(sub.get('slug') or '').rsplit('/', 1)[0]


def _jobs(out: dict, briefs: dict) -> list[dict]:
    """One job per image to generate. `og` is not a job — it is a crop of `wide`."""
    jobs = []
    for shift in out.get('key_trends') or []:
        slug = str(shift.get('slug') or '')
        if not slug:
            continue
        concept = briefs.get(('key_trend', slug))
        if not concept:
            continue
        for frame in ('hero', 'wide'):
            jobs.append({'scope': 'key_trend', 'slug': slug, 'frame': frame,
                         'sphere': str(shift.get('domain_id') or ''),
                         'prompt': image_prompt(shift.get('domain_id'), frame, concept)})
    for sub in out.get('sub_trends') or []:
        slug = str(sub.get('slug') or '')
        if not slug or '/' not in slug:
            continue
        concept = briefs.get(('sub_trend', slug))
        if not concept:
            continue
        jobs.append({'scope': 'sub_trend', 'slug': slug, 'frame': 'tile',
                     'sphere': str(sub.get('domain_id') or ''),
                     'prompt': image_prompt(sub.get('domain_id'), 'tile', concept)})
    return jobs


def _outputs(job: dict, master: bytes) -> list[dict]:
    """The rows one generated master produces. `wide` also yields `og`, free."""
    rows = []
    spec = FRAMES[job['frame']]
    encoded, digest = raster.cover_crop(master, int(spec['width']), int(spec['height']),
                                        int(spec['quality']))
    rows.append({**job, 'bytes': encoded, 'sha256': digest,
                 'width': spec['width'], 'height': spec['height'],
                 'byte_size': len(encoded), 'style': STYLE_NAME,
                 'model': gemini.MODEL})
    if job['frame'] == OG['from']:
        encoded, digest = raster.cover_crop(master, int(OG['width']), int(OG['height']),
                                            int(OG['quality']))
        rows.append({**job, 'frame': 'og', 'bytes': encoded, 'sha256': digest,
                     'width': OG['width'], 'height': OG['height'],
                     'byte_size': len(encoded), 'style': STYLE_NAME,
                     'model': gemini.MODEL})
    return rows


def _attach(out: dict, art: dict) -> int:
    """Write the art URLs onto the candidate. Absent art means an ABSENT key.

    Never `null` and never a URL to nothing: the frontend's precedence chain
    treats a falsy value as "fall through to the next source", and a URL that
    404s would instead paint a broken image over a working gradient.

    `?v=` carries the content digest, which is what makes the swap instant
    through any cache and lets the route answer `immutable` safely.
    """
    attached = 0

    def url(scope: str, slug: str, frame: str) -> str | None:
        row = art.get((scope, slug, frame))
        return f'/art/{frame}/{slug}.jpg?v={row["sha256"][:12]}' if row else None

    hero_by_shift: dict[str, tuple[str | None, str | None, str | None]] = {}
    for shift in out.get('key_trends') or []:
        slug = str(shift.get('slug') or '')
        hero, wide = url('key_trend', slug, 'hero'), url('key_trend', slug, 'wide')
        og = url('key_trend', slug, 'og')
        hero_by_shift[slug] = (hero, wide, og)
        for key, value in (('hero_image', hero), ('hero_image_wide', wide),
                           ('og_image', og)):
            if value:
                shift[key] = value
                attached += 1

    for sub in out.get('sub_trends') or []:
        slug = str(sub.get('slug') or '')
        tile = url('sub_trend', slug, 'tile')
        if tile:
            sub['tile_image'] = tile
            attached += 1
        # A sub-shift page inherits its parent's poster and its link-preview
        # card; only the tile is its own. seo.rs reads og_image straight off the
        # row, so without this a sub-shift page would fall back to the committed
        # static card while its parent used the generated one.
        hero, wide, og = hero_by_shift.get(_sub_parent(sub), (None, None, None))
        if hero:
            sub['hero_image'] = hero
        if wide:
            sub['hero_image_wide'] = wide
        if og:
            sub['og_image'] = og
    return attached


def generate_and_attach(conn, out: dict, briefs: dict | None = None) -> dict:
    """Generate what is missing, attach every URL we have. Never raises."""
    stats = {'generated': 0, 'reused': 0, 'failed': 0, 'skipped': 0,
             'cost_usd': 0.0, 'attached': 0}
    try:
        art = store.load_art(conn)
        if not ENABLED:
            print('  art: SS_ART=0 — attaching existing rows only')
        elif not gemini.api_key():
            # Deliberately not fatal, unlike the ANTHROPIC_API_KEY check in
            # cli.main: a map with last week's art is a good map.
            print('  art: GEMINI_API_KEY not set — attaching existing rows only')
        else:
            stats.update(_generate(conn, out, briefs or {}, art))
            art = store.load_art(conn)
        stats['attached'] = _attach(out, art)
    except Exception as exc:  # noqa: BLE001 — the whole point is that nothing escapes
        print(f'  art: generation failed ({type(exc).__name__}: {exc}) — '
              f'publishing the map without new artwork')
        stats['failed'] += 1
    return stats


def _generate(conn, out: dict, briefs: dict, art: dict) -> dict:
    generated = reused = failed = skipped = 0
    started = time.monotonic()
    pending = []
    for job in _jobs(out, briefs):
        job['prompt_sha256'] = prompt_sha256(
            gemini.MODEL, FRAMES[job['frame']]['aspect'], job['prompt'])
        existing = art.get((job['scope'], job['slug'], job['frame']))
        if not FORCE and existing and existing['prompt_sha256'] == job['prompt_sha256'] \
                and existing['model'] == gemini.MODEL:
            reused += 1
            continue
        pending.append(job)

    if not pending:
        print(f'  art: {reused} image(s) already current, nothing to generate')
        return {'generated': 0, 'reused': reused, 'failed': 0, 'skipped': 0,
                'cost_usd': 0.0}

    print(f'  art: {len(pending)} image(s) to generate, {reused} already current '
          f'(~${len(pending) * gemini.COST_PER_IMAGE:.2f})')

    def run(job):
        # pmap propagates exceptions when the result list is materialised, so a
        # worker that raises would take the whole chunk with it. Catch here and
        # return a sentinel — the pattern core/parallel.py's docstring asks for.
        try:
            return job, gemini.generate_image(
                job['prompt'], FRAMES[job['frame']]['aspect']), ''
        except Exception as exc:  # noqa: BLE001 — one image, not a run
            return job, None, f'{type(exc).__name__}: {exc}'

    for start in range(0, len(pending), CHUNK):
        if time.monotonic() - started > DEADLINE_SECONDS:
            skipped = len(pending) - start
            print(f'  art: deadline reached — {skipped} image(s) left for next run')
            break
        if generated * gemini.COST_PER_IMAGE > BUDGET_USD:
            skipped = len(pending) - start
            print(f'  art: ${BUDGET_USD:.2f} ceiling reached — {skipped} left')
            break
        chunk = pending[start:start + CHUNK]
        rows: list[dict] = []
        for job, master, error in parallel.pmap(run, chunk, workers=WORKERS):
            if master is None:
                print(f'    art: {job["slug"]} {job["frame"]} — {error}')
                failed += 1
                continue
            try:
                rows.extend(_outputs(job, master))
                generated += 1
            except Exception as exc:  # noqa: BLE001 — one bad image, not a run
                print(f'    art: {job["slug"]} {job["frame"]} — {exc}')
                failed += 1
        if rows:
            # Committed as we go. Nothing can reach these rows until the document
            # names them, so partial progress is invisible but not wasted.
            store.upsert_art(conn, rows)
            conn.commit()

    return {'generated': generated, 'reused': reused, 'failed': failed,
            'skipped': skipped, 'cost_usd': round(generated * gemini.COST_PER_IMAGE, 2)}
