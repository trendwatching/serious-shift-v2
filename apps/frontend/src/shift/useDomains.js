/**
 * useDomains — the one adapter between `/api/map` and the UI.
 *
 * Components consume the view-model below and never touch the raw document.
 * Every rich field is optional: a section renders only when its field is
 * present, so the page degrades cleanly while the pipeline backfills columns.
 * When the live document has no domains yet we fall back to the authored
 * design content so the site is never empty.
 */
import { useMemo } from 'react'
import { useData } from '../hooks/useData'
import { DECK, SHIFTS } from './content'
import { DOMAIN_ORDER, themeFor, pad2, slugify, readTimeOf } from './theme'

const first = (...v) => v.find((x) => x !== undefined && x !== null && x !== '')

/**
 * Normalise a `{value,text,source}` stat.
 *
 * `hero_stat` carries {value, thinker, source, year} but the accompanying prose
 * lives in its own column on the parent row, so callers pass it in as `text`.
 */
const toStat = (live, fallback, text) => {
  const value = first(live?.value, fallback?.value)
  if (!value) return undefined
  return {
    value,
    text: first(text, live?.text, fallback?.text) || '',
    source: first(live?.source, fallback?.source, live?.thinker) || '',
  }
}

const toPairs = (v) =>
  Array.isArray(v)
    ? v.map((x) => ({ name: x.name || x.label || '', text: x.text || x.body || '' })).filter((x) => x.name)
    : undefined

const toSteps = (v) => {
  if (Array.isArray(v)) return v.filter((s) => s?.text).map((s) => ({ label: s.label, text: s.text }))
  if (v && typeof v === 'object') {
    const out = ['now', 'next', 'beyond']
      .filter((k) => v[k])
      .map((k) => ({ label: k[0].toUpperCase() + k.slice(1), text: v[k] }))
    return out.length ? out : undefined
  }
  return undefined
}

const toList = (v) => (Array.isArray(v) && v.length ? v.filter(Boolean) : undefined)

/** Merge one authored sub-shift with its live row. */
function toSubShift(live, fallback, i) {
  const src = live || {}
  const fb = fallback || {}
  const title = first(src.name, fb.title) || ''
  return {
    id: first(src.id, `sub-${i}`),
    num: pad2(i + 1),
    slug: slugify(title),
    title,
    context: first(src.context, fb.context),
    dek: first(src.description, fb.dek) || '',
    lede: first(src.lede, fb.lede),
    from: first(src.from_text, fb.from),
    to: first(src.to_text, fb.to),
    quote: first(src.tension, fb.quote),
    stat: toStat(src.stat, fb.stat),
    whatChanging: first(src.whats_changing, fb.whatChanging),
    whyNow: first(src.why_now, fb.whyNow),
    needs: first(src.human_needs, fb.needs),
    signals: toList(src.signals) || toList(fb.signals),
    counter: toList(src.counter_signals) || toList(fb.counter),
    horizonSteps: toSteps(src.timeline) || toSteps(fb.horizonSteps),
    territories: toPairs(src.territories) || toPairs(fb.territories),
  }
}

/** Merge one authored key shift with its live row. */
function toShift(live, fallback, i, domain) {
  const src = live || {}
  const fb = fallback || {}
  const title = first(src.name, fb.title) || ''
  const dek = first(src.subtitle, src.description, fb.dek) || ''

  const liveSubs = Array.isArray(src.sub_trends) ? src.sub_trends : []
  const fbSubs = fb.subshifts || []
  const subCount = Math.max(liveSubs.length, fbSubs.length)

  return {
    id: first(src.id, fb.id, `kt-${i}`),
    num: pad2(i + 1),
    slug: slugify(title),
    domain,
    kicker: first(src.kicker, fb.kicker, `Shift ${pad2(i + 1)}`),
    title,
    dek,
    read: first(src.read_time, fb.read, readTimeOf(dek, src.description)),
    from: first(src.from_text, fb.from),
    to: first(src.to_text, fb.to),
    stat: toStat(src.hero_stat || src.stat, fb.stat, src.stat_text),
    whatChanging: first(src.whats_changing, fb.whatChanging),
    whyNow: first(src.why_now, fb.whyNow),
    needs: first(src.human_needs, fb.needs),
    tension: first(src.consumer_tension, fb.tension),
    horizonSteps: toSteps(src.timeline) || toSteps(fb.horizonSteps),
    industries: toPairs(src.industries) || toPairs(fb.industries),
    territories: toPairs(src.opportunities || src.territories) || toPairs(fb.territories),
    subshifts: Array.from({ length: subCount }, (_, k) => toSubShift(liveSubs[k], fbSubs[k], k)),
  }
}

export function useDomains() {
  const { data, loading } = useData('map.json')

  const domains = useMemo(() => {
    // Index the live document, tolerating a document that predates the
    // rich-field migration (or is missing entirely).
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

      // Either the live document supplies this domain's shifts or the authored
      // content does — never a positional blend of the two, which would splice
      // one shift's prose onto a different shift.
      const keyShifts = liveKts.length
        ? liveKts.map((row, i) => toShift(row, null, i, domainRef()))
        : (deck.shifts || [])
            .map((sid) => SHIFTS.find((s) => s.id === sid))
            .filter(Boolean)
            .map((row, i) => toShift(null, row, i, domainRef()))

      function domainRef() {
        return { id, name: first(live?.name, deck.name), grad: t.grad, dot: t.dot }
      }

      return {
        id,
        slug: id,
        name: first(live?.name, deck.name) || id,
        num: t.num,
        grad: t.grad,
        dot: t.dot,
        horizon: first(live?.horizon, deck.horizon) || '',
        blurb: first(live?.short_description, deck.blurb) || '',
        readers: deck.readers,
        // The headline count is how many shifts the domain tracks, which can
        // exceed the number we list. Live data wins once it exists.
        count: liveKts.length
          ? first(live?.key_trend_ids?.length, liveKts.length)
          : first(deck.count, keyShifts.length),
        keyShifts,
      }
    })
  }, [data])

  return { domains, loading }
}

/** Resolve a domain (and optionally a shift / sub-shift) from URL params. */
export function useResolved({ domainSlug, ktSlug, subSlug } = {}) {
  const { domains, loading } = useDomains()
  const domain = domains.find((d) => d.slug === domainSlug || d.id === domainSlug)
  const shift = ktSlug ? domain?.keyShifts.find((s) => s.slug === ktSlug) : undefined
  const sub = subSlug ? shift?.subshifts.find((s) => s.slug === subSlug) : undefined
  return { domains, domain, shift, sub, loading }
}
