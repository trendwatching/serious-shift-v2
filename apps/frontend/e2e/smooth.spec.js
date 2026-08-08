import { test, expect } from '@playwright/test'
import { mockMap } from './fixtures.js'

/**
 * Nothing the reader is looking at may move while the page loads.
 *
 * Three separate faults were doing exactly that, and each is asserted here:
 *
 *  - the deck's skeleton was `min-h-dvh` plus `--topbar` of padding where the
 *    deck is exactly `100dvh`, so the document collapsed by the height of the
 *    bar the moment the map arrived (0.082, on the first screen of the site);
 *  - the reading pages' skeleton was a centred block that became a page with a
 *    660px hero (0.099);
 *  - and worst, a sphere is assembled from TWO requests, so the index made
 *    `domain` truthy while its key shifts were still in flight — the sheet
 *    painted at its 520px minimum with the footer in view, then five rows
 *    arrived and shoved it a thousand pixels down the page (0.386).
 *
 * `stagger` holds the fragment 500ms behind the index so that last race happens
 * on every run rather than whenever the network feels like it. The CDP
 * throttling is for the other half of the problem — fonts and chunks, which do
 * go over the emulated connection.
 */
for (const [name, path] of [
  ['home', '/'],
  ['domain', '/map/society'],
  ['shift', '/map/society/trust-machines'],
  ['sub', '/map/society/trust-machines/sub-1'],
  ['about', '/about'],
]) {
  test(`${name} does not shift while it loads`, async ({ page }) => {
    await mockMap(page, undefined, true)
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Network.emulateNetworkConditions', {
      offline: false, latency: 200, downloadThroughput: 400 * 1024, uploadThroughput: 400 * 1024,
    })
    await page.setViewportSize({ width: 393, height: 852 })
    await page.goto(path, { waitUntil: 'commit' })
    await page.evaluate(() => {
      window.__cls = 0
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value
      }).observe({ type: 'layout-shift', buffered: true })
    })
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(900)
    const cls = await page.evaluate(() => Number(window.__cls.toFixed(4)))
    console.log(`  ${name}: CLS ${cls}`)
    // Google calls 0.1 "good"; this asserts an order of magnitude better,
    // because the deck's shift was 0.082 and cleared that bar comfortably.
    expect(cls).toBeLessThan(0.01)
  })
}

test('the homepage is the whole app, with no footer and nothing to scroll', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 393, height: 852 })
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.trim())
  await page.waitForLoadState('networkidle')
  expect(await page.locator('footer').count()).toBe(0)
  expect(await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight))
    .toBeLessThanOrEqual(0)
  // …and it is still there on a reading page.
  await page.goto('/map/society', { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => document.querySelector('footer'))
  expect(await page.locator('footer').count()).toBe(1)
})
