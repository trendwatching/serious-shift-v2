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
const DIR = resolve(ROOT, 'public/shift/heroes')
const manifest = JSON.parse(readFileSync(resolve(ROOT, 'src/lib/heroes.json'), 'utf8'))

/** The hot stop of each sphere's ramp — enough to identify which one was used. */
const HOT = { society: '#FF007A', economy: '#0FA6FF', organisations: '#C2C64F', consumers: '#FF6A1F' }

const fail = (m) => {
  console.error(`✗ ${m}`)
  process.exitCode = 1
}

const files = existsSync(DIR) ? readdirSync(DIR).filter((f) => f.endsWith('.svg')) : []
const slugs = Object.keys(manifest)

for (const slug of slugs) {
  if (manifest[slug] !== `/shift/heroes/${slug}.svg`) fail(`${slug}: manifest path does not match its slug`)
  if (!files.includes(`${slug}.svg`)) fail(`${slug}: in the manifest with no file — the hero would 404`)
}
for (const f of files) {
  if (!slugs.includes(f.replace(/\.svg$/, ''))) fail(`${f}: on disk but not in the manifest — nothing will ever request it`)
}

for (const f of files) {
  const svg = readFileSync(resolve(DIR, f), 'utf8')
  // Cheap well-formedness: the tag counts have to balance and it has to close.
  const opens = (svg.match(/<[a-zA-Z]/g) || []).length
  const closes = (svg.match(/<\/[a-zA-Z]|\/>/g) || []).length
  if (opens !== closes) fail(`${f}: ${opens} open tags vs ${closes} closes — not well-formed`)
  if (!svg.trimEnd().endsWith('</svg>')) fail(`${f}: truncated`)

  const used = Object.entries(HOT).filter(([, hex]) => svg.includes(hex)).map(([k]) => k)
  if (used.length !== 1) fail(`${f}: lit by ${used.length ? used.join(' + ') : 'no'} sphere ramp — expected exactly one`)
}

if (!slugs.length) fail('the manifest is empty — run `npm run heroes`')
if (!process.exitCode) console.log(`✓ ${files.length} hero posters, each one sphere's ramp, all in the manifest`)
