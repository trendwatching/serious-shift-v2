#!/usr/bin/env node
/**
 * The manifest and the directory must agree.
 *
 * `useDomains` trusts src/lib/heroes.json completely: a slug listed there gets an
 * <img>-shaped background, and a slug missing from it falls back to the gradient
 * hero. So a manifest entry with no file on disk is the one failure mode that
 * ships a broken image to a reader, and a file with no manifest entry is dead
 * weight in the deploy. Neither is visible in review, so it is checked here.
 *
 * Also asserts each poster is well-formed and carries exactly one sphere's ramp,
 * because the whole point of generating per sphere is that a Consumers hero is
 * not lit with Society's pink.
 */
import { readdirSync, readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SETS = [
  { dir: 'public/shift/heroes', manifest: 'src/lib/heroes.json', base: '/shift/heroes', label: 'key-shift posters' },
  // Sub-shift keys are `<key shift>/<sub-shift>` while the file is
  // `<key>__<sub>.svg`, so the path cannot be derived from the key by string
  // substitution alone — which is exactly why this checks the pair.
  { dir: 'public/shift/subs', manifest: 'src/lib/sub-art.json', base: '/shift/subs', label: 'sub-shift fragments' },
  // The landscape cut of the same 51 posters, for the desktop hero band.
  { dir: 'public/shift/heroes-wide', manifest: 'src/lib/heroes-wide.json', base: '/shift/heroes-wide', label: 'key-shift posters (wide)' },
]

/** The hot stop of each sphere's ramp — enough to identify which one was used. */
const HOT = { society: '#FF007A', economy: '#0FA6FF', organizations: '#C2C64F', consumers: '#FF6A1F' }

const fail = (m) => {
  console.error(`✗ ${m}`)
  process.exitCode = 1
}

const counts = []
for (const set of SETS) {
  const dir = resolve(ROOT, set.dir)
  const manifest = JSON.parse(readFileSync(resolve(ROOT, set.manifest), 'utf8'))
  const files = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith('.svg')) : []
  const keys = Object.keys(manifest)
  const claimed = new Set(keys.map((k) => manifest[k].slice(`${set.base}/`.length)))

  for (const key of keys) {
    const file = manifest[key].startsWith(`${set.base}/`) && manifest[key].slice(`${set.base}/`.length)
    if (!file) fail(`${set.label}: ${key} points outside ${set.base}`)
    else if (!files.includes(file)) fail(`${set.label}: ${key} → ${file}, which is not on disk — the image would 404`)
  }
  for (const f of files) {
    if (!claimed.has(f)) fail(`${set.label}: ${f} is on disk but unclaimed — nothing will ever request it`)
  }
  if (new Set(Object.values(manifest)).size !== keys.length) {
    fail(`${set.label}: two keys share one file — a slug collision is silently reusing art`)
  }

  for (const f of files) {
    const svg = readFileSync(resolve(dir, f), 'utf8')
    // Cheap well-formedness: the tag counts have to balance and it has to close.
    const opens = (svg.match(/<[a-zA-Z]/g) || []).length
    const closes = (svg.match(/<\/[a-zA-Z]|\/>/g) || []).length
    if (opens !== closes) fail(`${set.label}: ${f} has ${opens} open tags vs ${closes} closes — not well-formed`)
    if (!svg.trimEnd().endsWith('</svg>')) fail(`${set.label}: ${f} is truncated`)

    const used = Object.entries(HOT).filter(([, hex]) => svg.includes(hex)).map(([k]) => k)
    if (used.length !== 1) fail(`${set.label}: ${f} is lit by ${used.length ? used.join(' + ') : 'no'} sphere ramp — expected exactly one`)
  }

  if (!keys.length) fail(`${set.label}: the manifest is empty — run \`npm run heroes\``)
  counts.push(`${files.length} ${set.label}`)
}

if (!process.exitCode) console.log(`✓ ${counts.join(' + ')}, each one sphere's ramp, all manifested`)

/* Every portrait poster must have a landscape twin, and vice versa.
   Without this a half-completed run ships some shifts with a landscape hero and
   some with a portrait one stretched across the same band — the exact failure
   this file exists to catch, and the one least visible in review. */
const tall = JSON.parse(readFileSync(resolve(ROOT, 'src/lib/heroes.json'), 'utf8'))
const wide = JSON.parse(readFileSync(resolve(ROOT, 'src/lib/heroes-wide.json'), 'utf8'))
const og = JSON.parse(readFileSync(resolve(ROOT, 'src/lib/heroes-og.json'), 'utf8'))

let broken = false
for (const [label, set] of [['landscape', wide], ['link-preview card', og]]) {
  for (const slug of Object.keys(tall)) {
    if (!set[slug]) { broken = true; console.error(`\u2717 ${slug}: portrait poster with no ${label}`) }
  }
  for (const slug of Object.keys(set)) {
    if (!tall[slug]) { broken = true; console.error(`\u2717 ${slug}: ${label} with no portrait original`) }
  }
}

/* The card is what an unfurler fetches, so a manifest entry with no file is a
   blank preview on every share of that shift. It is also RASTER on purpose —
   og:image pointing at an SVG renders as no image at all in Facebook,
   LinkedIn, X, Slack and WhatsApp. */
for (const [slug, path] of Object.entries(og)) {
  if (!path.endsWith('.jpg')) {
    broken = true
    console.error(`\u2717 ${slug}: link-preview card must be raster, got ${path}`)
  }
  if (!existsSync(resolve(ROOT, `public${path}`))) {
    broken = true
    console.error(`\u2717 ${slug}: manifest lists ${path}, which is not on disk`)
  }
}
if (broken) process.exit(1)
console.log(`\u2713 all ${Object.keys(tall).length} posters have all three frames`)

