/**
 * The map fixtures and the route mock, shared by every spec that needs data.
 *
 * They lived inside app.spec.js until smooth.spec.js needed the same document:
 * that spec was pointed at a hand-started `vite preview` on port 4400, which
 * exists on one laptop and nowhere else, so all six of its tests failed the
 * moment CI ran them. A spec that cannot run on the runner is not a gate.
 */
// Society carries the ceiling the 18 Aug 2026 review allows, so the CLS spec
// exercises the case that actually hurts: the backend caps the index preview at
// four shifts, and the sphere page used to paint those four and then jump to
// the full list.
const SOCIETY_SHIFTS = 15
const societyShifts = Array.from({ length: SOCIETY_SHIFTS }, (_, i) => ({
  id: `kt-${i + 1}`, domain_id: 'society', slug: i === 0 ? 'trust-machines' : `shift-${i + 1}`,
  name: i === 0 ? 'Trust Machines' : `Shift ${i + 1}`,
  subtitle: `Subtitle ${i + 1}`, read_time: '4 min read',
}))

const domains = [
  ['society', 'Society', '2028'],
  ['economy', 'Economy', '2027'],
  ['organizations', 'Organizations', '2026'],
  ['consumers', 'Consumers', '2026'],
].map(([id, name, horizon]) => ({ id, name, horizon, short_description: `${name} shifts`, key_shift_count: id === 'society' ? SOCIETY_SHIFTS : 1 }))

const index = {
  updated: '2026-08-02',
  totals: { domains: 4, key_shifts: SOCIETY_SHIFTS + 3, sub_shifts: 25 },
  // `key_shifts` is the backend's `.take(4)` preview (main.rs). Omitting it
  // meant every spec ran against a payload production never sends, and the
  // sphere page's partial-paint bug could not be reproduced.
  domains: domains.map((d) => (d.id === 'society'
    ? { ...d, key_shifts: societyShifts.slice(0, 4) }
    : d)),
}
const shift = {
  id: 'kt-1', domain_id: 'society', slug: 'trust-machines', name: 'Trust Machines',
  subtitle: 'Verification becomes a product.', read_time: '5 min read',
  modules: [
    { type: 'peel_tabs', data: { whats_changing: 'Trust becomes designed.', why_now: 'Synthetic media is ordinary.' } },
    { type: 'human_needs', data: { unlocked: 'Agency grows.', threatened: 'Trust erodes.' } },
    { type: 'sub_shift_list', data: {} },
  ],
}
const shiftTwo = { id: 'kt-2', domain_id: 'society', slug: 'synthetic-belonging', name: 'Synthetic Belonging', subtitle: 'Presence changes.', read_time: '4 min read' }
const subs = Array.from({ length: 5 }, (_, i) => ({
  id: `st-${i + 1}`, key_trend_id: 'kt-1', domain_id: 'society', slug: `sub-${i + 1}`,
  name: `Sub Shift ${i + 1}`, description: `Sub shift ${i + 1} description`,
}))
const shiftDetail = { updated: index.updated, domain: domains[0], shift, siblings: [shift, shiftTwo], sub_shifts: subs }
const domainDetail = {
  updated: index.updated,
  domain: domains[0],
  key_shifts: [shift, ...societyShifts.slice(1)].map((s) => ({ ...s, modules: undefined })),
  insights: [],
}
const subDetail = {
  updated: index.updated,
  domain: domains[0],
  parent_shift: { ...shift, modules: undefined, sub_shift_count: 5 },
  sub_shift: {
    ...subs[0],
    modules: [
      { type: 'lede', data: { text: 'Full sub-shift context.' } },
      { type: 'evidence', data: { items: [{ thinker: 'Researcher', text: 'Verified evidence.', source: 'Study', url: 'https://example.com/study' }] } },
    ],
  },
  siblings: subs,
}

async function mockMap(page, failure, stagger = false) {
  await page.route('**/api/v1/map**', async (route) => {
    if (failure) {
      await route.fulfill({ status: failure, contentType: 'application/json', body: JSON.stringify({ error: { code: failure === 503 ? 'unavailable' : 'internal_error' } }) })
      return
    }
    const pathname = new URL(route.request().url()).pathname
    const data = pathname === '/api/v1/map' ? index
      : pathname === '/api/v1/map/society' ? domainDetail
        : pathname === '/api/v1/map/society/trust-machines' ? shiftDetail
          : pathname === '/api/v1/map/society/trust-machines/sub-1' ? subDetail
            : null
    // A page is assembled from two requests and the index always wins, because
    // it is one document for the whole site and the fragment is per-route. That
    // ordering is what produced the worst layout shift on the site, so `stagger`
    // makes it explicit rather than leaving it to whatever the network does on
    // the day: fulfilment is not throttled by CDP, so without this the two land
    // in the same frame and the race the test exists for never happens.
    if (stagger) await new Promise((r) => setTimeout(r, pathname === '/api/v1/map' ? 100 : 600))
    await route.fulfill({ status: data ? 200 : 404, contentType: 'application/json', body: JSON.stringify(data || { error: { code: 'not_found' } }) })
  })
}

export { domains, index, shift, shiftTwo, subs, shiftDetail, domainDetail, subDetail, mockMap }
