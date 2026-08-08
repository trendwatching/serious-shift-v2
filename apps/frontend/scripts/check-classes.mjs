#!/usr/bin/env node
/**
 * Every class the source applies must actually exist in the built stylesheet.
 *
 * `/about` shipped for months wearing `w-prose` in five places. Tailwind's class
 * is `max-w-prose`; `w-prose` is not a class in any layer, matched nothing, and
 * emitted no CSS at all. It was the only thing holding the page's masthead, so
 * the title and standfirst ran from x=0 while every section below them sat in a
 * centred column — and nothing anywhere reported it, because a typo'd utility
 * is indistinguishable from a deliberate one until you look at the output.
 *
 * Tailwind only emits the utilities it finds, so "in the source but not in the
 * stylesheet" is exactly the set of names that do nothing. Run AFTER a build:
 * the built CSS is the oracle.
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname
const SRC = join(ROOT, 'src')
const ASSETS = join(ROOT, 'out/assets')

if (!existsSync(ASSETS)) {
  console.error('✗ no build to check against — run `npm run build` first')
  process.exit(1)
}

const cssFiles = readdirSync(ASSETS).filter((f) => f.endsWith('.css'))
if (!cssFiles.length) {
  console.error('✗ the build produced no stylesheet')
  process.exit(1)
}
const css = cssFiles.map((f) => readFileSync(join(ASSETS, f), 'utf8')).join('\n')

// Class names that appear as selectors in the output, with CSS escapes undone
// so `.text-\[15px\]` matches the `text-[15px]` written in the JSX.
const emitted = new Set()
for (const m of css.matchAll(/\.((?:\\.|[^\s.,:>~+[\]{}()"'#])+)/g)) {
  emitted.add(m[1].replace(/\\/g, ''))
}

const walk = (dir) => readdirSync(dir).flatMap((name) => {
  const full = join(dir, name)
  return statSync(full).isDirectory() ? walk(full) : [full]
})

const problems = []
for (const file of walk(SRC).filter((f) => /\.jsx?$/.test(f))) {
  readFileSync(file, 'utf8').split('\n').forEach((line, i) => {
    for (const match of line.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)) {
      // Interpolations are dropped rather than parsed: a `${a ? 'x' : 'y'}`
      // would otherwise contribute `?`, `:` and quoted fragments as "classes".
      const list = (match[1] ?? match[2] ?? '').replace(/\$\{[^}]*\}/g, ' ')
      for (const raw of list.split(/\s+/)) {
        const name = raw.trim()
        if (!name || emitted.has(name)) continue
        problems.push(
          `${relative(SRC, file)}:${i + 1}  class "${name}" emits no CSS\n` +
          `    className="${list.trim().slice(0, 90)}"\n` +
          '    It is a typo or a stale name: nothing in the built stylesheet matches it,\n' +
          '    so whatever it was meant to do is simply not happening.'
        )
      }
    }
  })
}

if (problems.length) {
  console.error(`\n✗ ${problems.length} class(es) that style nothing:\n`)
  console.error(problems.join('\n\n'))
  console.error('')
  process.exit(1)
}
console.log('✓ every class in the source exists in the built stylesheet')
