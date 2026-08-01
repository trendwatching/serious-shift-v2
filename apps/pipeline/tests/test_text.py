"""Slug helpers.

`url_slug` and the frontend's `slugify` must agree byte-for-byte or deep links
404. Both sides assert the same fixture — this file for Python, and a node check
in the frontend's CI for JavaScript.

The two slug functions are deliberately different from each other: one produces
URLs, the other filesystem paths, and unifying them would break either live links
or everything already written to raw_content/.
"""
import json

import pytest

from serious_shift_pipeline.core.text import fs_slug, url_slug
from serious_shift_pipeline.paths import contracts_dir

CASES = json.loads((contracts_dir() / "slug_fixtures.json").read_text())["url_slug"]


@pytest.mark.parametrize("text,expected", CASES)
def test_url_slug_matches_shared_fixture(text, expected):
    assert url_slug(text) == expected


def test_apostrophes_close_up_rather_than_split():
    # The bug this guards: [^a-z0-9] turned "can't" into "can-t", so the URL the
    # frontend built never matched the slug the pipeline stored.
    assert url_slug("Capability Arrives, Deployment Doesn't") == \
        "capability-arrives-deployment-doesnt"


def test_url_slug_keeps_non_ascii_letters():
    assert url_slug("Rôle of AI") == "rôle-of-ai"


def test_fs_slug_uses_underscores_and_caps_length():
    # raw_content/ directory names — changing the separator orphans existing files.
    assert fs_slug("Andrej Karpathy") == "andrej_karpathy"
    assert len(fs_slug("x" * 200)) == 60
    assert fs_slug("x" * 200, max_len=10) == "x" * 10


def test_the_two_slugs_stay_distinct():
    assert url_slug("A B") == "a-b"
    assert fs_slug("A B") == "a_b"
