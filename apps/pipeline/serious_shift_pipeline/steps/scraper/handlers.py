"""
The eight source handlers, and the dispatch that picks one.

Each takes (thinker_name, cfg, since, until, …) and returns the number of items
saved. They share `content.py` for fetching and saving; none of them touches
the watermark — the runner owns that, so a handler cannot advance a mark by
accident.
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from ...core import db
from ...core.text import fs_slug as slugify
from .content import (
    ScrapeFetchError, extract_date_from_url, external_id_in_db, fetch_article_text,
    in_range, parse_date, raw_file_exists, save_raw, should_skip_url, thinker_dir,
    url_in_db,
)


def scrape_substack(thinker_name, cfg, since, until, mode, log, error_log=None):
    """
    Returns (watermark_date, count_fetched).
    Watermark strategy: same as scrape_rss — see that docstring.
    """
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
                        step='scrape_item', thinker=thinker_name,
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
                    step='scrape_item', thinker=thinker_name,
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
                    step='scrape_item', thinker=thinker_name,
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


#: Phrases in an exception that mean "the host refused this IP", not "this
#: source is broken". Matched against yt-dlp's stderr as well as the transcript
#: library's exceptions, because the listing and the transcript fetch are
#: blocked by the same thing but fail through different paths.
_BLOCK_SIGNS = (
    'blocking requests', 'ipblocked', 'sign in to confirm', 'not a bot',
    'too many requests', 'http error 429', 'cookies are no longer valid',
)


def is_ip_block(exc) -> bool:
    """True when the host is refusing this IP rather than the source being broken.

    YouTube blocks datacenter IPs, which is what any cloud host runs on. That is
    a configuration gap (no proxy credential), not a fault in the source, and
    conflating the two meant the failed-source alert fired every run forever.
    """
    if type(exc).__name__ in ('RequestBlocked', 'IpBlocked'):
        return True
    msg = str(exc).lower()
    return any(sign in msg for sign in _BLOCK_SIGNS)



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
            if is_ip_block(e):
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
# RESEARCH-PAPER SCRAPERS (arXiv + OpenAlex)
# ============================================================

def _load_gate_context():
    """Load (allowlist, venue_overrides) for the reputability gate from the DB.
    Best-effort: returns empty defaults if the DB isn't reachable so the scraper
    still runs (the gate then falls back to venue/citation heuristics)."""
    allowlist: set[str] = set()
    overrides: dict[str, int] = {}
    try:
        with db.connect() as c:
            for r in db.query(c, "SELECT name, reputation_tier FROM thinkers"):
                allowlist.add(r['name'])
            for r in db.query(c, "SELECT name, tier FROM reputable_venues"):
                overrides[r['name']] = r['tier']
    except Exception:
        pass
    return allowlist, overrides


def ingest_papers(papers, since, until, platform, log, error_log=None,
                   apply_gate=False, gate_params=None):
    """Shared paper ingest: gate for reputability, attribute to the primary
    author, save abstract + metadata. Returns (watermark_date, count_fetched)."""
    from . import gate as _gate
    gp = gate_params or {}
    allowlist, overrides = _load_gate_context() if apply_gate else (set(), {})

    fetched = 0
    success_dates: list[str] = []
    for p in papers:
        title = p.get('title') or 'Untitled'
        url   = p.get('url') or ''
        date_str = p.get('date') or datetime.now().strftime('%Y-%m-%d')
        if not in_range(date_str, since, until):
            continue
        abstract = (p.get('abstract') or '').strip()
        if len(abstract) < 80:
            continue  # too thin to extract meaningful claims

        # Reputability gate (discovery paths). Curated feeds pass apply_gate=False.
        authority = None
        if apply_gate:
            passed, authority = _gate.is_reputable(
                p, allowlist=allowlist, venue_overrides=overrides,
                min_citations=int(gp.get('min_citations', 0)),
                min_authority=float(gp.get('min_authority', 0.35)),
            )
            if not passed:
                log.log('skipped', p.get('venue') or 'paper', platform, title, url)
                continue

        authors = p.get('authors') or []
        primary = (authors[0] if authors else (p.get('venue') or 'Unknown')).strip()
        if (url_in_db(url) or external_id_in_db(p.get('external_id'))
                or raw_file_exists(primary, date_str, platform, title)):
            log.log('skipped', primary, platform, title, url)
            continue
        meta = {
            'authors': authors,
            'venue': p.get('venue'),
            'doi': p.get('doi'),
            'external_id': p.get('external_id'),
            'citation_count': p.get('citation_count'),
            'source_type': 'research_paper',
            'authority': authority,
        }
        body = (
            f"{title}\n\nAuthors: {', '.join(authors)}\n"
            f"Venue: {p.get('venue')}"
            + (f"  |  Citations: {p['citation_count']}" if p.get('citation_count') is not None else "")
            + f"\n\nAbstract:\n{abstract}"
        )
        log.log('found', primary, platform, title, url)
        if save_raw(primary, date_str, platform, title, url, body, meta=meta):
            log.log('fetched', primary, platform, title, url)
            fetched += 1
            success_dates.append(date_str)
            print(f"    FETCHED [paper]: {title[:60]} — {primary}")
    return (max(success_dates) if success_dates else None), fetched


def scrape_arxiv_category(thinker_name, cfg, since, until, log, error_log=None):
    """arXiv API by category (title + abstract). Returns (watermark, count)."""
    from ...core import sources_api
    params = cfg.get('params') or {}
    categories = params.get('categories') or ['cs.AI']
    max_results = int(params.get('max_results', 60))
    print(f"  arXiv categories {categories} | since={since}")
    papers = sources_api.arxiv_search(categories, since=since, max_results=max_results)
    print(f"    {len(papers)} papers returned")
    return ingest_papers(papers, since, until, cfg.get('platform', 'paper'), log, error_log)


def scrape_arxiv_author(thinker_name, cfg, since, until, log, error_log=None):
    from ...core import sources_api
    params = cfg.get('params') or {}
    author = params.get('author') or cfg.get('handle') or thinker_name
    max_results = int(params.get('max_results', 30))
    print(f"  arXiv author '{author}' | since={since}")
    papers = sources_api.arxiv_by_author(author, since=since, max_results=max_results)
    return ingest_papers(papers, since, until, cfg.get('platform', 'paper'), log, error_log)


def scrape_openalex(thinker_name, cfg, since, until, log, error_log=None):
    """OpenAlex works search, citation-gated. Returns (watermark, count)."""
    from ...core import sources_api
    params = cfg.get('params') or {}
    search = params.get('search') or 'artificial intelligence'
    min_citations = int(params.get('min_citations', 0))
    per_page = int(params.get('per_page', 50))
    print(f"  OpenAlex '{search}' | min_citations={min_citations} | since={since}")
    papers = sources_api.openalex_search(
        search, since=since, min_citations=min_citations, per_page=per_page)
    print(f"    {len(papers)} works returned")
    return ingest_papers(
        papers, since, until, cfg.get('platform', 'paper'), log, error_log,
        apply_gate=True, gate_params=params)


def scrape_org_blog(thinker_name, cfg, since, until, log, error_log=None):
    """AI lab / org blog: RSS when a feed exists, else index scrape."""
    if cfg.get('rss'):
        return scrape_rss(thinker_name, cfg, since, until, log, error_log)
    return scrape_blog(thinker_name, cfg, since, until, log, error_log)


def _run_scraper(method, name, src, since, until, mode, log, error_log):
    """Dispatch a source to its scraper. Central registry so new source types
    register in one place. Every scraper returns (watermark_date, count)."""
    if method == 'rss':
        if src.get('platform') == 'substack':
            return scrape_substack(name, src, since, until, mode, log, error_log)
        return scrape_rss(name, src, since, until, log, error_log)
    if method == 'scrape_index':
        return scrape_blog(name, src, since, until, log, error_log)
    if method == 'org_blog':
        return scrape_org_blog(name, src, since, until, log, error_log)
    if method == 'youtube':
        return scrape_youtube(name, src, since, until, log)
    if method == 'arxiv_category':
        return scrape_arxiv_category(name, src, since, until, log, error_log)
    if method == 'arxiv_author':
        return scrape_arxiv_author(name, src, since, until, log, error_log)
    if method == 'openalex_query':
        return scrape_openalex(name, src, since, until, log, error_log)
    raise ValueError(f"Unknown scrape method '{method}'")


