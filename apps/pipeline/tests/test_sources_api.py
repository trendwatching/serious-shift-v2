"""arXiv + OpenAlex parsers — fixture-based tests (no network)."""
from serious_shift_pipeline.core import sources_api

ARXIV_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v1</id>
    <title>Test Paper Title on AI</title>
    <summary>This is the abstract text about artificial intelligence and labor.</summary>
    <published>2026-01-15T00:00:00Z</published>
    <author><name>Alice Researcher</name></author>
    <author><name>Bob Scientist</name></author>
    <category term="cs.AI"/>
    <category term="econ.GN"/>
  </entry>
</feed>"""

OPENALEX_JSON = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "title": "AI and Labor Markets",
            "abstract_inverted_index": {"AI": [0], "transforms": [1], "labor": [2]},
            "publication_date": "2026-02-01",
            "doi": "https://doi.org/10.1234/abc",
            "cited_by_count": 42,
            "authorships": [{"author": {"display_name": "Carol Economist"}}],
            "primary_location": {"source": {"display_name": "American Economic Review"}},
            "concepts": [{"display_name": "Economics"}, {"display_name": "Labour economics"}],
        }
    ]
}


def test_parse_arxiv_atom():
    papers = sources_api.parse_arxiv_atom(ARXIV_ATOM)
    assert len(papers) == 1
    p = papers[0]
    assert p["external_id"] == "arXiv:2401.01234v1"
    assert p["title"] == "Test Paper Title on AI"
    assert "artificial intelligence" in p["abstract"]
    assert p["authors"] == ["Alice Researcher", "Bob Scientist"]
    assert p["date"] == "2026-01-15"
    assert p["venue"] == "arXiv"
    assert "cs.AI" in p["categories"]


def test_reconstruct_abstract():
    assert sources_api._reconstruct_abstract({"AI": [0], "transforms": [1], "labor": [2]}) == "AI transforms labor"
    assert sources_api._reconstruct_abstract(None) == ""


def test_parse_openalex_works():
    papers = sources_api.parse_openalex_works(OPENALEX_JSON)
    assert len(papers) == 1
    p = papers[0]
    assert p["external_id"] == "openalex:W123"
    assert p["authors"] == ["Carol Economist"]
    assert p["venue"] == "American Economic Review"
    assert p["doi"] == "10.1234/abc"          # https://doi.org/ prefix stripped
    assert p["citation_count"] == 42
    assert p["abstract"] == "AI transforms labor"
    assert p["date"] == "2026-02-01"
