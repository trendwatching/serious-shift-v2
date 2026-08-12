import { test, expect } from '@playwright/test'
import { mockMap } from './fixtures.js'

/**
 * The two things a stakeholder reads before they read anything else: the name of
 * the trend, and the name of the site.
 *
 * Both were wrong in the link preview. The wordmark carried the logo's "(f)" in
 * running text, and the trend name arrived in title case with no quotation marks
 * — because the page's CAPS is `text-transform`, which is presentational and
 * never reaches the tab, the unfurl, or a copy-paste. So the page said
 * “DELEGATED DISCOVERY” and the WhatsApp card next to it said
 * `Delegated Discovery`.
 */
const SHIFT = '/society/trust-machines'
const SUB = '/society/trust-machines/sub-1'

test('the wordmark never carries the logo’s (f) in running text', async ({ page }) => {
  await mockMap(page)
  for (const path of ['/', '/about', '/society', SHIFT, SUB]) {
    await page.goto(path)
    await page.waitForFunction(() => document.title && !document.title.startsWith('Vite'))
    const { title, og } = await page.evaluate(() => ({
      title: document.title,
      og: document.querySelector('meta[property="og:title"]')?.content ?? '',
    }))
    expect(title, `${path} <title>`).not.toContain('Shi(f)t')
    expect(title, `${path} <title>`).toContain('Serious Shift')
    if (og) expect(og, `${path} og:title`).not.toContain('Shi(f)t')
  }
})

test('a trend name reaches the tab in caps, in quotes — a sphere name does not', async ({ page }) => {
  await mockMap(page)

  await page.goto(SHIFT)
  await page.waitForFunction(() => document.title.includes('—'))
  expect(await page.title()).toBe('“TRUST MACHINES” — Serious Shift')

  await page.goto(SUB)
  await page.waitForFunction(() => document.title.includes('—'))
  expect(await page.title()).toBe('“SUB SHIFT 1” — Serious Shift')

  // A sphere is a section of the site, not the name of a trend.
  await page.goto('/society')
  await page.waitForFunction(() => document.title.includes('—'))
  expect(await page.title()).toBe('Society — Serious Shift')
})

test('the rendered name is quoted, and the breadcrumb trail is not', async ({ page }) => {
  await mockMap(page)
  await page.goto(SHIFT)
  const h1 = page.getByRole('heading', { level: 1 })
  // UPPERCASE characters, not `text-transform`. This is the assertion the whole
  // change exists for: the page said DELEGATED DISCOVERY while every consumer
  // of the DOM — copy-paste, screen reader, crawler — saw Delegated Discovery.
  expect(await h1.textContent()).toBe('“TRUST MACHINES”')

  // The trail is navigation. The delivered design strips quotes there and a
  // quoted pill reads as clutter, so this exception is deliberate.
  const crumb = page.locator('.crumb-float')
  expect(await crumb.textContent()).not.toContain('“')

  // The sphere page's row list carries them too.
  await page.goto('/society')
  await expect(page.locator('.t-title').first()).toHaveText(/^“[^a-z]+”$/)
})

/**
 * A shift previews as itself.
 *
 * Every route stamped one generic logo card, so a shift shared into Slack or
 * WhatsApp looked like the site rather than like the thing that was shared.
 * The card is raster on purpose — `og:image` pointing at an SVG renders as no
 * image at all in every major unfurler.
 *
 * The tags are written by the BACKEND (seo.rs) into the served shell, so this
 * reads them off the served HTML rather than the hydrated DOM. The preview
 * server used here has no backend, so the assertion runs against the static
 * export's own manifest instead — and the served tags are checked on a real
 * origin in verify.spec.js.
 */
test('every shift has its own link-preview card, and it is raster', async ({ page }) => {
  // Derived from the committed manifest rather than a pinned slug: a republish
  // renames every shift, and a slug from the previous taxonomy asserts on a
  // card that no longer exists. check-heroes.mjs already vets manifest↔disk;
  // what only this test can see is whether the server hands the bytes over,
  // because a manifest entry the server answers with nothing is a blank
  // preview on every share of that shift.
  const { default: og } = await import('../src/lib/heroes-og.json', { with: { type: 'json' } })
  const cards = Object.entries(og)
  expect(cards.length, 'the build ships at least one card').toBeGreaterThan(0)
  for (const [slug, path] of cards) {
    expect(path, `${slug}'s card is raster`).toMatch(/\.jpg$/)
    const res = await page.request.get(path)
    expect(res.status(), `${slug}'s card is served`).toBe(200)
    expect(Number(res.headers()['content-length'] ?? 0), `${slug}'s card is not empty`)
      .toBeGreaterThan(1000)
  }
})

/**
 * The hero band is a letterbox on a desktop and a portrait window on a phone,
 * and there is a separately drawn poster for each. Painting the portrait one
 * into the desktop band showed about 30% of the picture — the crowd the whole
 * composition lands on was cropped clean off.
 */
test('the hero takes the poster cut for the shape of its band', async ({ page }) => {
  // A slug that actually has generated art. The shared fixture's `trust-machines`
  // is not in heroes.json, so its hero falls back to the gradient and there is no
  // `.hero-art` element at all — which is correct behaviour, and useless here.
  // Derived from the manifests rather than hardcoded: a republish renames
  // shifts and regenerates every poster, and a pinned slug from the previous
  // taxonomy times out waiting for art that no longer exists.
  const { default: heroes } = await import('../src/lib/heroes.json', { with: { type: 'json' } })
  const { default: heroesWide } = await import('../src/lib/heroes-wide.json', { with: { type: 'json' } })
  const slug = Object.keys(heroes).find((s) => s in heroesWide)
  expect(slug, 'some shift has both poster cuts').toBeTruthy()
  const path = `/society/${slug}`
  await page.route('**/api/v1/map**', async (route) => {
    const url = new URL(route.request().url()).pathname
    const domain = { id: 'society', name: 'Society', horizon: '2028', short_description: 'Society shifts', key_shift_count: 1 }
    const shift = {
      id: 'kt-a', domain_id: 'society', slug, name: 'Autonomous Infection',
      subtitle: 'Software spreads itself.', read_time: '5 min read',
      modules: [{ type: 'lede', data: { text: 'Body.' } }],
    }
    const body = url === '/api/v1/map'
      ? { updated: '2026-08-02', totals: { domains: 1, key_shifts: 1 }, domains: [domain] }
      : url === path.replace('/', '/api/v1/map/')
        ? { updated: '2026-08-02', domain, shift, siblings: [shift], sub_shifts: [] }
        : null
    await route.fulfill({
      status: body ? 200 : 404,
      contentType: 'application/json',
      body: JSON.stringify(body || { error: { code: 'not_found' } }),
    })
  })

  const art = () => page.evaluate(() => {
    const el = document.querySelector('.hero-art')
    return el ? getComputedStyle(el).backgroundImage : null
  })

  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto(path)
  await page.waitForSelector('.hero-art')
  expect(await art(), 'phone takes the portrait cut').toContain('/shift/heroes/')

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(path)
  await page.waitForSelector('.hero-art')
  expect(await art(), 'desktop takes the landscape cut').toContain('/shift/heroes-wide/')

  // …and the swap is a CSS rule, which only works because nothing paints
  // `background-image` inline. An inline style would beat the layer silently.
  const inline = await page.evaluate(
    () => document.querySelector('.hero-art').getAttribute('style') ?? '',
  )
  expect(inline).not.toMatch(/background-image|background:/)
})
