#!/usr/bin/env node
/**
 * The portrait posters on disk are exactly what the generator still draws.
 *
 * `poster()` gained a frame so it could also draw the landscape set, and every
 * absolute length in it is now multiplied by a knob. Those knobs are 1 in the
 * portrait frame, so `x * 1 === x` bit-for-bit and the 51 committed SVGs must
 * not move by a byte — but "must not" is worth nothing without a check, and the
 * failure is silent: a stray `toFixed`, a rewritten expression, or one extra
 * `r()` call shifts the whole pseudo-random stream and every poster changes
 * subtly enough to pass review.
 *
 * The generator itself cannot prove this — it fetches 58 shifts from staging
 * before it draws anything. This redraws in-process from the committed manifest
 * and needs no network, so it can run in CI.
 *
 * The sphere is recovered from each file's own hot stop, the same trick
 * check-heroes.mjs uses, because the manifest records paths and not palettes.
 */
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'

import { poster, FRAMES } from './generate-heroes.mjs'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const MANIFEST = resolve(ROOT, 'src/lib/heroes.json')

/** The hot stop of each sphere's ramp — enough to identify which one was used. */
const HOT = { society: '#FF007A', economy: '#0FA6FF', organisations: '#C2C64F', consumers: '#FF6A1F' }

const sha = (text) => createHash('sha256').update(text).digest('hex')

const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8'))
const slugs = Object.keys(manifest)
if (!slugs.length) {
  console.error('✗ src/lib/heroes.json is empty — nothing to verify')
  process.exit(1)
}

const problems = []
let checked = 0

for (const slug of slugs) {
  const file = resolve(ROOT, `public${manifest[slug]}`)
  if (!existsSync(file)) {
    problems.push(`${slug}: manifest points at ${manifest[slug]}, which is not on disk`)
    continue
  }
  const onDisk = readFileSync(file, 'utf8')
  const sphere = Object.keys(HOT).find((name) => onDisk.includes(HOT[name]))
  if (!sphere) {
    problems.push(`${slug}: no sphere ramp found in the file, cannot redraw it`)
    continue
  }
  const redrawn = poster(slug, sphere, FRAMES.tall)
  checked += 1
  if (sha(redrawn) !== sha(onDisk)) {
    // Show where they first diverge — a whole SVG diff is unreadable.
    let at = 0
    while (at < redrawn.length && at < onDisk.length && redrawn[at] === onDisk[at]) at += 1
    problems.push(
      `${slug}: redrawn output differs at byte ${at}\n` +
      `      on disk: …${onDisk.slice(Math.max(0, at - 40), at + 40)}…\n` +
      `      redrawn: …${redrawn.slice(Math.max(0, at - 40), at + 40)}…`
    )
  }
}

if (problems.length) {
  console.error(`\n✗ ${problems.length} poster(s) no longer redraw byte-identically:\n`)
  console.error(problems.slice(0, 6).join('\n\n'))
  if (problems.length > 6) console.error(`\n  …and ${problems.length - 6} more`)
  console.error('\n  A knob is not exactly 1 in the portrait frame, an expression was')
  console.error('  rewritten rather than multiplied, or an r() call moved.\n')
  process.exit(1)
}
console.log(`✓ all ${checked} portrait posters redraw byte-identically`)
