#!/usr/bin/env node
/**
 * The per-shift link-preview card, as a RASTER image.
 *
 * Every route shared one generic logo card, so a shift posted into Slack or
 * WhatsApp previewed as "the site" rather than as itself. `poster()` already
 * draws that shift's own artwork from one seed, and `FRAMES.og` is a 1200×630
 * cut of it — the size every unfurler crops to.
 *
 * IT HAS TO BE RASTER. `og:image` pointing at an SVG renders as no image at all
 * in Facebook, LinkedIn, X, Slack and WhatsApp — strictly worse than the generic
 * PNG it would replace. So the SVG is an intermediate that is never written to
 * disk, and this script owns the whole set: draw, rasterise, manifest.
 *
 * JPEG, not PNG: these posters are large smooth gradients with grain, which is
 * the case JPEG is good at and PNG is bad at — roughly 70KB against 400KB, for
 * 51 files that live in the repo.
 *
 * Chromium via Playwright rather than a new native dependency. Playwright is
 * already a devDependency and already in CI, and this runs only when the art is
 * regenerated, which is rare.
 *
 *   node scripts/render-og.mjs
 */
import { chromium } from '@playwright/test'
import { mkdirSync, writeFileSync, readdirSync, rmSync, existsSync, readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { poster, FRAMES } from './generate-heroes.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT_DIR = resolve(ROOT, 'public/shift/og')
const MANIFEST = resolve(ROOT, 'src/lib/heroes-og.json')
const HEROES = resolve(ROOT, 'src/lib/heroes.json')

/** The hot stop of each sphere's ramp — the same trick check-heroes.mjs uses. */
const HOT = { society: '#FF007A', economy: '#0FA6FF', organizations: '#C2C64F', consumers: '#FF6A1F' }

const { W, H } = FRAMES.og

// The shift list comes from the committed portrait manifest rather than the
// API, so this needs no network and no running backend — unlike the generator,
// which walks the published map to discover slugs in the first place.
const heroes = JSON.parse(readFileSync(HEROES, 'utf8'))
const slugs = Object.keys(heroes)
if (!slugs.length) {
  console.error('✗ src/lib/heroes.json is empty — run the generator first')
  process.exit(1)
}

if (existsSync(OUT_DIR)) for (const f of readdirSync(OUT_DIR)) rmSync(resolve(OUT_DIR, f))
mkdirSync(OUT_DIR, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })

const manifest = {}
for (const slug of slugs) {
  const onDisk = readFileSync(resolve(ROOT, `public${heroes[slug]}`), 'utf8')
  const sphere = Object.keys(HOT).find((name) => onDisk.includes(HOT[name]))
  if (!sphere) {
    console.error(`✗ ${slug}: no sphere ramp in its poster, cannot pick a palette`)
    process.exit(1)
  }
  const svg = poster(slug, sphere, FRAMES.og)
  // `margin:0` and an exact viewport, so the screenshot is the frame and not
  // the frame plus the user agent's default body margin.
  await page.setContent(
    `<style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>${svg}`,
    { waitUntil: 'load' },
  )
  await page.screenshot({
    path: resolve(OUT_DIR, `${slug}.jpg`),
    type: 'jpeg',
    quality: 82,
    clip: { x: 0, y: 0, width: W, height: H },
  })
  manifest[slug] = `/shift/og/${slug}.jpg`
}

await browser.close()
writeFileSync(MANIFEST, `${JSON.stringify(manifest, Object.keys(manifest).sort(), 2)}\n`)
console.log(`${slugs.length} link-preview cards → public/shift/og (${W}×${H} JPEG)`)
