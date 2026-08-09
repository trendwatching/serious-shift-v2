import { test, expect } from '@playwright/test'
import { mockMap } from './fixtures.js'

/**
 * The chrome fits the display it is on.
 *
 * The site was a 393px canvas at every width: an 84px bar carrying a 214px
 * logo, whether that was 21% of a phone or 3% of a 27" monitor. Everything the
 * reader treats as furniture — the bar, the lock-up, the gutters, the display
 * type — now rides one shared ramp from the design canvas to a large desktop.
 *
 * Three things are asserted, because each has already been got wrong once:
 * the phone floor is EXACT (the delivered design must survive untouched), the
 * ramp actually rises, and it stops rather than growing forever.
 */
const read = (page) => page.evaluate(() => {
  const bar = document.querySelector('header')
  const probe = document.createElement('div')
  probe.className = 'hero-tall'
  document.body.appendChild(probe)
  const heroH = parseFloat(getComputedStyle(probe).getPropertyValue('--hero-h'))
  probe.remove()
  return {
    bar: Math.round(bar.getBoundingClientRect().height),
    logo: Math.round(bar.querySelector('img').getBoundingClientRect().height),
    heroH,
  }
})

test('the chrome scales with the display, and stops', async ({ page }) => {
  await mockMap(page)
  const at = {}
  for (const w of [393, 768, 1280, 1920, 2560]) {
    await page.setViewportSize({ width: w, height: 900 })
    await page.goto('/')
    await page.getByRole('heading', { level: 1 }).first().waitFor()
    at[w] = await read(page)
  }

  // The design canvas, to the pixel. Every clamp floors here.
  expect(at[393].bar).toBe(84)
  expect(at[393].logo).toBe(74)

  // It rises.
  expect(at[768].bar).toBeGreaterThan(at[393].bar)
  expect(at[1280].bar).toBeGreaterThan(at[768].bar)
  expect(at[1920].bar).toBeGreaterThan(at[1280].bar)

  // And it stops: past the ceiling a bigger display is usually a further one.
  expect(at[2560].bar).toBe(at[1920].bar)

  // The lock-up is a fraction of the band, so it tracks it rather than
  // rattling around inside a bar that grew without it.
  for (const w of [393, 768, 1280, 1920]) {
    expect(at[w].logo / at[w].bar).toBeCloseTo(74 / 84, 1)
  }
})

test('--hero-h stays a number the shrink hook can read', async ({ page }) => {
  // `useHeroShrink` parseFloats this. Unregistered, a `clamp(…)` token computes
  // to its own text, parseFloat returns NaN, and the hook silently falls back
  // to the phone's 660px hero on every desktop. @property is what prevents it.
  await mockMap(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByRole('heading', { level: 1 }).first().waitFor()
  const { heroH } = await read(page)
  expect(Number.isFinite(heroH)).toBe(true)
  expect(heroH).toBeGreaterThan(460)
  expect(heroH).toBeLessThan(620)
})

test('the sphere badges stay on one line at every desktop width', async ({ page }) => {
  // They are primary navigation. Grown to a desktop size inside the 660px
  // reading column, the fourth dropped onto a line of its own — worse than the
  // phone's deliberate wrap — so the row takes `--wide` instead.
  await mockMap(page)
  for (const w of [1024, 1280, 1440, 1920, 2560]) {
    await page.setViewportSize({ width: w, height: 900 })
    await page.goto('/')
    await page.getByRole('heading', { level: 1 }).first().waitFor()
    const { lines, offset } = await page.evaluate(() => {
      const badges = [...document.querySelectorAll('.ss-badge')]
      const h1 = document.querySelector('h1').getBoundingClientRect()
      return {
        lines: new Set(badges.map((b) => Math.round(b.getBoundingClientRect().top))).size,
        offset: Math.round(badges[0].parentElement.getBoundingClientRect().left - h1.left),
      }
    })
    expect(lines, `${w}px`).toBe(1)
    // Still on the headline's axis — it gains room to the right, it does not
    // re-centre itself on a different one.
    expect(offset, `${w}px`).toBe(0)
  }
})

/**
 * The breadcrumb pill is the thing you tap, and it has to be as tall as it
 * looks.
 *
 * Every dimension in Breadcrumb.jsx is a fraction of `--crumb-h` — the paddings,
 * the gap, the type, the overlap between pills. The pill's own height was the
 * one exception: it came from an `h-full` that resolved against an `<li>` which
 * `items-center` had collapsed to text height. So the chain rendered a full
 * crumb's worth of horizontal padding around ~17px of pill, and raising
 * `--crumb-h` for large displays moved every measurement except the one anyone
 * can see. It also left the tap target below the 24px minimum.
 */
test('the breadcrumb pill fills the crumb height at every width', async ({ page }) => {
  await mockMap(page)
  for (const w of [375, 768, 1280, 1920]) {
    await page.setViewportSize({ width: w, height: 900 })
    await page.goto('/society/trust-machines')
    await page.locator('.crumb-float nav').waitFor()
    // `a-expand` scales the article on entry; anything measured mid-flight is
    // wrong by that factor.
    await page.evaluate(() => document.getAnimations().forEach((a) => {
      try { a.finish() } catch { /* infinite ambient loops cannot finish */ }
    }))
    const { navH, pills } = await page.evaluate(() => ({
      navH: document.querySelector('.crumb-float nav').getBoundingClientRect().height,
      pills: [...document.querySelectorAll('.crumb-float li > *')]
        .map((p) => p.getBoundingClientRect().height),
    }))
    expect(pills.length, `${w}px`).toBeGreaterThan(1)
    for (const h of pills) {
      expect(h, `${w}px pill vs nav`).toBeCloseTo(navH, 0)
      // WCAG 2.2 SC 2.5.8. The trail is navigation, not a link in a sentence,
      // so the inline exception does not apply to it.
      expect(h, `${w}px tap target`).toBeGreaterThanOrEqual(24)
    }
  }
})
