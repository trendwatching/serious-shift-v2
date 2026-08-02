export const indexFixture = {
  updated: '2026-08-02',
  totals: { domains: 1, key_shifts: 2, sub_shifts: 5 },
  domains: [{ id: 'society', name: 'Society', horizon: '2028', short_description: 'Society shifts', key_shift_count: 2 }],
}

export const shiftOne = {
  id: 'kt-1', domain_id: 'society', slug: 'trust-machines', name: 'Trust Machines',
  subtitle: 'Verification becomes a product.', read_time: '5 min read', modules: [],
}
export const shiftTwo = {
  id: 'kt-2', domain_id: 'society', slug: 'synthetic-belonging', name: 'Synthetic Belonging',
  subtitle: 'New forms of presence.', read_time: '4 min read', modules: [],
}
export const subs = Array.from({ length: 5 }, (_, index) => ({
  id: `st-${index + 1}`,
  key_trend_id: 'kt-1',
  domain_id: 'society',
  slug: `sub-${index + 1}`,
  name: `Sub Shift ${index + 1}`,
  description: `Sub shift ${index + 1} description`,
  modules: index === 0 ? [{ type: 'lede', data: { text: 'Full sub-shift context.' } }] : undefined,
}))

export const shiftFixture = {
  updated: '2026-08-02',
  domain: indexFixture.domains[0],
  shift: shiftOne,
  siblings: [shiftOne, shiftTwo],
  sub_shifts: subs.map(({ modules, ...summary }) => summary),
}

export const subFixture = {
  updated: '2026-08-02',
  domain: indexFixture.domains[0],
  parent_shift: { ...shiftOne, sub_shift_count: 5 },
  sub_shift: subs[0],
  siblings: subs.map(({ modules, ...summary }) => summary),
}

export const response = (data, status = 200) => Promise.resolve({
  ok: status >= 200 && status < 300,
  status,
  json: () => Promise.resolve(data),
})
