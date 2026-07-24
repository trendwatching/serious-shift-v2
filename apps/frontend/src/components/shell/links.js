/**
 * Shared site-nav + external destinations.
 *
 * The primary nav headers link to the public about page; "Shifts" is the in-app
 * home (the map). Until seriousshift.ai/about ships, we point at the live about
 * page it redirects to (TrendWatching's HubSpot). Each section links to its
 * anchor id, all of which exist on that page: #methodology, #subscribe,
 * #services, #trendwatching.
 */

// Live about page (what seriousshift.ai/about redirects to for now).
export const ABOUT_URL = 'https://info.trendwatching.com/serious-shift/about'

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
