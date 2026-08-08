/**
 * The five-panel swipe deck: an intro screen followed by one full-bleed panel
 * per domain.
 *
 * Performance notes — this is the page every visitor lands on:
 *  • The track is `width: 500%` and each panel `20%`, so the offset is a
 *    percentage. No measuring, no ResizeObserver, correct at any viewport.
 *  • During a drag the transform is written straight to the node through a
 *    ref. React does not re-render on pointermove, so a drag costs one
 *    compositor property per frame instead of a reconcile.
 *  • Only the settled index is state, which is what the pager and the hint
 *    read — they change once per swipe, not once per frame.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { useDomains } from '../lib/useDomains'
import { failureState } from '../lib/failure'
import HomePanel from './HomePanel'
import DomainPanel from './DomainPanel'

const THRESHOLD = 56    // px of travel that commits a swipe
const DAMP = 0.85       // the design damps the finger everywhere, not just at the ends
const STEP_MS = 170     // a badge tap walks the deck one panel at a time

export default function Deck() {
  const { domains, meta, unavailable, error, retry } = useDomains()
  useDocumentMeta(undefined, meta?.shiftCount
    ? `${meta.domainCount} domains and ${meta.shiftCount} shifts in the current weekly map.`
    : undefined)

  const [index, setIndex] = useState(0)
  const [fast, setFast] = useState(false)
  const trackRef = useRef(null)
  const drag = useRef(null)
  const walk = useRef(null)

  const count = domains.length + 1
  const step = 100 / count
  const last = count - 1

  const paint = useCallback((i, dx = 0) => {
    const el = trackRef.current
    if (el) el.style.transform = `translate3d(calc(${(-i * step).toFixed(4)}% + ${dx}px), 0, 0)`
  }, [step])

  useEffect(() => { paint(index) }, [index, paint])
  useEffect(() => () => clearInterval(walk.current), [])

  const settle = () => (fast
    ? 'transform 0.16s cubic-bezier(0.4,0,0.3,1)'
    : 'transform 0.55s var(--ease-deck)')

  /**
   * Walk to a panel one step at a time rather than cutting straight there.
   * The design does this deliberately: tapping "Consumers" from the intro
   * flies you past Society, Economy and Organizations, so you learn the deck
   * has four panels and roughly what is on them.
   */
  const jump = useCallback((target) => {
    clearInterval(walk.current)
    setFast(true)
    walk.current = setInterval(() => {
      setIndex((cur) => {
        if (cur === target) {
          clearInterval(walk.current)
          setFast(false)
          return cur
        }
        return cur + (target > cur ? 1 : -1)
      })
    }, STEP_MS)
  }, [])

  const go = useCallback((i) => setIndex(Math.max(0, Math.min(last, i))), [last])

  const onPointerDown = (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (e.target.closest?.('button, a, input, textarea, select, [role="button"]')) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, dx: 0, axis: null }
    if (trackRef.current) trackRef.current.style.transition = 'none'
  }

  const onPointerMove = (e) => {
    const d = drag.current
    if (!d || d.id !== e.pointerId) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    // Commit to one axis and stay committed, or the deck fights the page.
    if (!d.axis && Math.abs(dx) + Math.abs(dy) > 8) d.axis = Math.abs(dx) > Math.abs(dy) * 1.15 ? 'x' : 'y'
    if (d.axis !== 'x') return
    d.dx = dx
    paint(index, dx * DAMP)
  }

  const endDrag = (e) => {
    const d = drag.current
    if (!d || (e?.pointerId !== undefined && d.id !== e.pointerId)) return
    drag.current = null
    if (e?.currentTarget?.hasPointerCapture?.(d.id)) e.currentTarget.releasePointerCapture(d.id)
    if (trackRef.current) trackRef.current.style.transition = settle()
    const dx = d.axis === 'x' ? d.dx : 0
    const next = Math.abs(dx) > THRESHOLD ? index + (dx < 0 ? 1 : -1) : index
    const clamped = Math.max(0, Math.min(last, next))
    if (clamped === index) paint(index)
    else setIndex(clamped)
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
      if (e.target.closest?.('button, a, input, textarea, select, [contenteditable="true"], dialog')) return
      if (e.key === 'ArrowRight') go(index + 1)
      else if (e.key === 'ArrowLeft') go(index - 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [index, go])

  // No loading state. The intro panel is entirely static — headline, standfirst
  // and four badges whose names come from DECK — so it renders on the first
  // paint and the map streams in behind it.
  //
  // The skeleton it replaced was `min-h-dvh` PLUS `--topbar` of padding, where
  // the deck is exactly `100dvh`. Swapping one for the other collapsed the
  // document by 84px the instant the map arrived: a 0.082 layout shift on the
  // first screen of the site, which is what the stutter was. Panels 2–5 arrive
  // off-screen, so nothing the reader is looking at moves at all.

  if (unavailable) {
    const failure = failureState(error)
    return (
      <div className="screen text-center">
        <div className="flex max-w-[390px] flex-col items-center gap-4">
          <p className="t-eyebrow" style={{ color: 'var(--color-ink-meta)' }}>{failure.eyebrow}</p>
          <h1 className="t-display text-[28px] font-bold" style={{ letterSpacing: '-0.03em' }}>{failure.title}</h1>
          <p style={{ color: 'var(--color-ink-row)' }}>{failure.body}</p>
          <button type="button" className="pill-yellow" onClick={retry}>Retry</button>
        </div>
      </div>
    )
  }

  const active = index === 0 ? null : domains[index - 1]

  return (
    <>
      {/* The deck starts 14px UNDER the top of the bar, so the bar overlaps it.
          That overlap is the design's, and it is why the bar is absolute. */}
      <section
        className="relative overflow-hidden bg-white"
        style={{ height: 'calc(100dvh - var(--topbar) + 14px)', marginTop: 'calc(var(--topbar) - 14px)' }}
        aria-label="Current shift domains"
        aria-roledescription="carousel"
      >
        <div
          ref={trackRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onLostPointerCapture={endDrag}
          className="flex h-full cursor-grab active:cursor-grabbing"
          style={{ width: `${count * 100}%`, touchAction: 'pan-y', willChange: 'transform', transition: settle() }}
        >
          <HomePanel width={`${step}%`} active={index === 0} count={count} domains={domains} onJump={jump} />
          {domains.map((d, i) => (
            <DomainPanel
              key={d.id} domain={d} width={`${step}%`}
              active={index === i + 1} position={i + 2} count={count} total={domains.length}
            />
          ))}
        </div>

        <div
          className="pointer-events-none absolute inset-x-0 text-center uppercase"
          style={{ bottom: 54, fontSize: 11.5, letterSpacing: '0.14em', color: index === 0 ? '#3E3949' : 'rgba(255,255,255,0.85)' }}
        >
          {index === last ? 'Swipe back' : `Swipe for ${domains[index]?.name ?? ''}`}
        </div>

        {/* Indicators, not controls — the design makes them inert and the deck
            is driven by the swipe, the keyboard and the intro badges. */}
        <div className="pointer-events-none absolute inset-x-0 flex items-center justify-center" style={{ bottom: 32, gap: 8 }}>
          {Array.from({ length: count }, (_, i) => (
            <span
              key={i}
              className="block rounded-full"
              style={{
                height: 4,
                width: i === index ? 26 : 10,
                background: i === index
                  ? (index === 0 ? '#1B1620' : '#FDFF85')
                  : (index === 0 ? '#8E88A0' : 'rgba(255,255,255,0.45)'),
                transition: 'width 0.35s ease, background 0.35s ease',
              }}
            />
          ))}
        </div>

        <span className="sr-only" aria-live="polite">
          {active ? `${active.name}, panel ${index + 1} of ${count}` : `Intro, panel 1 of ${count}`}
        </span>
      </section>
    </>
  )
}
