"""
Blog-index link resolution.

The crawler built absolute URLs by concatenating `base_url + href`. `base_url`
carries a path — the manifest stores things like https://deepmind.google/blog —
so an absolute href of /blog/some-post produced
https://deepmind.google/blog/blog/some-post. Those 404, and they accounted for
61 item failures in a single live run before anyone could see them, because the
error log did not survive the container.

These are the cases `urljoin` gets right and concatenation does not.
"""
from urllib.parse import urljoin, urlparse

import pytest

BASE = "https://deepmind.google/blog"


@pytest.mark.parametrize("href,expected", [
    # The regression: an absolute path must resolve against the ORIGIN, not the
    # base's path. Concatenation gave /blog/blog/… here.
    ("/blog/alphaevolve", "https://deepmind.google/blog/alphaevolve"),
    ("/careers", "https://deepmind.google/careers"),
    # Relative hrefs resolve against the base's directory.
    ("alphaevolve", "https://deepmind.google/alphaevolve"),
    # Absolute URLs pass through untouched.
    ("https://example.com/x", "https://example.com/x"),
    # Protocol-relative keeps the base's scheme.
    ("//cdn.example.com/x", "https://cdn.example.com/x"),
])
def test_href_resolution(href, expected):
    assert urljoin(BASE, href) == expected


def test_concatenation_would_have_doubled_the_segment():
    """Pin the actual bug, so the reasoning survives the fix."""
    naive = BASE + "/blog/alphaevolve"
    assert naive == "https://deepmind.google/blog/blog/alphaevolve"
    assert urljoin(BASE, "/blog/alphaevolve") != naive


@pytest.mark.parametrize("href,same_host", [
    ("https://deepmind.google/blog/x", True),
    ("https://evil.example/deepmind.google/x", False),
    # Substring matching on the host let this through: the old check was
    # `base_domain not in href`, and the domain appears in the path here.
    ("https://attacker.test/?q=deepmind.google", False),
])
def test_host_check_is_exact_not_substring(href, same_host):
    assert (urlparse(href).netloc == urlparse(BASE).netloc) is same_host
