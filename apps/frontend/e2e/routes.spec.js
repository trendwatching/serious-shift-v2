import { test, expect } from '@playwright/test'
import { mockMap } from './fixtures.js'

/**
 * The URL scheme after the `/map` prefix was dropped.
 *
 * A sphere is `/organizations`, a shift `/organizations/moat-migration`, a
 * sub-shift `/organizations/moat-migration/vendor-lock`. Two things that were
 * free under the old scheme are now hazards, and both are asserted here:
 *
 *  - `/:domainSlug` matches ANY single segment, so `/about` is one route
 *    ordering mistake away from being swallowed by the sphere page;
 *  - an unknown single segment used to fall through to the catch-all and 404.
 *    It now matches the sphere route, so the page has to recognise that its
 *    slug is not a sphere and 404 itself.
 *
 * The HTTP status codes are the backend's business — `spa` answers from the SEO
 * index — and the preview server used here serves the SPA for everything, so
 * these assert what the CLIENT renders. The status codes are checked against a
 * deployed origin in verify.spec.js.
 */
test('a sphere lives at the root, and /map is gone', async ({ page }) => {
  await mockMap(page)

  await page.goto('/society')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('SOCIETY')

  await page.goto('/society/trust-machines')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('“TRUST MACHINES”')

  // The old scheme is not a route any more.
  await page.goto('/map')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This shift has moved.')
  await page.goto('/map/society')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This shift has moved.')
})

test('/about is not swallowed by the sphere route', async ({ page }) => {
  await mockMap(page)
  await page.goto('/about')
  // Route order decides this — `/about` is declared before `/:domainSlug` and
  // the first match wins — and RESERVED in useDomains.js keeps the data layer
  // from firing a sphere fragment request for it either way.
  await expect(page.getByRole('heading', { level: 1 })).toContainText('About')
  await expect(page).toHaveTitle(/^About — Serious Shift$/)
})

test('an unknown single segment 404s instead of rendering a sphere', async ({ page }) => {
  await mockMap(page)
  await page.goto('/not-a-real-sphere')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This shift has moved.')
  await expect(page).toHaveTitle('Page not found · Serious Shift')
  // And it costs no request: the slug is checked against the local sphere list.
  const fragments = []
  page.on('request', (r) => { if (r.url().includes('/api/v1/map/')) fragments.push(r.url()) })
  await page.goto('/still-not-a-sphere')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('This shift has moved.')
  expect(fragments).toEqual([])
})
