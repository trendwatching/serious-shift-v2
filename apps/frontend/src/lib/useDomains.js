/** Route-scoped map data → the view-model consumed by the UI. */
import CONTRACT from '../../../../packages/contracts/shift_modules.json'
import HERO_GENERATED from './heroes.json'
import SUB_GENERATED from './sub-art.json'
import HERO_WIDE from './heroes-wide.json'
import { useMemo } from 'react'
import { useLocation } from './router'
import { useData } from './useData'
import { DECK } from './site'
import { DOMAIN_ORDER, isSphere, themeFor, pad2, slugify, readTimeOf } from './theme'

const first = (...v) => v.find((x) => x !== undefined && x !== null && x !== '')
const nonEmpty = (v) => (Array.isArray(v) && v.length ? v : null)

function isoWeek(dateStr) {
  if (!dateStr) return null
  const d = new Date(`${dateStr}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return null
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
  const jan1 = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil(((d - jan1) / 86400000 + 1) / 7)
}

function projectKtModules(row) {
  const hero = row.hero_stat || {}
  const out = []
  const dek = first(row.subtitle, row.description)
  if (dek) out.push({ type: 'dek', data: { text: dek } })
  if (hero.value) {
    out.push({
      type: 'stat_band',
      data: { value: hero.value, text: row.stat_text || '', source: hero.source || hero.thinker || '' },
    })
  }
  out.push({ type: 'sub_shift_list', data: {} })
  return out
}

/**
 * Reading order, straight from the contract both the pipeline and the backend
 * obey — so there is one list, not three that can drift apart.
 *
 * Sorting again at render is not redundant. The published document was composed
 * by whatever order the contract had at export time, so an ordering change only
 * reaches readers after a full regeneration; sorting here means the page reads
 * correctly the moment the contract changes. Unknown types keep their relative
 * position at the end rather than being dropped — a module the front end has
 * not heard of is the renderer's problem, not the sorter's.
 */
const ORDER = {
  key_shift: CONTRACT.order.key_trend,
  sub_shift: CONTRACT.order.sub_trend,
}

function inReadingOrder(modules, scope) {
  const order = ORDER[scope] || []
  const rank = (m) => {
    const at = order.indexOf(m?.type)
    return at === -1 ? order.length : at
  }
  return [...modules].map((m, i) => [m, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([m]) => m)
}

function projectStModules(row) {
  const text = first(row.description, row.subtitle)
  return text ? [{ type: 'lede', data: { text } }] : []
}

/**
 * Hand-made hero art, by slug.
 *
 * Two shifts were art-directed by hand for the design build. Every other shift
 * gets its art from the pipeline (`hero_image` on the row), and these two are
 * the quality bar that generation is judged against — so they are pinned here
 * rather than overwritten by a generated substitute.
 */
const HERO_ART = {
  'cognitive-erosion': '/shift/hero-cognitive-erosion.jpg',
}

/**
 * Generated poster art, one per published key shift, keyed by slug.
 *
 * It is a manifest rather than a path template on purpose: a shift published
 * after the last `npm run heroes` has no file, and asking for one would give it
 * a broken image instead of the gradient hero, which is itself a finished
 * design. See scripts/generate-heroes.mjs.
 */
const HERO_GEN = HERO_GENERATED

const SUB_HERO_ART = {
  'capacity-collapse': '/shift/hero-capacity-collapse-graded.jpg',
}

/**
 * Generated sub-shift tile art, keyed `<key shift>/<sub-shift>`.
 *
 * The composite key, not the sub's own slug: nothing guarantees a sub-shift slug
 * is unique across all 58 key shifts, and two shifts quietly sharing one picture
 * is a bug that only surfaces in a screenshot months later.
 *
 * Tile only. It is a close crop, sized to read in a 152px box, and the page it
 * opens wants the opposite — both hand-made assets show a sub-shift under the
 * same wide scene as its parent, differently graded. So a sub-shift page inherits
 * the parent's poster and the tile carries the detail.
 */
const SUB_GEN = SUB_GENERATED

function toSubShift(src, i, parentSlug) {
  const title = src.name || ''
  const routeSlug = typeof src.slug === 'string' ? src.slug.split('/').filter(Boolean).at(-1) : ''
  const slug = first(routeSlug, slugify(title))
  return {
    id: first(src.id, `sub-${i}`),
    num: pad2(i + 1),
    slug,
    title,
    context: src.context,
    dek: src.description || src.subtitle || '',
    modules: inReadingOrder(nonEmpty(src.modules) || projectStModules(src), 'sub_shift'),
    heroImage: src.hero_image || SUB_HERO_ART[slug] || HERO_GEN[parentSlug] || null,
    // Only the GENERATED poster has a landscape twin. The pipeline's own art and
    // the two hand-made JPGs do not, so the wide slot stays null and the CSS
    // falls back to the portrait rather than 404ing on a file that was never
    // drawn. Note a sub-shift page inherits its PARENT's poster — the 640px
    // fragment is tile art and stays square.
    heroImageWide: !src.hero_image && !SUB_HERO_ART[slug] ? HERO_WIDE[parentSlug] || null : null,
    tileImage: SUB_GEN[`${parentSlug}/${slug}`] || null,
  }
}

function toShift(src, i, domain) {
  const title = src.name || ''
  const dek = first(src.subtitle, src.description) || ''
  const subs = Array.isArray(src.sub_trends) ? src.sub_trends : []

  return {
    id: first(src.id, `kt-${i}`),
    num: pad2(i + 1),
    slug: first(src.slug, slugify(title)),
    domain,
    kicker: first(src.kicker, `Shift ${pad2(i + 1)}`),
    title,
    dek,
    velocity: src.velocity,
    read: first(src.read_time, readTimeOf(dek)),
    modules: inReadingOrder(nonEmpty(src.modules) || projectKtModules(src), 'key_shift'),
    // Same-origin path served by the backend once art exists for this shift.
    // Absent is the normal case and the hero falls back to its gradient, which
    // is a finished design rather than a placeholder.
    heroImage: src.hero_image || HERO_ART[src.slug] || HERO_GEN[src.slug] || null,
    heroImageWide: !src.hero_image && !HERO_ART[src.slug] ? HERO_WIDE[src.slug] || null : null,
    subshifts: subs.map((s, k) => toSubShift(s, k, first(src.slug, slugify(title)))),
  }
}

/**
 * Reading order for the deck, and therefore for the sphere badges that jump
 * into it.
 *
 * Fixed information architecture, like the four names: Society, Economy,
 * Organizations, Consumers — numbered 01 to 04 by the design. The published
 * document lists them in the pipeline's own order (society, economy, consumers,
 * organizations), and following that put the panels in one order while
 * HomePanel drew its badges in another: the Consumers badge opened
 * Organizations, the Organizations badge opened Consumers, and the deck counted
 * 01, 02, 04, 03.
 *
 * A sphere the document carries but this list does not know about is appended
 * rather than dropped, so a new one appears instead of vanishing.
 */
export function orderDomains(published = []) {
  if (!published.length) return [...DOMAIN_ORDER]
  return [
    ...DOMAIN_ORDER.filter((id) => published.includes(id)),
    ...published.filter((id) => !DOMAIN_ORDER.includes(id)),
  ]
}

function routeSegments(pathname) {
  // The `/map` prefix is gone: a sphere is `/consumers`, a shift
  // `/consumers/delegated-discovery`. That means `/:domainSlug` matches ANY
  // single segment, so the first one is checked against the local sphere list
  // before anything is fetched — otherwise `/about`, `/robots.txt` and every
  // typo would each cost a fragment request that can only 404.
  const segments = pathname.split('/').filter(Boolean).slice(0, 3)
  if (!segments.length || !isSphere(segments[0])) return []
  return segments
}

export function useDomains() {
  const { pathname } = useLocation()
  const segments = useMemo(() => routeSegments(pathname), [pathname])
  const detailEnabled = segments.length > 0
  const detailResource = `/api/v1/map/${segments.join('/')}`

  const indexRequest = useData('/api/v1/map')
  const detailRequest = useData(detailResource, { enabled: detailEnabled })
  const index = indexRequest.data
  const detail = detailRequest.data

  const domains = useMemo(() => {
    const summaries = index?.domains || []
    const order = orderDomains(summaries.map((domain) => domain.id))
    return order.map((id) => {
      const deck = DECK.find((domain) => domain.id === id) || {}
      const summary = summaries.find((domain) => domain.id === id)
      const current = detail?.domain?.id === id ? detail.domain : null
      const live = current || summary
      const theme = themeFor(id)
      // The four domain names are fixed information architecture, not editorial
      // output, so the local list wins over the document. That is what keeps the
      // US spelling ("Organizations") correct on a publication that predates the
      // rename, instead of waiting a week for the next synthesize run.
      const domainRef = { id, name: first(deck.name, live?.name), grad: theme.grad, dot: theme.dot }

      let rows = []
      if (detail?.domain?.id === id && Array.isArray(detail.key_shifts)) {
        rows = detail.key_shifts
      } else if (detail?.domain?.id === id && detail.shift) {
        const current = { ...detail.shift, sub_trends: detail.sub_shifts || [] }
        rows = (detail.siblings || []).map((sibling) => (
          sibling.id === detail.shift.id ? current : sibling
        ))
        if (!rows.length) rows = [current]
      } else if (detail?.domain?.id === id && detail.parent_shift) {
        const siblings = detail.siblings || []
        const subRows = siblings.map((sibling) => (
          sibling.id === detail.sub_shift?.id ? detail.sub_shift : sibling
        ))
        rows = [{ ...detail.parent_shift, sub_trends: subRows }]
      } else if (Array.isArray(summary?.key_shifts)) {
        rows = summary.key_shifts
      }

      const keyShifts = rows.map((row, i) => toShift(row, i, domainRef))
      return {
        id,
        slug: id,
        name: domainRef.name || id,
        num: theme.num,
        grad: theme.grad,
        dot: theme.dot,
        horizon: first(live?.horizon, deck.horizon) || '',
        // Local-first, like `name`. Both are fixed information architecture
        // authored in mapgen/config.py, not model output, so the published
        // document is a mirror of this list rather than its source — and when
        // the two disagree the published one is simply older. This is what puts
        // the design's own line on the page today instead of next Monday.
        blurb: first(deck.blurb, live?.short_description) || '',
        // The "what's shifting right now" paragraph. Served only on the
        // per-sphere fragment, so on the deck (which reads the index) this
        // falls back to the authored copy in site.js.
        intro: first(live?.intro, deck.intro) || '',
        crumb: theme.crumb,
        eyebrow: theme.eyebrow,
        count: first(live?.key_shift_count, keyShifts.length),
        keyShifts,
        insights: (detail?.domain?.id === id ? detail.insights || [] : [])
          .filter((insight) => insight?.name && insight?.description)
          .map((insight) => ({ id: insight.id, name: insight.name, description: insight.description })),
      }
    })
  }, [detail, index])

  const meta = useMemo(() => {
    const updated = index?.updated || null
    return {
      updated,
      week: isoWeek(updated),
      domainCount: index?.totals?.domains ?? domains.length,
      shiftCount: index?.totals?.key_shifts ?? 0,
    }
  }, [domains.length, index])

  const loading = indexRequest.loading || (detailEnabled && detailRequest.loading)
  const error = indexRequest.error || (detailEnabled ? detailRequest.error : null)
  const notFound = error?.status === 404
  const unavailable = !loading && !notFound && (!index || (detailEnabled && !detail && !!error))
  const stale = !unavailable && !!error && !!index
  const retry = () => {
    indexRequest.retry()
    if (detailEnabled) detailRequest.retry()
  }

  return { domains, meta, loading, unavailable, stale, notFound, error, retry }
}

export function useResolved({ domainSlug, ktSlug, subSlug } = {}) {
  const state = useDomains()
  const domain = state.domains.find((item) => item.slug === domainSlug || item.id === domainSlug)
  const shift = ktSlug ? domain?.keyShifts.find((item) => item.slug === ktSlug) : undefined
  const sub = subSlug ? shift?.subshifts.find((item) => item.slug === subSlug) : undefined
  const shiftIndex = shift ? domain?.keyShifts.findIndex((item) => item.id === shift.id) : -1
  const subIndex = sub ? shift?.subshifts.findIndex((item) => item.id === sub.id) : -1
  return {
    ...state,
    domain,
    shift,
    sub,
    shiftSiblings: shiftIndex >= 0 ? {
      previous: domain.keyShifts[shiftIndex - 1] || null,
      next: domain.keyShifts[shiftIndex + 1] || null,
    } : { previous: null, next: null },
    subSiblings: subIndex >= 0 ? {
      previous: shift.subshifts[subIndex - 1] || null,
      next: shift.subshifts[subIndex + 1] || null,
    } : { previous: null, next: null },
  }
}
