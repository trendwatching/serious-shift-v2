#!/usr/bin/env python3
"""
verify_publication.py — validate the map document that is *currently being
served* against the *current* publication contract.

Why this exists
---------------
`mapgen` validates a candidate before promoting it, so a document can only be
published if it passed the contract as it stood at publication time. That leaves
one gap, and it is the gap that actually bit: when the contract is tightened,
every already-published document silently becomes non-conformant. Nothing
re-checks them, the site keeps serving the old one, and the release notes
describe invariants the live bytes do not satisfy.

That is not hypothetical. Staging served a map published 2026-08-02 against a
validator hardened 2026-08-03: 5,298 issues, including 1,831 evidence/voices
items with no source URL and 339 sub-shifts with no `evidence_ids` — on a
product whose proposition is sourced evidence. The code was right; the data was
a day stale, and nothing said so.

So: run this after tightening the contract, and in CI against staging. It is
read-only and costs nothing.

Usage
-----
  # against the live document in Postgres (what the backend reads)
  DATABASE_URL=... python -m serious_shift_pipeline.tools.verify_publication

  # against a deployed origin, via the operator-gated full-map endpoint
  python -m serious_shift_pipeline.tools.verify_publication \
      --url https://backend-staging-1c16.up.railway.app --token "$INSPECTION_TOKEN"

  # against a file
  python -m serious_shift_pipeline.tools.verify_publication --file map.json

Exit codes: 0 = conformant, 1 = issues found, 2 = the document could not be read.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.error
import urllib.request

from ..mapgen.validation import validate_map

# Printed per issue code before collapsing into a count. Enough to act on,
# short enough that a 5,000-issue document is still readable in a terminal.
SAMPLES_PER_CODE = 3


def _from_db(key: str) -> dict:
    from ..core import db

    with db.connect() as conn:
        row = db.query_one(conn, 'SELECT body FROM documents WHERE key = %s', (key,))
    if not row:
        raise RuntimeError(f"no documents row with key {key!r}")
    body = row['body']
    return body if isinstance(body, dict) else json.loads(body)


def _from_url(origin: str, token: str | None) -> dict:
    url = f"{origin.rstrip('/')}/api/map"
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    if token:
        request.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        hint = (' — /api/map is operator-gated; pass --token "$INSPECTION_TOKEN"'
                if e.code in (401, 404) else '')
        raise RuntimeError(f'GET {url} returned {e.code}{hint}') from e


def load_document(args) -> dict:
    if args.file:
        return json.loads(open(args.file, encoding='utf-8').read())
    if args.url:
        return _from_url(args.url, args.token)
    return _from_db(args.key)


def report(document: dict, *, verbose: bool = False) -> int:
    """Print a conformance report. Returns the number of issues found."""
    issues = validate_map(document)
    updated = document.get('updated') or 'unknown'
    shifts = len(document.get('key_trends') or [])
    subs = len(document.get('sub_trends') or [])

    print(f"  published:   {updated}")
    print(f"  content:     {shifts} key shifts, {subs} sub-shifts")

    if not issues:
        print("  contract:    ✓ conformant with the current publication contract")
        return 0

    by_code = collections.Counter(issue.code for issue in issues)
    print(f"  contract:    ✗ {len(issues)} issue(s) across {len(by_code)} code(s)\n")
    for code, count in by_code.most_common():
        print(f"    {count:>6}  {code}")
        examples = [i for i in issues if i.code == code]
        for issue in examples if verbose else examples[:SAMPLES_PER_CODE]:
            print(f"            {issue.path}: {issue.message}")
        if not verbose and len(examples) > SAMPLES_PER_CODE:
            print(f"            … and {len(examples) - SAMPLES_PER_CODE} more")

    repairable = sum(1 for issue in issues if issue.repairable)
    print(f"\n  {repairable} of {len(issues)} issue(s) are repairable by regeneration.")
    print("  Remediate with a synthesis run — `python -m serious_shift_pipeline.run "
          "synthesize --force` for a full rebuild, or `python -m "
          "serious_shift_pipeline.mapgen.cli --editorial-only` to regenerate the")
    print("  editorial modules without truncating the shift tables.")
    return len(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='serious_shift_pipeline.tools.verify_publication',
        description='Validate the served map document against the current contract.')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--url', help='Origin to fetch /api/map from (needs --token).')
    source.add_argument('--file', help='Read the document from a local JSON file.')
    parser.add_argument('--token', help='INSPECTION_TOKEN for the --url form.')
    parser.add_argument('--key', default='map',
                        help="documents key to read from Postgres (default: map). "
                             "Use 'map:previous' to check the rollback document.")
    parser.add_argument('--verbose', action='store_true',
                        help='List every issue instead of a sample per code.')
    args = parser.parse_args()

    print(f"\n{'=' * 60}\n  PUBLICATION CONFORMANCE\n{'=' * 60}")
    try:
        document = load_document(args)
    except Exception as e:  # noqa: BLE001 — an unreadable document is a clear operator error
        print(f"  ERROR: could not read the document: {e}")
        return 2

    issues = report(document, verbose=args.verbose)
    print('=' * 60)
    return 1 if issues else 0


if __name__ == '__main__':
    sys.exit(main())
