/**
 * Shared site-nav + external destinations.
 *
 * The primary nav headers link to sections of the public about page at
 * seriousshift.ai; "Shifts" is the in-app home (the map). Edit the base URL or
 * a section anchor here and it updates the desktop nav, mobile nav, the
 * Subscribe CTA, and the footer together.
 */

export const SITE_URL = 'https://www.seriousshift.ai'
export const ABOUT_URL = `${SITE_URL}/about`

// About-page section anchors.
export const METHODOLOGY_URL = `${ABOUT_URL}#methodology`
export const SUBSCRIBE_URL = `${ABOUT_URL}#subscribe`
export const SERVICES_URL = `${ABOUT_URL}#services`
export const TRENDWATCHING_URL = `${ABOUT_URL}#trendwatching`

export const CONTACT_URL = 'mailto:hello@trendwatching.com'

// Primary nav — matches the approved navbar spec.
// `to` = in-app route (Shifts = home); `href` = external about-page section.
export const NAV_LINKS = [
  { label: 'Shifts',        to: '/' },
  { label: 'Methodology',   href: METHODOLOGY_URL },
  { label: 'Subscribe',     href: SUBSCRIBE_URL },
  { label: 'Services',      href: SERVICES_URL },
  { label: 'TrendWatching', href: TRENDWATCHING_URL },
  { label: 'About',         href: ABOUT_URL },
]

// Footer link column ("Serious Shi(f)t" explainer prompts).
export const FOOTER_LINKS = [
  { label: 'Who is it for?',   href: ABOUT_URL },
  { label: 'Who am I reading?', to: '/map/thinkers' },
  { label: "What else you'd like?", href: CONTACT_URL },
]
