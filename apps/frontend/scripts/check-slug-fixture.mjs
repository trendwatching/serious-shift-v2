// Asserts the frontend slugify matches packages/contracts/slug_fixtures.json —
// the same fixture the pipeline asserts. If these two drift, every shift whose
// title contains punctuation deep-links to a 404.
//
// Deliberately dependency-free (node, no test runner): it is one assertion, and
// the frontend has no other reason to carry a test framework yet.
import { readFileSync } from 'node:fs'
import { slugify } from '../src/lib/theme.js'

const fixture = JSON.parse(
  readFileSync(new URL('../../../packages/contracts/slug_fixtures.json', import.meta.url)),
)

let failed = 0
for (const [input, expected] of fixture.url_slug) {
  const got = slugify(input)
  if (got !== expected) {
    console.error(`  ✗ slugify(${JSON.stringify(input)}) = ${JSON.stringify(got)}, expected ${JSON.stringify(expected)}`)
    failed++
  }
}
if (failed) {
  console.error(`\n${failed}/${fixture.url_slug.length} slug cases disagree with the pipeline.`)
  process.exit(1)
}
console.log(`✓ slugify matches all ${fixture.url_slug.length} shared cases`)
