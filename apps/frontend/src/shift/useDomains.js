/**
 * useDomains — the one adapter between `/api/map` and the UI.
 *
 * Components consume the view-model below and never touch the raw document. A
 * shift's page composition is its `modules` array, so this file does not know
 * what a section is — it only decides WHICH module list to hand over:
 *
 *   1. the live list from the map document, when the pipeline has written one;
 *   2. otherwise a minimal list projected from the fields the document always
 *      has (dek, hero stat, sub-shift list), so a database that has not run the
 *      editorial phase yet still renders a real page rather than a blank one.
 *
 * There is deliberately no third tier of authored fallback prose. Serving
 * months-old editorial as if it were this week's is worse than saying the map
 * is unavailable, so callers get `unavailable` and render an honest empty state.
 */
import { useMemo } from 'react'
import { useData } from '../hooks/useData'
import { DECK } from './site'
import { DOMAIN_ORDER, themeFor, pad2, slugify, readTimeOf } from './theme'

const first = (...v) => v.find((x) => x !== undefined && x !== null && x !== '')
const nonEmpty = (v) => (Array.isArray(v) && v.length ? v : null)

/**
 * ISO-8601 week number for a `YYYY-MM-DD` string, or null.
 *
 * ISO rather than a naive day-of-year / 7: weeks start Monday and week 1 is the
 * one containing the first Thursday, which is the convention a reader checking
 * against a calendar will assume.
 */
function isoWeek(dateStr) {
  if (!dateStr) return null
  const d = new Date(`${dateStr}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return null
  // Shift to the Thursday of this week; its year is the ISO week-numbering year.
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
  const jan1 = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil(((d - jan1) / 86400000 + 1) / 7)
}

/**
 * Minimal composition for a live shift whose editorial modules haven't been
 * generated. Mirrors the head of the pipeline's template so the page reads the
 * same, just shorter.
 */
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

/** One sub-shift: identity for routing plus its module list. */
function toSubShift(src, i) {
  const title = src.name || ''
  return {
    id: first(src.id, `sub-${i}`),
    num: pad2(i + 1),
    slug: slugify(title),
    title,
    context: src.context,
    dek: src.description || '',
    modules: nonEmpty(src.modules) || projectStModules(src),
  }
}

/** One key shift: identity, the bits the domain sheet shows, and its modules. */
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
    // Generated every run by the taxonomy phase; shown on the domain sheet row.
    velocity: src.velocity,
    read: first(src.read_time, readTimeOf(dek)),
    modules: nonEmpty(src.modules) || projectKtModules(src),
    subshifts: subs.map((s, k) => toSubShift(s, k)),
  }
}

export function useDomains() {
  // `loading` comes from the fetch, not from `!data`: a failed request settles
  // with no data, and the page must then show the unavailable state rather than
  // spinning forever.
  const { data, error, loading } = useData('map.json')

  const domains = useMemo(() => {
    const liveDomains = new Map((data?.domains || []).map((d) => [d.id, d]))
    const ktsByDomain = new Map()
    const subsByKt = new Map()

    for (const st of data?.sub_trends || []) {
      const arr = subsByKt.get(st.key_trend_id) || []
      arr.push(st)
      subsByKt.set(st.key_trend_id, arr)
    }
    for (const kt of data?.key_trends || []) {
      const arr = ktsByDomain.get(kt.domain_id) || []
      arr.push({ ...kt, sub_trends: subsByKt.get(kt.id) || [] })
      ktsByDomain.set(kt.domain_id, arr)
    }

    return DOMAIN_ORDER.map((id) => {
      const deck = DECK.find((d) => d.id === id) || {}
      const live = liveDomains.get(id)
      const liveKts = ktsByDomain.get(id) || []
      const t = themeFor(id)
      const domainRef = { id, name: first(live?.name, deck.name), grad: t.grad, dot: t.dot }

      const keyShifts = liveKts.map((row, i) => toShift(row, i, domainRef))

      return {
        id,
        slug: id,
        name: domainRef.name || id,
        num: t.num,
        grad: t.grad,
        dot: t.dot,
        horizon: first(live?.horizon, deck.horizon) || '',
        blurb: first(live?.short_description, deck.blurb) || '',
        // How many shifts the domain tracks, which can exceed the number listed.
        count: first(live?.key_trend_ids?.length, liveKts.length),
        keyShifts,
        // Per-domain closing insights from the synthesis phase. Generated every
        // run and previously unrendered; the domain sheet now closes on them.
        insights: (data?.synthesis_insights || [])
          .filter((s) => s?.domain_id === id && s?.name && s?.description)
          .map((s) => ({ id: s.id, name: s.name, description: s.description })),
      }
    })
  }, [data])

  // Headline figures, counted from the document rather than written into the
  // copy. The homepage used to state "Week 31 · four domains" and "eight shifts
  // this week" as literals; the database held 60 shifts, and the week number
  // was going to drift every Monday. On a product whose whole claim is sourced
  // evidence, the numbers on the front page have to come from the evidence.
  const meta = useMemo(() => {
    const updated = data?.updated || null
    return {
      updated,
      week: isoWeek(updated),
      domainCount: domains.length,
      shiftCount: domains.reduce((n, d) => n + d.keyShifts.length, 0),
    }
  }, [data, domains])

  // No document (network failure, or the pipeline has never written one) means
  // there is nothing to read — distinct from "loaded, but this domain is empty".
  const unavailable = !loading && (!!error || !data)

  return { domains, meta, loading, unavailable }
}

/** Resolve a domain (and optionally a shift / sub-shift) from URL params. */
export function useResolved({ domainSlug, ktSlug, subSlug } = {}) {
  const { domains, loading, unavailable } = useDomains()
  const domain = domains.find((d) => d.slug === domainSlug || d.id === domainSlug)
  const shift = ktSlug ? domain?.keyShifts.find((s) => s.slug === ktSlug) : undefined
  const sub = subSlug ? shift?.subshifts.find((s) => s.slug === subSlug) : undefined
  return { domains, domain, shift, sub, loading, unavailable }
}
