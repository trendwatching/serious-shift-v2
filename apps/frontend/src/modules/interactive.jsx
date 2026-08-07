/** The modules the reader operates: the peel-tab stack, the needs pair, the
 *  chip filter, and the two card rails. */
import { useId, useLayoutEffect, useRef, useState } from 'react'
import { Link } from '../lib/router'
import { Eyebrow } from './blocks'

/**
 * The peel-tab stack — two cards in one place, one on top.
 *
 * Both panels stay in the DOM and the container is pinned to the taller of
 * them, which is the whole point: switching tabs must not resize the page
 * under the reader's thumb. Measuring is what makes that possible, and it is
 * re-measured on resize, which is the bug the previous CSS-grid version was
 * written to avoid and then reintroduced by letting the height jump instead.
 */
export function PeelTabs({ data, ctx }) {
  const cards = [
    data.whats_changing && { label: "What's changing", text: data.whats_changing },
    data.why_now && { label: 'Why now', text: data.why_now },
  ].filter(Boolean)

  const [top, setTop] = useState(0)
  const [height, setHeight] = useState(0)
  const bodies = useRef([])
  const id = useId()
  const sub = ctx.scope === 'sub_shift'

  useLayoutEffect(() => {
    const measure = () => {
      const tallest = bodies.current.reduce((m, el) => (el ? Math.max(m, el.scrollHeight) : m), 0)
      if (tallest) setHeight(tallest + 96)
    }
    measure()
    // Re-measure on reflow, not just on mount. A one-shot measurement is what
    // left the previous version's stack sized for the text it had on first
    // paint, so a rotate or a font swap left the copy overflowing a stale box.
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(measure)
    bodies.current.forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [data.whats_changing, data.why_now])

  if (!cards.length) return null

  const radius = sub ? 18 : 20
  const front = sub ? 'var(--grad-sunset)' : 'var(--a-grad)'
  const back = 'linear-gradient(180deg, #F7F7F7 0%, #F1F1F3 100%)'

  const onKeyDown = (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
    e.preventDefault()
    setTop(e.key === 'Home' ? 0 : e.key === 'End' ? cards.length - 1 : (top + (e.key === 'ArrowRight' ? 1 : -1) + cards.length) % cards.length)
  }

  return (
    <section className="relative" style={{ height: height || 246, marginTop: 2 }}>
      <h2 className="sr-only">What’s changing and why now</h2>
      {/* Tabs and panels are siblings, not nested.
          A `tabpanel` is not an allowed child of a `tablist`, so the earlier
          shape — one wrapper per card holding both, with the wrappers inside the
          tablist — was an `aria-required-children` violation that also left a
          screen reader with two tabs it could not associate with anything.
          Splitting them costs nothing visually: the peel is pure z-index, so the
          tab and its panel just carry their own layer instead of sharing one. */}
      <div role="tablist" aria-label="Shift context" onKeyDown={onKeyDown}>
        {cards.map((card, i) => {
          const on = i === top
          const left = i === 0
          return (
            <button
              key={card.label}
              id={`${id}-tab-${i}`}
              type="button" role="tab" aria-selected={on} aria-controls={`${id}-${i}`} tabIndex={on ? 0 : -1}
              onClick={() => setTop(i)}
              className="absolute box-border flex cursor-pointer items-center justify-center"
              style={{
                zIndex: on ? 13 : 11,
                top: 0, left: left ? 0 : '48%', right: left ? '52%' : 0, height: 54, padding: '0 12px',
                borderRadius: `${radius}px ${radius}px 0 0`,
                backgroundImage: on ? front : back,
                backgroundSize: sub && on ? '100% 250px' : undefined,
                backgroundRepeat: 'no-repeat',
                transition: 'background-image 0.35s ease, color 0.35s ease',
              }}
            >
              <span
                className="t-display whitespace-nowrap uppercase"
                style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.04em', color: on ? '#fff' : 'var(--color-ink)', transition: 'color 0.3s ease' }}
              >
                {card.label}
              </span>
            </button>
          )
        })}
      </div>

      {cards.map((card, i) => {
        const on = i === top
        const left = i === 0
        return (
          <div
            key={card.label}
            id={`${id}-${i}`} role="tabpanel" aria-labelledby={`${id}-tab-${i}`}
            className="absolute box-border overflow-hidden"
            style={{
              zIndex: on ? 12 : 10,
              top: 50, left: 0, right: 0, bottom: 0, padding: '22px 20px',
              borderRadius: left ? `0 ${radius}px ${radius}px ${radius}px` : `${radius}px 0 ${radius}px ${radius}px`,
              backgroundImage: on ? front : back,
              boxShadow: '0 10px 26px rgba(27,22,32,0.14)',
              transition: 'background-image 0.35s ease',
            }}
          >
            <div
              ref={(el) => { bodies.current[i] = el }}
              className="text-pretty"
              style={{ fontSize: 14.5, lineHeight: 1.58, color: on ? '#fff' : 'var(--color-ink)', opacity: on ? 1 : 0, transition: 'opacity 0.3s ease' }}
            >
              {card.text}
            </div>
          </div>
        )
      })}
    </section>
  )
}

/** The needs pair: the selected card takes three shares of the row. */
export function HumanNeeds({ data, ctx }) {
  const [pick, setPick] = useState('u')
  const id = useId()
  if (!data.unlocked || !data.threatened) return null
  const sub = ctx.scope === 'sub_shift'

  const card = (key, label, text, grad, shadow) => {
    const on = pick === key
    return (
      <button
        type="button" onClick={() => setPick(key)} onMouseEnter={() => setPick(key)}
        aria-expanded={on} aria-controls={`${id}-${key}`}
        className="box-border flex min-w-0 flex-col overflow-hidden text-left text-white"
        style={{
          flex: on ? '3 1 0%' : '1 1 0%',
          borderRadius: 18, padding: '18px 16px', gap: 10,
          backgroundImage: grad,
          opacity: on ? 1 : 0.82,
          // The design gives the sub-shift pair no shadow at all.
          boxShadow: sub ? undefined : (on ? shadow : '0 3px 12px rgba(27,22,32,0.08)'),
          transition: 'flex-grow 0.45s var(--ease-out), opacity 0.35s ease, box-shadow 0.35s ease',
        }}
      >
        <span className="t-eyebrow whitespace-nowrap" style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.12em' }}>{label}</span>
        <span
          id={`${id}-${key}`} aria-hidden={!on}
          className="text-pretty"
          style={{
            fontSize: 14, lineHeight: 1.5, opacity: on ? 1 : 0,
            maxHeight: on ? (sub ? 260 : 240) : 0, overflow: 'hidden',
            transition: 'opacity 0.3s ease, max-height 0.45s var(--ease-out)',
          }}
        >
          {text}
        </span>
      </button>
    )
  }

  return (
    <section className="flex flex-col" style={{ marginTop: 6, gap: 10 }}>
      <Eyebrow>Human needs</Eyebrow>
      <div className="flex items-stretch" style={{ gap: 10 }}>
        {card('u', 'Unlocked', data.unlocked, 'var(--pos-grad)', '0 12px 26px var(--pos-shadow)')}
        {/* On a key shift this is its own pink ramp; on a sub-shift it is
            sunset, like everything else one level down. */}
        {card('t', 'Threatened', data.threatened, sub ? 'var(--grad-sunset)' : 'var(--grad-threatened)', '0 12px 26px var(--a-shadow)')}
      </div>
    </section>
  )
}

/** Sector chips over a detail card that swaps on selection. */
export function Industries({ data }) {
  const items = (data.items || []).filter((i) => i?.name)
  const [pick, setPick] = useState(0)
  if (!items.length) return null
  const current = items[Math.min(pick, items.length - 1)]

  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right={`${Math.min(pick, items.length - 1) + 1} of ${items.length}`}>Implications by industry</Eyebrow>
      <div
        className="rail chips bleed-edge" role="tablist" aria-label="Industry sectors"
        style={{ padding: '2px 22px 4px', gap: 8, scrollSnapType: 'x proximity' }}
      >
        {items.map((item, i) => {
          const on = i === pick
          return (
            <button
              key={item.name} type="button" role="tab" aria-selected={on} onClick={() => setPick(i)}
              className="t-display box-border flex shrink-0 cursor-pointer items-center whitespace-nowrap"
              style={{
                scrollSnapAlign: 'center', height: 34, padding: '0 14px', borderRadius: 999,
                border: `1px solid ${on ? '#1B1620' : 'var(--color-line-chip)'}`,
                background: on ? '#1B1620' : '#fff',
                color: on ? '#fff' : 'var(--color-ink-soft)',
                fontSize: 12.5, fontWeight: 650,
                transition: 'background 0.28s ease, color 0.28s ease, border-color 0.28s ease',
              }}
            >
              {item.name}
            </button>
          )
        })}
      </div>
      <div
        key={current.name} role="tabpanel" className="card flex flex-col"
        style={{ padding: 18, gap: 8, animation: 'ssRise 0.42s var(--ease-out)' }}
      >
        <span className="t-display" style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em' }}>{current.name}</span>
        <span className="text-pretty" style={{ fontSize: 14.5, lineHeight: 1.55, color: 'var(--color-ink-sector)' }}>{current.text}</span>
      </div>
    </section>
  )
}

/** Opportunity cards, then the Work With Us card as the last cell. */
export function Territories({ data, ctx }) {
  const items = (data.items || []).filter((t) => t?.name)
  if (!items.length) return null
  const still = ctx.scope === 'sub_shift'   // the sub-shift rail has no entrances

  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right="Scroll ›">Opportunity territories</Eyebrow>
      <div className="rail bleed-edge" style={{ padding: '2px 22px 6px', gap: 12, scrollSnapType: 'x mandatory' }}>
        {items.map((t, i) => (
          <div
            key={t.name}
            className={`card box-border flex shrink-0 flex-col${still ? '' : ' card-lift'}`}
            style={{
              width: 236, padding: 16, gap: 9, scrollSnapAlign: 'center',
              animation: still ? undefined : `ssRise 0.6s var(--ease-out) ${(0.05 + i * 0.07).toFixed(2)}s`,
            }}
          >
            <span
              className="t-display flex items-center justify-center"
              style={{ width: 26, height: 26, borderRadius: 999, background: 'var(--color-yellow)', color: 'var(--color-ink)', fontSize: 12, fontWeight: 800 }}
            >{i + 1}</span>
            <span className="t-display" style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.01em' }}>{t.name}</span>
            <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-mid)' }}>{t.text}</span>
          </div>
        ))}

        {/* Sunset, unscrimmed — this card is a step outside the reading flow,
            which is exactly what the gradient marks everywhere else. */}
        <div
          className="box-border flex shrink-0 flex-col text-white"
          style={{
            width: 250, padding: '20px 18px', gap: 10, borderRadius: 18, scrollSnapAlign: 'center',
            backgroundImage: 'var(--grad-sunset)', boxShadow: '0 12px 26px rgba(94,0,51,0.24)',
            animation: still ? undefined : 'ssRise 0.6s var(--ease-out) 0.34s',
          }}
        >
          <span className="t-eyebrow" style={{ fontSize: 10.5, fontWeight: 800, color: 'var(--color-yellow)' }}>Work with us</span>
          <span className="t-title" style={{ fontSize: 21, lineHeight: 1.14, textTransform: 'none' }}>Don’t see your angle here?</span>
          <span className="text-pretty" style={{ fontSize: 13, lineHeight: 1.48, opacity: 0.94 }}>
            These territories are starting points, not limits. We work with organizations to find where a shift like this creates real commercial space for their specific context.
          </span>
          <a href="mailto:hello@trendwatching.com" className="pill-contact mt-auto self-start">
            Contact us <span aria-hidden="true" style={{ fontSize: 15 }}>→</span>
          </a>
        </div>
      </div>
    </section>
  )
}

/**
 * The shift's sub-shifts. Two card styles: a `tile` with artwork, and a `row`.
 * Both are a vertical stack — the design never turns this into a carousel,
 * because each card carries a paragraph you are meant to read.
 */
export function SubShiftList({ ctx }) {
  const subs = ctx.subs || []
  if (!subs.length) return null
  const tile = ctx.subCardStyle === 'tile'

  return (
    <section className="widen flex flex-col" style={{ marginTop: 6, gap: 10 }}>
      <Eyebrow right="Tap to open">The {subs.length} sub-shifts</Eyebrow>
      <div className="sub-stack" style={{ gap: 10 }}>
        {subs.map((s, i) => {
          const to = `${ctx.basePath}/${s.slug}`
          const delay = `${(0.05 + i * 0.06).toFixed(2)}s`
          if (tile) {
            const short = (s.dek || '').length > 118 ? `${(s.dek || '').slice(0, 116).trim()}…` : s.dek
            return (
              <Link
                key={s.id} to={to}
                className="ss-tile flex items-stretch overflow-hidden bg-white"
                style={{ minHeight: 148, borderRadius: 20, boxShadow: '0 6px 18px rgba(27,22,32,0.13)', animation: `ssRise 0.6s var(--ease-out) ${delay}` }}
              >
                {/* Each sub-shift's own art. The shipped jpg is the fallback,
                    and it used to be the whole story: every tile on every page
                    in every sphere carried the same Society-pink picture. */}
                <span
                  className="block shrink-0 self-stretch"
                  style={{
                    width: 152,
                    backgroundImage: `url('${s.tileImage || '/shift/sub-card-art.jpg'}')`,
                    backgroundSize: 'cover', backgroundPosition: 'center',
                  }}
                />
                <span className="box-border flex min-w-0 flex-1 flex-col justify-center" style={{ padding: '16px 16px 16px 15px', gap: 7 }}>
                  <span className="t-display uppercase" style={{ fontSize: 15, fontWeight: 800, lineHeight: 1.18, letterSpacing: '-0.01em' }}>{s.title}</span>
                  <span className="text-pretty" style={{ fontSize: 11.5, lineHeight: 1.42, color: 'var(--color-ink-mid)' }}>{short}</span>
                </span>
              </Link>
            )
          }
          return (
            <Link
              key={s.id} to={to}
              className="card card-lift relative flex flex-col overflow-hidden"
              style={{ padding: '15px 16px 15px 17px', gap: 9, animation: `ssRise 0.6s var(--ease-out) ${delay}` }}
            >
              {/* Sunset, because this rule points one level down. */}
              <span className="absolute inset-y-0 left-0" style={{ width: 4, backgroundImage: 'var(--grad-sunset)' }} />
              <span className="flex items-center" style={{ gap: 8 }}>
                <span
                  className="t-display inline-flex items-center uppercase"
                  style={{ height: 22, padding: '0 9px', gap: 6, borderRadius: 999, background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 10, fontWeight: 800, letterSpacing: '0.14em' }}
                >
                  Sub-shift {s.num}
                </span>
                <span className="ml-auto" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--a-ink)' }}>Open</span>
                <span
                  className="inline-flex items-center justify-center"
                  style={{ width: 22, height: 22, borderRadius: 999, background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 13 }}
                >↗</span>
              </span>
              <span className="t-display uppercase" style={{ fontSize: 16, fontWeight: 800, lineHeight: 1.2, letterSpacing: '-0.01em' }}>{s.title}</span>
              <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-mid)' }}>{s.dek}</span>
            </Link>
          )
        })}
      </div>
    </section>
  )
}

/**
 * Innovations in the wild.
 *
 * The design has no innovations module, so this borrows the territories rail —
 * the design's established way of showing a set of peer cards — rather than
 * inventing a shape for it.
 */
export function Innovations({ data }) {
  const items = (data.items || []).filter((i) => i?.title)
  if (!items.length) return null
  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right="Scroll ›">Innovations in the wild</Eyebrow>
      <div className="rail bleed-edge" style={{ padding: '2px 22px 6px', gap: 12, scrollSnapType: 'x mandatory' }}>
        {items.map((item, i) => {
          const Card = item.url ? 'a' : 'div'
          return (
            <Card
              key={`${item.title}-${i}`}
              {...(item.url ? { href: item.url, target: '_blank', rel: 'noopener noreferrer' } : {})}
              className="card card-lift box-border flex shrink-0 flex-col overflow-hidden"
              style={{ width: 236, scrollSnapAlign: 'center' }}
            >
              <span
                className="block"
                style={{
                  height: 132,
                  background: item.image ? `#F7F6F9 url('${item.image}') center/cover` : 'var(--color-paper)',
                }}
              />
              <span className="box-border flex flex-1 flex-col" style={{ padding: 16, gap: 8 }}>
                {item.brand && <span className="t-eyebrow" style={{ fontSize: 10, color: 'var(--a-ink)' }}>{item.brand}</span>}
                <span className="t-display" style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.01em' }}>{item.title}</span>
                {item.description && (
                  <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-mid)' }}>{item.description}</span>
                )}
                {!!(item.tags || []).length && (
                  <span className="mt-auto flex flex-wrap" style={{ gap: 6, paddingTop: 4 }}>
                    {item.tags.slice(0, 3).map((t) => (
                      <span
                        key={t} className="t-display"
                        style={{ padding: '3px 9px', borderRadius: 999, background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 10, fontWeight: 700 }}
                      >{t}</span>
                    ))}
                  </span>
                )}
              </span>
            </Card>
          )
        })}
      </div>
    </section>
  )
}

/** Numbered evidence and the honest case against, on their own panels. */
export function SignalList({ data, tone }) {
  const items = (data.items || []).filter(Boolean)
  if (!items.length) return null
  const positive = tone === 'counter'
  return (
    <section
      className="flex flex-col"
      style={{ borderRadius: 18, padding: 24, gap: 18, backgroundImage: positive ? 'var(--pos-grad)' : 'var(--a-grad)' }}
    >
      <h2 className="t-eyebrow text-white">{positive ? 'Counter-signals' : 'Signals'}</h2>
      <div className="flex flex-col" style={{ gap: 12 }}>
        {items.map((text, i) => (
          <div key={i} className="flex items-center bg-white" style={{ borderRadius: 10, padding: 16, gap: 14 }}>
            <span className="t-display" style={{ fontSize: 20, fontWeight: 700 }}>{i + 1}.</span>
            <span style={{ fontSize: 15, lineHeight: 1.45 }}>{text}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

/** Who is saying this: for on green, against on the accent. */
export function Voices({ data }) {
  const groups = [
    { label: 'Argue for', people: (data.proponents || []).filter((p) => p?.name && p?.quote), grad: 'var(--pos-grad)' },
    { label: 'Push back', people: (data.skeptics || []).filter((p) => p?.name && p?.quote), grad: 'var(--a-grad)' },
  ].filter((g) => g.people.length)
  if (!groups.length) return null
  const total = groups.reduce((n, g) => n + g.people.length, 0)
  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right={`${total} voices`}>Who is saying this</Eyebrow>
      <div className="sub-stack" style={{ gap: 10 }}>
        {groups.map((g) => (
          <div key={g.label} className="flex flex-col" style={{ borderRadius: 14, padding: 22, gap: 14, backgroundImage: g.grad }}>
            <span className="t-eyebrow text-white" style={{ letterSpacing: '0.14em' }}>{g.label}</span>
            {g.people.map((p, i) => (
              <div key={`${p.name}-${i}`} className="flex flex-col bg-white" style={{ borderRadius: 10, padding: 18, gap: 6 }}>
                <span className="t-display" style={{ fontSize: 15, fontWeight: 600 }}>{p.name}</span>
                <span style={{ fontSize: 14.5, lineHeight: 1.6, color: 'var(--color-ink-mid)' }}>“{p.quote}”</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}

/** The sourced claims behind a sub-shift. */
export function Evidence({ data }) {
  const items = (data.items || []).filter((c) => c?.text)
  if (!items.length) return null
  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right={`${items.length} sourced`}>The evidence</Eyebrow>
      <div className="sub-stack" style={{ gap: 10 }}>
        {items.map((c, i) => (
          <div key={i} className="card flex flex-col" style={{ padding: 18, gap: 10 }}>
            <span className="flex flex-wrap items-center" style={{ gap: 8 }}>
              <span className="t-display" style={{ fontSize: 14, fontWeight: 600 }}>{c.thinker || c.source}</span>
              {c.strength && (
                <span
                  className="t-display uppercase"
                  style={{ padding: '2px 8px', borderRadius: 999, background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 9, fontWeight: 700, letterSpacing: '0.1em' }}
                >{c.strength.replace(/_/g, ' ')}</span>
              )}
              {c.date && <span className="t-mono ml-auto" style={{ fontSize: 11, color: 'var(--color-ink-meta)' }}>{c.date}</span>}
            </span>
            <span style={{ fontSize: 15, lineHeight: 1.5 }}>{c.text}</span>
            {c.implication && (
              <span style={{ fontSize: 14.5, lineHeight: 1.5, color: 'var(--color-ink-mid)' }}>
                <strong style={{ color: 'var(--color-ink)' }}>So what</strong> — {c.implication}
              </span>
            )}
            {/* The whole claim of this module is that the evidence is sourced, so
                a claim that arrives with a URL has to be followable. The port
                dropped the link and left the module asserting provenance it gave
                the reader no way to check. */}
            {c.url && (
              <a
                href={c.url} target="_blank" rel="noopener noreferrer"
                className="t-display self-start"
                style={{ fontSize: 12.5, fontWeight: 700, letterSpacing: '-0.005em', color: 'var(--a-ink)' }}
              >
                Read source: {c.source || 'link'}
                <span aria-hidden="true" style={{ marginLeft: 5 }}>↗</span>
              </a>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
