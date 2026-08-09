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
/*
 * `id` is the database id and the URL segment, so Organisations keeps its s.
 * `name` is what a reader sees, and the content spec is US spelling throughout.
 * The two disagreeing is deliberate: renaming the id would 404 every published
 * link and strand every `shift_refs` row.
 *
 * `intro` is the "what's shifting right now" paragraph. It is authored in the
 * pipeline (`mapgen/config.py`) and served on the per-sphere fragment; this copy
 * is only the fallback for a cold or failed fetch, and is kept identical.
 */
export const DECK = [
  {
    id: 'society', name: 'Society', num: '01', horizon: '2028',
    blurb: 'Belonging, trust and truth when anything can be generated and nobody has to be present.',
    intro: 'Reasoning itself is thinning. As AI mediates more of what people read, judge and decide, the shared capacity democracy assumes is quietly falling — and nobody is measuring it.',
  },
  {
    id: 'economy', name: 'Economy', num: '02', horizon: '2027',
    blurb: 'Where value, work and money move once capability stops being scarce.',
    intro: 'Capability has stopped being scarce and verification has started. Value is migrating from producing work to proving a human judged it — and pricing is following.',
  },
  {
    id: 'organizations', name: 'Organizations', num: '03', horizon: '2026',
    blurb: 'How institutions decide, hire and defend themselves when speed is free.',
    intro: 'Speed is free, so deliberation is the differentiator. The bottleneck has moved from making the work to finding anyone qualified to review it.',
  },
  {
    id: 'consumers', name: 'Consumers', num: '04', horizon: '2026',
    blurb: 'Identity, taste and desire in a market where software does the shopping.',
    intro: 'Agents are entering the purchase. Brands are suddenly selling to software with a human sponsor, and the impulse aisle has no surface left to interrupt.',
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
export const TRENDWATCHING_URL = `${ABOUT_URL}#trendwatching`
export const CONTACT_URL = 'mailto:hello@trendwatching.com'
export const WHATSAPP_URL = `${ABOUT_URL}#whatsapp`

/*
 * The nav, exactly as the delivered build has it: six rows, each with a
 * right-aligned descriptor.
 *
 * A Miro sticky asked for the descriptors to be dropped; the later design build
 * still renders them, so they stay. They also earn their place — the shift count
 * is the only number on the site that tells a first-time reader how much is
 * behind the deck.
 *
 * `meta: null` on Shifts means "fill this in from the published totals". The
 * design writes the literal "52 key shifts"; a live site that says 52 while
 * serving 58 is worse than one that counts, so the Header substitutes the real
 * number and falls back to the plain label until the index has loaded.
 *
 * Every row but Shifts resolves to the internal /about page, which carries all
 * five sections. The external HubSpot page remains the destination only for the
 * deep links the About copy itself makes.
 */
export const MENU_LINKS = [
  { label: 'Shifts', meta: null, href: '/', internal: true },
  { label: 'Methodology', meta: 'How we track', href: '/about#methodology', internal: true },
  { label: 'Subscribe', meta: 'One shift a day', href: '/about#subscribe', internal: true },
  { label: 'Services', meta: 'Reports & workshops', href: '/about#services', internal: true },
  { label: 'TrendWatching', meta: '20+ years', href: '/about#trendwatching', internal: true },
  { label: 'About', meta: 'Why & who & what', href: '/about', internal: true },
]
