/** Route-scoped map data → the view-model consumed by the UI. */
import { useMemo } from 'react'
import { useLocation } from './router'
import { useData } from './useData'
import { DECK } from './site'
import { DOMAIN_ORDER, themeFor, pad2, slugify, readTimeOf } from './theme'

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

const SUB_HERO_ART = {
  'capacity-collapse': '/shift/hero-capacity-collapse-graded.jpg',
}

function toSubShift(src, i) {
  const title = src.name || ''
  const routeSlug = typeof src.slug === 'string' ? src.slug.split('/').filter(Boolean).at(-1) : ''
  return {
    id: first(src.id, `sub-${i}`),
    num: pad2(i + 1),
    slug: first(routeSlug, slugify(title)),
    title,
    context: src.context,
    dek: src.description || src.subtitle || '',
    modules: nonEmpty(src.modules) || projectStModules(src),
    heroImage: src.hero_image || SUB_HERO_ART[first(routeSlug, slugify(title))] || null,
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
    modules: nonEmpty(src.modules) || projectKtModules(src),
    // Same-origin path served by the backend once art exists for this shift.
    // Absent is the normal case and the hero falls back to its gradient, which
    // is a finished design rather than a placeholder.
    heroImage: src.hero_image || HERO_ART[src.slug] || null,
    subshifts: subs.map((s, k) => toSubShift(s, k)),
  }
}

function routeSegments(pathname) {
  if (!pathname.startsWith('/map/')) return []
  return pathname.slice('/map/'.length).split('/').filter(Boolean).slice(0, 3)
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
    const order = summaries.length ? summaries.map((domain) => domain.id) : DOMAIN_ORDER

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
