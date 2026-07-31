"""
Research-paper source clients — arXiv and OpenAlex.

Pure(ish) functions that fetch + normalise paper metadata into a single shape so
the scraper can treat papers like any other source. Both APIs are free and need
no key. Network I/O is isolated behind `_get`/`_get_json` so unit tests can call
the parsers (`parse_arxiv_atom`, `parse_openalex_works`) on fixture payloads.

Normalised paper dict:
    {
      "external_id": "arXiv:2401.01234" | "openalex:W123",
      "title": str,
      "abstract": str,
      "authors": [str, ...],          # display names, primary first
      "date": "YYYY-MM-DD" | None,
      "url": str,                     # canonical landing page
      "doi": str | None,
      "venue": str,                   # "arXiv" | journal/conf name
      "citation_count": int | None,
      "categories": [str, ...],
    }
"""
from __future__ import annotations

import os

# Polite identification for OpenAlex (recommended; unlocks the faster pool).
_MAILTO = os.environ.get("OPENALEX_MAILTO", "hello@trendwatching.com")
_UA = {"User-Agent": f"serious-shift-pipeline/1.0 (mailto:{_MAILTO})"}


def _get(url: str, params: dict | None = None, timeout: int = 30):
    import requests
    resp = requests.get(url, params=params or {}, headers=_UA, timeout=timeout)
    resp.raise_for_status()
    return resp


def _get_json(url: str, params: dict | None = None, timeout: int = 30) -> dict:
    return _get(url, params=params, timeout=timeout).json()


# ── arXiv ────────────────────────────────────────────────────────────────────

def parse_arxiv_atom(atom_bytes) -> list[dict]:
    """Parse an arXiv Atom API response (via feedparser) into paper dicts."""
    import feedparser
    feed = feedparser.parse(atom_bytes)
    out: list[dict] = []
    for e in feed.entries:
        arxiv_id = (e.get("id") or "").rsplit("/abs/", 1)[-1]
        authors = [a.get("name", "").strip() for a in e.get("authors", []) if a.get("name")]
        date = None
        published = e.get("published", "")
        if published:
            date = published[:10]  # arXiv uses ISO 'YYYY-MM-DDT…'
        cats = [t.get("term") for t in e.get("tags", []) if t.get("term")]
        out.append({
            "external_id": f"arXiv:{arxiv_id}" if arxiv_id else None,
            "title": " ".join((e.get("title") or "").split()),
            "abstract": " ".join((e.get("summary") or "").split()),
            "authors": authors,
            "date": date,
            "url": e.get("link") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
            "doi": e.get("arxiv_doi"),
            "venue": "arXiv",
            "citation_count": None,
            "categories": cats,
        })
    return out


def arxiv_search(categories: list[str], *, since: str | None = None,
                 max_results: int = 60) -> list[dict]:
    """Fetch newest arXiv papers in the given categories (title + abstract).

    `since` (YYYY-MM-DD) filters client-side on the submitted date — the public
    API's date filtering is unreliable, so we over-fetch newest-first and trim.
    """
    query = " OR ".join(f"cat:{c}" for c in categories)
    resp = _get("http://export.arxiv.org/api/query", params={
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    })
    papers = parse_arxiv_atom(resp.content)
    if since:
        papers = [p for p in papers if not p["date"] or p["date"] >= since]
    return papers


def arxiv_by_author(author: str, *, since: str | None = None,
                    max_results: int = 30) -> list[dict]:
    resp = _get("http://export.arxiv.org/api/query", params={
        "search_query": f'au:"{author}"',
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    })
    papers = parse_arxiv_atom(resp.content)
    if since:
        papers = [p for p in papers if not p["date"] or p["date"] >= since]
    return papers


# ── OpenAlex ─────────────────────────────────────────────────────────────────

def _reconstruct_abstract(inverted: dict | None) -> str:
    """Rebuild abstract text from OpenAlex's abstract_inverted_index."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def parse_openalex_works(payload: dict) -> list[dict]:
    """Parse an OpenAlex /works response into paper dicts."""
    out: list[dict] = []
    for w in payload.get("results", []):
        authors = [
            a.get("author", {}).get("display_name", "").strip()
            for a in w.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        venue = ""
        loc = (w.get("primary_location") or {}).get("source") or {}
        venue = loc.get("display_name") or ""
        doi = w.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        out.append({
            "external_id": f"openalex:{(w.get('id') or '').rsplit('/', 1)[-1]}",
            "title": " ".join((w.get("title") or "").split()),
            "abstract": _reconstruct_abstract(w.get("abstract_inverted_index")),
            "authors": authors,
            "date": w.get("publication_date"),
            "url": w.get("doi") or w.get("id") or "",
            "doi": doi,
            "venue": venue or "OpenAlex",
            "citation_count": w.get("cited_by_count"),
            "categories": [c.get("display_name") for c in w.get("concepts", [])[:5] if c.get("display_name")],
        })
    return out


def openalex_search(search: str, *, since: str | None = None,
                    min_citations: int = 0, per_page: int = 50) -> list[dict]:
    """Search OpenAlex works, newest first, with a citation floor.

    Citation and date filters are applied server-side via the `filter` param.
    """
    filters = []
    if since:
        filters.append(f"from_publication_date:{since}")
    if min_citations:
        filters.append(f"cited_by_count:>{min_citations - 1}")
    params = {
        "search": search,
        "per-page": min(per_page, 200),
        "sort": "publication_date:desc",
        "mailto": _MAILTO,
    }
    if filters:
        params["filter"] = ",".join(filters)
    return parse_openalex_works(_get_json("https://api.openalex.org/works", params=params))
