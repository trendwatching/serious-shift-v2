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
 *      editorial phase yet still renders a real page rather than a blank one;
 *   3. and if there is no live document at all, the authored design content.
 */
import { useMemo } from 'react'
import { useData } from '../hooks/useData'
import { DECK, SHIFTS } from './content'
import { DOMAIN_ORDER, themeFor, pad2, slugify, readTimeOf } from './theme'

const first = (...v) => v.find((x) => x !== undefined && x !== null && x !== '')
const nonEmpty = (v) => (Array.isArray(v) && v.length ? v : null)

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
    modules: nonEmpty(src.modules) || (live ? projectStModules(src) : fb.modules) || [],
  }
}

/** One key shift: identity, the bits the domain sheet shows, and its modules. */
function toShift(live, fallback, i, domain) {
  const src = live || {}
  const fb = fallback || {}
  const title = first(src.name, fb.title) || ''
  const dek = first(src.subtitle, src.description, fb.dek) || ''

  const liveSubs = Array.isArray(src.sub_trends) ? src.sub_trends : []
  const fbSubs = fb.subshifts || []
  const subshifts = liveSubs.length
    ? liveSubs.map((s, k) => toSubShift(s, null, k))
    : fbSubs.map((s, k) => toSubShift(null, s, k))

  return {
    id: first(src.id, fb.id, `kt-${i}`),
    num: pad2(i + 1),
    slug: first(src.slug, slugify(title)),
    domain,
    kicker: first(src.kicker, fb.kicker, `Shift ${pad2(i + 1)}`),
    title,
    dek,
    read: first(src.read_time, fb.read, readTimeOf(dek)),
    modules: nonEmpty(src.modules) || (live ? projectKtModules(src) : fb.modules) || [],
    subshifts,
  }
}

export function useDomains() {
  // `loading` comes from the fetch, not from `!data`: a failed request settles
  // with no data, and the page must then fall through to the authored content
  // rather than spinning forever.
  const { data, loading } = useData('map.json')

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

      // Either the live document supplies this domain's shifts or the authored
      // content does — never a positional blend, which would splice one shift's
      // prose onto a different shift.
      const keyShifts = liveKts.length
        ? liveKts.map((row, i) => toShift(row, null, i, domainRef))
        : (deck.shifts || [])
            .map((sid) => SHIFTS.find((s) => s.id === sid))
            .filter(Boolean)
            .map((row, i) => toShift(null, row, i, domainRef))

      return {
        id,
        slug: id,
        name: domainRef.name || id,
        num: t.num,
        grad: t.grad,
        dot: t.dot,
        horizon: first(live?.horizon, deck.horizon) || '',
        blurb: first(live?.short_description, deck.blurb) || '',
        readers: deck.readers,
        // How many shifts the domain tracks, which can exceed the number listed.
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
