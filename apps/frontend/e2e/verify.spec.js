import { test, expect } from '@playwright/test'
/**
 * Smoke tests against a DEPLOYED origin, not against this commit.
 *
 * They are opt-in for exactly that reason: run inside CI they assert whatever
 * staging happens to be serving, which is the previous commit until the deploy
 * lands — so a correct change fails its own build. Run them after a deploy:
 *
 *   VERIFY_ORIGIN=https://backend-staging-1c16.up.railway.app npx playwright test e2e/verify.spec.js
 */
const O = process.env.VERIFY_ORIGIN
test.skip(!O, 'set VERIFY_ORIGIN to smoke-test a deployed origin')

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
      wide: box('.widen'),
      band: box('.stat-surface'),
      list: box('.widen .sub-stack'),
      footer: box('footer'),
      footerInner: box('footer .footer-inner'),
      // `article header`, not `header`: the black top bar is a <header> too and
      // comes first in the DOM, so the old selector measured the chrome. At 84px
      // it satisfied `<= 470` on every run — the hero was never being checked.
      hero: Math.round(document.querySelector('article header').getBoundingClientRect().height),
      dots,
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    }
  })

  expect(seen.overflow).toBeLessThanOrEqual(1)
  // The hero band's bounds, not a frozen height: `.hero-tall` interpolates
  // 460 → 620 across the desktop range now.
  expect(seen.hero).toBeGreaterThanOrEqual(460)
  expect(seen.hero).toBeLessThanOrEqual(620)

  // Two widths, and everything is one of them.
  //
  // The wide one is read off the page rather than written down. It used to be
  // asserted as a literal 940, which is what it was while every measure was
  // fixed — and this spec is opt-in, so when `--wide` became a ramp (940 at
  // 1024 → 1180 at 1920, and 1051 here) nothing failed and the contract just
  // went stale. The invariant was never the number: it is that every wide
  // block shares ONE measure and sits on the same axis as the column.
  expect(seen.col.width).toBe(660)
  expect(seen.wide.width).toBeGreaterThanOrEqual(940)
  expect(seen.wide.width).toBeLessThanOrEqual(1180)
  expect(seen.band.width).toBe(seen.wide.width)
  expect(seen.list.width).toBe(seen.wide.width)
  // A footer band spans the page; only its contents take the measure.
  expect(seen.footer.width).toBe(1440)
  expect(seen.footerInner.width).toBe(seen.wide.width)
  // Centred on the same axis.
  const centre = (b) => b.left + b.width / 2
  for (const b of [seen.col, seen.wide, seen.band, seen.list, seen.footerInner]) {
    expect(Math.abs(centre(b) - 720)).toBeLessThanOrEqual(1)
  }
  // The horizon dots ride their own cards, spread across the rail — they used
  // to stack on the phone's vertical spine while the cards became a row.
  expect(seen.dots.length).toBe(3)
  expect(seen.dots[1] - seen.dots[0]).toBeGreaterThan(250)
  expect(seen.dots[2] - seen.dots[1]).toBeGreaterThan(250)
})
