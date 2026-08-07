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
        <Intro
          width={`${step}%`} meta={meta} active={index === 0} count={count}
          onJump={go}
          names={Object.fromEntries(domains.map((d) => [d.id, d.name]))}
        />
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

function Intro({ width, meta, active, count, onJump, names }) {
  // Both lines are counted from the map document. Until it loads there is
  // nothing truthful to say, so the eyebrow renders the domain list alone and
  // the standfirst drops the counts rather than guessing at them.
  const eyebrow = [
    meta?.week ? `Week ${meta.week}` : null,
    meta?.domainCount ? `${spell(meta.domainCount)} domains` : null,
  ].filter(Boolean).join(' · ')

  // The design's own standfirst, fixed. It says what the site is for, which no
  // generated count can. The week and domain counts stay in the eyebrow above,
  // where being empty until the map loads costs the reader nothing.
  const standfirst =
    'Understand how AI will transform society, the economy, consumers and '
    + 'organizations — then turn those shifts into your own daring new '
    + 'opportunities and futures.'

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
      <Orbs />
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

        {/* Four gradient pills that jump the deck. On mobile this is the only
            way in besides swiping; on desktop it doubles as the table of
            contents the wide layout would otherwise be missing. */}
        <div className="mt-6 flex flex-wrap items-center gap-[9px] lg:mt-10">
          {DOMAIN_ORDER.map((id, i) => (
            <button
              key={id}
              type="button"
              onClick={() => onJump(i + 1)}
              tabIndex={active ? 0 : -1}
              className="box-border inline-flex h-10 items-center gap-2.5 rounded-full px-4 text-white transition-transform duration-300 hover:-translate-y-0.5"
              style={{
                backgroundImage: DOMAIN_THEME[id].grad,
                boxShadow: '0 6px 14px rgba(27,22,32,0.2), inset 0 1px 0 rgba(255,255,255,0.26)',
                animation: `ssRise 0.7s var(--ease-out) ${(0.5 + i * 0.07).toFixed(2)}s both`,
              }}
            >
              <span className="t-eyebrow text-[13.5px]" style={{ letterSpacing: '0.05em' }}>{names[id]}</span>
              <span aria-hidden="true" className="text-base leading-none">→</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * The drifting colour field behind the homepage headline.
 *
 * One orb per domain plus the brand yellow, so the palette of the whole site is
 * present before a single word about it is read. Five different paths and five
 * different periods (29–41s) mean the composition never repeats within a visit.
 *
 * Purely decorative and `transform`-only, so it stays on the compositor and
 * costs nothing on the main thread — and it disappears entirely under
 * `prefers-reduced-motion`, which zeroes every animation.
 */
const ORBS = [
  { size: 300, bottom: 60, left: -80, rgb: '237,2,107', peak: 0.6, blur: 24, anim: 'ssFloat 34s ease-in-out infinite' },
  { size: 280, top: 150, right: -90, rgb: '15,145,238', peak: 0.52, blur: 26, anim: 'ssOrb1 29s ease-in-out infinite' },
  { size: 260, bottom: -50, right: 10, rgb: '173,176,58', peak: 0.52, blur: 24, anim: 'ssOrb2 37s ease-in-out infinite' },
  { size: 250, top: 60, left: 30, rgb: '246,85,16', peak: 0.46, blur: 28, anim: 'ssOrb3 32s ease-in-out infinite' },
  { size: 220, bottom: 170, left: 140, rgb: '253,255,133', peak: 0.85, blur: 22, anim: 'ssFloat 41s ease-in-out infinite reverse' },
]

function Orbs() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {ORBS.map((orb, i) => {
        const { size, blur, rgb, peak, anim, ...pos } = orb
        return (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              ...pos,
              width: size,
              height: size,
              background: `radial-gradient(circle at 43% 39%, rgba(${rgb},${peak}), rgba(${rgb},${(peak * 0.42).toFixed(2)}) 48%, rgba(${rgb},0) 72%)`,
              filter: `blur(${blur}px)`,
              animation: anim,
              willChange: 'transform',
            }}
          />
        )
      })}
    </div>
  )
}

/* ── Panels 1..N — one per domain ────────────────────────────────────── */

/**
 * Society is the only panel with photography behind it; the other three are
 * their gradient alone.
 *
 * That is the design's call and it is a load-bearing one: Society is panel 01,
 * the first thing anyone swipes to, so it carries the cost of proving the site
 * has a visual register beyond colour. The remaining three stay flat rather
 * than each waiting on their own commissioned image, and the panel reads the
 * same either way because the scrim, not the artwork, is what the type sits on.
 */
const PANEL_IMAGE = { society: '/shift/domain-society-bg.jpg' }

function panelBackground(domain) {
  const image = PANEL_IMAGE[domain.id]
  return image
    ? `linear-gradient(180deg, rgba(27,22,32,0.12) 0%, rgba(27,22,32,0.52) 100%), url('${image}')`
    : `linear-gradient(rgba(13,11,16,0.30), rgba(13,11,16,0.30)), ${domain.grad}`
}

function DomainPanel({ domain, width, active, total, position, count }) {
  return (
    <div
      className="box-border flex h-full shrink-0 flex-col px-6 pb-[74px] pt-[30px] text-white lg:justify-center lg:px-24"
      style={{ width, backgroundImage: panelBackground(domain), backgroundSize: 'cover', backgroundPosition: 'center' }}
      role="group"
      aria-roledescription="slide"
      aria-label={`${domain.name}, ${position} of ${count}`}
      aria-hidden={!active}
      inert={!active}
    >
      <div className="mx-auto flex w-full flex-1 flex-col lg:max-w-[1180px] lg:flex-none lg:flex-row lg:items-center lg:gap-20">
        {/* Left — the headline block. This is the entire panel on mobile. */}
        <div className="flex flex-1 flex-col lg:min-w-0">
          <div className="font-mono text-[11px] opacity-90" style={{ letterSpacing: '0.08em' }}>
            {domain.num} / {pad2(total)}
          </div>

          <h2
            className="t-display mt-[30px] text-[clamp(40px,12vw,46px)] uppercase leading-[0.98] lg:text-[clamp(64px,6.4vw,112px)]"
            style={{ letterSpacing: '-0.03em' }}
          >
            {domain.name}
          </h2>
          <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 lg:max-w-[520px] lg:text-[19px]">{domain.blurb}</p>

          {/* Pinned to the bottom of the panel: what is moving in this domain
              right now, as opposed to the evergreen line above. */}
          <div className="mt-auto flex flex-col gap-2 pt-8">
            <span className="t-eyebrow" style={{ color: domain.eyebrow }}>What’s shifting right now</span>
            <p className="max-w-[300px] text-[14px] leading-[1.5] text-pretty opacity-95 lg:max-w-[520px] lg:text-[16px]">
              {domain.intro}
            </p>
          </div>

          <div
            className="mb-[34px] mt-[26px] flex flex-col border-b pb-6"
            style={{ borderColor: 'rgba(255,255,255,0.3)' }}
          >
            {/* The arrow points DOWN, not right: the shift list is the next
                thing on this journey, and a right arrow read as "another site
                over there". */}
            <Link
              to={`/map/${domain.slug}`}
              onClick={(event) => { if (!active) event.preventDefault() }}
              className="pill-yellow self-start lg:h-12 lg:px-7 lg:text-[15px]"
              tabIndex={active ? 0 : -1}
            >
              All {domain.count} key shifts
              <span aria-hidden="true" className="inline-block rotate-90 text-base leading-none">→</span>
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
