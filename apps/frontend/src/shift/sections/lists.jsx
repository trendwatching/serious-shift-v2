/** List-shaped sections: sub-shifts, needs, innovations, timeline, industries, territories. */
import { useState } from 'react'
import { Eyebrow, SectionHead } from './primitives'
import { CONTACT_URL } from '../site'
import { quoteTitle } from '../theme'

const WHEN = ['0–12 months', '1–3 years', '3–10 years']

export function SubShiftList({ subs, onOpen }) {
  if (!subs?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title={`The ${subs.length} sub-shift${subs.length === 1 ? '' : 's'}`} aside="Tap to open" />
      <div className="grid gap-2.5 lg:grid-cols-2">
        {subs.map((b, i) => (
          <button
            key={b.id} type="button" onClick={() => onOpen(b)}
            className="card card-lift a-rise relative overflow-hidden text-left flex flex-col gap-[9px] pl-[17px] pr-4 py-[15px]"
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
            <span className="t-title text-[15px] leading-[1.24]">{quoteTitle(b.title)}</span>
            <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: '#5C5768' }}>{b.dek}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function HumanNeeds({ needs }) {
  const [pick, setPick] = useState('u')
  if (!needs?.unlocked && !needs?.threatened) return null

  const card = (key, label, text, grad, shadow) => {
    const on = pick === key
    return (
      <button
        type="button" onClick={() => setPick(key)} onMouseEnter={() => setPick(key)} aria-expanded={on}
        className="box-border min-w-0 rounded-[18px] px-4 py-[18px] text-white text-left flex flex-col gap-2.5 overflow-hidden"
        style={{
          flex: on ? '3 1 0%' : '1 1 0%',
          backgroundImage: grad,
          opacity: on ? 1 : 0.82,
          boxShadow: on ? shadow : '0 3px 12px rgba(27,22,32,0.08)',
          transition: 'flex-grow 0.45s var(--ease-out), opacity 0.35s ease, box-shadow 0.35s ease',
        }}
      >
        <span className="t-eyebrow whitespace-nowrap" style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.12em' }}>{label}</span>
        <span
          className="text-[14px] leading-[1.5] text-pretty overflow-hidden"
          style={{ opacity: on ? 1 : 0, maxHeight: on ? 260 : 0, transition: 'opacity 0.3s ease, max-height 0.45s var(--ease-out)' }}
        >{text}</span>
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-2.5">
      <Eyebrow>Human needs</Eyebrow>
      <div className="flex gap-2.5 items-stretch">
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
      <div className="grid gap-2.5 lg:grid-cols-2">
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
                     className="mb-1 h-[132px] w-full rounded-xl object-cover" />
              )}
              {n.brand && (
                <span className="t-eyebrow" style={{ color: 'var(--a-ink)', fontSize: 10, letterSpacing: '0.14em' }}>
                  {n.brand}
                </span>
              )}
              <span className="t-display text-[15px] leading-[1.25]" style={{ letterSpacing: '-0.01em' }}>{n.title}</span>
              {n.description && (
                <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{n.description}</span>
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
  return (
    <div className="flex flex-col gap-2.5">
      <Eyebrow>Now / next / beyond</Eyebrow>
      <div className="relative pl-[26px] flex flex-col gap-3">
        <span className="absolute left-[6px] top-2.5 bottom-2.5 w-0.5" style={{ background: '#E6E2EE' }} />
        {steps.map((h, i) => (
          <div
            key={h.label || i}
            className="relative box-border rounded-2xl px-4 py-[15px] flex flex-col gap-1.5"
            style={{ background: '#FBFAFD', color: 'var(--color-ink-strong)', animation: `ssFill${i + 1} 12s linear infinite` }}
          >
            <span
              className="absolute w-[13px] h-[13px] rounded-full box-border"
              style={{ left: -26, top: 18, border: '2.5px solid var(--a)', background: '#fff', animation: `ssDot${i + 1} 12s linear infinite` }}
            />
            <span className="flex items-baseline gap-2.5">
              <span className="t-display text-[14.5px]" style={{ letterSpacing: '-0.005em' }}>{h.label}</span>
              <span className="ml-auto font-mono text-[11px] opacity-75">{WHEN[i] || ''}</span>
            </span>
            <span className="text-[13.5px] leading-[1.5] text-pretty">{h.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Industries({ items }) {
  const [i, setI] = useState(0)
  if (!items?.length) return null
  const active = items[Math.min(i, items.length - 1)]
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Implications by industry" aside={`${Math.min(i, items.length - 1) + 1} of ${items.length}`} />
      {/* Mobile scrolls the chip row; desktop has room to wrap, which shows the
          whole sector list at once instead of hiding it behind a swipe. */}
      <div
        className="bleed flex gap-2 overflow-x-auto pt-0.5 pb-1 lg:flex-wrap lg:overflow-x-visible"
        style={{ scrollSnapType: 'x proximity' }}
      >
        {items.map((n, k) => {
          const on = k === i
          return (
            <button
              key={n.name} type="button" onClick={() => setI(k)}
              className="flex h-[34px] shrink-0 items-center whitespace-nowrap rounded-full px-3.5 text-[12.5px]"
              style={{
                scrollSnapAlign: 'center', fontFamily: 'var(--font-display)', fontWeight: 650,
                border: `1px solid ${on ? 'var(--color-ink)' : '#E7E3EF'}`,
                background: on ? 'var(--color-ink)' : '#fff',
                color: on ? '#fff' : 'var(--color-ink-soft)',
                transition: 'background 0.28s ease, color 0.28s ease, border-color 0.28s ease',
              }}
            >{n.name}</button>
          )
        })}
      </div>
      <div key={active.name} className="card a-rise flex flex-col gap-2 p-[18px] lg:gap-3 lg:p-7" style={{ animationDuration: '0.42s' }}>
        <span className="t-display text-[15px] lg:text-[19px]" style={{ letterSpacing: '-0.01em' }}>{active.name}</span>
        <span className="text-[14.5px] leading-[1.55] text-pretty lg:text-[16.5px]" style={{ color: '#4E485C' }}>{active.text}</span>
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
        className="bleed flex gap-3 overflow-x-auto pt-0.5 pb-1.5 lg:grid lg:grid-cols-3 lg:gap-5 lg:overflow-x-visible"
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
            <span className="t-display text-[15px] leading-[1.2]" style={{ letterSpacing: '-0.01em' }}>{t.name}</span>
            <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: '#5C5768' }}>{t.text}</span>
          </div>
        ))}
        <div
          className="a-rise box-border flex w-[250px] shrink-0 flex-col gap-2.5 rounded-[18px] px-[18px] py-5 text-white lg:w-auto lg:p-6"
          style={{ scrollSnapAlign: 'center', backgroundImage: 'var(--a-grad-hot)', boxShadow: '0 12px 26px var(--a-shadow)', animationDelay: '0.34s' }}
        >
          <span className="t-eyebrow" style={{ fontSize: 10.5, fontWeight: 800, color: 'var(--color-yellow)' }}>Work with us</span>
          <span style={{ fontFamily: 'var(--font-title)', fontSize: 21, lineHeight: 1.14 }}>Don’t see your angle here?</span>
          <span className="text-[13px] leading-[1.48] opacity-95 text-pretty">
            These territories are starting points, not limits. We work with organisations to find where a shift like this creates real commercial space for their specific context.
          </span>
          <a href={CONTACT_URL} target="_blank" rel="noopener noreferrer" className="pill-yellow mt-auto self-start h-10 px-4 text-[13.5px]">
            Contact us <span className="text-[15px]">→</span>
          </a>
        </div>
      </div>
    </div>
  )
}
