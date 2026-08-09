import { expect, test } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { index, shift, shiftTwo, subs, mockMap } from './fixtures.js'


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

  // The sphere page: its row numbers are the lightest text on the site, and it
  // was the one page type this walk never visited.
  await clientNavigate(page, '/society')
  await expect(page.getByRole('heading', { level: 1, name: /Society/i })).toBeVisible()
  await expectNoSeriousAxe(page)

  await clientNavigate(page, '/society/trust-machines')
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

  await clientNavigate(page, '/society/trust-machines/sub-1')
  // A sub-shift has no sibling rail and no next pager, so the breadcrumb IS the
  // way out — and it has to name the parent, not just the page you are on.
  const trail = page.getByRole('navigation', { name: 'Breadcrumb' })
  await expect(trail.getByRole('link', { name: 'Home' })).toBeVisible()
  await expect(trail.getByRole('link', { name: /Trust Machines/i })).toBeVisible()
  const source = page.getByRole('link', { name: 'Read source: Study' })
  await expect(source).toHaveAttribute('target', '_blank')
  await expect(source).toHaveAttribute('rel', 'noopener noreferrer')
  await expectNoSeriousAxe(page)

  // About is authored rather than projected, so nothing else covers it.
  await clientNavigate(page, '/about')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expectNoSeriousAxe(page)
})

test('a route change lands at the top, and a nav anchor lands on its section', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto('/')

  // Deep enough into a key shift that keeping the offset would drop the reader
  // into the middle of the next page — which is what used to happen, because
  // nothing reset it.
  await clientNavigate(page, '/society/trust-machines')
  await expect(page.getByRole('heading', { level: 1, name: /Trust Machines/i })).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, 1200))
  await page.getByRole('link', { name: /Sub Shift 1/i }).first().click()
  await expect(page).toHaveURL(/sub-1$/)
  expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(0)

  // Five of the six nav rows are `/about#section`. Without hash handling they
  // all landed at the top of /about and were indistinguishable from each other.
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: /Services/ }).click()
  await expect(page).toHaveURL(/#services$/)
  const box = await page.locator('#services').boundingBox()
  expect(box.y).toBeGreaterThan(0)
  expect(box.y).toBeLessThan(200)
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
    // `animations: 'disabled'` is not enough on this page: the orbs run
    // infinite keyframes, and Playwright cannot rewind those to a defined
    // frame, so consecutive runs differ by a few hundred sub-pixel-blurred
    // pixels — enough to fail intermittently at a threshold tight enough to
    // catch a real layout regression. Pin every animation to time zero and the
    // page becomes deterministic instead of merely tolerated.
    await page.evaluate(() => {
      for (const animation of document.getAnimations()) {
        animation.pause()
        animation.currentTime = 0
      }
    })
    await expect(page).toHaveScreenshot(`homepage-${width}x${height}.png`, { animations: 'disabled' })
  })
}
