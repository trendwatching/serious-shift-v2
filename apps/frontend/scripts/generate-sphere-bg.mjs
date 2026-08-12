#!/usr/bin/env node
/* ════════════════════════════════════════════════════════════════════════
 * Sphere background art for the deck panels and sphere landing heroes.
 *
 * The shipped Society background (design's own asset) is the mold: a
 * single-hue duotone field, silhouetted people lit by the devices they hold,
 * a soft crowd behind them, fine network lines, and three glowing keyword
 * nodes naming the sphere's stakes. This draws the other three spheres in
 * that family — interim, Claude-crafted stand-ins until design replaces them
 * with the photo-illustration set (prompts in docs/sphere-image-prompts.md).
 *
 * Deterministic: no randomness at runtime, same input → same JPEG bytes
 * modulo JPEG encoder wobble. Society is never overwritten.
 *
 *   node scripts/generate-sphere-bg.mjs
 *
 * Writes public/shift/domain-{economy,organizations,consumers}-bg.jpg at
 * 884×791 (the Society asset's exact frame), JPEG q82, no baked scrim —
 * DomainPage and DomainPanel apply their own gradients.
 * ════════════════════════════════════════════════════════════════════════ */
import { writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = (id) => resolve(ROOT, `public/shift/domain-${id}-bg.jpg`)
const W = 884
const H = 791

/* ── Palette per sphere ─────────────────────────────────────────────────
 * `hot` is the sphere's brand hue (same values render-og.mjs sniffs from the
 * hero posters), `deep` the near-black floor the silhouettes sink into, `sky`
 * the bright field behind the nodes. Words come from each sphere's deck
 * blurb — the stakes, not the topic. */
const SPHERES = [
  {
    id: 'economy',
    sky: '#28b7ff', hot: '#0FA6FF', mid: '#0765b8', deep: '#0a1f47', ink: '#04102b',
    words: ['VALUE', 'WORK', 'MONEY'],
    scene: 'economy',
  },
  {
    id: 'organizations',
    sky: '#d8dc66', hot: '#C2C64F', mid: '#7a7f2b', deep: '#2b2f10', ink: '#171a06',
    words: ['SPEED', 'TRUST', 'JUDGMENT'],
    scene: 'organizations',
  },
  {
    id: 'consumers',
    sky: '#ff8a3d', hot: '#FF6A1F', mid: '#b83f0a', deep: '#471505', ink: '#2b0b02',
    words: ['IDENTITY', 'TASTE', 'DESIRE'],
    scene: 'consumers',
  },
]

/* ── Small silhouette library ───────────────────────────────────────────
 * Everything is drawn in a local 100×160 box (origin at the head's center
 * top) and placed with translate/scale. Forms are simple on purpose: the
 * mold's figures are soft-edged, so blur carries the realism. Variants
 * differ in hair, shoulder width and stance so a row reads as different
 * people, not clones. */

// Standing, straight-on: neck, sloped shoulders, arms hinted by waist
// notches. hair: 'short' | 'bun' | 'long' | 'curly'
function standing(hair = 'short', wide = 1) {
  const sh = 30 * wide
  const hairTop = {
    short: '<circle cx="0" cy="14" r="13"/>',
    bun: '<circle cx="0" cy="14" r="12.5"/><circle cx="0" cy="-1" r="5.5"/>',
    long: '<circle cx="0" cy="14" r="12.5"/><path d="M -12 14 Q -17 48 -12 68 L 12 68 Q 17 48 12 14 Z"/>',
    curly: '<circle cx="0" cy="13" r="15"/>',
  }[hair]
  return `${hairTop}
    <path d="M -8 18 L -9 28
             C -18 31 ${-sh} 38 ${-sh} 62
             L ${-sh * 0.82} 96 L ${-sh * 0.62} 100 L ${-sh * 0.6} 160
             L ${sh * 0.6} 160 L ${sh * 0.62} 100 L ${sh * 0.82} 96
             C ${sh} 38 18 31 9 28 L 8 18 Z"/>`
}

// Head bowed at a phone, chest-up. All the action sits above local y≈90 so a
// 3× placement cropped at the frame's bottom edge still shows the phone.
function phoneFig(hair = 'short') {
  const hairTop = {
    short: '<circle cx="8" cy="20" r="13"/>',
    bun: '<circle cx="8" cy="20" r="12.5"/><circle cx="-2" cy="8" r="5.5"/>',
    long: '<circle cx="8" cy="20" r="12.5"/><path d="M -5 16 Q -12 46 -5 68 L 11 64 Q 18 42 20 24 Z"/>',
  }[hair]
  return `${hairTop}
    <path d="M -1 24 L 3 32
             C 30 36 44 52 46 76
             L 46 160 L -46 160
             C -48 62 -32 38 -8 33 L -10 26 Z"/>
    <path d="M 43 64 C 42 78 33 88 20 92 L 24 101 C 40 96 50 84 52 70 Z"/>
    <path d="M -41 70 C -35 82 -22 90 -6 93 L -8 102 C -27 99 -42 90 -49 77 Z"/>
    <rect x="2" y="88" width="20" height="12" rx="2" transform="rotate(-16 12 94)"/>`
}

// At a laptop, chest-up behind the lid: sloped shoulders, arm reaching down
// to a lid wedge that stays inside the visible band.
function laptopFig(hair = 'short') {
  const hairTop = hair === 'bun'
    ? '<circle cx="4" cy="16" r="12.5"/><circle cx="-4" cy="4" r="4.5"/>'
    : '<circle cx="4" cy="16" r="13"/>'
  return `${hairTop}
    <path d="M -5 20 L -6 30
             C -22 33 -34 44 -36 66
             L -36 160 L 38 160 L 38 68
             C 36 44 26 33 13 30 L 12 20 Z"/>
    <path d="M -34 70 C -26 82 -10 90 6 92 L 4 100 C -14 98 -32 88 -40 76 Z"/>`
}

// Mid-stride with a bag: one arm down to a trapezoid bag held at hip height.
function shopperFig(hair = 'long') {
  const hairTop = {
    long: '<circle cx="0" cy="14" r="12.5"/><path d="M -12 14 Q -16 46 -10 64 L 10 64 Q 16 46 12 14 Z"/>',
    short: '<circle cx="0" cy="14" r="13"/>',
  }[hair]
  return `${hairTop}
    <path d="M -8 18 L -9 28
             C -20 31 -30 42 -30 62
             L -26 160 L 28 160 L 30 62
             C 30 42 20 31 9 28 L 8 18 Z"/>
    <path d="M 26 54 C 32 64 36 74 37 84 L 30 88 C 28 76 24 66 20 58 Z"/>
    <path d="M 26 86 L 52 86 L 57 122 L 31 122 Z"/>
    <path d="M 36 78 Q 41 73 46 78 L 46 88 L 43 88 L 43 81 Q 41 78 39 81 L 39 88 L 36 88 Z"/>`
}

// Presenting: one arm raised toward a node, jacket line at the waist.
function presenterFig(hair = 'short') {
  const hairTop = hair === 'curly' ? '<circle cx="0" cy="13" r="15"/>' : '<circle cx="0" cy="14" r="13"/>'
  return `${hairTop}
    <path d="M -8 18 L -9 28
             C -18 31 -27 40 -27 60
             L -25 160 L 25 160 L 26 62
             C 26 44 18 31 9 28 L 8 18 Z"/>
    <path d="M 18 40 C 34 30 48 16 58 2 L 68 10 C 56 28 40 44 24 54 Z"/>
    <circle cx="66" cy="4" r="6"/>`
}

const place = (body, x, y, s, fill, blur = 0, opacity = 1) =>
  `<g transform="translate(${x} ${y}) scale(${s})" fill="${fill}" color="${fill}"
      ${blur ? `filter="url(#soft${blur})"` : ''} opacity="${opacity}">${body}</g>`

/* ── Network: dots, lines, keyword nodes ──────────────────────────────── */
function network(sphere, nodes, dots, links) {
  const dot = ([x, y, r]) =>
    `<circle cx="${x}" cy="${y}" r="${r}" fill="${sphere.sky}" opacity="0.9" filter="url(#soft1)"/>`
  const line = ([x1, y1, x2, y2]) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${sphere.sky}" stroke-width="1.1" opacity="0.45"/>`
  const node = ([x, y, r, word]) => `
    <circle cx="${x}" cy="${y}" r="${r * 1.9}" fill="url(#nodeGlow)"/>
    <circle cx="${x}" cy="${y}" r="${r}" fill="url(#nodeFill)" opacity="0.95"/>
    <text x="${x}" y="${y + 5}" text-anchor="middle"
          font-family="'Helvetica Neue', Arial, sans-serif" font-size="14.5"
          letter-spacing="3.2" font-weight="500" fill="${sphere.ink}" opacity="0.82">${word}</text>`
  return links.map(line).join('') + dots.map(dot).join('') + nodes.map(node).join('')
}

/* ── Per-sphere scene: who stands where ─────────────────────────────────
 * Coordinates are the 884×791 frame. Crowd row sits mid-frame and blurs
 * away; foreground figures crop at the bottom edge like the mold's. */
function scene(sphere) {
  const crowdFill = sphere.ink
  const figFill = sphere.ink

  // Two crowd rows, dissolving downward through the fade mask so nobody is
  // cut off mid-air. The far row is barely more than presence.
  const far = [
    [110, 330, 0.42, 'short', 1], [330, 338, 0.4, 'bun', 0.92], [575, 334, 0.42, 'long', 1],
    [782, 330, 0.4, 'curly', 1.05],
  ].map(([x, y, s, hair, wide]) =>
    place(standing(hair, wide), x, y, s, crowdFill, 3, 0.32))
  const near = [
    [58, 360, 0.7, 'short', 1], [172, 372, 0.64, 'bun', 0.92], [268, 356, 0.72, 'long', 1],
    [388, 380, 0.6, 'curly', 1.06], [508, 372, 0.62, 'short', 0.94],
    [628, 358, 0.7, 'long', 1], [742, 370, 0.64, 'short', 1.08], [836, 356, 0.68, 'bun', 0.95],
  ].map(([x, y, s, hair, wide]) =>
    place(standing(hair, wide), x, y, s, crowdFill, 2, 0.55))
  const crowd = `<g mask="url(#crowdFade)">${far.join('')}${near.join('')}</g>`

  // Three big foreground figures, chest-up, cropped by the bottom edge like
  // the mold's. Scale 3+ so heads sit around y≈540 and shoulders run out of
  // frame.
  const fg = {
    economy: [
      place(laptopFig('short'), 170, 472, 2.75, figFill, 1, 1),
      place(standing('long', 1), 452, 480, 2.6, figFill, 2, 0.82),
      place(phoneFig('short'), 698, 468, 2.7, figFill, 1, 1),
    ],
    organizations: [
      place(presenterFig('curly'), 175, 475, 2.7, figFill, 1, 1),
      place(standing('long', 0.95), 452, 485, 2.55, figFill, 2, 0.82),
      place(laptopFig('bun'), 710, 472, 2.75, figFill, 1, 1),
    ],
    consumers: [
      place(shopperFig('long'), 162, 468, 2.65, figFill, 1, 1),
      place(phoneFig('bun'), 452, 478, 2.75, figFill, 2, 0.88),
      place(shopperFig('short'), 724, 470, 2.65, figFill, 1, 1),
    ],
  }[sphere.scene]

  // Screen light, painted OVER the figure so it reads as the device lighting
  // the chest and chin — the mold's signature. mix-blend-mode screen keeps it
  // luminous instead of milky. Positions are the devices' global coordinates
  // (figure origin + local device point × scale).
  const glows = {
    economy: [[726, 668, 64, 52], [96, 730, 70, 52]],
    organizations: [[712, 700, 62, 48], [371, 512, 24, 18]],
    consumers: [[478, 682, 62, 50], [268, 682, 48, 38]],
  }[sphere.scene].map(([x, y, rx, ry]) =>
    `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="url(#deviceGlow)" style="mix-blend-mode:screen"/>`)

  return crowd + fg.join('') + glows.join('')
}

const NODE_LAYOUT = [[442, 108, 46], [180, 208, 40], [706, 210, 40]]
const DOTS = [
  [90, 120, 2.2], [300, 78, 1.8], [560, 70, 2], [800, 120, 2.2], [64, 300, 1.8],
  [340, 170, 1.6], [545, 168, 1.6], [828, 300, 1.8], [255, 300, 1.6], [620, 296, 1.6],
]
const LINKS = [
  [442, 108, 180, 208], [442, 108, 706, 210], [180, 208, 90, 120], [180, 208, 64, 300],
  [706, 210, 800, 120], [706, 210, 828, 300], [442, 108, 560, 70], [442, 108, 300, 78],
  [180, 208, 255, 300], [706, 210, 620, 296], [300, 78, 90, 120], [560, 70, 800, 120],
  [255, 300, 340, 170], [620, 296, 545, 168],
]

function svg(sphere) {
  const nodes = NODE_LAYOUT.map(([x, y, r], i) => [x, y, r, sphere.words[i]])
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="field" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${sphere.hot}"/>
      <stop offset="0.52" stop-color="${sphere.mid}"/>
      <stop offset="1" stop-color="${sphere.deep}"/>
    </linearGradient>
    <radialGradient id="skyGlow" cx="0.5" cy="0.13" r="0.75">
      <stop offset="0" stop-color="${sphere.sky}" stop-opacity="0.85"/>
      <stop offset="1" stop-color="${sphere.sky}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="nodeGlow">
      <stop offset="0" stop-color="${sphere.sky}" stop-opacity="0.7"/>
      <stop offset="1" stop-color="${sphere.sky}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="nodeFill">
      <stop offset="0" stop-color="${sphere.sky}"/>
      <stop offset="1" stop-color="${sphere.hot}"/>
    </radialGradient>
    <radialGradient id="deviceGlow">
      <stop offset="0" stop-color="${sphere.sky}" stop-opacity="0.38"/>
      <stop offset="0.55" stop-color="${sphere.sky}" stop-opacity="0.16"/>
      <stop offset="1" stop-color="${sphere.sky}" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft1" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="1.1"/></filter>
    <filter id="soft2" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.6"/></filter>
    <filter id="soft3" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="4.5"/></filter>
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/>
      <feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0.6 0.6 0.6 0 0"/>
      <feComposite operator="in" in2="SourceGraphic"/>
    </filter>
    <linearGradient id="crowdFadeRamp" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff"/>
      <stop offset="0.62" stop-color="#fff"/>
      <stop offset="0.86" stop-color="#000"/>
    </linearGradient>
    <mask id="crowdFade">
      <rect width="${W}" height="${H}" fill="url(#crowdFadeRamp)"/>
    </mask>
    <radialGradient id="floorPool" cx="0.5" cy="1.05" r="0.9">
      <stop offset="0" stop-color="${sphere.deep}" stop-opacity="0.55"/>
      <stop offset="1" stop-color="${sphere.deep}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="${W}" height="${H}" fill="url(#field)"/>
  <rect width="${W}" height="${H}" fill="url(#skyGlow)"/>

  ${network(sphere, nodes, DOTS, LINKS)}

  <!-- darkness pooling at the floor before the figures stand in it -->
  <rect width="${W}" height="${H}" fill="url(#floorPool)"/>

  ${scene(sphere)}

  <!-- poster grain -->
  <rect width="${W}" height="${H}" filter="url(#grain)" opacity="0.10"/>
</svg>`
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 })
for (const sphere of SPHERES) {
  await page.setContent(
    `<style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>${svg(sphere)}`,
    { waitUntil: 'networkidle' },
  )
  const jpeg = await page.screenshot({ type: 'jpeg', quality: 82, clip: { x: 0, y: 0, width: W, height: H } })
  writeFileSync(OUT(sphere.id), jpeg)
  console.log(`  ${sphere.id}: ${(jpeg.length / 1024).toFixed(0)} KB → public/shift/domain-${sphere.id}-bg.jpg`)
}
await browser.close()
console.log('3 sphere backgrounds written (society is the design’s own asset, untouched)')
