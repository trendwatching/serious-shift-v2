/** WCAG 2.2 AA contrast contract for every token used as normal text. */

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

const normalTextPairs = [
  ['ink-mid on white', '#6B6577', '#FFFFFF'],
  ['ink-dim on white', '#655F70', '#FFFFFF'],
  ['ink-faint on white', '#746E80', '#FFFFFF'],
  ['link on white', '#341482', '#FFFFFF'],
  ['link hover on white', '#8B1E63', '#FFFFFF'],
  ['CTA white on orange', '#FFFFFF', '#C63800'],
  ['Society surface', '#FFFFFF', '#C8006B'],
  ['Economy surface', '#FFFFFF', '#0A6FBF'],
  ['Organisations surface', '#FFFFFF', '#737425'],
  ['Consumers surface', '#FFFFFF', '#C93B05'],
  ['positive surface', '#FFFFFF', '#1F7A4D'],
  ['teal positive surface', '#FFFFFF', '#126E63'],
  ['yellow pill', '#1B1620', '#FDFF85'],
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
