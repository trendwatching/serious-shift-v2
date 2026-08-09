"""
Transport and parsing: turning a URL into dated, de-duplicated text on disk.

Everything here is about *one item* — no source-manifest logic, no watermark,
no orchestration. That separation is what lets the handlers in `handlers.py`
stay short: they decide which URLs to visit, this decides what a URL yields.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ...core import db
from ...core.text import fs_slug as slugify

# raw_content is cwd-based and ephemeral — scrape and extract run in the same
# invocation, and the watermark that decides what to fetch next is in Postgres,
# not on disk.
RAW_DIR = os.environ.get('RAW_CONTENT_DIR', os.path.join(os.getcwd(), 'raw_content'))

SKIP_PATTERNS = [
    'privacy', 'terms', 'policy', 'legal', 'careers', 'jobs', 'cookie',
    'login', 'signup', 'sign-in', 'sign_in', 'logout', 'contact', 'about-us',
    'tag/', 'category/', 'author/', 'search', 'page/', '#',
]

# Extensions that are never an article.
#
# SKIP_PATTERNS matches path substrings and has no extension rule, so a link
# harvested from a blog index — `BobTagxedoSmall.jpg`, a zip, an mp4 — was
# queued as an article, fetched, and recorded as a failure. That was 23 of 115
# fetch failures in one run: noise that makes the real failures (I2) harder to
# see, and paid requests for bytes we cannot read.
#
# `.pdf` is deliberately NOT here. For the academic sources a PDF *is* the
# content, and skipping it silently at the door would bury that rather than fix
# it — see I5 in docs/AUDIT-2026-08-08.md. It still gets dropped, loudly, where
# it can be counted.
SKIP_EXTENSIONS = frozenset({
    # images
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tif', 'tiff',
    'avif', 'heic',
    # archives and binaries
    'zip', 'gz', 'tgz', 'bz2', 'xz', '7z', 'rar', 'dmg', 'exe', 'pkg', 'deb',
    'rpm', 'iso',
    # media
    'mp3', 'mp4', 'm4a', 'm4v', 'mov', 'avi', 'mkv', 'webm', 'wav', 'flac',
    'ogg', 'aac',
    # documents we have no extractor for
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'csv', 'epub', 'mobi',
    # page furniture and feeds — a feed is fetched by its own handler, never as
    # an article
    'css', 'js', 'mjs', 'json', 'xml', 'rss', 'atom', 'woff', 'woff2', 'ttf',
    'otf', 'eot',
})


class ScrapeFetchError(Exception):
    """A per-item fetch failure, for error-log attribution.
    Raised when fetch_article_text returns nothing and both the article fetch
    and any available fallback have been exhausted.
    """


def thinker_dir(name):
    d = os.path.join(RAW_DIR, name.replace(' ', '_'))
    os.makedirs(d, exist_ok=True)
    return d

def raw_file_exists(thinker_name, date_str, platform, title):
    fname = f"{date_str}_{platform}_{slugify(title)}.txt"
    return os.path.exists(os.path.join(thinker_dir(thinker_name), fname))

def url_in_db(url):
    """Check whether a URL already exists in the sources table.
    Opens its own short-lived connection so fetch functions don't need conn threaded in.
    """
    if not url:
        return False
    try:
        with db.connect() as c:
            return db.query_one(c, "SELECT id FROM sources WHERE url = %s", (url,)) is not None
    except Exception:
        return False

def external_id_in_db(external_id):
    """Check whether a paper (by arXiv id / OpenAlex id) is already ingested —
    collapses arXiv↔OpenAlex cross-posts that have different URLs but the same
    external id. Own short-lived connection so callers don't thread `conn`."""
    if not external_id:
        return False
    try:
        with db.connect() as c:
            return db.query_one(
                c, "SELECT id FROM sources WHERE external_id = %s", (external_id,)
            ) is not None
    except Exception:
        return False


def save_raw(thinker_name, date_str, platform, title, url, content, meta=None):
    """Persist one raw item. `meta` (optional) carries paper/venue metadata
    (authors, venue, doi, external_id, citation_count, source_type) which is
    emitted into the front-matter so process_raw can attribute the item without
    re-deriving it. `thinker_name` is the ATTRIBUTED entity (for papers this is
    the primary author, not the feed owner)."""
    fname = f"{date_str}_{platform}_{slugify(title)}.txt"
    path = os.path.join(thinker_dir(thinker_name), fname)
    if os.path.exists(path):
        return None
    extra = ""
    if meta:
        for key in ("authors", "venue", "doi", "external_id", "citation_count", "source_type", "authority"):
            val = meta.get(key)
            if val is None or val == "":
                continue
            if key == "authors" and isinstance(val, (list, tuple)):
                val = "; ".join(str(a) for a in val)
            extra += f"{key}: {str(val).replace(chr(10), ' ')}\n"
    header = (
        f"---\nthinker: {thinker_name}\ntitle: {title}\ndate: {date_str}\n"
        f"platform: {platform}\nurl: {url}\n"
        f"{extra}"
        f"scraped_at: {datetime.now().isoformat()}\n---\n\n"
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(header + content)
    return path

def parse_date(d):
    if not d:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(d).strftime('%Y-%m-%d')
    except Exception:
        pass
    for fmt in ['%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
        try:
            return datetime.strptime(d.strip()[:25], fmt).strftime('%Y-%m-%d')
        except Exception:
            pass
    return None

def in_range(date_str, since, until):
    if not date_str:
        return True
    try:
        return since <= date_str <= until
    except Exception:
        return True

def url_extension(url):
    """The extension of a URL's last path segment, lowercased, or ''.

    Taken from the PATH only. A query string must not be able to hide an
    extension (`/dl?f=x.jpg` is a page, not an image) nor invent one
    (`/some-post?ref=a.png` is an article).
    """
    try:
        last = urlparse(url).path.rsplit('/', 1)[-1]
    except Exception:
        return ''
    _, dot, ext = last.rpartition('.')
    # `rpartition` returns ('', '', last) when there is no dot at all, and a
    # leading-dot name like `.gitignore` has no stem — neither is an extension.
    if not dot or not _:
        return ''
    return ext.lower()


def should_skip_url(url):
    lower = url.lower()
    if any(p in lower for p in SKIP_PATTERNS):
        return True
    return url_extension(url) in SKIP_EXTENSIONS

def extract_date_from_url(url: str) -> str | None:
    """
    Try to extract a YYYY-MM-DD date from a URL string alone (no fetch needed).
    Used by scrape_blog to sort candidates newest-first before fetching.

    Patterns tried in order:
      /2025/04/15/  or  /2025/04/   (path segments)
      2025-04-15                     (ISO date anywhere in URL)
      20250415                       (compact date in slug)
    Returns None if nothing parseable is found.
    """
    # /YYYY/MM/DD/  or  /YYYY/MM/
    m = re.search(r'/(\d{4})/(\d{1,2})(?:/(\d{1,2}))?(?:/|$|-)', url)
    if m:
        y, mo = m.group(1), m.group(2).zfill(2)
        d = (m.group(3) or '01').zfill(2)
        try:
            datetime.strptime(f"{y}-{mo}-{d}", '%Y-%m-%d')
            # Sanity-check: year must be plausible
            if 2000 <= int(y) <= 2100:
                return f"{y}-{mo}-{d}"
        except ValueError:
            pass
    # ISO date anywhere in URL
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', url)
    if m:
        try:
            datetime.strptime(m.group(0), '%Y-%m-%d')
            if 2000 <= int(m.group(1)) <= 2100:
                return m.group(0)
        except ValueError:
            pass
    # Compact YYYYMMDD in a URL slug (not part of a longer digit sequence)
    m = re.search(r'(?<!\d)(\d{8})(?!\d)', url)
    if m:
        s = m.group(1)
        try:
            datetime.strptime(s, '%Y%m%d')
            if 2000 <= int(s[:4]) <= 2100:
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        except ValueError:
            pass
    return None

def fetch_article_text(url):
    """Fetch and extract clean text from an article URL. Returns (text, pub_date)."""
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        pub_date = None
        import json as _json
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                if not isinstance(script.string, str):
                    continue
                ld = _json.loads(script.string)
                dp = ld.get('datePublished', '')
                if dp:
                    pub_date = parse_date(dp)
                    if pub_date:
                        break
            except Exception:
                pass
        if not pub_date:
            for meta in soup.find_all('meta'):
                prop = meta.get('property', '') or meta.get('name', '')
                if prop in ('article:published_time', 'og:published_time', 'datePublished'):
                    pub_date = parse_date(meta.get('content', ''))
                    if pub_date:
                        break
        if not pub_date:
            for tt in soup.find_all('time'):
                pub_date = parse_date(tt.get('datetime', ''))
                if pub_date:
                    break
        if not pub_date:
            dp_match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', resp.text)
            if dp_match:
                pub_date = parse_date(dp_match.group(1))

        for tag in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside', 'form']):
            tag.decompose()

        article = (
            soup.find('article') or
            soup.find('div', class_=re.compile(
                r'post-content|body-markup|entry-content|article-body|available-content'
            )) or
            soup.find('main')
        )
        text = (
            article.get_text(separator='\n', strip=True) if article
            else soup.body.get_text(separator='\n', strip=True) if soup.body
            else ''
        )
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text, pub_date
    except Exception:
        return None, None

