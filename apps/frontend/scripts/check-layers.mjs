#!/usr/bin/env node
/**
 * Guards the two mistakes that made the last build diverge from the design
 * silently — both invisible in review, both wrong on every page.
 *
 * 1. AN UNLAYERED CLASS RULE.
 *    Tailwind v4 emits utilities into `@layer utilities`. An unlayered rule
 *    beats a layered one regardless of order or specificity, so a top-level
 *    `.t-display { font-weight: 700 }` silently overrides a co-applied
 *    `font-semibold`. The last build had six such classes and they were
 *    quietly winning against about a dozen utilities across the app.
 *
 * 2. A RESPONSIVE VARIANT OUTSIDE styles/desktop.css.
 *    The design is one fixed 393px canvas. A `md:`/`lg:` inside a component
 *    means that component no longer holds the design's value at any width.
 *    Desktop belongs in exactly one file so it cannot drift.
 *
 * 3. A DISPLAY UTILITY ON AN ELEMENT THE DESKTOP LAYER RESHAPES.
 *    The mirror image of (1). desktop.css turns `.horizon` and `.sub-stack`
 *    into grids from @layer components, and a co-applied `flex` utility beats
 *    it — so the rule parsed, matched, and was discarded, and the widened
 *    layout never arrived at any width. Those elements declare their own
 *    `display` in components.css; a utility beside them re-breaks it.
 *
 * Keyframes, @media, @supports and element/attribute selectors are all fine
 * unlayered — only class rules can collide with a utility.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = new URL('../src', import.meta.url).pathname
const DESKTOP = join(SRC, 'styles/desktop.css')

const walk = (dir) => readdirSync(dir).flatMap((name) => {
  const full = join(dir, name)
  return statSync(full).isDirectory() ? walk(full) : [full]
})

const files = walk(SRC)
const problems = []

// ── 1. unlayered class rules in our own stylesheets ────────────────────────
for (const file of files.filter((f) => f.endsWith('.css'))) {
  const source = readFileSync(file, 'utf8')
  let depth = 0
  let inLayer = false
  let layerDepth = 0

  // A hand-rolled brace walk rather than a CSS parser: this runs on five
  // files we own, and a dependency is not worth it.
  const lines = source.split('\n')
  lines.forEach((line, i) => {
    const trimmed = line.trim()
    if (/^@layer\b[^;]*\{/.test(trimmed) && !inLayer) {
      inLayer = true
      layerDepth = depth
    }
    // A class selector at depth 0, outside any @layer, that opens a block.
    if (!inLayer && depth === 0 && /^\.[A-Za-z_-][^{}]*\{\s*$/.test(trimmed)) {
      problems.push(
        `${relative(SRC, file)}:${i + 1}  unlayered class rule "${trimmed.replace(/\s*\{$/, '')}"\n` +
        '    Wrap it in @layer components (or utilities). Unlayered rules beat\n' +
        '    Tailwind utilities, so this silently overrides anything applied beside it.'
      )
    }
    depth += (line.match(/\{/g) || []).length
    depth -= (line.match(/\}/g) || []).length
    if (inLayer && depth <= layerDepth) inLayer = false
  })
}

// ── 2. responsive variants outside the desktop layer ───────────────────────
const VARIANT = /(?:^|[\s"'`:])(?:sm|md|lg|xl|2xl):[a-z[]/
for (const file of files.filter((f) => /\.(jsx?|css)$/.test(f))) {
  if (file === DESKTOP) continue
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    if (VARIANT.test(line)) {
      problems.push(
        `${relative(SRC, file)}:${i + 1}  responsive variant outside styles/desktop.css\n` +
        `    ${line.trim().slice(0, 100)}\n` +
        '    The design is one fixed mobile canvas; desktop lives in desktop.css alone.'
      )
    }
  })
}

// ── 3. utilities that override what the desktop layer sets ────────────────
// A utility beats a component rule in v4's layer order, so a utility that sets
// the same property desktop.css sets means the desktop rule parses, matches and
// is silently discarded. `.horizon` and `.sub-stack` become grids; `.widen` and
// `.bleed` are given an explicit width.
const OVERRIDDEN = [
  { classes: ['horizon', 'sub-stack', 'about-body'], property: 'display',
    utility: /(?:^|\s)(?:flex|grid|block|inline-flex|inline-grid|contents)(?:$|\s)/ },
  { classes: ['widen', 'bleed', 'badge-row'], property: 'width',
    utility: /(?:^|\s)(?:w-full|w-screen|w-\[|max-w-)/ },
  // `.footer-inner` and `.measure` are centred / capped by the layer; a margin
  // or max-width utility on them wins and the block drifts off the page axis.
  { classes: ['footer-inner', 'crumb-float'], property: 'margin',
    utility: /(?:^|\s)(?:m-|mx-|ml-|mr-)/ },
  { classes: ['footer-inner', 'measure', 'about-section', 'about-masthead'], property: 'max-width',
    utility: /(?:^|\s)max-w-/ },
]
const has = (names, klass) => new RegExp(`(?:^|\\s)${klass}(?:$|\\s)`).test(names)

for (const file of files.filter((f) => /\.jsx?$/.test(f))) {
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    for (const match of line.matchAll(/className="([^"]*)"/g)) {
      const names = match[1]
      for (const rule of OVERRIDDEN) {
        if (!rule.classes.some((klass) => has(names, klass))) continue
        if (!rule.utility.test(names)) continue
        problems.push(
          `${relative(SRC, file)}:${i + 1}  utility sets \`${rule.property}\`, which styles/desktop.css also sets\n` +
          `    className="${names}"\n` +
          '    The utility layer wins, so the desktop rule is silently discarded.\n' +
          `    Drop it; the base ${rule.property} belongs in components.css.`
        )
      }
    }
  })
}

// ── 4. inline styles that override what the desktop layer sets ────────────
// The same failure as (3) but through the one channel nothing can outrank: an
// inline style beats every rule in every layer. This has bitten five times —
// an inline `minHeight` left a hero at phone height on desktop; inline geometry
// stranded the horizon dots on the phone's spine; an inline `padding` shorthand
// pinned /about to a 22px gutter; and `padding: '2px 22px 6px'` on the rails
// discarded `.widen .rail { padding-inline: 0 }`, putting every rail's first
// card 20px right of its own heading on every desktop.
//
// So the table is DERIVED from desktop.css rather than hand-kept: whatever that
// file sets is what an inline style must not restate. A hand-maintained list is
// exactly what let the rails through.
// Comments are stripped FIRST. A selector capture runs back to the previous
// brace, so it swallows the comment above the rule — and almost every rule in
// desktop.css has one. Leaving them in made this check silently parse eight
// rules out of thirty and pass on the very regression it was written for.
const desktop = readFileSync(DESKTOP, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
// selector → properties, for the simple `.a`/`.a .b`/`.a:nth… .b` shapes here
const guarded = new Map()
for (const block of desktop.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
  const selector = block[1].trim()
  if (!selector.startsWith('.')) continue
  const classes = [...selector.matchAll(/\.([A-Za-z_][\w-]*)/g)].map((m) => m[1])
  if (!classes.length) continue
  const target = classes[classes.length - 1]
  // NOTE the blind spot this still has. `.needs-pair > * { min-width: 190px }`
  // styles CHILDREN, so the utility that beats it (`min-w-0`) sits on an element
  // that never carries `needs-pair` — and both this check and (3) look at the
  // element wearing the class. A file-scoped heuristic was tried and produced
  // eight false positives, because it cannot tell which `min-w-0` belongs to
  // which parent; a check that cries wolf gets worked around. The exact version
  // of this assertion is at runtime, in e2e/desktop.spec.js, which reads the
  // computed value off a real desktop render.
  for (const decl of block[2].split(';')) {
    const prop = decl.split(':')[0]?.trim()
    if (!prop || prop.startsWith('--')) continue
    if (!guarded.has(target)) guarded.set(target, new Set())
    guarded.get(target).add(prop)
  }
}

// Which inline style keys write a given CSS property. Shorthands count: React's
// `padding` writes padding-inline, which is the whole point.
const WRITES = {
  'padding-inline': ['padding', 'paddingInline', 'paddingLeft', 'paddingRight'],
  'padding-left': ['padding', 'paddingInline', 'paddingLeft'],
  'margin-inline': ['margin', 'marginInline', 'marginLeft', 'marginRight'],
  width: ['width'],
  'max-width': ['maxWidth'],
  height: ['height'],
  'min-height': ['minHeight'],
  display: ['display'],
  'grid-template-columns': ['gridTemplateColumns'],
  order: ['order'],
  gap: ['gap'],
  left: ['left', 'inset'],
  top: ['top', 'inset'],
  inset: ['inset'],
  transform: ['transform'],
  'flex-wrap': ['flexWrap'],
  'padding-top': ['padding', 'paddingBlock', 'paddingTop'],
  // The hero art. Without these three the guard was a no-op for exactly the
  // property the desktop layer now depends on: an inline `backgroundImage`
  // would have won at runtime and reported clean.
  'background-image': ['background', 'backgroundImage'],
  'background-position': ['background', 'backgroundPosition'],
  'background-size': ['background', 'backgroundSize'],
}

for (const file of files.filter((f) => /\.jsx?$/.test(f))) {
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, i) => {
    const cls = line.match(/className=(?:"([^"]*)"|\{`([^`]*)`\})/)
    if (!cls) return
    const names = cls[1] ?? cls[2] ?? ''
    // The style prop for this element: same line, or the next few before the
    // tag closes. Stop at `>` so a child's style is never attributed here.
    const tag = lines.slice(i, i + 8).join('\n').split(/>\s*$|>\n/)[0]
    const style = tag.match(/style=\{\{([\s\S]*?)\}\}/)
    if (!style) return
    const keys = [...style[1].matchAll(/(?:^|[,{\s])'?([A-Za-z-]+)'?\s*:/g)].map((m) => m[1])
    for (const klass of names.split(/\s+/)) {
      const props = guarded.get(klass)
      if (!props) continue
      for (const prop of props) {
        const writers = WRITES[prop] || []
        const clash = keys.find((k) => writers.includes(k))
        if (!clash) continue
        problems.push(
          `${relative(SRC, file)}:${i + 1}  inline \`${clash}\` overrides \`${prop}\`, which styles/desktop.css sets on .${klass}\n` +
          `    ${line.trim().slice(0, 100)}\n` +
          '    An inline style beats every layer, so the desktop rule is silently discarded.\n' +
          `    Move the base value into components.css so desktop.css can win.`
        )
      }
    }
  })
}

if (problems.length) {
  console.error(`\n✗ ${problems.length} layering/responsive violation(s):\n`)
  console.error(problems.join('\n\n'))
  console.error('')
  process.exit(1)
}
console.log('✓ every class rule is layered, and desktop lives in one file')
