/**
 * Shared site-nav + external destinations.
 *
 * Per the redesign plan: internal (data-backed) routes stay in-app; the rest
 * link out to TrendWatching / Serious Shift properties. Methodology & Community
 * from the Figma nav are intentionally omitted until they have real pages.
 */

export const SUBSCRIBE_URL =
  'https://chat.whatsapp.com/EFptoaGlMau7sNog3onRP2?mode=gi_t'
export const ABOUT_URL =
  'https://info.trendwatching.com/serious-shift/about'
export const WORKSHOPS_URL = 'https://trendwatching.com/services'
export const TRENDWATCHING_URL = 'https://trendwatching.com'
export const CONTACT_URL = 'mailto:hello@trendwatching.com'

// Primary nav — order matches the Figma. `to` = internal route, `href` = external.
export const NAV_LINKS = [
  { label: 'Shifts',        to: '/' },
  { label: 'Thinkers',      to: '/map/thinkers' },
  { label: 'Workshops',     href: WORKSHOPS_URL },
  { label: 'TrendWatching', href: TRENDWATCHING_URL },
  { label: 'About',         href: ABOUT_URL },
  { label: 'Contact Us',    href: CONTACT_URL },
]

// Footer link column ("Serious Shi(f)t" explainer prompts).
export const FOOTER_LINKS = [
  { label: 'Who is it for?',   href: ABOUT_URL },
  { label: 'Who am I reading?', to: '/map/thinkers' },
  { label: "What else you'd like?", href: CONTACT_URL },
]
