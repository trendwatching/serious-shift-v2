import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const domains = [
  ['society', 'Society', '2028'],
  ['economy', 'Economy', '2027'],
  ['organisations', 'Organisations', '2026'],
  ['consumers', 'Consumers', '2026'],
].map(([id, name, horizon]) => ({ id, name, horizon, short_description: `${name} shifts`, key_shift_count: id === 'society' ? 2 : 1 }))

const index = {
  updated: '2026-08-02',
  totals: { domains: 4, key_shifts: 5, sub_shifts: 25 },
  domains,
}
const shift = {
  id: 'kt-1', domain_id: 'society', slug: 'trust-machines', name: 'Trust Machines',
  subtitle: 'Verification becomes a product.', read_time: '5 min read',
  modules: [
    { type: 'peel_tabs', data: { whats_changing: 'Trust becomes designed.', why_now: 'Synthetic media is ordinary.' } },
    { type: 'human_needs', data: { unlocked: 'Agency grows.', threatened: 'Trust erodes.' } },
    { type: 'sub_shift_list', data: {} },
  ],
}
const shiftTwo = { id: 'kt-2', domain_id: 'society', slug: 'synthetic-belonging', name: 'Synthetic Belonging', subtitle: 'Presence changes.', read_time: '4 min read' }
const subs = Array.from({ length: 5 }, (_, i) => ({
  id: `st-${i + 1}`, key_trend_id: 'kt-1', domain_id: 'society', slug: `sub-${i + 1}`,
  name: `Sub Shift ${i + 1}`, description: `Sub shift ${i + 1} description`,
}))
const shiftDetail = { updated: index.updated, domain: domains[0], shift, siblings: [shift, shiftTwo], sub_shifts: subs }
const subDetail = {
  updated: index.updated,
  domain: domains[0],
  parent_shift: { ...shift, modules: undefined, sub_shift_count: 5 },
  sub_shift: {
    ...subs[0],
    modules: [
      { type: 'lede', data: { text: 'Full sub-shift context.' } },
      { type: 'evidence', data: { items: [{ thinker: 'Researcher', text: 'Verified evidence.', source: 'Study', url: 'https://example.com/study' }] } },
    ],
  },
  siblings: subs,
}

async function mockMap(page, failure) {
  await page.route('**/api/v1/map**', async (route) => {
    if (failure) {
      await route.fulfill({ status: failure, contentType: 'application/json', body: JSON.stringify({ error: { code: failure === 503 ? 'unavailable' : 'internal_error' } }) })
      return
    }
    const pathname = new URL(route.request().url()).pathname
    const data = pathname === '/api/v1/map' ? index
      : pathname === '/api/v1/map/society/trust-machines' ? shiftDetail
        : pathname === '/api/v1/map/society/trust-machines/sub-1' ? subDetail
          : null
    await route.fulfill({ status: data ? 200 : 404, contentType: 'application/json', body: JSON.stringify(data || { error: { code: 'not_found' } }) })
  })
}

async function expectNoSeriousAxe(page) {
  // Entrance animations fade opacity, and axe composites whatever alpha it
  // finds at the instant it samples. Sampling mid-fade reported the nav's
  // white-at-50% meta as #555555 on black — a frame that exists for 400ms and
  // never rests. Settle first, then measure the page as a reader sees it.
  await page.evaluate(() => Promise.all(
    document.getAnimations().map((a) => {
      try { a.finish() } catch { /* infinite loops (marquee, orbs) cannot finish */ }
      return a.ready.catch(() => {})
    }),
  ))

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(({ impact }) => impact === 'serious' || impact === 'critical')).toEqual([])
}

async function clientNavigate(page, path) {
  await page.evaluate((next) => {
    window.history.pushState({}, '', next)
    window.dispatchEvent(new PopStateEvent('popstate'))
  }, path)
}

test('navigation, keyboard modules, source safety, and axe', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  const dialog = page.getByRole('dialog', { name: 'Site navigation' })
  await expect(dialog).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close navigation' })).toBeFocused()
  await expectNoSeriousAxe(page)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused()

  await clientNavigate(page, '/map/society/trust-machines')
  const why = page.getByRole('tab', { name: 'Why now' })
  await why.focus()
  await page.keyboard.press('ArrowRight')
  await expect(why).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('button', { name: 'Threatened' }).click()
  await expect(page.getByRole('button', { name: 'Threatened' })).toHaveAttribute('aria-expanded', 'true')

  // The sub-shifts are a stack of links, not a carousel. The design deleted the
  // counter and the next/previous pair, so paging affordances are what this
  // asserts the ABSENCE of — every sub-shift is reachable in one tap.
  await expect(page.getByRole('button', { name: /sub-shift/i })).toHaveCount(0)
  const subLinks = page.getByRole('link', { name: /Sub Shift 1/i })
  await expect(subLinks.first()).toBeVisible()
  await expectNoSeriousAxe(page)

  await clientNavigate(page, '/map/society/trust-machines/sub-1')
  // A sub-shift page is deliberately terminal: the breadcrumb menu is the only
  // way back up, which is why it is the thing under test rather than a
  // sibling-nav card.
  // The trigger is labelled with the sub-shift's own title, and the menu it
  // opens is the route back to the sphere and to every sibling.
  await page.getByRole('button', { name: /Sub Shift 1/i }).first().click()
  await expect(page.getByRole('button', { name: 'Society' })).toBeVisible()
  const source = page.getByRole('link', { name: 'Read source: Study' })
  await expect(source).toHaveAttribute('target', '_blank')
  await expect(source).toHaveAttribute('rel', 'noopener noreferrer')
})

test('pointer cancellation does not change slides and reduced motion is static', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 393, height: 852 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  const track = page.locator('.cursor-grab')
  await track.dispatchEvent('pointerdown', { pointerId: 7, pointerType: 'touch', clientX: 300, clientY: 300, button: 0 })
  await track.dispatchEvent('pointermove', { pointerId: 7, pointerType: 'touch', clientX: 160, clientY: 306 })
  await track.dispatchEvent('pointercancel', { pointerId: 7, pointerType: 'touch', clientX: 160, clientY: 306 })
  await expect(page.locator('[aria-live="polite"]')).toContainText('Intro, panel 1')
  await expect(page.locator('.cursor-grab')).toHaveCSS('transition-duration', '0s')
})

test('accessible 404 and explicit unavailable state', async ({ page }) => {
  await mockMap(page)
  await page.goto('/')
  await clientNavigate(page, '/not-a-real-route')
  await expect(page.getByRole('heading', { level: 1, name: 'This shift has moved.' })).toBeVisible()

  await page.unroute('**/api/v1/map**')
  await mockMap(page, 503)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'The current map isn’t available.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible()
})

for (const [width, height] of [[390, 844], [393, 852], [768, 1024], [1440, 900]]) {
  test(`homepage visual ${width}x${height}`, async ({ page }) => {
    await mockMap(page)
    await page.setViewportSize({ width, height })
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1, name: /Everything that is about to change/i })).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(`homepage-${width}x${height}.png`, { animations: 'disabled' })
  })
}
