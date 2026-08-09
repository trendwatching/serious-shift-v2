#!/usr/bin/env node
/**
 * Is this origin's DATA compatible with this build? Run before moving a domain.
 *
 *   node scripts/preflight-origin.mjs https://backend-production-d723.up.railway.app
 *
 * The site is two halves that are versioned separately and can silently
 * disagree: editorial content lives in Postgres and is served from
 * `documents['map']`, while the artwork and the sphere list are compiled into
 * the frontend bundle. Nothing at runtime notices when they are from different
 * vintages — a shift with no art falls back to its sphere gradient, which looks
 * deliberate, and a route that is not in the map is simply a 404.
 *
 * Checked against production on 2026-08-09, this is not hypothetical. Its map
 * was the pre-rebuild schema: 58 key shifts and 290 sub-shifts with **no `slug`
 * and no `modules` on any of them**, and a sphere still called `organisations`.
 * Deployed as-is that is 348 pages of 404 and every image missing, on a site
 * that otherwise looks fine — the homepage and /about would have rendered
 * perfectly.
 *
 * Exits non-zero with a specific reason, so it can gate a cutover script.
 */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const origin = (process.argv[2] || '').replace(/\/$/, '')
if (!origin) {
  console.error('usage: node scripts/preflight-origin.mjs <origin>')
  process.exit(2)
}

const read = (p) => JSON.parse(readFileSync(resolve(ROOT, p), 'utf8'))
const heroes = read('src/lib/heroes.json')
const wide = read('src/lib/heroes-wide.json')
const og = read('src/lib/heroes-og.json')
const subs = read('src/lib/sub-art.json')
// The sphere ids this bundle will accept. `isSphere()` rejects anything else,
// so a mismatch 404s the sphere page in the browser even when the server
// serves it happily.
const SPHERES = readFileSync(resolve(ROOT, 'src/lib/theme.js'), 'utf8')
  .match(/DOMAIN_ORDER\s*=\s*\[([^\]]*)\]/)[1]
  .split(',').map((s) => s.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)

const problems = []
const note = (m) => console.log(`  ${m}`)

const get = async (path) => {
  const res = await fetch(origin + path, { redirect: 'manual' })
  return { status: res.status, body: res.ok ? await res.json().catch(() => null) : null }
}

console.log(`preflight: ${origin}`)
console.log(`bundle expects spheres: ${SPHERES.join(', ')}\n`)

const index = await get('/api/v1/map')
if (index.status !== 200 || !index.body) {
  console.error(`✗ /api/v1/map returned ${index.status} — no map to check against`)
  process.exit(1)
}
const served = (index.body.domains || []).map((d) => d.id)
note(`spheres served: ${served.join(', ') || '(none)'}`)
for (const id of served) {
  if (!SPHERES.includes(id)) {
    problems.push(`sphere '${id}' is served but this bundle does not know it — `
      + `its page will 404 in the browser (see isSphere in src/lib/theme.js)`)
  }
}

let published = { kt: [], st: [] }
for (const sphere of served) {
  const { status, body } = await get(`/api/v1/map/${sphere}`)
  if (status !== 200 || !body) { problems.push(`/api/v1/map/${sphere} returned ${status}`); continue }
  for (const k of body.key_shifts || body.key_trends || []) {
    published.kt.push({ sphere, slug: (k.slug || '').split('/').pop(), name: k.name })
  }
}
note(`key shifts published: ${published.kt.length}`)

const unslugged = published.kt.filter((k) => !k.slug)
if (unslugged.length) {
  problems.push(`${unslugged.length} of ${published.kt.length} key shifts have NO slug — `
    + `seo.rs registers a route only for a non-empty slug, so those pages 404`)
}

// Art is keyed by slug and compiled into the image; a published slug with no
// entry renders the sphere gradient and looks intentional.
const missing = { hero: [], wide: [], og: [] }
for (const k of published.kt) {
  if (!k.slug) continue
  if (!heroes[k.slug]) missing.hero.push(k.slug)
  if (!wide[k.slug]) missing.wide.push(k.slug)
  if (!og[k.slug]) missing.og.push(k.slug)
}
note(`art coverage: hero ${published.kt.length - missing.hero.length}/${published.kt.length}, `
  + `landscape ${published.kt.length - missing.wide.length}/${published.kt.length}, `
  + `cards ${published.kt.length - missing.og.length}/${published.kt.length}`)
for (const [kind, list] of Object.entries(missing)) {
  if (list.length) {
    problems.push(`${list.length} published shift(s) have no ${kind} art in this build — `
      + `e.g. ${list.slice(0, 3).join(', ')}. Run 'npm run heroes' against this origin, `
      + `then 'npm run heroes:og', commit, and redeploy BEFORE moving the domain`)
  }
}
const orphanArt = Object.keys(heroes).filter((s) => !published.kt.some((k) => k.slug === s))
if (orphanArt.length) {
  note(`(${orphanArt.length} art file(s) in the build are not published — harmless, just weight)`)
}

// Caching. Not cosmetic: this origin served EVERY static file with no
// `Cache-Control` at all, because the immutable-asset nest was still pointed at
// `/_next/static` from the Next export. With no directive a browser falls back
// to heuristic freshness — a fraction of the file's age — and right after a
// deploy every file's age is ~0, so the bundle, the stylesheet, the fonts and
// all the artwork revalidate on every navigation. Launch day is the worst case,
// because nothing is warm.
{
  const shell = await fetch(origin + '/').then((r) => r.text()).catch(() => '')
  const bundle = shell.match(/\/assets\/[^"']+\.js/)?.[0]
  const someArt = published.kt.find((k) => k.slug && heroes[k.slug])
  const cc = async (path) =>
    (await fetch(origin + path)).headers.get('cache-control') ?? '(none)'

  if (bundle) {
    const v = await cc(bundle)
    note(`cache  ${bundle.padEnd(34)} ${v}`)
    // Vite content-hashes this filename, so a changed file is a changed URL and
    // a stale entry cannot happen — anything short of immutable is money left
    // on the table.
    if (!v.includes('immutable')) {
      problems.push(`the hashed bundle is served with '${v}' — expected `
        + `'immutable'. The /assets nest is not matching; check it against `
        + `Vite's output dir in apps/backend/src/main.rs`)
    }
  }
  if (someArt) {
    const path = `/shift/heroes/${someArt.slug}.svg`
    const v = await cc(path)
    note(`cache  ${'artwork'.padEnd(34)} ${v}`)
    if (v === '(none)') problems.push(`artwork is served with no Cache-Control`)
    // Art filenames are slug-keyed, not content-hashed, so a republish reuses
    // the URL. `immutable` here would pin a stale poster for a year.
    if (v.includes('immutable')) {
      problems.push(`artwork is 'immutable', but its filenames are keyed by slug `
        + `and reused on republish — a regenerated poster could never evict the `
        + `old one`)
    }
  }
  const shellCc = await cc('/')
  note(`cache  ${'index.html'.padEnd(34)} ${shellCc}`)
  if (!/no-cache|no-store|max-age=0/.test(shellCc)) {
    problems.push(`the shell is cached ('${shellCc}') — it names the current `
      + `hashed bundles, so caching it makes a deploy invisible to a returning `
      + `browser`)
  }
}

// A page each, end to end: the shapes a reader actually hits.
if (published.kt.length && published.kt[0].slug) {
  const k = published.kt[0]
  for (const [label, path] of [
    ['home', '/'],
    ['about', '/about'],
    ['sphere', `/${k.sphere}`],
    ['shift', `/${k.sphere}/${k.slug}`],
    ['robots', '/robots.txt'],
    ['sitemap', '/sitemap.xml'],
  ]) {
    const res = await fetch(origin + path, { redirect: 'manual' })
    note(`${label.padEnd(8)} ${path.padEnd(34)} ${res.status}`)
    if (res.status !== 200) problems.push(`${path} returned ${res.status}, expected 200`)
  }
}

console.log()
if (problems.length) {
  console.error(`✗ ${problems.length} reason(s) this origin is not ready:\n`)
  for (const p of problems) console.error(`  • ${p}`)
  console.error('')
  process.exit(1)
}
console.log('✓ this origin\'s data and this build agree — safe to move the domain')
