"""Evidence-pack research: the model only points; deterministic code decides.
Pure-function tests for the pointer-list validator, coverage self-audit, and
the llm.Req tool plumbing the research call rides on."""
import pytest

from serious_shift_pipeline.core import llm
from serious_shift_pipeline.steps.research import clean_items, coverage_of

GOOD = {
    "url": "https://example.org/study", "title": "A Study", "publisher": "Example",
    "author": "Dr. A", "date": "2026-08-01",
    "quote": "adoption reached 41% of US adults in Q2 2026",
    "finding": "Adoption crossed 41% in the US.",
    "statistic": "41% of US adults", "kind": "support",
    "sector": None, "primary": True, "domain": "consumer_behavior",
}


def test_clean_items_accepts_good_and_normalizes_host():
    items, rejects = clean_items([GOOD])
    assert rejects == []
    assert items[0]["host"] == "example.org"
    assert items[0]["primary"] is True


def test_clean_items_rejects_bad_urls_missing_quotes_and_dupes():
    dupe = dict(GOOD, quote=GOOD["quote"].upper())   # same normalized quote
    items, rejects = clean_items([
        GOOD, dupe,
        dict(GOOD, url="ftp://x/y"),
        dict(GOOD, url="https://ok.com/a", quote=""),
    ])
    assert len(items) == 1
    assert len(rejects) == 3


def test_clean_items_defaults_invalid_enums():
    items, _ = clean_items([dict(GOOD, kind="rant", domain="astrology", sector="Nope")])
    assert items[0]["kind"] == "context"
    assert items[0]["domain"] == "technology_capability"
    assert items[0]["sector"] is None


def test_clean_items_requires_a_list():
    items, rejects = clean_items({"not": "a list"})
    assert items == [] and rejects


def test_coverage_self_audit():
    stored = [
        dict(GOOD, host="a.com", kind="support", primary=True, statistic="41%",
             sector="Retail", date="2026-08-01"),
        dict(GOOD, host="b.com", kind="counter", primary=False, statistic=None,
             sector=None, date="2026-07-01"),
    ]
    cov = coverage_of(stored, {"fetch_failed": 1})
    assert cov["items"] == 2 and cov["hosts"] == 2
    assert cov["kinds"] == {"support": 1, "counter": 1}
    assert cov["primary_share"] == 0.5
    assert cov["newest"] == "2026-08-01"
    assert cov["dropped"] == {"fetch_failed": 1}


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_api_fetched_docs_handles_both_sdk_shapes_and_canonical():
    from serious_shift_pipeline.steps.research import api_fetched_docs, norm_url
    # Non-streaming: typed attribute objects.
    typed = _Obj(type="web_fetch_tool_result",
                 content=_Obj(url="https://a.com/p/", content=_Obj(
                     source=_Obj(data="x" * 400))))
    # Streaming: plain dicts, with a canonical front-matter line.
    text = "---\ncanonical: https://Canon.com/real\n---\n" + "y" * 400
    dictish = _Obj(type="web_fetch_tool_result",
                   content={"url": "https://redirect.net/tmp", "type": "web_fetch_result",
                            "content": {"source": {"data": text}}})
    short = _Obj(type="web_fetch_tool_result",
                 content=_Obj(url="https://b.com", content=_Obj(source=_Obj(data="tiny"))))
    msg = _Obj(content=[typed, dictish, short, _Obj(type="text", text="hi")])
    docs = api_fetched_docs(msg)
    assert docs[norm_url("https://www.a.com/p")] == "x" * 400
    assert docs[norm_url("https://canon.com/real/")] == text     # canonical index
    assert docs[norm_url("https://redirect.net/tmp")] == text    # fetch-url index
    assert norm_url("https://b.com") not in docs


def test_salvage_recovers_complete_items_from_truncation():
    from serious_shift_pipeline.steps.research import salvage_item_array
    full = ('Here is what I found:\n[\n{"url": "https://a.com", "quote": "q1"},'
            '\n{"url": "https://b.com", "quote": "q2"},'
            '\n{"url": "https://c.com", "quo')   # cut mid-item
    items = salvage_item_array(full)
    assert [i["url"] for i in items] == ["https://a.com", "https://b.com"]
    assert salvage_item_array("no array here") is None
    assert salvage_item_array("[") is None


def test_merge_usages_sums_counters_keeps_identity():
    merged = llm.merge_usages([
        {"model": "m", "input_tokens": 10, "output_tokens": 5,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
         "web_search_requests": 3, "batch": False},
        {"model": "m", "input_tokens": 7, "output_tokens": 2,
         "cache_read_input_tokens": 1, "cache_creation_input_tokens": 0,
         "web_search_requests": 2, "batch": False},
    ])
    assert merged["input_tokens"] == 17 and merged["output_tokens"] == 7
    assert merged["web_search_requests"] == 5
    assert merged["model"] == "m"


def test_req_params_carry_tools_and_documents():
    req = llm.Req(user="q", tools=[{"type": "web_search_20250305",
                                    "name": "web_search", "max_uses": 5}],
                  documents=[{"type": "document", "source": {"type": "text",
                              "media_type": "text/plain", "data": "d"},
                              "citations": {"enabled": True}}])
    p = req.params()
    assert p["tools"][0]["name"] == "web_search"
    assert p["messages"][0]["content"][0]["type"] == "document"
    assert p["messages"][0]["content"][-1] == {"type": "text", "text": "q"}


def test_call_batch_refuses_tool_requests():
    with pytest.raises(ValueError, match="sync-only"):
        llm.call_batch([llm.Req(user="q", custom_id="a",
                                tools=[{"type": "web_search_20250305",
                                        "name": "web_search"}])])
