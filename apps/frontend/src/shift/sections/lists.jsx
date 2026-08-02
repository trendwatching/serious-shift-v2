/** List-shaped sections: sub-shifts, needs, innovations, timeline, industries, territories. */
import { useId, useRef, useState } from 'react'
import { Eyebrow, SectionHead } from './primitives'
import { CONTACT_URL } from '../site'
import { quoteTitle } from '../theme'

const WHEN = ['0–12 months', '1–3 years', '3–10 years']

export function SubShiftList({ subs, onOpen }) {
  if (!subs?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title={`The ${subs.length} sub-shift${subs.length === 1 ? '' : 's'}`} aside="Tap to open" />
      <div className="grid gap-2.5 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
        {subs.map((b, i) => (
          <button
            key={b.id} type="button" onClick={() => onOpen(b)}
            className="card card-lift a-rise relative overflow-hidden text-left flex flex-col gap-[9px] pl-[17px] pr-4 py-[15px] lg:pl-[21px] lg:pr-5 lg:py-[18px]"
            style={{ animationDelay: `${(0.05 + i * 0.06).toFixed(2)}s` }}
          >
            <span className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundImage: 'var(--a-grad)' }} />
            <span className="flex items-center gap-2">
              <span
                className="inline-flex items-center h-[22px] px-[9px] rounded-full t-eyebrow"
                style={{ background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 10, fontWeight: 800, letterSpacing: '0.14em' }}
              >Sub-shift {b.num}</span>
              <span className="ml-auto text-[11.5px] font-semibold" style={{ color: 'var(--a-ink)' }}>Open</span>
              <span
                className="grid place-items-center w-[22px] h-[22px] rounded-full text-[13px]"
                style={{ background: 'var(--a-wash)', color: 'var(--a-ink)' }}
              >↗</span>
            </span>
            <span className="t-title text-[15px] leading-[1.24] lg:text-[17px]">{quoteTitle(b.title)}</span>
            <span className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{b.dek}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function HumanNeeds({ needs }) {
  const [pick, setPick] = useState('u')
  const id = useId()
  if (!needs?.unlocked && !needs?.threatened) return null

  const card = (key, label, text, grad, shadow) => {
    const on = pick === key
    return (
      <button
        type="button" onClick={() => setPick(key)} onMouseEnter={() => setPick(key)} aria-expanded={on} aria-controls={`${id}-${key}`}
        className="box-border min-w-0 rounded-[18px] px-4 py-[18px] text-white text-left flex flex-col gap-2.5 overflow-hidden lg:px-6 lg:py-6"
        style={{
          flex: on ? '3 1 0%' : '1 1 0%',
          backgroundImage: grad,
          opacity: on ? 1 : 0.82,
          boxShadow: on ? shadow : '0 3px 12px rgba(27,22,32,0.08)',
          transition: 'flex-grow 0.45s var(--ease-out), opacity 0.35s ease, box-shadow 0.35s ease',
        }}
      >
        <span className="t-eyebrow whitespace-nowrap" style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.12em' }}>{label}</span>
        {/* 0fr → 1fr rather than a max-height: the copy runs to 441 characters
            and the old 260px cap simply cut the end off the longer ones. */}
        <span
          id={`${id}-${key}`}
          aria-hidden={!on}
          inert={on ? undefined : ''}
          className="grid overflow-hidden"
          style={{
            gridTemplateRows: on ? '1fr' : '0fr',
            opacity: on ? 1 : 0,
            transition: 'grid-template-rows 0.45s var(--ease-out), opacity 0.3s ease',
          }}
        ><span className="t-body min-h-0 text-pretty">{text}</span></span>
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-2.5">
      <Eyebrow as="h2">Human needs</Eyebrow>
      <div className="flex gap-2.5 items-stretch lg:gap-4">
        {card('u', 'Unlocked', needs.unlocked, 'var(--pos-grad)', '0 12px 26px var(--pos-shadow)')}
        {card('t', 'Threatened', needs.threatened, 'var(--a-grad)', '0 12px 26px var(--a-shadow)')}
      </div>
    </div>
  )
}

export function Innovations({ items }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Innovations in the wild" aside={`${items.length}`} />
      <div className="grid gap-2.5 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
        {items.map((n, i) => {
          const Card = n.url ? 'a' : 'div'
          return (
            <Card
              key={i}
              {...(n.url ? { href: n.url, target: '_blank', rel: 'noopener noreferrer' } : {})}
              className="card card-lift flex flex-col gap-2 overflow-hidden p-4 lg:p-5"
            >
              {n.image && (
                <img src={n.image} alt="" loading="lazy" decoding="async"
                     className="mb-1 h-[132px] w-full rounded-xl object-cover lg:h-[160px]" />
              )}
              {n.brand && (
                <span className="t-eyebrow" style={{ color: 'var(--a-ink)', fontSize: 10, letterSpacing: '0.14em' }}>
                  {n.brand}
                </span>
              )}
              <span className="t-display text-[15px] leading-[1.25] lg:text-[17px]" style={{ letterSpacing: '-0.01em' }}>{n.title}</span>
              {n.description && (
                <span className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{n.description}</span>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}

export function Timeline({ steps }) {
  if (!steps?.length) return null
  // The sweep is a three-phase loop. Real data is always three steps, but a
  // fourth would have asked for a `ssFill4` that doesn't exist and rendered
  // inert, so anything past the third simply sits still.
  const anim = (i) => (i < 3 ? { animation: `ssFill${i + 1} 12s linear infinite` } : null)
  const dotAnim = (i) => (i < 3 ? { animation: `ssDot${i + 1} 12s linear infinite` } : null)

  return (
    <div className="flex flex-col gap-2.5">
      <Eyebrow as="h2">Now / next / beyond</Eyebrow>
      {/* A rail down the left on mobile; across the top on desktop, where
          "now → next → beyond" reads as the horizontal thing it is and three
          stacked cards become one row. */}
      <div className="relative flex flex-col gap-3 pl-[26px] lg:grid lg:auto-cols-fr lg:grid-flow-col lg:gap-5 lg:pl-0 lg:pt-7">
        <span
          className="absolute left-[6px] top-2.5 bottom-2.5 w-0.5 lg:inset-x-6 lg:top-[6px] lg:bottom-auto lg:h-0.5 lg:w-auto"
          style={{ background: 'var(--color-hairline)' }}
        />
        {steps.map((h, i) => (
          <div
            key={h.label || i}
            className="relative box-border flex flex-col gap-1.5 rounded-2xl px-4 py-[15px] lg:px-5 lg:py-5"
            style={{ background: 'var(--color-paper)', color: 'var(--color-ink-strong)', ...anim(i) }}
          >
            <span
              className="absolute box-border h-[13px] w-[13px] rounded-full left-[-26px] top-[18px] lg:left-6 lg:top-[-28px]"
              style={{ border: '2.5px solid var(--a)', background: '#fff', ...dotAnim(i) }}
            />
            <span className="flex items-baseline gap-2.5">
              <span className="t-display text-[14.5px] lg:text-[16px]" style={{ letterSpacing: '-0.005em' }}>{h.label}</span>
              <span className="ml-auto font-mono text-[11px] opacity-75">{WHEN[i] || ''}</span>
            </span>
            <span className="t-body text-pretty">{h.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Industries({ items }) {
  const [i, setI] = useState(0)
  const id = useId()
  const tabs = useRef([])
  if (!items?.length) return null
  const active = items[Math.min(i, items.length - 1)]
  const onKeyDown = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? items.length - 1
        : (i + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length
    setI(next)
    tabs.current[next]?.focus()
  }
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Implications by industry" aside={`${Math.min(i, items.length - 1) + 1} of ${items.length}`} />
      {/* Mobile scrolls the chip row; desktop has room to wrap, which shows the
          whole sector list at once instead of hiding it behind a swipe. */}
      <div
        role="tablist"
        aria-label="Industries"
        onKeyDown={onKeyDown}
        className="bleed-m carousel-scrollbar-hidden flex gap-2 overflow-x-auto pt-0.5 pb-1 lg:flex-wrap lg:overflow-x-visible"
        style={{ scrollSnapType: 'x proximity' }}
      >
        {items.map((n, k) => {
          const on = k === i
          return (
            <button
              key={n.name} ref={(node) => { tabs.current[k] = node }} id={`${id}-tab-${k}`}
              type="button" role="tab" aria-selected={on} aria-controls={`${id}-panel`} tabIndex={on ? 0 : -1}
              onClick={() => setI(k)}
              className="flex h-11 shrink-0 items-center whitespace-nowrap rounded-full px-3.5 text-[12.5px]"
              style={{
                scrollSnapAlign: 'center', fontFamily: 'var(--font-display)', fontWeight: 650,
                border: `1px solid ${on ? 'var(--color-ink)' : 'var(--color-hairline)'}`,
                background: on ? 'var(--color-ink)' : '#fff',
                color: on ? '#fff' : 'var(--color-ink-soft)',
                transition: 'background 0.28s ease, color 0.28s ease, border-color 0.28s ease',
              }}
            >{n.name}</button>
          )
        })}
      </div>
      <div key={active.name} id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-tab-${i}`} tabIndex={0} className="card a-rise flex flex-col gap-2 p-[18px] md:p-6 lg:gap-3 lg:p-7" style={{ animationDuration: '0.42s' }}>
        <h3 className="t-display text-[15px] md:text-[17px] lg:text-[19px]" style={{ letterSpacing: '-0.01em' }}>{active.name}</h3>
        {/* The one card in the wide track that holds running prose, so it takes
            the prose measure rather than stretching to 1120px. */}
        <span className="t-prose max-w-[var(--measure)] text-pretty" style={{ color: 'var(--color-ink-soft)' }}>{active.text}</span>
      </div>
    </div>
  )
}

export function Territories({ items }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Opportunity territories" aside={<span className="lg:hidden">Scroll ›</span>} />
      {/* A scroller on mobile; on desktop the cards fit as a grid, so show them
          all rather than making a wide screen swipe. */}
      <div
        className="bleed-m carousel-scrollbar-hidden flex gap-3 overflow-x-auto pt-0.5 pb-1.5 lg:grid lg:grid-cols-2 lg:gap-5 lg:overflow-x-visible xl:grid-cols-3"
        style={{ scrollSnapType: 'x mandatory' }}
      >
        {items.map((t, i) => (
          <div
            key={t.name}
            className="card card-lift a-rise box-border flex w-[236px] shrink-0 flex-col gap-[9px] p-4 lg:w-auto lg:p-5"
            style={{ scrollSnapAlign: 'center', animationDelay: `${(0.05 + i * 0.07).toFixed(2)}s` }}
          >
            <span
              className="grid place-items-center w-[26px] h-[26px] rounded-full t-display text-xs"
              style={{ background: 'var(--color-yellow)', color: 'var(--color-ink)', fontWeight: 800, letterSpacing: 0 }}
            >{i + 1}</span>
            <span className="t-display text-[15px] leading-[1.2] lg:text-[17px]" style={{ letterSpacing: '-0.01em' }}>{t.name}</span>
            <span className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{t.text}</span>
          </div>
        ))}
        <div
          className="a-rise box-border flex w-[250px] shrink-0 flex-col gap-2.5 rounded-[18px] px-[18px] py-5 text-white lg:w-auto lg:p-6"
          style={{ scrollSnapAlign: 'center', backgroundImage: 'linear-gradient(rgba(13,11,16,0.34), rgba(13,11,16,0.34)), var(--a-grad-hot)', boxShadow: '0 12px 26px var(--a-shadow)', animationDelay: '0.34s' }}
        >
          <span className="t-eyebrow" style={{ fontSize: 10.5, fontWeight: 800, color: 'var(--color-yellow)' }}>Work with us</span>
          <span className="text-[21px] leading-[1.14] lg:text-[24px]" style={{ fontFamily: 'var(--font-title)' }}>Don’t see your angle here?</span>
          <span className="text-[13px] leading-[1.48] opacity-95 text-pretty lg:text-[14.5px] lg:leading-[1.55]">
            These territories are starting points, not limits. We work with organisations to find where a shift like this creates real commercial space for their specific context.
          </span>
          <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer" className="pill-yellow mt-auto h-11 self-start px-4 text-[13.5px]">
            Contact us <span className="text-[15px]">→</span>
          </a>
        </div>
      </div>
    </div>
  )
}
