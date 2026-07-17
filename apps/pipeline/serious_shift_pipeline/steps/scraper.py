#!/usr/bin/env python3
"""
Serious Shift Scraper v3 — append-only, watermark-based refresh.

Fetch modes
  --auto-since (default)  Per-source watermark from source_state table.
                          Each source resumes from where it last stopped.
  --since DATE            Global override — use DATE for all sources.
                          Use this for backfills; it bypasses source_state.
  --until DATE            Upper bound (default: today). Rarely needed.

Usage
  python3 scraper.py --all                              # weekly append-only
  python3 scraper.py --thinker "Ethan Mollick"          # one thinker
  python3 scraper.py --all --since 2023-01-01           # backfill override
  python3 scraper.py --all --mode historical --since 2023-01-01

Watermark invariant
  source_state.last_item_date advances ONLY after a successful fetch.
  Processing (process_raw.py) reads from raw_content/ independently.
  A crash between scrape and process leaves the watermark where it was,
  so raw files on disk get processed on the next process_raw.py run —
  they are NOT re-fetched because the watermark already advanced.

Dependencies: pip install requests beautifulsoup4 feedparser youtube-transcript-api yt-dlp
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from datetime import datetime

from ..core import db, parallel

# Source manifest now lives in the DB (scrape_sources); raw_content + logs are cwd-based.
RAW_DIR     = os.environ.get('RAW_CONTENT_DIR', os.path.join(os.getcwd(), 'raw_content'))
LOG_PATH    = os.path.join(os.getcwd(), 'scrape_log.json')
LOGS_DIR    = os.environ.get('SS_LOGS_DIR', os.path.join(os.getcwd(), 'logs'))

# Default lookback when a source has no source_state entry yet.
FALLBACK_SINCE = '2023-01-01'

SKIP_PATTERNS = [
    'privacy', 'terms', 'policy', 'legal', 'careers', 'jobs', 'cookie',
    'login', 'signup', 'sign-in', 'sign_in', 'logout', 'contact', 'about-us',
    'tag/', 'category/', 'author/', 'search', 'page/', '#',
]


class ScrapeFetchError(Exception):
    """Represents a per-item fetch failure for error_log attribution.
    Used when fetch_article_text returns no content and both article-fetch
    and any available fallback have been exhausted.
    """


# ============================================================
# UTILITY
# ============================================================

def slugify(text, max_len=60):
    s = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[\s_]+', '_', s).strip('_')[:max_len]

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

def save_raw(thinker_name, date_str, platform, title, url, content):
    fname = f"{date_str}_{platform}_{slugify(title)}.txt"
    path = os.path.join(thinker_dir(thinker_name), fname)
    if os.path.exists(path):
        return None
    header = (
        f"---\nthinker: {thinker_name}\ntitle: {title}\ndate: {date_str}\n"
        f"platform: {platform}\nurl: {url}\n"
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

def should_skip_url(url):
    lower = url.lower()
    return any(p in lower for p in SKIP_PATTERNS)

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
    import requests
    from bs4 import BeautifulSoup
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        pub_date = None
        import json as _json
        for script in soup.find_all('script', type='application/ld+json'):
            try:
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


# ============================================================
# DATABASE SCHEMA + WATERMARK HELPERS
# ============================================================

# NOTE: the source_state table is created by packages/db migrations, not here.

def get_thinker_id(conn, name):
    """Look up thinker.id by name (fuzzy match). Returns None if not found."""
    r = db.query_one(conn, "SELECT id FROM thinkers WHERE name ILIKE %s", (f"%{name}%",))
    return r['id'] if r else None

def get_since_for_source(conn, thinker_id, platform, source_url, fallback):
    """
    Return the since-date (YYYY-MM-DD string) to use for this specific source.
    Uses last_item_date from source_state, or fallback if no entry exists.
    """
    r = db.query_one(
        conn,
        """SELECT last_item_date FROM source_state
           WHERE thinker_id = %s AND platform = %s AND source_url = %s""",
        (thinker_id, platform, source_url),
    )
    if r and r['last_item_date']:
        # Postgres returns a date object; keep the string contract downstream.
        d = r['last_item_date']
        return d.isoformat() if hasattr(d, 'isoformat') else str(d)
    return fallback

def update_source_state(conn, thinker_id, platform, source_url,
                        newest_date, items_fetched, status):
    """
    Upsert source_state for one source after a fetch attempt.

    Invariant: last_item_date only moves forward — it never regresses.
    If newest_date is None (nothing fetched), last_item_date is unchanged.
    (Postgres: SQLite's 2-arg MAX(a,b) becomes GREATEST(a,b).)
    """
    db.execute(
        conn,
        """INSERT INTO source_state
               (thinker_id, platform, source_url,
                last_fetched_at, last_item_date, last_run_status, items_last_run)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(thinker_id, platform, source_url) DO UPDATE SET
               last_fetched_at = excluded.last_fetched_at,
               last_item_date  = CASE
                   WHEN excluded.last_item_date IS NOT NULL
                   THEN GREATEST(COALESCE(source_state.last_item_date, '2000-01-01'::date),
                                 excluded.last_item_date)
                   ELSE source_state.last_item_date
               END,
               last_run_status = excluded.last_run_status,
               items_last_run  = excluded.items_last_run
        """,
        (
            thinker_id, platform, source_url,
            datetime.now().isoformat(),
            newest_date,
            status,
            items_fetched,
        ),
    )
    conn.commit()


# ============================================================
# LOG
# ============================================================

class Log:
    def __init__(self):
        self.stats = {'found': 0, 'fetched': 0, 'skipped': 0, 'failed': 0}
        self.entries = []
        self._lock = threading.Lock()   # log() is called from worker threads

    def log(self, action, thinker, platform, title='', url='', error=''):
        with self._lock:
            self.entries.append({
                'action': action,
                'thinker': thinker,
                'platform': platform,
                'title': title[:80],
            })
            self.stats[action] = self.stats.get(action, 0) + 1

    def save(self):
        with open(LOG_PATH, 'w') as f:
            json.dump(
                {'run_at': datetime.now().isoformat(),
                 'stats': self.stats,
                 'entries': self.entries},
                f, indent=2,
            )

    def summary(self):
        print(f"\n{'='*50}\nSCRAPE SUMMARY\n{'='*50}")
        for k, v in self.stats.items():
            print(f"  {k}: {v}")


class ErrorLog:
    """
    Append-only structured error log shared across all pipeline stages.
    Writes one JSON object per line to logs/error_log.jsonl.
    Both scraper.py and process_raw.py write to the same file.
    """
    PATH = os.path.join(LOGS_DIR, 'error_log.jsonl')

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._count = 0
        self._lock = threading.Lock()   # record() is called from worker threads
        os.makedirs(LOGS_DIR, exist_ok=True)

    def record(self, *, stage, thinker, exc,
               retry_attempted: bool, outcome: str = 'skipped', **extra):
        """
        Append one error entry. Extra kwargs (platform, source_url, etc.)
        are merged into the JSON object so both scraper and processor can
        pass stage-specific fields without a shared schema.
        """
        import traceback as tb
        entry = {
            'run_id':          self.run_id,
            'timestamp':       datetime.now().isoformat(),
            'stage':           stage,
            'thinker':         thinker,
            'error_class':     type(exc).__name__,
            'error_message':   str(exc)[:500],
            'traceback':       tb.format_exc(),
            'retry_attempted': retry_attempted,
            'outcome':         outcome,
            **{k: str(v)[:200] for k, v in extra.items()},
        }
        line = json.dumps(entry) + '\n'
        with self._lock:
            with open(self.PATH, 'a', encoding='utf-8') as f:
                f.write(line)
            self._count += 1

    @property
    def count(self) -> int:
        return self._count


# ============================================================
# SUBSTACK SCRAPER
# ============================================================

def scrape_substack(thinker_name, cfg, since, until, mode, log, error_log=None):
    """
    Returns (watermark_date, count_fetched).
    Watermark strategy: same as scrape_rss — see that docstring.
    """
    import requests
    base_url = cfg['url'].rstrip('/')
    platform = cfg.get('platform', 'substack')

    if mode == 'historical':
        print(f"  Fetching sitemap: {base_url}/sitemap.xml")
        try:
            resp = requests.get(
                f"{base_url}/sitemap.xml", timeout=15,
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            post_urls = re.findall(
                r'<loc>(' + re.escape(base_url) + r'/p/[^<]+)</loc>', resp.text
            )
            print(f"    Found {len(post_urls)} posts in sitemap")
        except Exception as e:
            print(f"    Sitemap failed: {e}. Falling back to RSS.")
            post_urls = []

        if not post_urls:
            return scrape_rss(thinker_name, cfg, since, until, log, error_log)

        fetched_this_run = 0
        success_dates: list[str] = []
        all_dates:    list[str] = []
        had_fetch_failure = False
        td = thinker_dir(thinker_name)

        for url in post_urls:
            if should_skip_url(url) or url_in_db(url):
                log.log('skipped', thinker_name, platform, url=url)
                continue

            slug = url.split('/p/')[-1].rstrip('/')
            title = slug.replace('-', ' ').title()
            title_slug = slugify(title)
            existing = [f for f in os.listdir(td) if title_slug in f and f.endswith('.txt')]
            if existing:
                log.log('skipped', thinker_name, platform, title, url)
                continue

            time.sleep(2)
            text, pub_date = fetch_article_text(url)
            date_str = pub_date or datetime.now().strftime('%Y-%m-%d')

            if not in_range(date_str, since, until):
                continue

            all_dates.append(date_str)

            if not text or len(text) < 200:
                had_fetch_failure = True
                if error_log is not None:
                    exc = ScrapeFetchError(f"No usable content for: {url}")
                    error_log.record(
                        stage='scrape_item', thinker=thinker_name,
                        exc=exc, retry_attempted=False, outcome='skipped',
                        platform=platform, item_url=url,
                        item_title=title[:200], item_date=date_str,
                    )
                continue

            log.log('found', thinker_name, platform, title, url)
            path = save_raw(thinker_name, date_str, platform, title, url, text)
            if path:
                log.log('fetched', thinker_name, platform, title, url)
                fetched_this_run += 1
                success_dates.append(date_str)
                print(f"    FETCHED [{fetched_this_run}]: {title[:50]} ({len(text)} chars)")

        print(f"    Total fetched from sitemap: {fetched_this_run}")

        if success_dates:
            if had_fetch_failure and all_dates:
                watermark_date = min(all_dates)
                print(f"    ⚠  Item fetch failures — watermark set to earliest attempted: {watermark_date}")
            else:
                watermark_date = max(success_dates)
        else:
            watermark_date = None

        return watermark_date, fetched_this_run
    else:
        return scrape_rss(thinker_name, cfg, since, until, log, error_log)


def scrape_rss(thinker_name, cfg, since, until, log, error_log=None):
    """
    Standard RSS scraping. Returns (watermark_date, count_fetched).

    Watermark strategy (Bug 2 fix):
      - Normal run (no failures): watermark = newest success date.
      - Any per-item failure: watermark = min(all_attempted_dates) so the
        failed items fall inside the next run's window.  Successfully-fetched
        items that get re-visited are deduped by raw_file_exists / url_in_db.
    """
    import feedparser
    import requests
    rss_url = cfg.get('rss') or cfg['url'].rstrip('/') + '/feed'
    platform = cfg.get('platform', 'blog')

    print(f"  Fetching RSS: {rss_url}")
    # Fetch via requests (certifi roots) then hand the body to feedparser.
    # Calling feedparser.parse(url) directly used the stdlib opener which on
    # this machine fails with SSL CERTIFICATE_VERIFY_FAILED for many feeds
    # — and the silent failure mode is "0 entries", which historically read
    # as "source produced no content" rather than "scraper couldn't connect".
    try:
        resp = requests.get(rss_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        feed = feedparser.parse(resp.content) if resp.ok else feedparser.parse(rss_url)
    except Exception as e:
        print(f"    requests fetch failed ({e}), falling back to feedparser.parse(url)")
        feed = feedparser.parse(rss_url)
    print(f"    Found {len(feed.entries)} entries")

    fetched = 0
    success_dates: list[str] = []   # dates of items successfully saved
    all_dates:    list[str] = []    # dates of every in-range item attempted
    had_fetch_failure = False

    for entry in feed.entries:
        title    = entry.get('title', 'Untitled')
        url      = entry.get('link', '')
        pub_date = parse_date(entry.get('published', ''))
        date_str = pub_date or datetime.now().strftime('%Y-%m-%d')

        if not in_range(date_str, since, until):
            continue
        if raw_file_exists(thinker_name, date_str, platform, title) or url_in_db(url):
            log.log('skipped', thinker_name, platform, title, url)
            continue

        all_dates.append(date_str)
        log.log('found', thinker_name, platform, title, url)
        time.sleep(2)
        text, _ = fetch_article_text(url)
        if not text or len(text) < 200:
            from bs4 import BeautifulSoup
            html = (
                entry.get('content', [{}])[0].get('value', '')
                or entry.get('summary', '')
            )
            text = (
                BeautifulSoup(html, 'html.parser').get_text(separator='\n', strip=True)
                if html else ''
            )

        if text and len(text) >= 200:
            path = save_raw(thinker_name, date_str, platform, title, url, text)
            if path:
                log.log('fetched', thinker_name, platform, title, url)
                fetched += 1
                success_dates.append(date_str)
                print(f"    FETCHED: {title[:50]} ({len(text)} chars)")
        else:
            # Both full-fetch and RSS-fallback failed — this item needs a retry.
            had_fetch_failure = True
            log.log('failed', thinker_name, platform, title, url, 'Too short or no content')
            if error_log is not None:
                exc = ScrapeFetchError(
                    f"No usable content after full-fetch + RSS fallback for: {url}"
                )
                error_log.record(
                    stage='scrape_item', thinker=thinker_name,
                    exc=exc, retry_attempted=False, outcome='skipped',
                    platform=platform, item_url=url,
                    item_title=title[:200], item_date=date_str,
                )

    # Watermark strategy: if any item failed, go back to the earliest date
    # we attempted so the failure falls inside the next run's window.
    if success_dates:
        if had_fetch_failure and all_dates:
            watermark_date = min(all_dates)
            print(f"    ⚠  Item fetch failures — watermark set to earliest attempted: {watermark_date}")
        else:
            watermark_date = max(success_dates)
    else:
        watermark_date = None

    return watermark_date, fetched


# ============================================================
# BLOG SCRAPER
# ============================================================

def scrape_blog(thinker_name, cfg, since, until, log, error_log=None):
    """
    Blog index scraper. Returns (watermark_date, count_fetched).

    Bug 1 fix — sort candidates by date before fetching:
      URLs containing a parseable date (path segments, ISO, compact YYYYMMDD)
      are sorted newest-first.  URLs with no extractable date are deprioritised
      (placed after all dated links).  This maximises the chance that the 30
      fetch slots go to recent content.

    Bug 2 fix — watermark on partial batch failure:
      Dates are only known after a successful fetch, so when per-item fetch
      failures occur, the watermark falls back to min(success_dates).
      Successfully-fetched items re-seen on the next run are deduped by
      raw_file_exists.
    """
    import requests
    from bs4 import BeautifulSoup

    if cfg.get('rss'):
        return scrape_rss(thinker_name, cfg, since, until, log, error_log)

    base_url = cfg['url'].rstrip('/')
    platform = cfg.get('platform', 'blog')

    print(f"  Scraping blog: {base_url}")
    try:
        resp = requests.get(
            base_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'}
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        # Re-raise so scrape_thinker's retry wrapper can catch it, retry once,
        # write to error_log.jsonl, and set source_state status='failed'.
        print(f"    FAILED to fetch index page: {e}")
        raise

    archive_urls = [base_url]
    for a in soup.find_all('a', href=True):
        if 'archive' in a['href'].lower():
            href = a['href']
            if href.startswith('/'):
                href = base_url + href
            archive_urls.append(href)

    links = set()
    for page_url in archive_urls[:2]:
        try:
            if page_url != base_url:
                time.sleep(1)
                resp = requests.get(
                    page_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'}
                )
                soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                if not text or len(text) < 8:
                    continue
                if href.startswith('/'):
                    href = base_url + href
                if not href.startswith('http'):
                    continue
                base_domain = base_url.split('//')[1].split('/')[0]
                if base_domain not in href:
                    continue
                if should_skip_url(href):
                    continue
                if href in (base_url, base_url + '/'):
                    continue
                links.add((text, href))
        except Exception:
            pass

    print(f"    Found {len(links)} article links (filtered)")

    # Bug 1: sort by URL-extractable date descending, undated links last.
    # sort key: ('0' + inverted_date) for dated, ('1') for undated
    # — this groups dated links before undated, newest-first within dated.
    def _date_sort_key(link):
        _, url = link
        d = extract_date_from_url(url)
        return ('0', d) if d else ('1', '')

    candidates = sorted(links, key=_date_sort_key, reverse=True)[:30]

    fetched = 0
    success_dates: list[str] = []
    had_fetch_failure = False

    for title, url in candidates:
        time.sleep(2)
        text, pub_date = fetch_article_text(url)
        date_str = pub_date or datetime.now().strftime('%Y-%m-%d')

        if not in_range(date_str, since, until):
            continue

        if text is None:
            # Complete fetch failure — log to error_log for visibility.
            had_fetch_failure = True
            if error_log is not None:
                exc = ScrapeFetchError(f"fetch_article_text returned None for: {url}")
                error_log.record(
                    stage='scrape_item', thinker=thinker_name,
                    exc=exc, retry_attempted=False, outcome='skipped',
                    platform=platform, item_url=url, item_title=title[:200],
                )
            continue

        if len(text) < 300:
            continue

        if raw_file_exists(thinker_name, date_str, platform, title):
            log.log('skipped', thinker_name, platform, title, url)
            continue

        log.log('found', thinker_name, platform, title, url)
        path = save_raw(thinker_name, date_str, platform, title, url, text)
        if path:
            log.log('fetched', thinker_name, platform, title, url)
            fetched += 1
            success_dates.append(date_str)
            print(f"    FETCHED: {title[:50]} ({len(text)} chars)")

    # Watermark: fall back to oldest success when failures occurred so the
    # failed articles remain within the next run's window.
    if success_dates:
        if had_fetch_failure:
            watermark_date = min(success_dates)
            print(f"    ⚠  Item fetch failures — watermark set to oldest success: {watermark_date}")
        else:
            watermark_date = max(success_dates)
    else:
        watermark_date = None

    return watermark_date, fetched


# ============================================================
# YOUTUBE SCRAPER
# ============================================================

def _youtube_proxy_url():
    """Generic proxy URL for YouTube, if configured (http://user:pass@host:port)."""
    return os.environ.get('YOUTUBE_PROXY_URL')


def _build_ytt():
    """YouTubeTranscriptApi, optionally routed through a proxy.

    YouTube blocks transcript requests from most datacenter/cloud IPs (Railway,
    AWS, …). To make YouTube work from a cloud host, set either:
      * WEBSHARE_PROXY_USERNAME + WEBSHARE_PROXY_PASSWORD  (Webshare residential), or
      * YOUTUBE_PROXY_URL = http://user:pass@host:port      (any HTTP proxy)
    Without one of these, transcript fetches from a cloud IP will be IP-blocked and
    skipped (the rest of the pipeline still runs).
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    ws_user = os.environ.get('WEBSHARE_PROXY_USERNAME')
    ws_pass = os.environ.get('WEBSHARE_PROXY_PASSWORD')
    generic = _youtube_proxy_url()
    try:
        if ws_user and ws_pass:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            return YouTubeTranscriptApi(proxy_config=WebshareProxyConfig(
                proxy_username=ws_user, proxy_password=ws_pass))
        if generic:
            from youtube_transcript_api.proxies import GenericProxyConfig
            return YouTubeTranscriptApi(proxy_config=GenericProxyConfig(
                http_url=generic, https_url=generic))
    except Exception as e:  # noqa: BLE001 — proxy is best-effort; fall back to direct
        print(f"    ⚠  YouTube proxy config failed ({e}); continuing without a proxy.")
    return YouTubeTranscriptApi()


def _is_ip_block(exc) -> bool:
    """True if the exception is YouTube IP-blocking us (cloud IP, no proxy)."""
    name = type(exc).__name__
    msg = str(exc).lower()
    return (name in ('RequestBlocked', 'IpBlocked')
            or 'blocking requests' in msg or 'ipblocked' in msg)


def scrape_youtube(thinker_name, cfg, since, until, log):
    """
    YouTube transcript scraper. Returns (newest_date_fetched_or_None, count_fetched).
    """
    import subprocess
    channel_url = cfg.get('channel_url', '')
    platform = 'youtube'
    if not channel_url:
        print(f"  No YouTube channel for {thinker_name}")
        return None, 0

    print(f"  Fetching YouTube: {channel_url}")
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--skip-download', '--print', '%(id)s|||%(title)s|||%(upload_date)s',
        f'{channel_url}/videos',
        '--no-warnings', '--quiet',
        '--match-filter', f'upload_date >= {since.replace("-","")}'
    ]
    if _youtube_proxy_url():  # route listing through the same proxy as transcripts
        cmd += ['--proxy', _youtube_proxy_url()]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        # Re-raise so scrape_thinker's retry wrapper handles it consistently.
        print(f"    yt-dlp subprocess failed: {e}")
        raise

    # Bug 3: yt-dlp non-zero exit with no output means a real failure
    # (rate-limit, geo-block, auth error).  Raise so the retry wrapper fires.
    # If we got partial output despite a non-zero code, warn and use what we have.
    if result.returncode != 0:
        if not result.stdout.strip():
            stderr_snippet = (result.stderr or '').strip()[:200]
            raise RuntimeError(
                f"yt-dlp exited {result.returncode} with no output. "
                f"stderr: {stderr_snippet or '(empty)'}"
            )
        else:
            print(f"    ⚠  yt-dlp exited {result.returncode} (partial output). Continuing with available data.")

    videos = []
    for line in result.stdout.strip().split('\n'):
        if '|||' not in line:
            continue
        parts = line.split('|||')
        if len(parts) < 3:
            continue
        vid_id, title, date_raw = parts[0], parts[1], parts[2]
        if date_raw and len(date_raw) == 8:
            date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        else:
            date_str = None
        if date_str and in_range(date_str, since, until):
            videos.append((vid_id, title, date_str))

    print(f"    Found {len(videos)} videos in range")

    if not videos:
        return None, 0

    ytt = _build_ytt()

    fetched = 0
    newest_date = None

    for vid_id, title, date_str in videos:
        url = f"https://www.youtube.com/watch?v={vid_id}"
        if raw_file_exists(thinker_name, date_str, platform, title):
            log.log('skipped', thinker_name, platform, title, url)
            print(f"    SKIP: {title[:50]}")
            continue

        log.log('found', thinker_name, platform, title, url)
        try:
            time.sleep(2)
            transcript_list = ytt.fetch(vid_id)
            text = ' '.join(entry.text for entry in transcript_list)
            if len(text) < 100:
                log.log('failed', thinker_name, platform, title, url, 'Transcript too short')
                continue
            path = save_raw(thinker_name, date_str, platform, title, url, text)
            if path:
                log.log('fetched', thinker_name, platform, title, url)
                fetched += 1
                if not newest_date or date_str > newest_date:
                    newest_date = date_str
                print(f"    FETCHED: {title[:50]} ({len(text)} chars)")
        except Exception as e:
            log.log('failed', thinker_name, platform, title, url, str(e))
            if _is_ip_block(e):
                # The whole channel is blocked from this IP — don't hammer every
                # video (each would sleep + fail identically). Stop here.
                print(f"    ⛔  YouTube is IP-blocking transcript requests (cloud IP). "
                      f"Skipping YouTube for {thinker_name}. Set WEBSHARE_PROXY_USERNAME/"
                      f"WEBSHARE_PROXY_PASSWORD or YOUTUBE_PROXY_URL to enable it.")
                break
            print(f"    FAILED: {title[:50]} — {e}")

    return newest_date, fetched


# ============================================================
# MANUAL HANDLER
# ============================================================

def handle_manual(thinker_name, cfg, log):
    """Manual sources: drop a placeholder reminder file."""
    platform = cfg.get('platform', 'manual')
    handle   = cfg.get('handle', '')
    d = thinker_dir(thinker_name)
    placeholder = os.path.join(d, f'_MANUAL_{platform}.txt')
    if not os.path.exists(placeholder):
        with open(placeholder, 'w') as f:
            f.write(f"Manual collection needed for {thinker_name}\nPlatform: {platform}\n")
            if handle:
                f.write(f"Handle: @{handle}\nProfile: https://x.com/{handle}\n")
    print(f"  Manual: {thinker_name} on {platform}" + (f" (@{handle})" if handle else ""))
    log.log('skipped', thinker_name, platform)
    # Manual sources don't update source_state — there's nothing to watermark.


# ============================================================
# ORCHESTRATOR
# ============================================================

def load_thinker_sources(conn, name_filter=None):
    """Load the scrape manifest from the DB as [{name, sources:[{platform, method,
    url, rss, channel_url, handle, note}, …]}, …] — replaces scraper_config.json."""
    rows = db.query(conn, """
        SELECT t.name, ss.platform, ss.method, ss.url, ss.rss, ss.channel_url, ss.handle, ss.note
        FROM scrape_sources ss JOIN thinkers t ON t.id = ss.thinker_id
        ORDER BY t.name, ss.id""")
    by_name: dict = {}
    for r in rows:
        entry = by_name.setdefault(r["name"], {"name": r["name"], "sources": []})
        entry["sources"].append({k: r[k] for k in
                                 ("platform", "method", "url", "rss", "channel_url", "handle", "note")})
    thinkers = list(by_name.values())
    if name_filter:
        thinkers = [t for t in thinkers if name_filter.lower() in t["name"].lower()]
    return thinkers


def scrape_thinker(cfg, mode, global_since, until, log, conn, auto_since, error_log):
    """
    Orchestrate fetching for one thinker across all their sources.

    If auto_since=True, per-source since is read from source_state.
      global_since acts as the fallback for sources with no prior run.
    If auto_since=False, global_since is used for every source.

    Failure handling
      Each source gets one retry (10 s delay). If both attempts fail,
      the error is logged to error_log and the run continues with the
      next source. source_state is ALWAYS updated — even on failure —
      so last_run_status reflects what happened and broken sources are
      visible via a query.

    Watermark invariant
      update_source_state is called after every attempt (success or fail).
      On failure, newest_date=None so last_item_date does not regress.
    """
    name = cfg['name']
    print(f"\n{'='*50}\nSCRAPING: {name} ({mode})\n{'='*50}")

    thinker_id = get_thinker_id(conn, name)
    if thinker_id is None:
        print(f"  WARNING: '{name}' not found in thinkers table — skipping source_state updates.")

    for src in cfg.get('sources', []):
        method   = src.get('method', 'manual')
        platform = src.get('platform', method)
        # Stable per-source identifier for the watermark key. Use `or` (not
        # dict.get defaults): a manifest row has all of url/channel_url/rss/handle
        # as keys, but most are NULL — e.g. a YouTube source sets only
        # channel_url, so `src.get('url', …)` would return None, not fall through.
        src_url  = (src.get('url') or src.get('channel_url') or src.get('rss')
                    or src.get('handle') or 'unknown')

        # Determine effective since for this source
        if auto_since and thinker_id is not None:
            since = get_since_for_source(
                conn, thinker_id, platform, src_url, global_since
            )
        else:
            since = global_since

        print(f"\n  Source: {platform} | {src_url} | since={since}")

        if method == 'manual':
            handle_manual(name, src, log)
            # Manual sources have no watermark — nothing to update
            continue

        newest_date, count, status = None, 0, 'ok'
        last_exc = None

        for attempt in range(2):
            try:
                if method == 'rss':
                    if src.get('platform') == 'substack':
                        newest_date, count = scrape_substack(
                            name, src, since, until, mode, log, error_log
                        )
                    else:
                        newest_date, count = scrape_rss(
                            name, src, since, until, log, error_log
                        )
                elif method == 'scrape_index':
                    newest_date, count = scrape_blog(
                        name, src, since, until, log, error_log
                    )
                elif method == 'youtube':
                    newest_date, count = scrape_youtube(name, src, since, until, log)
                else:
                    print(f"  Unknown method '{method}' — skipping")
                    status = 'failed'
                last_exc = None   # success — clear any previous attempt error
                break
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    print(
                        f"  ⚠  attempt 1 failed "
                        f"({type(exc).__name__}: {str(exc)[:120]}). "
                        f"Retrying in 10 s…"
                    )
                    time.sleep(10)

        if last_exc is not None:
            status = 'failed'
            newest_date, count = None, 0
            print(f"  ✗  {platform} | {src_url[:60]} failed after retry: {last_exc}")
            error_log.record(
                stage='scrape',
                thinker=name,
                exc=last_exc,
                retry_attempted=True,
                outcome='skipped',
                platform=platform,
                source_url=src_url,
            )

        # Update watermark — ALWAYS called, success or failure.
        # On failure: newest_date=None → last_item_date does not change.
        # last_run_status='failed' makes broken sources queryable.
        if thinker_id is not None:
            update_source_state(
                conn, thinker_id, platform, src_url,
                newest_date, count, status,
            )
            if count:
                print(f"  ✓ Watermark updated: {newest_date} ({count} new items)")
            elif status == 'failed':
                print("  ✗ status=failed written to source_state")
            else:
                print("  — No new items; watermark unchanged")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Serious Shift Scraper v3')
    parser.add_argument('--thinker', help='Scrape specific thinker by name')
    parser.add_argument('--all', action='store_true', help='Scrape all thinkers')
    parser.add_argument('--mode', choices=['historical', 'live'], default='live',
                        help='historical=full archive via sitemap; live=recent RSS (default)')
    parser.add_argument('--since', default=None,
                        help='Override watermark globally. Use for backfills. '
                             'Format: YYYY-MM-DD. Without this flag, per-source '
                             'watermarks from source_state are used.')
    parser.add_argument('--until', default=datetime.now().strftime('%Y-%m-%d'),
                        help='Upper date bound (default: today)')
    args = parser.parse_args()

    if not args.thinker and not args.all:
        parser.error("Specify --thinker 'Name' or --all")

    # auto_since=True  unless user explicitly passed --since
    auto_since   = args.since is None
    global_since = args.since or FALLBACK_SINCE

    conn = db.raw_connect()      # source_state + scrape_sources live in packages/db migrations

    log = Log()
    thinkers = load_thinker_sources(conn, None if args.all else args.thinker)
    if not thinkers:
        print(f"Thinker not found: {args.thinker}")
        conn.close()
        sys.exit(1)

    run_id     = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    error_log  = ErrorLog(run_id)
    mode_label = 'auto-since' if auto_since else f'since={global_since}'
    print(f"Run ID: {run_id}")
    print(f"Mode: {args.mode} | {mode_label} | until={args.until}")
    print(f"Thinkers: {len(thinkers)}")

    # Scrape thinkers concurrently — this is network-bound. Each worker gets its
    # own DB connection (psycopg connections aren't shared across threads); the
    # shared Log/ErrorLog are lock-guarded. Raw files write to per-source paths.
    def scrape_one(t):
        wconn = db.raw_connect()
        try:
            scrape_thinker(t, args.mode, global_since, args.until,
                           log, wconn, auto_since, error_log)
        except Exception as exc:  # noqa: BLE001 — one thinker failing must not stop the rest
            error_log.record(stage='scrape', thinker=t.get('name', '?'), exc=exc,
                             retry_attempted=False, outcome='skipped')
            print(f"  ✗  {t.get('name', '?')} failed: {type(exc).__name__}: {str(exc)[:100]}")
        finally:
            wconn.close()

    parallel.pmap(scrape_one, thinkers)

    conn.close()
    log.save()
    log.summary()

    if error_log.count:
        print(f"\n  Errors: {error_log.count} — see {ErrorLog.PATH}")
    else:
        print("\n  Errors: 0")


if __name__ == '__main__':
    main()
