"""Generated artwork: geometry, idempotency, and the rule that it never blocks.

The load-bearing test here is the isolation one. Art generation is now the most
expensive and most failure-prone step in a run that otherwise fails closed, and
a Gemini outage must cost this week's images rather than the taxonomy.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from serious_shift_pipeline.mapgen import art
from serious_shift_pipeline.mapgen.art import gemini, raster
from serious_shift_pipeline.mapgen.art.prompts import (concept_from_modules,
                                                       image_prompt, prompt_sha256)
from serious_shift_pipeline.mapgen.art.style import (FRAMES, MASTER_PIXELS, OG, RAMP,
                                                      ramp_for)
from serious_shift_pipeline.mapgen.phases.art_briefs import (ART_BRIEF_PROMPT_VERSION,
                                                             CONTEXT_LIMIT, REGISTERS,
                                                             _context, _with_registers,
                                                             brief_inputs_sha256,
                                                             briefs_from_result,
                                                             describes_written_matter,
                                                             register_for)


def _png(width=1024, height=1024, colour=(120, 30, 90)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (width, height), colour).save(buffer, 'PNG')
    return buffer.getvalue()


def _document():
    return {
        'key_trends': [{'slug': 'silent-commerce', 'name': 'Silent Commerce',
                        'domain_id': 'consumers', 'subtitle': 's', 'modules': []}],
        'sub_trends': [{'slug': 'silent-commerce/charm-arithmetic',
                        'name': 'Charm Arithmetic', 'domain_id': 'consumers',
                        'subtitle': 's', 'modules': []}],
    }


# ── geometry: Pillow must do exactly what object-fit: cover did ──────────

@pytest.mark.parametrize('frame', ['hero', 'wide', 'tile'])
def test_each_frame_lands_on_its_exact_pixel_size(frame):
    spec = FRAMES[frame]
    encoded, digest = raster.cover_crop(_png(), spec['width'], spec['height'],
                                        spec['quality'])
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (spec['width'], spec['height'])
        assert image.format == 'JPEG'
    assert len(digest) == 64


def test_og_is_a_crop_of_the_wide_master_not_a_second_generation():
    """One generation, two outputs — which is why the OG card costs nothing."""
    assert OG['from'] == 'wide'
    master = _png()
    encoded, _ = raster.cover_crop(master, OG['width'], OG['height'], OG['quality'])
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (1200, 630)


def test_a_portrait_master_still_covers_a_panoramic_frame():
    encoded, _ = raster.cover_crop(_png(800, 1400), 1600, 600, 80)
    with Image.open(io.BytesIO(encoded)) as image:
        assert (image.width, image.height) == (1600, 600)


def test_the_digest_is_over_the_encoded_bytes():
    """It is the ETag and the ?v= cache-buster, so identical input must give an
    identical URL and a regeneration must give a different one."""
    first, digest_a = raster.cover_crop(_png(colour=(10, 20, 30)), 640, 640, 78)
    _, digest_b = raster.cover_crop(_png(colour=(10, 20, 30)), 640, 640, 78)
    _, digest_c = raster.cover_crop(_png(colour=(200, 10, 10)), 640, 640, 78)
    assert digest_a == digest_b != digest_c
    assert first[:2] == b'\xff\xd8'  # JPEG SOI


# ── prompt assembly and idempotency ──────────────────────────────────────

def test_the_style_and_the_guards_are_not_the_brief_to_argue_with():
    prompt = image_prompt('consumers', 'hero', 'A queue of people at a doorway.')
    assert RAMP['consumers']['hot'] in prompt
    assert 'A queue of people at a doorway.' in prompt
    assert FRAMES['hero']['clause'] in prompt
    assert 'Absolutely no text anywhere in the image' in prompt
    assert 'No explanatory symbols of any kind' in prompt


def test_the_image_prompt_bans_what_the_first_fleet_kept_drawing():
    """19 Aug 2026 review: arrows, lightning and people at screens, everywhere.

    The brief prompt bans these too, but a brief is written by a different model
    from the image, and this one volunteers them unprompted.
    """
    prompt = image_prompt('society', 'wide', 'A field after rain.')
    for banned in ('no arrows', 'no lightning bolts', 'no circuitry',
                   'no rising graphs', 'nobody looking at a screen'):
        assert banned in prompt


def test_the_register_is_stable_for_a_slug_and_spread_across_the_set():
    """The register reaches the image through the brief, and the brief is hashed.

    Anything that moved — a position in a list, a count of siblings — would re-pay
    for a family's images the first time the repair pass re-clustered a sub-shift.
    """
    assert register_for('silent-commerce') == register_for('silent-commerce')
    assert register_for('') in REGISTERS
    picks = {register_for(f'shift-{i}') for i in range(60)}
    assert picks == set(REGISTERS), 'every register should be reachable'


def test_no_two_siblings_get_the_same_register():
    """Independent hashing was tried first: with six registers and four siblings a
    collision is more likely than not, and the sub tiles are exactly where it
    shows — they sit next to each other on one page."""
    subs = [{'slug': f'parent/sub-{i}'} for i in range(5)]
    for parent in ('parent', 'another-parent', 'a-third'):
        picked = [sub['register'] for sub in _with_registers(subs, parent)]
        assert len(set(picked)) == len(picked), picked
        assert register_for(parent) not in picked, 'a child repeats its parent'


def test_sibling_registers_survive_a_reordered_export():
    """Ranked by slug, not by array position: a document the export happened to
    emit in another order must not repaint the family."""
    subs = [{'slug': f'parent/sub-{i}'} for i in range(4)]
    forward = {s['slug']: s['register'] for s in _with_registers(subs, 'parent')}
    backward = {s['slug']: s['register']
                for s in _with_registers(list(reversed(subs)), 'parent')}
    assert forward == backward


def test_the_register_is_not_stapled_onto_the_image_prompt():
    """It was, first. A register picked in code contradicts the scene as often as
    it shapes it — "a crowd seen whole" landing under a brief about two people in
    a doorway — so it is given to the brief writer, which cannot disagree with
    itself."""
    prompt = image_prompt('society', 'hero', 'Two people in a flooded doorway.')
    assert not any(register in prompt for register in REGISTERS)


def test_the_hero_frame_no_longer_mandates_a_crowd():
    """It used to read "lands on the crowd in the lower third", which put the same
    composition under every key shift and left the register nothing to vary."""
    assert 'crowd' not in FRAMES['hero']['clause']


def test_an_unknown_sphere_falls_back_rather_than_raising():
    assert ramp_for('not-a-sphere') == RAMP['society']
    assert ramp_for('') == RAMP['society']


def test_the_hash_covers_the_model_and_the_aspect_not_just_the_words():
    """The same words at a different aspect ratio are a different image."""
    base = prompt_sha256('m', '4:5', 'p')
    assert base != prompt_sha256('m', '21:9', 'p')
    assert base != prompt_sha256('other', '4:5', 'p')
    assert base != prompt_sha256('m', '4:5', 'p2')
    assert base == prompt_sha256('m', '4:5', 'p')


def test_the_fallback_concept_keeps_a_sentence_case_initial_intact():
    """"AI treated as…" must not become "aI treated as…"."""
    concept = concept_from_modules('X', arc_from='AI treated as a tool',
                                   arc_to='AI treated as a colleague')
    assert 'AI treated as a tool' in concept
    concept = concept_from_modules('X', arc_from='Trust in brands',
                                   arc_to='Trust in agents')
    assert 'trust in brands' in concept


# ── what the brief writer is allowed to read ─────────────────────────────

def _shift_with_modules():
    return {'name': 'X', 'subtitle': 'y', 'modules': [
        {'type': 'from_to', 'data': {'from': 'A', 'to': 'B'}},
        {'type': 'dek', 'data': {'text': 'The dek.'}},
        {'type': 'peel_tabs', 'data': {'whats_changing': 'CHANGING',
                                       'why_now': 'NOW'}},
        {'type': 'tension_band', 'data': {'quote': 'TENSION'}},
        {'type': 'human_needs', 'data': {'unlocked': 'UNLOCKED',
                                         'threatened': 'THREATENED'}},
        {'type': 'industries', 'data': {'items': ['FURNITURE']}},
        {'type': 'territories', 'data': {'items': ['FURNITURE']}},
        {'type': 'timeline', 'data': {'steps': ['FURNITURE']}},
    ]}


def test_the_brief_reads_the_thesis_and_not_the_page_furniture():
    """The tension is what a metaphor is drawn from, and it used to be withheld —
    which is why the first fleet illustrated the subject matter instead."""
    context = _context(_shift_with_modules())
    for wanted in ('A', 'B', 'The dek.', 'CHANGING', 'NOW', 'TENSION',
                   'UNLOCKED', 'THREATENED'):
        assert wanted in context
    # Industries, territories and timeline stay out: hand those over and the brief
    # describes the page rather than the shift.
    assert 'FURNITURE' not in context


@pytest.mark.parametrize('brief', [
    'the numbers are still impressed into the paper, legible as grooves',
    'A hand-lettered placard leans against the doorway.',
    'A price tag pinned through the produce.',
    'Rows of jars, each with a paper label.',
])
def test_a_brief_that_describes_writing_is_rejected(brief):
    """Seen on the first metaphor-first sample run: a brief about ink and numbers
    came back as a picture full of garbled figures. The image prompt's ban on text
    cannot un-ask for a price tag, so the brief has to be stopped instead."""
    assert describes_written_matter(brief)


@pytest.mark.parametrize('brief', [
    'A number of people wait at the gate.',
    'Any number of crates stacked against the wall.',
    'Shelves of unlabelled jars in a cold room.',
    'A vast airport concourse, hundreds of travellers moving in loose streams.',
    'A wooden crate on a concrete floor, packing straw spilling over the edge.',
])
def test_the_guard_does_not_reject_a_scene_with_nothing_written_in_it(brief):
    """A false positive costs a shift its new artwork for the week, so the common
    quantity idiom is excused and "unlabelled" — a scene with no writing in it —
    must pass."""
    assert not describes_written_matter(brief)


def test_a_sub_shift_with_no_brief_makes_its_family_stale(monkeypatch):
    """A rejected KEY shift self-heals — its missing row makes the family stale
    next run. A rejected SUB-shift did not: the parent stayed current every week,
    the family was skipped on the parent's word, and the sub had no art forever.
    A publish on 2026-08-20 left four sub-shifts art-less exactly this way."""
    from serious_shift_pipeline.mapgen.phases import art_briefs as ab

    shift = {'slug': 'p', 'name': 'P', 'subtitle': 's', 'modules': []}
    subs = [{'slug': 'p/a', 'name': 'A'}, {'slug': 'p/b', 'name': 'B'}]
    out = {'key_trends': [shift], 'sub_trends': subs}
    digest = ab.brief_inputs_sha256(shift, subs)

    # Parent and ONE sub stored; the other was rejected and has no row.
    monkeypatch.setattr(ab.store, 'load_briefs', lambda conn: {
        ('key_trend', 'p'): {'brief': 'parent scene', 'input_sha256': digest},
        ('sub_trend', 'p/a'): {'brief': 'a scene', 'input_sha256': digest},
    })
    asked: list = []

    def fake_generate(items, prompt_of, **kwargs):
        asked.extend(items)
        return [{'shift': {'brief': 'NEW parent'},
                 'sub_shifts': [{'name': 'A', 'brief': 'NEW a'},
                                {'name': 'B', 'brief': 'b scene'}]}]

    monkeypatch.setattr(ab, 'generate_json', fake_generate)
    monkeypatch.setattr(ab.store, 'upsert_briefs', lambda conn, rows: None)
    briefs = ab.phase10_art_briefs(_FakeConn(), out)

    assert asked, 'the family must be re-asked to fill the gap'
    assert briefs[('sub_trend', 'p/b')] == 'b scene', 'the missing brief is adopted'
    # The ones that already existed keep their exact text, or every sibling image
    # re-pays for nothing.
    assert briefs[('key_trend', 'p')] == 'parent scene'
    assert briefs[('sub_trend', 'p/a')] == 'a scene'


class _FakeConn:
    def commit(self): pass


def test_a_rejected_parent_does_not_take_its_sub_shifts_down_with_it():
    """Losing five pages of artwork to one bad word on the parent is a far worse
    trade than the parent going a week without."""
    result = {'shift': {'brief': 'A wall of handwritten numbers.'},
              'sub_shifts': [{'name': 'Charm Collapse', 'brief': 'A knot in weathered timber.'}]}
    subs = [{'name': 'Charm Collapse', 'slug': 'silent-commerce/charm-collapse'}]
    shift_brief, sub_briefs = briefs_from_result(result, 'silent-commerce', subs)
    assert shift_brief == ''
    assert sub_briefs == [('silent-commerce/charm-collapse', 'A knot in weathered timber.')]


def test_the_sample_tool_filters_exactly_like_the_phase():
    """The sample is what the team reviews before a fleet regeneration. One that
    parsed or filtered differently would be a review of the wrong thing — which is
    what happened when it had its own copy and let a handwritten card through."""
    from serious_shift_pipeline.mapgen.art import sample
    assert sample.briefs_from_result is briefs_from_result


def test_a_runaway_context_is_cut_on_a_word_boundary():
    """A 900-char cap used to bite on the first real shift tried, and it took the
    last slot — the human need threatened — with it. That slot is the tension the
    brief is asked to draw, so losing it silently is the expensive failure."""
    shift = {'modules': [{'type': 'peel_tabs',
                          'data': {'whats_changing': 'word ' * 2000}}]}
    context = _context(shift)
    assert len(context) <= CONTEXT_LIMIT + 1        # +1 for the ellipsis
    assert context.endswith('…')
    assert 'wor…' not in context


def test_a_normal_shift_is_never_truncated():
    """The cap is a runaway guard, not a budget: every field feeding it is already
    word-capped by FIELD_WORD_LIMITS."""
    assert '…' not in _context(_shift_with_modules())


def test_the_context_orders_itself_not_the_export():
    """Two documents that differ only in module order must hash the same, or a
    reordering that changes nothing a reader sees re-pays for every image."""
    shift = _shift_with_modules()
    shuffled = {**shift, 'modules': list(reversed(shift['modules']))}
    assert brief_inputs_sha256(shift, []) == brief_inputs_sha256(shuffled, [])


def test_bumping_the_prompt_version_rewrites_every_brief(monkeypatch):
    """Editing art_brief.txt alone is a silent no-op — the hash covers the shift's
    editorial, not the prompt. The version constant is the only thing that makes a
    prompt change reach the model."""
    shift = _shift_with_modules()
    before = brief_inputs_sha256(shift, [])
    monkeypatch.setattr('serious_shift_pipeline.mapgen.phases.art_briefs.'
                        'ART_BRIEF_PROMPT_VERSION', ART_BRIEF_PROMPT_VERSION + 1)
    assert brief_inputs_sha256(shift, []) != before


# ── the rule: art never blocks a publish ─────────────────────────────────

class _Conn:
    def __init__(self):
        self.committed = 0

    def execute(self, sql, params=None):
        return type('_C', (), {'fetchall': lambda _s: [], 'fetchone': lambda _s: None})()

    def commit(self):
        self.committed += 1


def test_a_dead_gemini_never_raises_and_the_document_survives(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    monkeypatch.setattr(gemini, 'generate_image',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    document = _document()
    stats = art.generate_and_attach(
        _Conn(), document, {('key_trend', 'silent-commerce'): 'a brief'})
    assert stats['failed'] >= 1
    # No key means no key: the frontend falls through to its gradient, which is
    # a finished design. A null or a 404 URL would paint a broken image instead.
    assert 'hero_image' not in document['key_trends'][0]


def test_no_api_key_is_not_fatal(monkeypatch):
    """Unlike the ANTHROPIC_API_KEY check in cli.main, which exits 1."""
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    document = _document()
    stats = art.generate_and_attach(_Conn(), document, {})
    assert stats['generated'] == 0
    assert 'hero_image' not in document['key_trends'][0]


def test_a_shift_with_no_brief_is_skipped_not_guessed(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'present')
    calls = []
    monkeypatch.setattr(gemini, 'generate_image',
                        lambda *a, **k: calls.append(a) or _png())
    art.generate_and_attach(_Conn(), _document(), {})
    assert calls == []


# ── attaching URLs to the candidate ──────────────────────────────────────

def test_urls_carry_the_content_digest_so_a_swap_is_instant():
    document = _document()
    rows = {
        ('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64},
        ('key_trend', 'silent-commerce', 'wide'): {'sha256': 'b' * 64},
        ('key_trend', 'silent-commerce', 'og'): {'sha256': 'c' * 64},
        ('sub_trend', 'silent-commerce/charm-arithmetic', 'tile'): {'sha256': 'd' * 64},
    }
    attached = art._attach(document, rows)
    shift, sub = document['key_trends'][0], document['sub_trends'][0]
    assert shift['hero_image'] == '/art/hero/silent-commerce.jpg?v=aaaaaaaaaaaa'
    assert shift['hero_image_wide'].startswith('/art/wide/silent-commerce.jpg?v=')
    assert shift['og_image'].startswith('/art/og/')
    assert sub['tile_image'].endswith('?v=dddddddddddd')
    # A sub-shift PAGE inherits the parent's poster; only its tile is its own.
    assert sub['hero_image'] == shift['hero_image']
    assert attached == 4


def test_a_sub_shift_wears_its_own_poster_not_its_parents():
    """It used to wear its parent's, which made five sibling pages look like one
    page. The tile was the only thing that was its own."""
    document = _document()
    art._attach(document, {
        ('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64},
        ('key_trend', 'silent-commerce', 'wide'): {'sha256': 'b' * 64},
        ('sub_trend', 'silent-commerce/charm-arithmetic', 'hero'): {'sha256': 'c' * 64},
        ('sub_trend', 'silent-commerce/charm-arithmetic', 'wide'): {'sha256': 'd' * 64},
    })
    sub = document['sub_trends'][0]
    assert sub['hero_image'].startswith('/art/hero/silent-commerce/charm-arithmetic.jpg')
    assert sub['hero_image_wide'].startswith('/art/wide/silent-commerce/charm-arithmetic.jpg')
    assert 'c' * 12 in sub['hero_image'], 'the digest should be the sub\'s own'


def test_a_sub_shift_falls_back_to_its_parent_rather_than_to_a_gradient():
    """Art is decoration and a failed generation must not strip the page bare.
    seo.rs reads og_image straight off the row, so without the fallback a
    sub-shift's link preview would regress to the committed static card."""
    document = _document()
    art._attach(document, {('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64},
                           ('key_trend', 'silent-commerce', 'og'): {'sha256': 'b' * 64}})
    sub = document['sub_trends'][0]
    assert sub['hero_image'] == document['key_trends'][0]['hero_image']
    assert sub['og_image'] == document['key_trends'][0]['og_image']


def test_a_sub_shift_generates_two_masters_and_gets_four_frames():
    """Two generations, four frames: the poster is a crop of the tile master and
    the share card a crop of the wide one, so the extra frames cost nothing."""
    jobs = art._jobs(_document(), {('key_trend', 'silent-commerce'): 'c',
                                   ('sub_trend', 'silent-commerce/charm-arithmetic'): 'c'})
    sub_jobs = [j for j in jobs if j['scope'] == 'sub_trend']
    assert sorted(j['frame'] for j in sub_jobs) == ['tile', 'wide']
    master = _png()
    frames = {row['frame'] for job in sub_jobs for row in art._outputs(job, master)}
    assert frames == {'tile', 'hero', 'wide', 'og'}


def test_every_derived_frame_is_a_downscale_of_its_master():
    """A frame that rides along free must not be a softer frame. Checked against
    the master sizes Gemini really returns (style.MASTER_PIXELS), not against an
    assumed 1024 square — 21:9 comes back 1584x672, and guessing got this wrong."""
    for (scope, master_frame), derived in art.DERIVED.items():
        source_w, source_h = MASTER_PIXELS[master_frame]
        for frame in derived:
            spec = art.spec_for(frame)
            scale = max(spec['width'] / source_w, spec['height'] / source_h)
            assert scale <= 1.0, (f'{scope}/{master_frame} -> {frame} upscales '
                                  f'{scale:.2f}x from {source_w}x{source_h}')


def test_the_generated_frames_are_the_ones_we_measured():
    """MASTER_PIXELS is only as good as its coverage: a new generated frame with
    no measurement would silently skip the check above."""
    generated = {job_frame for _, job_frame in art.DERIVED} | {'hero', 'wide', 'tile'}
    assert generated <= set(MASTER_PIXELS)


def test_the_art_route_reads_the_scope_off_the_slug_not_the_frame():
    """The backend used to infer scope from the frame — only a sub-shift had a
    tile. Sub-shifts now have heroes too, so that inference 404s every one."""
    source = (Path(__file__).resolve().parents[3]
              / 'apps' / 'backend' / 'src' / 'main.rs')
    if not source.exists():
        pytest.skip('backend not present (installed layout)')
    body = source.read_text(encoding='utf-8')
    assert 'let scope = if slug.contains(\'/\')' in body
    assert 'let scope = if frame == "tile"' not in body


def test_a_missing_frame_leaves_the_key_off_entirely():
    document = _document()
    art._attach(document, {('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64}})
    shift = document['key_trends'][0]
    assert 'hero_image' in shift
    assert 'hero_image_wide' not in shift
    assert 'og_image' not in shift


def test_the_route_is_not_nested_under_shift():
    """/shift is already a ServeDir nest_service in the backend; an overlapping
    route panics at router construction."""
    document = _document()
    art._attach(document, {('key_trend', 'silent-commerce', 'hero'): {'sha256': 'a' * 64}})
    assert document['key_trends'][0]['hero_image'].startswith('/art/')


# ── the publish stamp, against real Postgres ────────────────────────────

@pytest.mark.skipif(not __import__('os').environ.get('DATABASE_URL'),
                    reason='needs DATABASE_URL (integration)')
def test_the_publish_stamp_runs_on_real_postgres():
    """This is the one that cannot be faked.

    `(scope, slug) = ANY(%s)` with a list of tuples type-checks fine in Python
    and fails in Postgres with "input of anonymous composite types is not
    implemented" — inside the publish transaction, after every image has already
    been paid for. A fake connection would have accepted it happily.
    """
    from serious_shift_pipeline.core import db
    from serious_shift_pipeline.mapgen.art import store

    row = {'frame': 'hero', 'bytes': b'\xff\xd8jpeg', 'width': 1, 'height': 1,
           'byte_size': 5, 'sha256': 'x' * 64, 'prompt_sha256': 'y' * 16,
           'style': 'collage', 'model': 'm'}
    with db.connect() as conn:
        try:
            store.upsert_art(conn, [{**row, 'scope': 'key_trend', 'slug': 'kept'},
                                    {**row, 'scope': 'key_trend', 'slug': 'departed'}])
            store.publish_art(conn, {('key_trend', 'kept')})
            left = [r['slug'] for r in conn.execute(
                'SELECT slug FROM shift_art ORDER BY slug').fetchall()]
            assert 'kept' in left
            assert 'departed' not in left
        finally:
            conn.rollback()


def test_a_missing_pillow_cannot_take_the_cli_down(monkeypatch):
    """Pillow is a decoration dependency and must behave like one.

    `mapgen.cli` imports the art package eagerly, so a module-level
    `from PIL import Image` in raster.py made Pillow a hard requirement of the
    whole CLI — an environment without it could not run mapgen, could not
    --export-only, and could not even collect this test suite. CI found that the
    hard way: requirements-dev.lock had not been regenerated, and all eight
    mapgen test modules failed to import.
    """
    import importlib
    import sys

    blocked = [name for name in sys.modules if name.split('.')[0] == 'PIL']
    saved = {name: sys.modules.pop(name) for name in blocked}

    class _Block:
        def find_module(self, name, path=None):
            return self if name.split('.')[0] == 'PIL' else None

        def load_module(self, name):
            raise ImportError('PIL blocked')

    sys.meta_path.insert(0, _Block())
    try:
        for module in ('serious_shift_pipeline.mapgen.art.raster',
                       'serious_shift_pipeline.mapgen.art',
                       'serious_shift_pipeline.mapgen.cli'):
            sys.modules.pop(module, None)
            assert importlib.import_module(module) is not None
    finally:
        sys.meta_path.pop(0)
        sys.modules.update(saved)
