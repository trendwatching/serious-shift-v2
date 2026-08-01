/**
 * theme.js — the single source of truth for per-domain identity.
 *
 * Gradient + dot are presentation, so they live here rather than in the DB.
 * `num` is the display order shown as "01 / 04" on the deck panels.
 * Domain ids match the backend map document exactly.
 */
export const DOMAIN_ORDER = ['society', 'economy', 'organisations', 'consumers']

export const DOMAIN_THEME = {
  society:       { num: '01', dot: '#ED026B', grad: 'var(--grad-society)' },
  economy:       { num: '02', dot: '#0A7FDA', grad: 'var(--grad-economy)' },
  organisations: { num: '03', dot: '#9A9A43', grad: 'var(--grad-organisations)' },
  consumers:     { num: '04', dot: '#E74707', grad: 'var(--grad-consumers)' },
}

export const themeFor = (id) => DOMAIN_THEME[id] || DOMAIN_THEME.society

export const pad2 = (n) => String(n).padStart(2, '0')

/**
 * Shift and sub-shift names are always shown in caps inside double quotation
 * marks — a naming rule from the content spec, not decoration.
 *
 * The casing is CSS (`.t-title`); the quotes have to be characters. Sources
 * disagree about whether they are already there — the pipeline stores plain
 * names, the authored design content includes curly quotes — so strip whatever
 * is present and apply one consistent pair.
 */
export const quoteTitle = (s) => {
  const t = String(s ?? '').trim().replace(/^[“”"'\s]+|[“”"'\s]+$/g, '').trim()
  return t ? `“${t}”` : ''
}

/**
 * URL-safe slug. Must stay byte-identical to the pipeline's `url_slug`
 * (apps/pipeline/serious_shift_pipeline/core/text.py) or deep links 404 —
 * packages/contracts/slug_fixtures.json pins both sides.
 *
 * Punctuation is dropped, not turned into a separator, so "can't" closes up to
 * "cant" rather than splitting into "can-t". The previous [^a-z0-9] rule split
 * on apostrophes and stripped non-ASCII letters, disagreeing with the backend on
 * every title containing one.
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
