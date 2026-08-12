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
 * `id` is the database id and the URL segment, US-spelled to match the DB and
 * every published URL since the 20260809 sphere-id migration ('organizations',
 * not 'organisations'). `name` is what a reader sees; same spelling.
 *
 * `intro` is the "what's shifting right now" paragraph. It is authored in the
 * pipeline (`mapgen/config.py`) and served on the per-sphere fragment; this copy
 * is only the fallback for a cold or failed fetch, and is kept identical.
 */
export const DECK = [
  {
    id: 'society', name: 'Society', num: '01', horizon: '2028',
    blurb: 'Belonging, trust and truth when anything can be generated and nobody has to be present.',
    intro: 'As AI moves deeper into everyday life, institutions, relationships, identities and power structures begin to shift, especially once intelligent machines become social participants themselves.',
  },
  {
    id: 'economy', name: 'Economy', num: '02', horizon: '2027',
    blurb: 'Where value, work and money move once capability stops being scarce.',
    intro: 'Intelligence is becoming an economic resource in its own right, transforming how value is created, who or what produces it, who owns it and how wealth is distributed.',
  },
  {
    id: 'consumers', name: 'Consumers', num: '03', horizon: '2026',
    blurb: 'Identity, taste and desire in a market where software does the shopping.',
    intro: 'What people need may remain remarkably constant. AI radically changes how those needs are understood and fulfilled, and increasingly acts, chooses and buys on people’s behalf.',
  },
  {
    id: 'organizations', name: 'Organizations', num: '04', horizon: '2026',
    blurb: 'How institutions decide, hire and defend themselves when speed is free.',
    intro: 'From individual tasks to entire workflows, AI is rebuilding the organization around autonomy, changing how companies operate, innovate, compete and ultimately what a company even is.',
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
// Direct group-invite link, per the 12 Aug 2026 Miro review — the pill used to
// point at the HubSpot about page's #whatsapp anchor, one hop short.
export const WHATSAPP_URL = 'https://chat.whatsapp.com/EFptoaGlMau7sNog3onRP2?s=cl&p=i&ilr=0'

/*
 * The nav: five rows, labels only. The 5 Aug 2026 Miro review ("no need for all
 * this info!") dropped the right-aligned descriptors the delivered build drew;
 * that supersedes the earlier decision to keep them. The Shifts row went in the
 * 13 Aug pass: it pointed at `/`, which the logo already covers and which the
 * router's same-route guard turns into a no-op from the home deck — a nav item
 * that visibly did nothing.
 *
 * Every row resolves to the internal /about page, which carries all five
 * sections. The external HubSpot page remains the destination only for the
 * deep links the About copy itself makes.
 */
export const MENU_LINKS = [
  { label: 'Methodology', href: '/about#methodology', internal: true },
  { label: 'Subscribe', href: '/about#subscribe', internal: true },
  { label: 'Services', href: '/about#services', internal: true },
  { label: 'TrendWatching', href: '/about#trendwatching', internal: true },
  { label: 'About', href: '/about', internal: true },
]
