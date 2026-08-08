import { test, expect } from '@playwright/test'

/**
 * The nav's five `/about#section` rows have to land on their heading.
 *
 * They did not: the scroll runs in a layout effect, before any image has
 * decoded, and unsized images above the target moved it afterwards — 330–570px
 * in CI, by a distance that changed with the network. Images now carry their
 * intrinsic size and the scroll re-settles after the fonts swap.
 *
 * Throttled on purpose. On a fast machine everything has arrived before the
 * scroll happens and the bug is invisible, which is why only CI ever saw it.
 */
test('a nav anchor settles on its section', async ({ page }) => {
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency: 300, downloadThroughput: 200 * 1024, uploadThroughput: 200 * 1024,
  })
  await page.setViewportSize({ width: 393, height: 852 })

  await page.goto('/')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name: /Services/ }).click()
  await expect(page).toHaveURL(/#services$/)

  const y = async () => (await page.locator('#services').boundingBox()).y

  // Let the page finish arriving AND the correction finish running. Measuring
  // before that is measuring the fix mid-flight, not the outcome.
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(900)

  const settled = await y()
  // `scroll-mt-24` is 96px, so that is where the heading is meant to come to
  // rest — not zero.
  expect(settled, 'the section rests at its scroll margin').toBeGreaterThan(60)
  expect(settled, 'and near the top of the viewport, not a section away').toBeLessThan(140)

  // And it stays there.
  await page.waitForTimeout(700)
  expect(Math.abs((await y()) - settled), 'nothing moves it afterwards').toBeLessThan(4)
})
