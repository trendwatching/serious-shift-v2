/**
 * Home.jsx — the swipe deck: an intro panel followed by one full-bleed panel
 * per domain.
 *
 * Performance notes (this is the page every visitor lands on):
 *  • The track is `width: N*100%` and each panel `100/N%`, so the offset is a
 *    percentage — no measuring, no ResizeObserver, correct at any viewport.
 *  • While dragging we write `transform` straight to the node through a ref.
 *    React does not re-render on pointermove, so a drag costs one compositor
 *    property update per frame instead of a full reconcile.
 *  • Only the settled index lives in state, which is also what the dots and the
 *    hint read — they change once per swipe, not once per frame.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from '../router'
import { useDocumentMeta } from '../hooks/useDocumentMeta'
import { useDomains } from './useDomains'
import { failureState } from './failure'
import { DOMAIN_ORDER, DOMAIN_THEME, pad2, quoteTitle } from './theme'

const THRESHOLD = 56      // px of travel that commits a swipe (from the design)
const FLICK = 0.45        // px/ms that commits regardless of distance

/** Small counts read better as words in body copy; anything larger stays numeric. */
const WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
               'eight', 'nine', 'ten']
const spell = (n) => (n >= 0 && n < WORDS.length ? WORDS[n] : n.toLocaleString())

export default function Home() {
  const { domains, meta, loading, unavailable, stale, error, retry } = useDomains()
  // No page title: the homepage IS the site title. Passing undefined also
  // restores it when navigating back from a shift.
  useDocumentMeta(undefined, meta?.shiftCount
    ? `${meta.domainCount} domains and ${meta.shiftCount} shifts in the current weekly map.`
    : undefined)
  const [index, setIndex] = useState(0)
  const trackRef = useRef(null)
  const drag = useRef(null)

  const count = domains.length + 1
  const step = 100 / count
  const last = count - 1

  const paint = useCallback((i, dx = 0) => {
    const el = trackRef.current
    if (el) el.style.transform = `translate3d(calc(${(-i * step).toFixed(4)}% + ${dx}px), 0, 0)`
  }, [step])

  // Keep the rendered offset in sync when the index changes (including the
  // initial paint and any change coming from the dots/arrows/keyboard).
  useEffect(() => { paint(index) }, [index, paint])

  const go = useCallback((i) => setIndex(Math.max(0, Math.min(last, i))), [last])

  const onPointerDown = (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (e.target.closest?.('button, a, input, textarea, select, [role="button"], [role="dialog"]')) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { pointerId: e.pointerId, x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, axis: null }
    const el = trackRef.current
    if (el) el.style.transition = 'none'
  }

  const onPointerMove = (e) => {
    const d = drag.current
    if (!d || d.pointerId !== e.pointerId) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    // Decide once whether this gesture is a horizontal swipe or a vertical
    // scroll, then stay committed — otherwise the deck fights the page.
    if (!d.axis && Math.abs(dx) + Math.abs(dy) > 8) d.axis = Math.abs(dx) > Math.abs(dy) * 1.15 ? 'x' : 'y'
    if (d.axis !== 'x') return
    d.dx = dx
    // Rubber-band at the two ends.
    const overscroll = (index === 0 && dx > 0) || (index === last && dx < 0)
    paint(index, overscroll ? dx * 0.35 : dx)
  }

  const endDrag = (event) => {
    const d = drag.current
    if (!d || (event?.pointerId !== undefined && d.pointerId !== event.pointerId)) return
    drag.current = null
    if (event?.currentTarget?.hasPointerCapture?.(d.pointerId)) event.currentTarget.releasePointerCapture(d.pointerId)
    const el = trackRef.current
    if (el) el.style.transition = 'transform 0.55s cubic-bezier(0.22,1,0.28,1)'

    const dx = d.axis === 'x' ? d.dx : 0
    const velocity = Math.abs(dx) / Math.max(1, performance.now() - d.t)
    const commit = Math.abs(dx) > THRESHOLD || velocity > FLICK
    const next = commit ? index + (dx < 0 ? 1 : -1) : index
    const clamped = Math.max(0, Math.min(last, next))

    if (clamped === index) paint(index)  // snap back
    else setIndex(clamped)
  }

  const cancelDrag = (event) => {
    const d = drag.current
    if (!d || d.pointerId !== event.pointerId) return
    drag.current = null
    if (event.currentTarget.hasPointerCapture?.(d.pointerId)) event.currentTarget.releasePointerCapture(d.pointerId)
    const el = trackRef.current
    if (el) el.style.transition = 'transform 0.55s cubic-bezier(0.22,1,0.28,1)'
    paint(index)
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
      if (e.target.closest?.('button, a, input, textarea, select, [contenteditable="true"], [role="dialog"], [role="tab"]')) return
      if (e.key === 'ArrowRight') go(index + 1)
      else if (e.key === 'ArrowLeft') go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, go])

  const active = index === 0 ? null : domains[index - 1]

  if (loading) {
    return <section className="grid min-h-[70dvh] place-items-center px-6" aria-busy="true" aria-label="Loading the current map"><div className="w-full max-w-[420px] animate-pulse space-y-5" aria-hidden="true"><div className="h-3 w-28 rounded bg-black/15"/><div className="h-16 rounded-xl bg-black/10"/><div className="h-20 rounded-xl bg-black/10"/></div></section>
  }
  if (unavailable) {
    const failure = failureState(error)
    return (
      <section className="grid min-h-[70dvh] place-items-center px-6 text-center">
        <div className="flex max-w-[390px] flex-col items-center gap-4">
          <p className="t-eyebrow" style={{ color: 'var(--color-ink-dim)' }}>{failure.eyebrow}</p>
          <h1 className="t-display text-3xl">{failure.title}</h1>
          <p className="t-body" style={{ color: 'var(--color-ink-mid)' }}>
            {failure.body}
          </p>
          <button type="button" className="pill-yellow" onClick={retry}>Retry</button>
        </div>
      </section>
    )
  }

  return (
    <section
      className="relative overflow-hidden bg-white"
      style={{ height: 'calc(100dvh - var(--topbar))' }}
      aria-label="Current shift domains"
      aria-roledescription="carousel"
    >
      <div
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={cancelDrag}
        onLostPointerCapture={cancelDrag}
        className="flex h-full cursor-grab active:cursor-grabbing"
        style={{
          width: `${count * 100}%`,
          touchAction: 'pan-y',
          willChange: 'transform',
          transition: 'transform 0.55s cubic-bezier(0.22,1,0.28,1)',
        }}
      >
        <Intro width={`${step}%`} meta={meta} active={index === 0} count={count} />
        {domains.map((d, i) => (
          <DomainPanel
            key={d.id}
            domain={d}
            width={`${step}%`}
            active={index === i + 1}
            total={domains.length}
            position={i + 2}
            count={count}
          />
        ))}
      </div>

      {/* Bottom scrim, straight from the design: a short dark wash so the dots
          and the swipe hint hold against a light panel as well as a gradient. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-10 z-[16]"
        style={{ background: 'linear-gradient(180deg, rgba(27,22,32,0) 0%, rgba(27,22,32,0.42) 100%)' }}
      />

      {/* Hint + dots. Both read the settled index only. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-[54px] text-center text-[11.5px] uppercase"
        style={{ letterSpacing: '0.14em', color: index === 0 ? '#3E3949' : 'rgba(255,255,255,0.85)' }}
      >
        {index === last ? 'Swipe back' : `Swipe for ${domains[index]?.name ?? ''}`}
      </div>

      <div className="absolute inset-x-0 bottom-3 flex items-center justify-center">
        {Array.from({ length: count }, (_, i) => (
          <button
            key={i} type="button" onClick={() => go(i)}
            aria-label={i === 0 ? 'Intro' : `Go to ${domains[i - 1]?.name}`}
            aria-current={i === index}
            className="grid h-11 w-11 place-items-center"
          ><span
              className="block h-1 rounded-full"
              style={{
                width: i === index ? 26 : 10,
                background: i === index
                  ? (index === 0 ? 'var(--color-ink)' : 'var(--color-yellow)')
                  : (index === 0 ? '#655F70' : 'rgba(255,255,255,0.72)'),
                transition: 'width 0.35s ease, background 0.35s ease',
              }}
            /></button>
        ))}
      </div>

      {/* Desktop affordances — the deck is drag/keyboard driven on touch. */}
      <Arrow side="left"  show={index > 0}    onClick={() => go(index - 1)} dark={index === 0} />
      <Arrow side="right" show={index < last} onClick={() => go(index + 1)} dark={index === 0} />

      <span className="sr-only" aria-live="polite">
        {active ? `${active.name}, panel ${index + 1} of ${count}` : `Intro, panel 1 of ${count}`}
      </span>
      {stale && <button type="button" onClick={retry} className="absolute left-1/2 top-3 z-30 min-h-11 -translate-x-1/2 rounded-full bg-black px-4 text-xs font-semibold text-white shadow-lg">Showing saved data · retry live map</button>}
    </section>
  )
}

function Arrow({ side, show, onClick, dark }) {
  if (!show) return null
  return (
    <button
      type="button" onClick={onClick} aria-label={side === 'left' ? 'Previous' : 'Next'}
      className={`absolute top-1/2 hidden h-11 w-11 -translate-y-1/2 place-items-center rounded-full text-[19px] backdrop-blur transition-transform hover:scale-110 lg:grid ${side === 'left' ? 'left-4' : 'right-4'}`}
      style={{
        background: dark ? 'rgba(27,22,32,0.08)' : 'rgba(255,255,255,0.22)',
        color: dark ? 'var(--color-ink)' : '#fff',
        fontFamily: 'var(--font-display)',
      }}
    >{side === 'left' ? '‹' : '›'}</button>
  )
}

/* ── Panel 0 — the editorial intro ───────────────────────────────────── */

function Intro({ width, meta, active, count }) {
  // Both lines are counted from the map document. Until it loads there is
  // nothing truthful to say, so the eyebrow renders the domain list alone and
  // the standfirst drops the counts rather than guessing at them.
  const eyebrow = [
    meta?.week ? `Week ${meta.week}` : null,
    meta?.domainCount ? `${spell(meta.domainCount)} domains` : null,
  ].filter(Boolean).join(' · ')

  // `spell` returns lower-case words for use mid-sentence; this is the one place
  // a count opens a sentence, so capitalise here rather than carrying two lists.
  const domainsWord = spell(meta?.domainCount ?? 0)
  const standfirst = meta?.shiftCount
    ? `${domainsWord[0].toUpperCase()}${domainsWord.slice(1)} domains, `
      + `${meta.shiftCount.toLocaleString()} shifts in the current weekly map, told as stories. `
      + 'Swipe and they come to you.'
    : 'Everything that is about to change, told as stories. Swipe and they come to you.'

  return (
    <div
      className="relative box-border flex h-full shrink-0 flex-col overflow-hidden bg-white px-6 pb-[104px] pt-[30px] lg:justify-center lg:px-24"
      style={{ width }}
      role="group"
      aria-roledescription="slide"
      aria-label={`Introduction, 1 of ${count}`}
      aria-hidden={!active}
      inert={!active}
    >
      {/* Ambient orb — transform-only animation, runs on the compositor. */}
      <div
        className="pointer-events-none absolute h-[300px] w-[300px] rounded-full"
        style={{
          bottom: -70, left: -90,
          background: 'radial-gradient(circle at 42% 38%, rgba(253,255,133,0.95), rgba(253,255,133,0.5) 48%, rgba(253,255,133,0) 72%)',
          filter: 'blur(14px)',
          animation: 'ssFloat 30s ease-in-out infinite reverse',
          willChange: 'transform',
        }}
      />
      <div className="relative mx-auto w-full lg:max-w-[1060px]">
        <div className="flex items-center gap-2.5 a-fade" style={{ animationDelay: '0.15s', animationDuration: '0.7s' }}>
          <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--color-yellow)', border: '1px solid var(--color-ink)' }} />
          <span className="t-eyebrow">{eyebrow}</span>
        </div>

        <h1
          className="t-display mt-7 text-[clamp(52px,13vw,58px)] leading-[0.94] lg:text-[clamp(76px,7vw,116px)]"
          style={{ letterSpacing: '-0.04em' }}
        >
          {['Everything', 'that is about'].map((line, i) => (
            <span key={line} className="block" style={{ animation: `ssWord 0.75s var(--ease-out) ${0.05 + i * 0.09}s both` }}>{line}</span>
          ))}
          <span className="block italic" style={{ animation: 'ssWord 0.75s var(--ease-out) 0.23s both' }}>to change</span>
        </h1>

        <p
          className="mt-6 max-w-[320px] text-[18.5px] leading-[1.45] a-rise lg:max-w-[560px] lg:text-[22px]"
          style={{ color: 'var(--color-ink-soft)', animationDelay: '0.4s' }}
        >
          {standfirst}
        </p>

        {/* Desktop: name the four domains up front, so a wide screen shows the
            shape of the week instead of a single line of copy. */}
        <ul className="mt-10 hidden gap-8 a-rise lg:flex" style={{ animationDelay: '0.5s' }}>
          {DOMAIN_ORDER.map((id, i) => (
            <li key={id} className="flex items-center gap-2.5">
              <span className="h-2 w-2 rounded-full" style={{ background: DOMAIN_THEME[id].dot }} />
              <span className="t-eyebrow" style={{ color: 'var(--color-ink-soft)' }}>
                {String(i + 1).padStart(2, '0')} {id}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/* ── Panels 1..N — one per domain ────────────────────────────────────── */

function DomainPanel({ domain, width, active, total, position, count }) {
  return (
    <div
      className="box-border flex h-full shrink-0 flex-col px-6 pb-[74px] pt-[30px] text-white lg:justify-center lg:px-24"
      style={{ width, backgroundImage: `linear-gradient(rgba(13,11,16,0.38), rgba(13,11,16,0.38)), ${domain.grad}` }}
      role="group"
      aria-roledescription="slide"
      aria-label={`${domain.name}, ${position} of ${count}`}
      aria-hidden={!active}
      inert={!active}
    >
      <div className="mx-auto flex w-full flex-1 flex-col lg:max-w-[1180px] lg:flex-none lg:flex-row lg:items-center lg:gap-20">
        {/* Left — the headline block. This is the entire panel on mobile. */}
        <div className="flex flex-1 flex-col lg:min-w-0">
          <div className="flex items-center justify-between font-mono text-[11px] opacity-90 lg:justify-start lg:gap-6" style={{ letterSpacing: '0.08em' }}>
            <span>{domain.num} / {pad2(total)}</span>
            <span>horizon {domain.horizon}</span>
          </div>

          <div className="mt-[26px] text-[15px] italic opacity-90 lg:text-[19px]">Everything that is about to change in</div>
          <h2
            className="t-display mt-1.5 text-[clamp(40px,12vw,46px)] leading-[0.98] lg:text-[clamp(64px,6.4vw,112px)]"
            style={{ letterSpacing: '-0.035em' }}
          >
            {domain.name}
          </h2>
          <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 lg:max-w-[520px] lg:text-[19px]">{domain.blurb}</p>

          <div className="mt-auto flex flex-col border-t pt-5 lg:mt-9 lg:border-t-0 lg:pt-0" style={{ borderColor: 'rgba(255,255,255,0.3)' }}>
            <Link to={`/map/${domain.slug}`} onClick={(event) => { if (!active) event.preventDefault() }} className="pill-yellow mt-5 self-start lg:mt-0 lg:h-12 lg:px-7 lg:text-[15px]" tabIndex={active ? 0 : -1}>
              All {domain.count} shifts <span className="text-[15px]">›</span>
            </Link>
          </div>
        </div>

        {/* Right — a peek at what's inside. Desktop only: on a wide viewport the
            gradient is otherwise dead space, and naming the shifts gives the
            panel something to read rather than only to look at. */}
        {domain.keyShifts.length > 0 && <div className="hidden w-[38%] max-w-[420px] shrink-0 lg:block">
          <div className="t-eyebrow opacity-80">In this domain</div>
          <ul className="mt-4">
            {domain.keyShifts.slice(0, 4).map((s) => (
              <li key={s.id} style={{ borderTop: '1px solid rgba(255,255,255,0.28)' }}>
                <Link
                  to={`/map/${domain.slug}/${s.slug}`}
                  tabIndex={active ? 0 : -1}
                  onClick={(event) => { if (!active) event.preventDefault() }}
                  className="group flex w-full items-start gap-3.5 py-3.5 text-left opacity-90 transition-opacity hover:opacity-100"
                >
                  <span className="mt-0.5 font-mono text-[11px] opacity-70">{s.num}</span>
                  <span className="t-title flex-1 text-[15px] leading-[1.22]">{quoteTitle(s.title)}</span>
                  <span className="mt-0.5 text-[15px] opacity-0 transition-opacity group-hover:opacity-100">›</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>}
      </div>
    </div>
  )
}
