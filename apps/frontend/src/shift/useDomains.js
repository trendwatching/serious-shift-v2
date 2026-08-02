/** Route-scoped map data → the view-model consumed by the UI. */
import { useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useData } from '../hooks/useData'
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
      const domainRef = { id, name: first(live?.name, deck.name), grad: theme.grad, dot: theme.dot }

      let rows = []
      if (detail?.domain?.id === id && Array.isArray(detail.key_shifts)) {
        rows = detail.key_shifts
      } else if (detail?.domain?.id === id && detail.shift) {
        rows = [{ ...detail.shift, sub_trends: detail.sub_shifts || [] }]
      } else if (detail?.domain?.id === id && detail.parent_shift) {
        const siblings = detail.siblings || []
        const subRows = siblings.map((sibling) => (
          sibling.id === detail.sub_shift?.id ? detail.sub_shift : sibling
        ))
        rows = [{ ...detail.parent_shift, sub_trends: subRows }]
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
        blurb: first(live?.short_description, deck.blurb) || '',
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
  const retry = () => {
    indexRequest.retry()
    if (detailEnabled) detailRequest.retry()
  }

  return { domains, meta, loading, unavailable, notFound, error, retry }
}

export function useResolved({ domainSlug, ktSlug, subSlug } = {}) {
  const state = useDomains()
  const domain = state.domains.find((item) => item.slug === domainSlug || item.id === domainSlug)
  const shift = ktSlug ? domain?.keyShifts.find((item) => item.slug === ktSlug) : undefined
  const sub = subSlug ? shift?.subshifts.find((item) => item.slug === subSlug) : undefined
  return { ...state, domain, shift, sub }
}
