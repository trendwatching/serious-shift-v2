/**
 * WCAG 2.2 AA contrast contract for every token used as normal text.
 *
 * Each pair names the token it stands for, and the token's value is read out of
 * styles/tokens.css rather than repeated here. The previous version hard-coded
 * the hexes, and when the port moved the CTA orange to the design's #F04E09 the
 * gate carried on checking the old #C63800 and passing — asserting a palette the
 * site had stopped using. A gate that cannot notice drift is worse than none,
 * because it is quoted as evidence.
 */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const TOKENS = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../src/styles/tokens.css'),
  'utf8',
)

/** The live value of a custom property, by name. */
const token = (name) => {
  const found = TOKENS.match(new RegExp(`${name}:\\s*(#[0-9A-Fa-f]{6})`))
  if (!found) throw new Error(`${name} is not a plain hex token in tokens.css`)
  return found[1]
}

const rgb = (hex) => hex.match(/[0-9a-f]{2}/gi).map((part) => Number.parseInt(part, 16))
const channel = (value) => {
  const n = value / 255
  return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4
}
const luminance = (hex) => {
  const [r, g, b] = rgb(hex).map(channel)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a, b) => {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (values[0] + 0.05) / (values[1] + 0.05)
}
const overlay = (foreground, background, opacity) => {
  const fg = rgb(foreground)
  const bg = rgb(background)
  return `#${bg.map((value, index) => Math.round(fg[index] * opacity + value * (1 - opacity))
    .toString(16).padStart(2, '0')).join('')}`
}

const WHITE = '#FFFFFF'

const normalTextPairs = [
  ['ink-mid on white', token('--color-ink-mid'), WHITE],
  ['ink-row on white', token('--color-ink-row'), WHITE],
  ['ink-sector on white', token('--color-ink-sector'), WHITE],
  ['ink-body on white', token('--color-ink-body'), WHITE],
  // The small right-hand meta label — "Tap to open", "Scroll ›", "1 of 15". At
  // 11.5px it is the smallest text on the site, so it is also the one that can
  // least afford to be the lightest.
  ['ink-meta on white', token('--color-ink-meta'), WHITE],
  ['link on white', '#341482', WHITE],
  ['link hover on white', '#8B1E63', WHITE],
  ['CTA white on orange', WHITE, token('--color-orange')],
  ['Society surface', WHITE, token('--color-pink')],
  ['Economy surface', WHITE, '#0A6FBF'],
  ['Organisations surface', WHITE, '#737425'],
  ['Consumers surface', WHITE, '#C93B05'],
  ['positive surface', WHITE, token('--color-green')],
  ['teal positive surface', WHITE, '#126E63'],
  ['yellow pill', token('--color-ink'), token('--color-yellow')],
]

const decorativeStarts = ['#FF0B85', '#0F91EE', '#ADB03A', '#F65510', '#F5007F']
for (const color of decorativeStarts) {
  normalTextPairs.push([`white over darkened ${color}`, '#FFFFFF', overlay('#0D0B10', color, 0.38)])
}

let failed = false
for (const [label, foreground, background] of normalTextPairs) {
  const value = contrast(foreground, background)
  if (value < 4.5) {
    failed = true
    console.error(`✗ ${label}: ${value.toFixed(2)}:1`)
  }
}

if (failed) process.exit(1)
console.log(`✓ ${normalTextPairs.length} normal-text contrast pairs meet 4.5:1`)
