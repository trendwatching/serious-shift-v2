/**
 * Per-domain identity, verbatim from the delivered build's DECK table.
 *
 * `crumb` is the breadcrumb "you are here" fill and `eyebrow` the colour of a
 * label set on the domain's own gradient — white for Organizations, because
 * brand yellow on olive is barely a colour change. Both are literals rather
 * than `var(--a-*)` because the chrome that uses them renders above the element
 * that sets `data-domain`.
 */
export const DOMAIN_ORDER = ['society', 'economy', 'consumers', 'organizations']

/**
 * Is this URL segment one of the four spheres?
 *
 * Needed since the `/map` prefix went: `/:domainSlug` now matches ANY single
 * segment, so `/not-real` used to fall through to the 404 and instead started
 * rendering the sphere page's loading state, then its "unavailable" error —
 * the client disagreeing with the server, which correctly 404s an unknown path.
 * Checked against the local list rather than the fetched one so an unknown path
 * costs no request at all.
 */
export const isSphere = (slug) => DOMAIN_ORDER.includes(String(slug ?? ''))

export const DOMAIN_THEME = {
  society: {
    num: '01', dot: '#ED026B', crumb: '#7A0038', eyebrow: '#FDFF85',
    grad: 'linear-gradient(135deg, #FF0B85 0%, #ED026B 46%, #9A0046 100%)',
  },
  economy: {
    num: '02', dot: '#0A7FDA', crumb: '#023F6C', eyebrow: '#FDFF85',
    grad: 'linear-gradient(135deg, #0F91EE 0%, #0A7FDA 46%, #04528B 100%)',
  },
  consumers: {
    num: '03', dot: '#E74707', crumb: '#6E2202', eyebrow: '#FDFF85',
    grad: 'linear-gradient(135deg, #F65510 0%, #E74707 46%, #922E03 100%)',
  },
  organizations: {
    num: '04', dot: '#9A9A43', crumb: '#41500A', eyebrow: '#FFFFFF',
    grad: 'linear-gradient(135deg, #ADB03A 0%, #9A9A43 42%, #5F6E13 100%)',
  },
}

export const themeFor = (id) => DOMAIN_THEME[id] || DOMAIN_THEME.society

export const pad2 = (n) => String(n).padStart(2, '0')

/**
 * URL-safe slug. Must stay byte-identical to the pipeline's `url_slug`
 * (apps/pipeline/serious_shift_pipeline/core/text.py) or deep links 404 —
 * packages/contracts/slug_fixtures.json pins both sides.
 *
 * Punctuation is dropped, not turned into a separator, so "can't" closes up to
 * "cant" rather than splitting into "can-t".
 */
export const slugify = (s) =>
  String(s || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_\s-]/gu, '')
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')

/** "6 min read" from prose, when the source didn't author a read time. */
export const readTimeOf = (...parts) => {
  const words = parts.filter(Boolean).join(' ').trim().split(/\s+/).length
  return `${Math.max(1, Math.round(words / 200))} min read`
}

/** Strip whatever quoting a title arrived with. The build's data carries curly
 *  quotes in the string itself; ours does not, so titles are quoted at the one
 *  or two call sites that want them and left bare everywhere else. */
export const unquote = (s) => String(s ?? '').trim().replace(/^[“”"'\s]+|[“”"'\s]+$/g, '').trim()

/**
 * A trend name as the house style writes it: “DELEGATED DISCOVERY”.
 *
 * THE CAPS ARE CHARACTERS, not `text-transform`. They used to be CSS on the page
 * and real only in the `<title>`, which meant the page and the link preview
 * disagreed for anything that reads the DOM rather than the render: a
 * copy-paste, a screen reader, a crawler, an export. The name is uppercase in
 * the house style, so it is uppercase in the markup.
 *
 * This must stay byte-identical to `trend_title` in apps/backend/src/seo.rs.
 * The backend renders the title into the shell and the client re-stamps it after
 * hydration; if they disagree the tab text visibly changes a beat after load.
 *
 * It strips before it quotes: the naming prompt shows its examples already
 * quoted (packages/prompts/map/key_trends.txt), so a name occasionally arrives
 * carrying a pair of its own and `““NAME””` is one edit away.
 */
export const quoted = (s) => {
  const t = unquote(s)
  return t ? `“${t.toUpperCase()}”` : ''
}

/** The same string. Kept as its own name because the meta layer reads better
 *  saying what it wants, and it is the one the Rust twin is pinned to. */
export const trendTitle = quoted
