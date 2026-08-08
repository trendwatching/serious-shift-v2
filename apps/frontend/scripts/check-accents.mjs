#!/usr/bin/env node
/**
 * The per-sphere palette exists twice, and this asserts the two copies agree.
 *
 * tokens.css holds it as CSS custom properties, scoped by `[data-domain]`.
 * lib/theme.js holds four of the same values as JS literals, because the chrome
 * that uses them — the deck panels, the breadcrumb pill — renders ABOVE the
 * element that sets `data-domain`, so `var(--a-crumb)` would resolve to the
 * `:root` default (Society's) rather than to the sphere in view.
 *
 * That is a real constraint, not laziness, so the duplication stays. What
 * cannot stay is the drift: nothing stops someone deepening `--a-crumb` in
 * tokens.css and leaving the breadcrumb pill on the old tint, and the result is
 * two shades of the same colour on one screen with no error anywhere.
 *
 * Also asserts the invariant that made these consistent in the first place:
 *  - `dot` is the gradient's own mid stop, not an independent colour.
 *  - `--pos` is one green for every sphere, because it means "the side you are
 *    moving away from", not "this sphere". A per-sphere override there is what
 *    made Organizations teal while its neighbours were green.
 */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const TOKENS = readFileSync(resolve(ROOT, 'src/styles/tokens.css'), 'utf8')
const THEME = readFileSync(resolve(ROOT, 'src/lib/theme.js'), 'utf8')

const SPHERES = ['society', 'economy', 'organisations', 'consumers']

const fail = (m) => {
  console.error(`✗ ${m}`)
  process.exitCode = 1
}

/** The `[data-domain='x'] { … }` block, or `:root` for Society's defaults. */
const scope = (sphere) => {
  if (sphere === 'society') return TOKENS.slice(TOKENS.indexOf(':root {'), TOKENS.indexOf("[data-domain='economy']"))
  const start = TOKENS.indexOf(`[data-domain='${sphere}']`)
  if (start === -1) throw new Error(`no [data-domain='${sphere}'] block in tokens.css`)
  return TOKENS.slice(start, TOKENS.indexOf('}', start))
}

/**
 * A sphere's value for a token: its own override if it has one, otherwise the
 * `:root` default it inherits. The gradients and the yellow eyebrow are only
 * ever declared at `:root`, so without the fallback this reads them as missing.
 */
const cssVar = (sphere, name) => {
  const pattern = new RegExp(`${name}:\\s*([^;]+);`)
  const own = scope(sphere).match(pattern)
  if (own) return own[1].trim()
  const root = scope('society').match(pattern)
  return root ? root[1].trim() : null
}

/** The `society: { … }` entry in DOMAIN_THEME. */
const themeEntry = (sphere) => {
  const start = THEME.indexOf(`  ${sphere}: {`)
  if (start === -1) throw new Error(`no ${sphere} entry in DOMAIN_THEME`)
  return THEME.slice(start, THEME.indexOf('\n  },', start))
}

const themeField = (sphere, field) => {
  const found = themeEntry(sphere).match(new RegExp(`${field}:\\s*'([^']+)'`))
  return found ? found[1] : null
}

const norm = (v) => (v || '').replace(/\s+/g, ' ').trim().toLowerCase()

for (const sphere of SPHERES) {
  const pairs = [
    ['grad', `--grad-${sphere}`],
    ['crumb', '--a-crumb'],
    ['eyebrow', '--a-eyebrow'],
  ]
  for (const [field, token] of pairs) {
    const js = themeField(sphere, field)
    let css = cssVar(sphere, token)
    // Society's eyebrow is the token's own default, spelled as a var().
    if (css === 'var(--color-yellow)') css = TOKENS.match(/--color-yellow:\s*([^;]+);/)[1].trim()
    if (!js || !css) { fail(`${sphere}: cannot read ${field} / ${token}`); continue }
    if (norm(js) !== norm(css)) {
      fail(`${sphere}.${field} is ${js} but ${token} is ${css} — the two palettes have drifted`)
    }
  }

  // The dot is the gradient's mid stop, so it can never be "nearly" the sphere.
  const grad = themeField(sphere, 'grad') || ''
  const stops = grad.match(/#[0-9A-Fa-f]{6}/g) || []
  const dot = themeField(sphere, 'dot')
  if (stops.length < 2 || norm(dot) !== norm(stops[1])) {
    fail(`${sphere}.dot is ${dot} but the gradient's mid stop is ${stops[1]} — pick one`)
  }
}

// One positive green, site-wide.
for (const sphere of SPHERES.slice(1)) {
  if (/--pos(-deep)?:/.test(scope(sphere))) {
    fail(`${sphere} overrides --pos. It means "the side you are moving away from", not "this sphere" — one green everywhere.`)
  }
}

if (!process.exitCode) console.log(`✓ ${SPHERES.length} sphere palettes agree across tokens.css and theme.js`)
