"""
Which harvested links are worth fetching.

`SKIP_PATTERNS` matches path substrings and had no extension rule, so an asset
link scraped off a blog index — `BobTagxedoSmall.jpg`, a zip, an mp4 — was
queued as an article, fetched, and written to `pipeline_errors`. That was 23 of
115 fetch failures in one run: paid requests for bytes nothing can read, and
noise that hides the three genuinely misconfigured sources underneath it.

The interesting cases are the ones a naive `'.jpg' in url` check gets wrong in
both directions, which is why the rule reads the path and ignores the query.
"""
import pytest

from serious_shift_pipeline.steps.scraper.content import (
    SKIP_EXTENSIONS,
    should_skip_url,
    url_extension,
)

BASE = "https://example.com"


@pytest.mark.parametrize("url,ext", [
    (f"{BASE}/img/BobTagxedoSmall.jpg", "jpg"),
    (f"{BASE}/files/deck.PPTX", "pptx"),              # case is not a signal
    (f"{BASE}/feed.xml", "xml"),
    (f"{BASE}/2026/04/the-post", ""),                 # no dot at all
    (f"{BASE}/2026/04/the-post/", ""),                # trailing slash, no segment
    (f"{BASE}/.gitignore", ""),                       # leading dot is not an extension
    (f"{BASE}/", ""),
    ("not a url at all", ""),
    # The query must not be able to invent an extension...
    (f"{BASE}/2026/04/the-post?ref=share.png", ""),
    (f"{BASE}/2026/04/the-post#fig.jpg", ""),
    # ...nor to hide one behind a parameter.
    (f"{BASE}/download.zip?token=abc", "zip"),
])
def test_extension_comes_from_the_path_only(url, ext):
    assert url_extension(url) == ext


@pytest.mark.parametrize("url", [
    f"{BASE}/img/BobTagxedoSmall.jpg",
    f"{BASE}/assets/site.css",
    f"{BASE}/downloads/archive.zip",
    f"{BASE}/talks/keynote.mp4",
    f"{BASE}/feed.rss",
    f"{BASE}/privacy",                                # the pre-existing rule still applies
])
def test_assets_and_furniture_are_skipped(url):
    assert should_skip_url(url) is True


@pytest.mark.parametrize("url", [
    f"{BASE}/2026/04/why-scaling-stalled",
    f"{BASE}/2026/04/why-scaling-stalled?utm_source=x.png",
    f"{BASE}/notes/on-alignment.html",                # html IS an article
    f"{BASE}/p/some-substack-post",
])
def test_real_articles_survive(url):
    assert should_skip_url(url) is False


def test_pdfs_are_not_silently_skipped():
    """A PDF *is* the content for the academic sources.

    Adding `pdf` here would make I5 invisible rather than fixed: the item would
    vanish at the door instead of being dropped somewhere it can be counted and
    later extracted. Asserted so nobody tidies it in.
    """
    assert "pdf" not in SKIP_EXTENSIONS
    assert should_skip_url(f"{BASE}/papers/2604.11234v1.pdf") is False
