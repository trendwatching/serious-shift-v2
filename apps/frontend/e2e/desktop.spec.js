import { test, expect } from '@playwright/test'
import { mockMap } from './fixtures.js'

/**
 * The desktop page reads as one column.
 *
 * It did not. Measured on staging at 1440, a Society key shift ran
 * `591, 591, 1051, 591, 1051, 591, 1051, 1051` — five width changes in eight
 * blocks, three of them single blocks marooned between wide ones — and the left
 * edge swung 230px per side, 300px at 1920. The cause was that `--col` was a
 * border box carrying the gutter while `--wide` was a raw content width, so the
 * two were never comparable and drifted further apart the bigger the display.
 *
 * `--wide` is now `--col + 160px`, which is what these assertions protect: at
 * most two measures, 80px between them, both on the page's own axis.
 */
const SHIFT = '/society/trust-machines'
const SUB = '/society/trust-machines/sub-1'
const WIDTHS = [1024, 1280, 1440, 1920]

const geometry = (page) => page.evaluate(() => {
  const column = document.querySelector('article .canvas.gutter.flex')
  if (!column) return null
  return [...column.children]
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.width > 1)
    .map((r) => ({ left: Math.round(r.left), width: Math.round(r.width) }))
})

for (const path of [SHIFT, SUB]) {
  test(`every block on ${path} sits on one of two axes, 80px apart`, async ({ page }) => {
    await mockMap(page)
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(path)
      await page.waitForSelector('article .canvas.gutter.flex > *')
      // Settle the entrance animation first. `a-expand` scales the article, so
      // a mid-flight measurement reports every width at 88% — which is exactly
      // how I nearly diagnosed a phantom layout bug.
      await page.evaluate(() => Promise.all(document.getAnimations().map((a) => {
        try { a.finish() } catch { /* infinite loops cannot finish */ }
        return a.ready.catch(() => {})
      })))

      const blocks = await geometry(page)
      expect(blocks, `${width}px has modules`).not.toHaveLength(0)

      const edges = [...new Set(blocks.map((b) => b.left))].sort((a, b) => a - b)
      expect(edges.length, `${width}px: distinct left edges ${edges}`).toBeLessThanOrEqual(2)
      if (edges.length === 2) {
        expect(edges[1] - edges[0], `${width}px: step between the two measures`).toBeLessThanOrEqual(81)
      }

      // Every block centred on the same axis — that is what makes two widths
      // read as one column rather than two documents.
      for (const b of blocks) {
        expect(Math.abs(b.left + b.width / 2 - width / 2), `${width}px: block off-axis`).toBeLessThanOrEqual(1)
      }
    }
  })
}

test('the breadcrumb rides the same axis as the title it sits above', async ({ page }) => {
  await mockMap(page)
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(SHIFT)
    await page.waitForSelector('.crumb-float')
    // Settle first — the article's entrance animation scales it, so a mid-flight
    // read reports 28px for a 31.5px chain and looks like a sizing bug.
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => {
      try { a.finish() } catch { /* infinite loops cannot finish */ }
      return a.ready.catch(() => {})
    })))
    const { crumb, h1, crumbHeight, crumbFont } = await page.evaluate(() => {
      const c = document.querySelector('.crumb-float')
      const heading = document.querySelector('article h1')
      const pill = c.querySelector('a, span')
      return {
        crumb: Math.round(c.getBoundingClientRect().left),
        h1: Math.round(heading.getBoundingClientRect().left),
        crumbHeight: Math.round(c.getBoundingClientRect().height),
        crumbFont: parseFloat(getComputedStyle(pill).fontSize),
      }
    })
    // It used to be offset by the canvas BORDER box, so it aligned with nothing:
    // 34px left of its own H1 and 196px right of every wide block.
    expect(crumb, `${width}px: breadcrumb vs H1`).toBe(h1)
    // …and it grows, instead of staying an 11px ribbon under a 92px headline.
    if (width >= 1440) {
      expect(crumbHeight).toBeGreaterThan(28)
      expect(crumbFont).toBeGreaterThan(12)
    }
  }
})

/**
 * Two rules the desktop layer sets that were being thrown away.
 *
 * Asserted at runtime because neither is statically detectable: both are set on
 * a DESCENDANT (`.needs-pair > *`), so the utility that beat them sat on an
 * element that never carried the class. See the note in check-layers.mjs.
 */
test('the desktop layer actually reaches the blocks it styles', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(SHIFT)
  await page.waitForSelector('.needs-pair')

  const needs = await page.evaluate(() => {
    const kids = [...document.querySelector('.needs-pair').children]
    return {
      minWidth: getComputedStyle(kids[0]).minWidth,
      widths: kids.map((k) => Math.round(k.getBoundingClientRect().width)),
    }
  })
  // `min-w-0` on the card computed to 0px, so the collapsed one was a 161px
  // sliver holding a rotated-looking label.
  expect(needs.minWidth).toBe('190px')
  expect(Math.min(...needs.widths)).toBeGreaterThanOrEqual(190)
})

test('the industry chips shrink-wrap instead of inheriting the card grid', async ({ page }) => {
  await mockMap(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(SHIFT)
  const chips = page.locator('.chips')
  if (!(await chips.count())) test.skip(true, 'industries is hidden on this fixture')
  // `.widen .rail` turns every rail into a card grid and the chips carry `rail`
  // too, so they were laid out as 4 stretched 257px tracks. `flex-wrap` beside
  // it was inert because `display` was never reset.
  expect(await chips.first().evaluate((el) => getComputedStyle(el).display)).toBe('flex')
})
