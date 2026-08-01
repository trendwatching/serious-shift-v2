"""core.llm: request shaping, JSON salvage, and the batch contract.

parse_model_json handles untrusted model output and had no coverage; the batch
helpers enforce invariants (unique custom_ids) whose violation would silently
mismatch results to inputs.
"""
import pytest

from serious_shift_pipeline.core import llm


# ── Req ──────────────────────────────────────────────────────────────────────

def test_req_builds_message_params():
    p = llm.Req(user="hi", model="claude-haiku-4-5", max_tokens=100).params()
    assert p == {
        "model": "claude-haiku-4-5",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "hi"}],
    }


def test_req_omits_system_when_absent():
    assert "system" not in llm.Req(user="hi").params()


def test_req_includes_system_when_given():
    blocks = [{"type": "text", "text": "context"}]
    assert llm.Req(user="hi", system=blocks).params()["system"] == blocks


# ── batch invariants ─────────────────────────────────────────────────────────

def test_call_batch_is_a_noop_for_no_requests():
    assert llm.call_batch([]) == {}


def test_call_batch_requires_custom_ids():
    # Without them results cannot be matched back to inputs.
    with pytest.raises(ValueError, match="custom_id"):
        llm.call_batch([llm.Req(user="a")])


def test_call_batch_rejects_duplicate_custom_ids():
    # Duplicates would silently drop one result and mispair the other.
    reqs = [llm.Req(user="a", custom_id="x"), llm.Req(user="b", custom_id="x")]
    with pytest.raises(ValueError, match="unique"):
        llm.call_batch(reqs)


# ── JSON salvage ─────────────────────────────────────────────────────────────

def test_parses_plain_json():
    assert llm.parse_model_json('{"a": 1}') == {"a": 1}


def test_strips_json_code_fence():
    assert llm.parse_model_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_strips_bare_code_fence():
    assert llm.parse_model_json('```\n{"a": 1}\n```') == {"a": 1}


def test_salvages_json_wrapped_in_prose():
    assert llm.parse_model_json('Here you go:\n{"a": 1}\nHope that helps!') == {"a": 1}


def test_salvages_a_top_level_array():
    assert llm.parse_model_json('Sure:\n[1, 2, 3]') == [1, 2, 3]


def test_braces_inside_strings_do_not_end_the_block():
    assert llm.parse_model_json('x {"a": "} not the end"} y') == {"a": "} not the end"}


def test_escaped_quote_inside_string_is_handled():
    assert llm.parse_model_json(r'{"a": "say \"hi\""}') == {"a": 'say "hi"'}


def test_raises_on_unparseable_output():
    with pytest.raises(ValueError, match="Could not parse JSON"):
        llm.parse_model_json("no json here at all")
