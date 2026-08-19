"""Write one image brief per shift and sub-shift, and remember them.

Runs after the gate passes, against the FINAL document, because the brief is
keyed by published slug and slugs are only final at export.

The briefs live in `shift_art_briefs`, not in the v2 tables. That is the single
most expensive decision available here: the v2 tables are truncated every week,
so a brief stored there would be rewritten every week, changing every image
prompt, invalidating every prompt hash, and re-paying for all ~250 images every
Monday. Keyed durably and hashed on the editorial inputs it was written from, an
unchanged shift costs nothing at all.
"""
from __future__ import annotations

import hashlib
import json
import re

from ...prompts import SYNTHESIS_MODEL, prompt_art_brief
from ..art import store
from ..llm import generate_json


#: Bumped by hand whenever `packages/prompts/map/art_brief.txt` changes in a way
#: that should rewrite existing briefs. `brief_inputs_sha256` hashes the shift's
#: editorial, not the prompt, so without this a template edit is a silent no-op:
#: every stored brief still matches its hash, phase 10 reports "all current", and
#: the new instructions never reach the model. Bumping re-pays for the fleet.
ART_BRIEF_PROMPT_VERSION = 2

#: One of these is handed to the brief writer per shift. The first fleet came
#: back as one picture drawn 281 times — a crowd, at middle distance, with
#: something happening above it — because the style and the frame clause between
#: them described that picture and the brief was the only thing varying.
#:
#: It is given to the brief rather than added to the image prompt, where it was
#: tried first: a register chosen in code contradicts the scene outright as often
#: as it shapes it ("stage it as a crowd seen whole" under a brief about two
#: people in a doorway). Written INTO the scene it cannot disagree with it, and
#: the brief's own words are a more specific instruction than the clause was.
REGISTERS: tuple[str, ...] = (
    'Stage it as a still life: objects on a surface, nobody present, the light '
    'doing the work.',
    'Stage it as a landscape: the scene read from a distance, the land or the '
    'weather larger than anything human in it.',
    'Stage it as an architectural interior: the room and what it does to the '
    'people in it, walls and thresholds carrying the frame.',
    'Stage it on the hands and the materials: close in on the work being done, '
    'the tools and the texture of what is being handled.',
    'Stage it as a crowd seen whole: many people at a distance, the pattern they '
    'make mattering more than any one of them.',
    'Stage it as one surface close up: a single material filling the frame, its '
    'wear and grain and damage read at scale.',
)


def _register_index(slug: str) -> int:
    """sha256 rather than hash(): PYTHONHASHSEED randomises str hashing per
    process, so the built-in would hand the same shift a different register on
    every run and re-pay for its images each time."""
    digest = hashlib.sha256(str(slug or '').encode()).digest()
    return int.from_bytes(digest[:8], 'big') % len(REGISTERS)


def register_for(slug: str) -> str:
    """The key shift's register. Keyed on the slug and nothing else.

    The register goes into the brief, the brief goes into the image prompt, and
    the image prompt is hashed — so anything that moved would re-pay. A slug is
    stable for as long as the shift is, which is exactly as long as its picture
    should be.
    """
    return REGISTERS[_register_index(slug)]


#: What the brief writer reads, in the order it reads it, and what each line is
#: called. Emitting in THIS order rather than in module order is what keeps the
#: hash stable: a document reordered by the export changes nothing a reader sees
#: and must not re-pay for every image on the page.
#:
#: The label matters as much as the text. The model is asked to name the shift's
#: underlying tension before it draws anything, and unlabelled prose gives it no
#: way to tell the thesis from the trimming.
_CONTEXT_SLOTS: tuple[tuple[str, str, str], ...] = (
    ('peel_tabs', 'whats_changing', 'What is changing'),
    ('peel_tabs', 'why_now', 'Why now'),
    ('tension_band', 'quote', 'The tension'),
    ('human_needs', 'unlocked', 'Human need unlocked'),
    ('human_needs', 'threatened', 'Human need threatened'),
)


def _context(shift: dict) -> str:
    """The editorial the brief is allowed to see.

    Wider than it was, and still nothing like the whole module tree. The brief is
    asked to name the shift's underlying tension and draw a metaphor for it, and
    that tension lives in `peel_tabs`, `tension_band` and `human_needs` — all of
    which used to be withheld, which is why the first fleet came back illustrating
    the subject matter instead (arrows, lightning, people at screens).

    Still excluded, and this is the point: industries, territories, timeline,
    stat_band, pull_quote and evidence. Hand those over and the brief describes
    the page rather than the shift, which is the failure the narrow version was
    built to avoid.
    """
    arc = ''
    scene = ''
    slots: dict[tuple[str, str], str] = {}
    for module in shift.get('modules') or []:
        if not isinstance(module, dict):
            continue
        type_ = module.get('type')
        data = module.get('data') or {}
        if type_ in {'from_to', 'from_to_solid'} and not arc:
            arc_from, arc_to = data.get('from'), data.get('to')
            if arc_from and arc_to:
                arc = f'The world is moving from {arc_from} to {arc_to}.'
        elif type_ in {'dek', 'lede'} and data.get('text') and not scene:
            scene = str(data['text'])
        for slot_type, field, label in _CONTEXT_SLOTS:
            if type_ == slot_type and data.get(field):
                slots.setdefault((slot_type, field), f'{label}: {data[field]}')

    parts = [part for part in (arc, scene) if part]
    parts.extend(line for slot_type, field, _ in _CONTEXT_SLOTS
                 if (line := slots.get((slot_type, field))))
    return _clip(' '.join(parts))


#: Every field above is already word-capped by FIELD_WORD_LIMITS, and the whole
#: block adds up to ~390 words on the most verbose shift — so this is a runaway
#: guard, not a budget, and it should essentially never fire. It replaced a 900
#: that fired on the first real shift tried, taking "Human need threatened" with
#: it: the last slot is the most easily lost and the least replaceable, since the
#: brief is asked to draw the tension.
CONTEXT_LIMIT = 3000


def _clip(text: str) -> str:
    """Trim to CONTEXT_LIMIT on a word boundary rather than mid-word."""
    if len(text) <= CONTEXT_LIMIT:
        return text
    cut = text[:CONTEXT_LIMIT]
    head, space, _ = cut.rpartition(' ')
    return (head if space else cut).rstrip(' ,;:—-') + '…'


#: A brief that describes writing produces a picture full of garbled characters,
#: because the image prompt's ban on text cannot un-ask for a price tag. Seen on
#: the first metaphor-first sample run: a brief about numbers "impressed into the
#: paper, legible as grooves" came back as a wall of scrawled figures.
#:
#: The prompt forbids this too. This is the backstop, because the cost of missing
#: one is a visible defect on a live page, and the cost of a false positive is
#: that one shift keeps last week's artwork.
_WRITTEN_MATTER = (
    'handwriting', 'handwritten', 'lettering', 'letter', 'letters', 'numeral',
    'numerals', 'digit', 'digits', 'number', 'numbers', 'inscription', 'inscribed',
    'receipt', 'receipts', 'ledger', 'ledgers', 'price tag', 'price tags',
    'signage', 'slogan', 'headline', 'caption', 'captions', 'logo', 'logos',
    'barcode', 'placard', 'label', 'labels', 'labelled', 'labeled',
    'typography', 'typeface', 'written', 'writing', 'text',
    # NOT 'legible' / 'illegible': "the pattern of bodies is legible from above"
    # is clean, writing-free prose, and rejecting it cost a whole family on the
    # 19 Aug run. The words that mattered in the real failure — numbers, ink —
    # are caught on their own.
    # Objects whose whole job is to carry writing. The model fills them in even
    # when the brief says they are blank, or that the writing has been lifted
    # away — both were tried on the 19 Aug sample runs.
    'menu', 'menus', 'newspaper', 'newspapers', 'poster', 'posters', 'leaflet',
    'leaflets', 'pamphlet', 'pamphlets', 'banner', 'banners', 'certificate',
    'certificates', 'signpost', 'departure board', 'departure boards',
    'noticeboard', 'billboard', 'chalkboard', 'blackboard', 'whiteboard',
    'sticker', 'stickers',
)
#: "a number of people" is a quantity, not something written on anything. It is
#: the one common phrase that trips the list, so it is removed before matching
#: rather than costing the word "number", which is what caught the real failure.
_QUANTITY = re.compile(r'\b(?:a|any|the) numbers? of\b')


def describes_written_matter(brief: str) -> str:
    """The banned word this brief uses, or '' if it is clean.

    Note what is deliberately NOT caught: "unlabelled jars" is a scene with no
    writing in it, and the lookarounds let it through.
    """
    lowered = _QUANTITY.sub(' ', str(brief or '').lower())
    for term in _WRITTEN_MATTER:
        if re.search(rf'(?<![a-z]){re.escape(term)}(?![a-z])', lowered):
            return term
    return ''


def _with_registers(subs: list[dict], parent_slug: str = '') -> list[dict]:
    """Each sub-shift carries a register, and no two siblings share one.

    Hashing each slug independently was tried first and is not good enough: with
    six registers and four siblings a collision is more likely than not, and the
    sub tiles are precisely where convergence shows — they sit next to each other
    on one page. So the family walks the list instead, starting one past the
    parent's register, which also keeps every child different from its parent.

    Ranked by slug rather than by array position so the export's ordering cannot
    move a register. Adding or removing a sibling does shift the ranks below it —
    but the sibling set is already part of `brief_inputs_sha256`, so any change to
    it rewrites the whole family's briefs regardless. This adds no churn that was
    not already there.
    """
    base = _register_index(parent_slug)
    out = list(subs)
    ranked = sorted(range(len(subs)), key=lambda i: str(subs[i].get('slug') or ''))
    for rank, index in enumerate(ranked, start=1):
        out[index] = {**subs[index],
                      'register': REGISTERS[(base + rank) % len(REGISTERS)]}
    return out


def brief_inputs_sha256(shift: dict, subs: list[dict]) -> str:
    """What the brief was written from. Unchanged inputs, unchanged brief.

    Ordered and explicit rather than a hash of the whole row: a `db_id` that is
    recycled weekly, or a module reordering that changes nothing a reader sees,
    would otherwise re-pay for every image on the page.

    `ART_BRIEF_PROMPT_VERSION` rides along so that the *prompt* counts as an input
    too — see its comment for why editing the template alone changes nothing.
    """
    payload = json.dumps({
        'prompt_version': ART_BRIEF_PROMPT_VERSION,
        'name': shift.get('name'), 'subtitle': shift.get('subtitle'),
        'context': _context(shift),
        'register': register_for(str(shift.get('slug') or '')),
        'subs': [[s.get('name'), s.get('subtitle') or s.get('description'),
                  s.get('register')]
                 for s in _with_registers(subs, str(shift.get('slug') or ''))],
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def briefs_from_result(result: dict | None, slug: str,
                       subs: list[dict]) -> tuple[str, list[tuple[str, str]]]:
    """One family's briefs out of one model response, guard applied.

    Shared with `art.sample` rather than duplicated into it. The sample tool is
    what the team reviews before a fleet regeneration, so a sample that parsed or
    filtered differently from the real phase would be reviewing the wrong thing —
    which is exactly what happened on 19 Aug: the sample skipped the
    written-matter guard and showed briefs production would have rejected.

    Sub-shifts are matched on NAME, like the editorial phase, because the model
    is asked to echo the name verbatim and array order has been wrong before.
    """
    shift_brief = str(((result or {}).get('shift') or {}).get('brief') or '').strip()
    offence = describes_written_matter(shift_brief)
    if offence:
        print(f'  art briefs: {slug} describes written matter ("{offence}"), rejected')
        shift_brief = ''

    # A rejected key-shift brief does NOT take its sub-shifts down with it. Their
    # scenes are independent, and losing five pages of artwork to one bad word on
    # the parent is a far worse trade than the parent going a week without.
    by_name = {str(s.get('name') or '').strip().lower(): s for s in subs}
    out: list[tuple[str, str]] = []
    for item in (result or {}).get('sub_shifts') or []:
        sub = by_name.get(str((item or {}).get('name') or '').strip().lower())
        brief = str((item or {}).get('brief') or '').strip()
        if not sub or not brief:
            continue
        offence = describes_written_matter(brief)
        if offence:
            print(f'  art briefs: {sub.get("slug")} describes written matter '
                  f'("{offence}"), rejected')
            continue
        out.append((str(sub.get('slug') or ''), brief))
    return shift_brief, out


def phase10_art_briefs(conn, out: dict) -> dict[tuple[str, str], str]:
    """Returns {(scope, slug): brief}. Never raises — the caller publishes anyway."""
    subs_by_parent: dict[str, list[dict]] = {}
    for sub in out.get('sub_trends') or []:
        parent = str(sub.get('slug') or '').rsplit('/', 1)[0]
        if parent:
            subs_by_parent.setdefault(parent, []).append(sub)

    stored = store.load_briefs(conn)
    briefs: dict[tuple[str, str], str] = {}
    work: list[tuple[dict, list[dict], str, bool]] = []

    for shift in out.get('key_trends') or []:
        slug = str(shift.get('slug') or '')
        if not slug:
            continue
        subs = subs_by_parent.get(slug, [])
        digest = brief_inputs_sha256(shift, subs)
        current = stored.get(('key_trend', slug))
        kept = (current['brief']
                if current is not None and current['input_sha256'] == digest else None)
        # A sub-shift with no stored brief is not "current", whatever its parent
        # says. It is usually one the written-matter guard rejected, and skipping
        # the family on the parent's word alone left it with no art FOREVER: the
        # parent stays current every week, so the retry never comes. A rejected
        # KEY shift self-heals (its missing row makes the family stale); a
        # rejected sub-shift did not, and that asymmetry was invisible until a
        # publish left four sub-shifts art-less. Found 2026-08-20.
        gaps = [s for s in subs if not stored.get(('sub_trend', str(s.get('slug'))))]
        if kept is not None and not gaps:
            briefs[('key_trend', slug)] = kept
            for sub in subs:
                held = stored.get(('sub_trend', str(sub.get('slug'))))
                if held:
                    briefs[('sub_trend', str(sub.get('slug')))] = held['brief']
            continue
        # `fresh` means the editorial has not moved and we are here only to fill
        # gaps: keep every brief that already exists so its images stay cached,
        # and adopt only the ones that are missing. Rewriting the whole family
        # would re-pay for siblings that are already correct.
        if kept is not None:
            briefs[('key_trend', slug)] = kept
            for sub in subs:
                held = stored.get(('sub_trend', str(sub.get('slug'))))
                if held:
                    briefs[('sub_trend', str(sub.get('slug')))] = held['brief']
        work.append((shift, subs, digest, kept is not None))

    if not work:
        print(f'  art briefs: all {len(briefs)} current, nothing to write')
        return briefs

    gap_fills = sum(1 for item in work if item[3])
    print(f'  art briefs: writing {len(work)} shift family/families '
          f'({len(briefs)} already current'
          f'{f", {gap_fills} filling gaps only" if gap_fills else ""})…')
    results = generate_json(
        work,
        lambda item: prompt_art_brief(item[0].get('name', ''),
                                      item[0].get('subtitle', ''),
                                      _context(item[0]),
                                      _with_registers(item[1],
                                                      str(item[0].get('slug') or '')),
                                      register_for(str(item[0].get('slug') or ''))),
        default=lambda: {},
        describe=lambda item: str(item[0].get('name', ''))[:30],
    )

    rows: list[dict] = []
    for (shift, subs, digest, fresh), result in zip(work, results):
        slug = str(shift.get('slug') or '')
        shift_brief, sub_briefs = briefs_from_result(result, slug, subs)
        if fresh:
            # Gap-fill only: never overwrite a brief that already exists, or its
            # images all re-pay for nothing.
            shift_brief = '' if ('key_trend', slug) in briefs else shift_brief
            sub_briefs = [(sub_slug, brief) for sub_slug, brief in sub_briefs
                          if ('sub_trend', sub_slug) not in briefs]
        # A missing key-shift brief costs that shift its art this week and nothing
        # else: the existing row (if any) stays, _jobs skips it, and the absent
        # row makes the family non-current so the next run retries it. Its
        # sub-shifts are stored regardless — their scenes are their own.
        if shift_brief:
            briefs[('key_trend', slug)] = shift_brief
            rows.append({'scope': 'key_trend', 'slug': slug, 'brief': shift_brief[:4000],
                         'input_sha256': digest, 'model': SYNTHESIS_MODEL})
        for sub_slug, brief in sub_briefs:
            briefs[('sub_trend', sub_slug)] = brief
            rows.append({'scope': 'sub_trend', 'slug': sub_slug, 'brief': brief[:4000],
                         'input_sha256': digest, 'model': SYNTHESIS_MODEL})

    if rows:
        store.upsert_briefs(conn, rows)
        conn.commit()
    return briefs
