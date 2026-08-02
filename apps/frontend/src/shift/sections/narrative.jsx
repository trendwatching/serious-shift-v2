/** Longer-form editorial blocks: peel tabs, the tension band, the pull quote. */
import { useId, useRef, useState } from 'react'
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
  const id = useId()
  const tabs = useRef([])

  const onKeyDown = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? cards.length - 1
        : (top + (event.key === 'ArrowRight' ? 1 : -1) + cards.length) % cards.length
    setTop(next)
    tabs.current[next]?.focus()
  }

  if (!cards.length) return null
  if (cards.length === 1) {
    return (
      <div className="rounded-[20px] p-5 text-white lg:p-7" style={{ backgroundImage: 'var(--a-grad)' }}>
        <h2 className="t-eyebrow mb-2.5" style={{ letterSpacing: '0.04em' }}>{cards[0].label}</h2>
        <div className="t-prose text-pretty">{cards[0].text}</div>
      </div>
    )
  }

  return (
    <div>
      <h2 className="sr-only">What’s changing and why now</h2>
      <div role="tablist" aria-label="Shift context" className="grid h-[54px] grid-cols-2" onKeyDown={onKeyDown}>
        {cards.map((card, index) => {
          const selected = index === top
          return (
            <button
              key={card.label}
              ref={(node) => { tabs.current[index] = node }}
              id={`${id}-tab-${index}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${id}-panel-${index}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setTop(index)}
              className="flex items-center justify-center rounded-t-[20px] px-3"
              style={{ backgroundImage: selected ? 'var(--a-grad)' : 'var(--grad-grey)' }}
            ><span className="t-eyebrow whitespace-nowrap" style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.04em', color: selected ? '#fff' : 'var(--color-ink)' }}>{card.label}</span></button>
          )
        })}
      </div>
      {cards.map((card, index) => (
        <div
          key={card.label}
          id={`${id}-panel-${index}`}
          role="tabpanel"
          aria-labelledby={`${id}-tab-${index}`}
          hidden={index !== top}
          tabIndex={0}
          className="-mt-1 box-border p-[22px_20px] text-white lg:p-7"
          style={{ borderRadius: index === 0 ? '0 20px 20px 20px' : '20px 0 20px 20px', backgroundImage: 'var(--a-grad)', boxShadow: '0 10px 26px rgba(27,22,32,0.14)' }}
        ><div className="t-prose text-pretty">{card.text}</div></div>
      ))}
    </div>
  )
}

export function TensionBand({ quote, label = 'Consumer tension' }) {
  if (!quote) return null
  return (
    <div className="bleed py-8 text-white flex flex-col gap-3.5 md:py-10 lg:py-14" style={{ background: 'var(--color-dark)' }}>
      <Eyebrow as="h2" color="var(--color-yellow)">{label}</Eyebrow>
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
      <figcaption className="sr-only"><h2>Editorial perspective</h2></figcaption>
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
