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
import { useNavigate } from 'react-router-dom'
import { useDomains } from './useDomains'
import { DOMAIN_ORDER, DOMAIN_THEME } from './theme'

const THRESHOLD = 56      // px of travel that commits a swipe (from the design)
const FLICK = 0.45        // px/ms that commits regardless of distance

export default function Home() {
  const { domains } = useDomains()
  const navigate = useNavigate()
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
    drag.current = { x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, axis: null }
    const el = trackRef.current
    if (el) el.style.transition = 'none'
  }

  const onPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    // Decide once whether this gesture is a horizontal swipe or a vertical
    // scroll, then stay committed — otherwise the deck fights the page.
    if (!d.axis && Math.abs(dx) + Math.abs(dy) > 8) d.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
    if (d.axis !== 'x') return
    d.dx = dx
    // Rubber-band at the two ends.
    const overscroll = (index === 0 && dx > 0) || (index === last && dx < 0)
    paint(index, overscroll ? dx * 0.35 : dx)
  }

  const endDrag = () => {
    const d = drag.current
    if (!d) return
    drag.current = null
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

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') go(index + 1)
      else if (e.key === 'ArrowLeft') go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, go])

  const active = index === 0 ? null : domains[index - 1]

  return (
    <section
      className="relative overflow-hidden bg-white"
      style={{ height: 'calc(100dvh - var(--topbar))' }}
      aria-roledescription="carousel"
    >
      <div
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onPointerLeave={endDrag}
        className="flex h-full cursor-grab active:cursor-grabbing"
        style={{
          width: `${count * 100}%`,
          touchAction: 'pan-y',
          willChange: 'transform',
          transition: 'transform 0.55s cubic-bezier(0.22,1,0.28,1)',
        }}
      >
        <Intro width={`${step}%`} />
        {domains.map((d, i) => (
          <DomainPanel
            key={d.id}
            domain={d}
            width={`${step}%`}
            active={index === i + 1}
            onOpen={() => navigate(`/map/${d.slug}`)}
            onOpenShift={(s) => navigate(`/map/${d.slug}/${s.slug}`)}
          />
        ))}
      </div>

      {/* Hint + dots. Both read the settled index only. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-[54px] text-center text-[11.5px] uppercase"
        style={{ letterSpacing: '0.14em', color: index === 0 ? '#3E3949' : 'rgba(255,255,255,0.85)' }}
      >
        {index === last ? 'Swipe back' : `Swipe for ${domains[index]?.name ?? ''}`}
      </div>

      <div className="absolute inset-x-0 bottom-8 flex items-center justify-center gap-2">
        {Array.from({ length: count }, (_, i) => (
          <button
            key={i} type="button" onClick={() => go(i)}
            aria-label={i === 0 ? 'Intro' : `Go to ${domains[i - 1]?.name}`}
            aria-current={i === index}
            className="h-1 rounded-full"
            style={{
              width: i === index ? 26 : 10,
              background: i === index
                ? (index === 0 ? 'var(--color-ink)' : 'var(--color-yellow)')
                : (index === 0 ? '#8E88A0' : 'rgba(255,255,255,0.45)'),
              transition: 'width 0.35s ease, background 0.35s ease',
            }}
          />
        ))}
      </div>

      {/* Desktop affordances — the deck is drag/keyboard driven on touch. */}
      <Arrow side="left"  show={index > 0}    onClick={() => go(index - 1)} dark={index === 0} />
      <Arrow side="right" show={index < last} onClick={() => go(index + 1)} dark={index === 0} />

      <span className="sr-only" aria-live="polite">
        {active ? `${active.name}, panel ${index + 1} of ${count}` : `Intro, panel 1 of ${count}`}
      </span>
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

function Intro({ width }) {
  return (
    <div
      className="relative box-border flex h-full shrink-0 flex-col overflow-hidden bg-white px-6 pb-[104px] pt-[30px] lg:justify-center lg:px-24"
      style={{ width }}
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
          <span className="t-eyebrow">Week 31 · four domains</span>
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
          Four domains, eight shifts this week, told as stories. Swipe and they come to you.
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

function DomainPanel({ domain, width, active, onOpen, onOpenShift }) {
  return (
    <div
      className="box-border flex h-full shrink-0 flex-col px-6 pb-[74px] pt-[30px] text-white lg:justify-center lg:px-24"
      style={{ width, backgroundImage: domain.grad }}
    >
      <div className="mx-auto flex w-full flex-1 flex-col lg:max-w-[1180px] lg:flex-none lg:flex-row lg:items-center lg:gap-20">
        {/* Left — the headline block. This is the entire panel on mobile. */}
        <div className="flex flex-1 flex-col lg:min-w-0">
          <div className="flex items-center justify-between font-mono text-[11px] opacity-90 lg:justify-start lg:gap-6" style={{ letterSpacing: '0.08em' }}>
            <span>{domain.num} / 04</span>
            <span>horizon {domain.horizon}</span>
          </div>

          <div className="mt-[26px] text-[15px] italic opacity-90 lg:text-[19px]">Everything that is about to change in</div>
          <div
            className="t-display mt-1.5 text-[clamp(40px,12vw,46px)] leading-[0.98] lg:text-[clamp(64px,6.4vw,112px)]"
            style={{ letterSpacing: '-0.035em' }}
          >
            {domain.name}
          </div>
          <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 lg:max-w-[520px] lg:text-[19px]">{domain.blurb}</p>

          <div className="mt-auto flex flex-col border-t pt-5 lg:mt-9 lg:border-t-0 lg:pt-0" style={{ borderColor: 'rgba(255,255,255,0.3)' }}>
            <button type="button" onClick={onOpen} className="pill-yellow mt-5 self-start lg:mt-0 lg:h-12 lg:px-7 lg:text-[15px]" tabIndex={active ? 0 : -1}>
              All {domain.count} shifts <span className="text-[15px]">›</span>
            </button>
          </div>
        </div>

        {/* Right — a peek at what's inside. Desktop only: on a wide viewport the
            gradient is otherwise dead space, and naming the shifts gives the
            panel something to read rather than only to look at. */}
        <div className="hidden w-[38%] max-w-[420px] shrink-0 lg:block">
          <div className="t-eyebrow opacity-80">In this domain</div>
          <ul className="mt-4">
            {domain.keyShifts.slice(0, 4).map((s) => (
              <li key={s.id} style={{ borderTop: '1px solid rgba(255,255,255,0.28)' }}>
                <button
                  type="button"
                  tabIndex={active ? 0 : -1}
                  onClick={() => onOpenShift(s)}
                  className="group flex w-full items-start gap-3.5 py-3.5 text-left opacity-90 transition-opacity hover:opacity-100"
                >
                  <span className="mt-0.5 font-mono text-[11px] opacity-70">{s.num}</span>
                  <span className="t-title flex-1 text-[15px] leading-[1.22]">{s.title}</span>
                  <span className="mt-0.5 text-[15px] opacity-0 transition-opacity group-hover:opacity-100">›</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
