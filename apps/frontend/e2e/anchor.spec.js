import { test, expect } from '@playwright/test'

test('a nav anchor holds its position while the images above it load', async ({ page }) => {
  // Throttled, because that is the difference between this passing on a fast
  // laptop and failing in CI: the scroll happens in a layout effect, before any
  // image has loaded, so anything unsized above the target moves it afterwards.
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
  const early = await y()
  await page.waitForLoadState('networkidle')
  const late = await y()

  console.log(`  #services y: ${Math.round(early)} → ${Math.round(late)} (drift ${Math.round(late - early)}px)`)
  expect(Math.abs(late - early), 'the section must not move once the images arrive').toBeLessThan(8)
  expect(late, 'and it must be at the top of the viewport').toBeLessThan(200)
})
