"""Chunked extraction: long sources are split at seams, extracted per chunk,
and merged — never truncated. Extraction previously saw raw_text[:12000] (a
third of a typical podcast transcript) and the store kept [:50000], so every
claim in the back of a long source silently never entered the corpus."""
from serious_shift_pipeline.prompts.extraction import extraction_prompt
from serious_shift_pipeline.steps.process_raw import (
    CHUNK_CHARS, chunk_body, merge_extractions)


def test_short_body_is_one_chunk():
    body = 'word ' * 100
    assert chunk_body(body) == [body]


def test_body_within_a_quarter_of_the_limit_stays_whole():
    """A tiny tail chunk would just re-extract the overlap."""
    body = 'a' * (CHUNK_CHARS + CHUNK_CHARS // 5)
    assert len(chunk_body(body)) == 1


def test_long_body_chunks_cover_everything_with_overlap():
    # Unique tokens make every substring position unambiguous.
    body = ' '.join(f'w{i}.' for i in range(15000))
    chunks = chunk_body(body)
    assert len(chunks) >= 3
    assert all(len(c) <= CHUNK_CHARS for c in chunks)
    assert chunks[0].startswith('w0.')
    assert chunks[-1].endswith('w14999.')
    # No gaps: each chunk starts at or before where the previous one ended.
    covered = 0
    for chunk in chunks:
        start = body.index(chunk)
        assert start <= covered
        covered = max(covered, start + len(chunk))
    assert covered == len(body)
    # Real overlap, so a claim straddling a seam appears whole in one chunk.
    for first, second in zip(chunks, chunks[1:]):
        assert second[:80] in first


def test_merge_dedupes_seam_claims_and_keeps_first_source():
    part_one = {
        'source': {'title': 'First'},
        'claims': [{'claim_text': 'Agents ship in Q3.'},
                   {'claim_text': 'Tokens got cheap!'}],
        'predictions': [{'claim_text': 'AGI by 2030'}],
    }
    part_two = {
        'source': {'title': 'Second'},
        'claims': [{'claim_text': 'Tokens got CHEAP'},   # seam duplicate
                   {'claim_text': 'Something new'}],
        'predictions': [{'claim_text': 'AGI by 2030'}],
        'position_changes': [{'description': 'softened stance'}],
    }
    merged = merge_extractions([part_one, part_two])
    assert merged['source'] == {'title': 'First'}
    assert [c['claim_text'] for c in merged['claims']] == [
        'Agents ship in Q3.', 'Tokens got cheap!', 'Something new']
    assert len(merged['predictions']) == 1
    assert merged['position_changes'] == [{'description': 'softened stance'}]


def test_part_note_marks_only_multichunk_prompts():
    thinker = {'name': 'Test Thinker', 'credibility_score': 0.5}
    single = extraction_prompt(thinker, {}, 'some text', [], [])
    assert 'part 1 of' not in single
    chunked = extraction_prompt(thinker, {}, 'some text', [], [], part=(2, 3))
    assert 'part 2 of 3' in chunked
