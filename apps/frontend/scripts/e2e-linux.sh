#!/usr/bin/env bash
# Run the Playwright suite in the same container CI uses.
#
# Visual baselines are per-platform (see playwright.config.mjs). The macOS ones
# come from `npm run test:e2e:update`; the Linux ones have to come from Linux,
# and this is the supported way to produce them:
#
#   npm run test:e2e:linux                          # verify
#   npm run test:e2e:linux -- --update-snapshots    # regenerate
#
# The repo is COPIED into the container, not bind-mounted read-write. Mounting
# it writable and running `npm ci` inside replaces node_modules with Linux
# binaries on the host and breaks every local command until you reinstall.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="$(node -p "require('$HERE/node_modules/@playwright/test/package.json').version")"

# Arguments are passed positionally to the container's shell rather than
# interpolated into the -c string: `$*` flattens quoting, so
# `-- --grep "homepage visual"` arrived as two separate patterns and matched
# nothing while reporting success.
docker run --rm \
  -v "$ROOT":/src:ro \
  -v "$HERE/e2e/__screenshots__":/out \
  "mcr.microsoft.com/playwright:v${VERSION}-noble" \
  sh -c 'cp -r /src /repo \
    && cd /repo/apps/frontend \
    && rm -rf node_modules \
    && npm ci --no-audit --no-fund >/dev/null 2>&1 \
    && CI=true npx playwright test "$@" ; status=$? ; \
    cp -r /repo/apps/frontend/e2e/__screenshots__/linux /out/ 2>/dev/null || true ; \
    exit $status' _ "$@"
