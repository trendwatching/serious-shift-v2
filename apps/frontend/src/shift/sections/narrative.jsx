/** Longer-form editorial blocks: peel tabs, the tension band, the pull quote. */
import { useLayoutEffect, useRef, useState } from 'react'
import { Eyebrow } from './primitives'

export function PeelTabs({ whatChanging, whyNow }) {
  const cards = [
    whatChanging && { label: "What's changing", text: whatChanging },
    whyNow && { label: 'Why now', text: whyNow },
  ].filter(Boolean)

  const [top, setTop] = useState(0)
  const [h, setH] = useState(0)
  const refs = useRef([])

  // The stack is absolutely positioned, so it needs an explicit height: the
  // tallest body plus the tab. Measured once per content change.
  useLayoutEffect(() => {
    const tallest = refs.current.reduce((m, el) => (el ? Math.max(m, el.scrollHeight) : m), 0)
    if (tallest) setH(tallest)
  }, [whatChanging, whyNow])

  if (!cards.length) return null
  if (cards.length === 1) {
    return (
      <div className="rounded-[20px] p-5 text-white" style={{ backgroundImage: 'var(--a-grad)' }}>
        <div className="t-eyebrow mb-2.5" style={{ letterSpacing: '0.04em' }}>{cards[0].label}</div>
        <div className="text-[14.5px] leading-[1.58] lg:text-[16.5px] lg:leading-[1.62] text-pretty">{cards[0].text}</div>
      </div>
    )
  }

  return (
    <div className="relative" style={{ height: (h || 150) + 96 }}>
      {cards.map((c, i) => {
        const front = i === top
        const left = i === 0
        const bg = front ? 'var(--a-grad)' : 'var(--grad-grey)'
        const fg = front ? '#fff' : 'var(--color-ink)'
        return (
          <div key={c.label} className="absolute inset-0 pointer-events-none" style={{ zIndex: front ? 12 : 10 }}>
            <button
              type="button" onClick={() => setTop(i)} aria-pressed={front}
              className="absolute top-0 h-[54px] box-border pointer-events-auto flex items-center justify-center px-3 rounded-t-[20px]"
              style={{
                left: left ? 0 : '48%', right: left ? '52%' : 0,
                backgroundImage: bg, transition: 'background-image 0.35s ease',
              }}
            >
              <span
                className="t-eyebrow whitespace-nowrap"
                style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.04em', color: fg, transition: 'color 0.3s ease' }}
              >{c.label}</span>
            </button>
            <div
              className="absolute left-0 right-0 bottom-0 box-border overflow-hidden pointer-events-auto p-[22px_20px]"
              style={{
                top: 50,
                borderRadius: left ? '0 20px 20px 20px' : '20px 0 20px 20px',
                backgroundImage: bg, transition: 'background-image 0.35s ease',
                boxShadow: '0 10px 26px rgba(27,22,32,0.14)',
              }}
            >
              <div
                ref={(el) => { refs.current[i] = el }}
                className="text-[14.5px] leading-[1.58] lg:text-[16.5px] lg:leading-[1.62] text-pretty"
                style={{ color: fg, opacity: front ? 1 : 0, transition: 'opacity 0.3s ease' }}
              >{c.text}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function TensionBand({ quote, label = 'Consumer tension' }) {
  if (!quote) return null
  return (
    <div className="bleed py-8 text-white flex flex-col gap-3.5" style={{ background: 'var(--color-dark)' }}>
      <Eyebrow color="var(--color-yellow)">{label}</Eyebrow>
      <span className="t-display text-[24px] leading-[1.28] text-pretty lg:text-[30px]" style={{ fontWeight: 600, letterSpacing: '-0.018em' }}>
        “{quote}”
      </span>
    </div>
  )
}

/* ── Pull quote: the editorial verdict, set right after From/To ──────────── */

export function PullQuote({ quote }) {
  if (!quote) return null
  return (
    <figure className="relative m-0 py-2 pl-5 lg:pl-7">
      <span className="absolute left-0 top-2 bottom-2 w-1 rounded-full" style={{ backgroundImage: 'var(--a-grad)' }} />
      <blockquote
        className="t-display m-0 text-[21px] leading-[1.3] text-pretty lg:text-[27px]"
        style={{ fontWeight: 600, letterSpacing: '-0.018em', color: 'var(--color-ink)' }}
      >
        “{quote}”
      </blockquote>
    </figure>
  )
}
