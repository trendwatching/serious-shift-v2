/** Longer-form editorial blocks: peel tabs, the tension band, the pull quote. */
import { useState } from 'react'
import { Eyebrow } from './primitives'

/**
 * The two-card "folder" — what's changing / why now.
 *
 * Both cards occupy the same grid cell, so the stack is exactly as tall as its
 * tallest body and the shorter one stretches to match. That is the whole reason
 * for the grid: the previous version positioned the cards absolutely and so had
 * to measure the text in a layout effect and set an explicit pixel height. That
 * height was measured once and never revisited, so any width change — a window
 * resize, or crossing a breakpoint into a different type size — left the text
 * reflowing inside a box that stayed the size it was on first paint. CSS can
 * size this correctly on its own; JS could only ever be measuring the past.
 */
export function PeelTabs({ whatChanging, whyNow }) {
  const cards = [
    whatChanging && { label: "What's changing", text: whatChanging },
    whyNow && { label: 'Why now', text: whyNow },
  ].filter(Boolean)

  const [top, setTop] = useState(0)

  if (!cards.length) return null
  if (cards.length === 1) {
    return (
      <div className="rounded-[20px] p-5 text-white lg:p-7" style={{ backgroundImage: 'var(--a-grad)' }}>
        <div className="t-eyebrow mb-2.5" style={{ letterSpacing: '0.04em' }}>{cards[0].label}</div>
        <div className="t-prose text-pretty">{cards[0].text}</div>
      </div>
    )
  }

  return (
    <div className="grid">
      {cards.map((c, i) => {
        const front = i === top
        const left = i === 0
        const bg = front ? 'var(--a-grad)' : 'var(--grad-grey)'
        const fg = front ? '#fff' : 'var(--color-ink)'
        return (
          <div
            key={c.label}
            className="col-start-1 row-start-1 flex flex-col pointer-events-none"
            style={{ zIndex: front ? 12 : 10 }}
          >
            {/* Tab strip. The button is positioned inside it so the two tabs
                sit side by side while each card keeps its own full-width body. */}
            <div className="relative h-[54px]">
              <button
                type="button" onClick={() => setTop(i)} aria-pressed={front}
                className="absolute inset-y-0 box-border pointer-events-auto flex items-center justify-center px-3 rounded-t-[20px]"
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
            </div>
            {/* -4px pulls the body up under the tab, as in the design. */}
            <div
              className="-mt-1 flex-1 box-border overflow-hidden pointer-events-auto p-[22px_20px] lg:p-7"
              style={{
                borderRadius: left ? '0 20px 20px 20px' : '20px 0 20px 20px',
                backgroundImage: bg, transition: 'background-image 0.35s ease',
                boxShadow: '0 10px 26px rgba(27,22,32,0.14)',
              }}
            >
              <div
                className="t-prose text-pretty"
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
    <div className="bleed py-8 text-white flex flex-col gap-3.5 md:py-10 lg:py-14" style={{ background: 'var(--color-dark)' }}>
      <Eyebrow color="var(--color-yellow)">{label}</Eyebrow>
      <span className="t-display text-[24px] leading-[1.28] text-pretty md:text-[27px] lg:text-[32px]" style={{ fontWeight: 600, letterSpacing: '-0.018em' }}>
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
        className="t-display m-0 text-[21px] leading-[1.3] text-pretty md:text-[24px] lg:text-[27px]"
        style={{ fontWeight: 600, letterSpacing: '-0.018em', color: 'var(--color-ink)' }}
      >
        “{quote}”
      </blockquote>
    </figure>
  )
}
