import { test, expect } from '@playwright/test'
const O = 'https://backend-staging-1c16.up.railway.app'

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(', ')

test('the stat band is lit by its own sphere', async ({ page }) => {
  const ramps = {}
  for (const [sphere, path] of [
    ['society', '/map/society/pacing-panic'],
    ['economy', '/map/economy/entry-erasure'],
    ['organisations', '/map/organisations/agent-saturation'],
    ['consumers', '/map/consumers/provenance-premium'],
  ]) {
    await page.goto(O + path, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('h1')?.textContent?.trim())
    const seen = await page.evaluate(() => {
      const article = document.querySelector('article')
      const band = document.querySelector('.stat-surface')
      return {
        accent: getComputedStyle(article).getPropertyValue('--a').trim(),
        ramp: getComputedStyle(article).getPropertyValue('--grad-stat').trim(),
        band: band ? getComputedStyle(band).backgroundImage : null,
      }
    })
    // The ramp must resolve against THIS sphere's accent, not :root's Society.
    // A custom property keeps its hex; only the painted value becomes rgb().
    expect(seen.ramp, `${sphere} ramp should contain its own accent`).toContain(seen.accent)
    if (seen.band) expect(seen.band).toContain(rgb(seen.accent))
    ramps[sphere] = seen.ramp
  }
  // And no two spheres may resolve to the same surface.
  expect(new Set(Object.values(ramps)).size).toBe(4)
})

test('desktop lines every module up on one of two axes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto(`${O}/map/economy/entry-erasure`, { waitUntil: 'domcontentloaded' })
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.trim())
  await page.waitForTimeout(1200)

  const seen = await page.evaluate(() => {
    const box = (sel) => {
      const el = document.querySelector(sel)
      if (!el) return null
      const r = el.getBoundingClientRect()
      return { left: Math.round(r.left), width: Math.round(r.width) }
    }
    const dots = [...document.querySelectorAll('.horizon-dot')].map((d) => Math.round(d.getBoundingClientRect().left))
    return {
      col: box('.canvas.gutter'),
      band: box('.stat-surface'),
      list: box('.widen .sub-stack'),
      footer: box('footer'),
      hero: Math.round(document.querySelector('header').getBoundingClientRect().height),
      dots,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }
  })

  expect(seen.overflow).toBeLessThanOrEqual(1)
  expect(seen.hero).toBeLessThanOrEqual(470)
  // Two widths, and everything is one of them.
  expect(seen.col.width).toBe(660)
  expect(seen.band.width).toBe(940)
  expect(seen.list.width).toBe(940)
  expect(seen.footer.width).toBe(940)
  // Centred on the same axis.
  const centre = (b) => b.left + b.width / 2
  for (const b of [seen.col, seen.band, seen.list, seen.footer]) {
    expect(Math.abs(centre(b) - 720)).toBeLessThanOrEqual(1)
  }
  // The horizon dots ride their own cards, spread across the rail — they used
  // to stack on the phone's vertical spine while the cards became a row.
  expect(seen.dots.length).toBe(3)
  expect(seen.dots[1] - seen.dots[0]).toBeGreaterThan(250)
  expect(seen.dots[2] - seen.dots[1]).toBeGreaterThan(250)
})
