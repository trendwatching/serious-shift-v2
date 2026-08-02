/**
 * site.js — static site configuration: the four domains and the external links
 * in the chrome. Editorial content comes from the route-scoped `/api/v1/map/*`
 * documents; the deprecated full-map endpoint is never fetched by the client.
 *
 * This replaced a 36 KB `content.js` that also carried a full authored copy of
 * the editorial content as an offline fallback. That fallback shipped to every
 * visitor to cover a case that should be near-zero-frequency, and — worse — it
 * rendered months-old prose as if it were the current week with no indication
 * anything was wrong. When the map is unavailable the UI now says so (see
 * `useDomains`), which is the honest failure mode.
 */

/** The four domains, in reading order. Names/blurbs are overridden by the live
 *  document when it has them; these are the fallback and the deck ordering. */
export const DECK = [
  {
    id: 'society', name: 'Society', num: '01', horizon: '2028',
    blurb: 'Belonging, trust and truth when anything can be generated and nobody has to be present.',
  },
  {
    id: 'economy', name: 'Economy', num: '02', horizon: '2027',
    blurb: 'Where value, work and money move once capability stops being scarce.',
  },
  {
    id: 'organisations', name: 'Organisations', num: '03', horizon: '2026',
    blurb: 'How institutions decide, hire and defend themselves when speed is free.',
  },
  {
    id: 'consumers', name: 'Consumers', num: '04', horizon: '2026',
    blurb: 'Identity, taste and desire in a market where software does the shopping.',
  },
]

/** Client logos for the footer marquee. */
export const LOGOS = [
  'itc-hotels', 'sephora', 'google', 'didi', 'blink-digital',
  'starbucks', 'mastercard', 'cg', 'hero', 'dentsu',
].map((n) => `/shift/logo-${n}.jpg`)

/* ── External destinations ───────────────────────────────────────────────── */

// Live about page (what seriousshift.ai/about redirects to for now). Each
// section below is an anchor that exists on that page.
export const ABOUT_URL = 'https://info.trendwatching.com/serious-shift/about'
export const METHODOLOGY_URL = `${ABOUT_URL}#methodology`
export const SUBSCRIBE_URL = `${ABOUT_URL}#subscribe`
export const SERVICES_URL = `${ABOUT_URL}#services`
export const TRENDWATCHING_URL = `${ABOUT_URL}#trendwatching`
export const CONTACT_URL = 'mailto:hello@trendwatching.com'
export const LINKEDIN_URL = 'https://www.linkedin.com/company/trendwatching-com/'

// The later Miro navigation is authoritative. Keep this list exact: no dormant
// Saved/Room destinations and no unverified social stand-ins.
export const MENU_LINKS = [
  { label: 'Shifts', href: '/', internal: true },
  { label: 'Methodology', href: METHODOLOGY_URL },
  { label: 'Subscribe', href: SUBSCRIBE_URL },
  { label: 'Services', href: SERVICES_URL },
  { label: 'TrendWatching', href: TRENDWATCHING_URL },
  { label: 'About', href: ABOUT_URL },
]

export const FOOTER_LINKS = [
  { label: 'Who is it for?', href: ABOUT_URL },
  { label: 'Who am I reading?', href: METHODOLOGY_URL },
  { label: 'What else you’d like?', href: CONTACT_URL },
]

export const SOCIALS = [
  { label: 'LinkedIn', mark: 'in', href: LINKEDIN_URL },
]
