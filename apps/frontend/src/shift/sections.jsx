/**
 * sections.jsx — the editorial blocks shared by the shift and sub-shift pages.
 *
 * Ported style-for-style from the approved design. Each block returns null when
 * its data is absent, so a page composed of these renders exactly the sections
 * the content supports. Motion is CSS (see index.css keyframes) rather than a
 * JS animation loop — the ambient animations run on the compositor and cost no
 * main-thread work, which is what keeps long detail pages smooth while scrolling.
 */
import { useLayoutEffect, useRef, useState } from 'react'
import { CONTACT_URL } from './content'

const PAD = 22
const WHEN = ['0–12 months', '1–3 years', '3–10 years']

/* ── small shared pieces ─────────────────────────────────────────────── */

export function Eyebrow({ children, color = 'var(--color-ink)', className = '' }) {
  return <div className={`t-eyebrow ${className}`} style={{ color }}>{children}</div>
}

export function SectionHead({ title, aside, color }) {
  return (
    <div className="flex items-baseline gap-2.5">
      <Eyebrow color={color}>{title}</Eyebrow>
      {aside && <div className="ml-auto text-[11.5px]" style={{ color: 'var(--color-ink-dim)' }}>{aside}</div>}
    </div>
  )
}

export function BackButton({ onClick, label = 'Back' }) {
  return (
    <button
      type="button" onClick={onClick} aria-label={label}
      className="grid place-items-center w-[34px] h-[34px] rounded-full text-[17px] font-semibold text-white shrink-0 transition-colors hover:bg-white/40"
      style={{ background: 'rgba(255,255,255,0.24)', fontFamily: 'var(--font-display)' }}
    >‹</button>
  )
}

/**
 * Gradient page header. `stripes` adds the shift page's diagonal texture.
 * `face` picks the title type: 'title' = Suez (shift names, uppercase),
 * 'display' = Urbanist (domain names).
 */
export function GradientHero({ grad, onBack, eyebrow, eyebrowColor, title, sub, blurb, minHeight = 300, stripes, face = 'title' }) {
  // The darkening wash + diagonal texture belong to the shift hero only; the
  // domain and sub-shift heroes are a clean gradient in the design.
  const layers = [
    stripes && 'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.58) 100%)',
    stripes && 'repeating-linear-gradient(115deg, rgba(255,255,255,0.1) 0 10px, rgba(255,255,255,0) 10px 26px)',
    grad,
  ].filter(Boolean)

  return (
    <header
      className="relative flex flex-col text-white box-border"
      style={{ minHeight, paddingTop: 62, paddingBottom: PAD, backgroundImage: layers.join(', ') }}
    >
      {/* Content shares the reading column's exact measure and padding so the
          hero lines up with the body copy instead of hugging the edge. */}
      <div className="mx-auto flex w-full flex-1 flex-col px-[22px] lg:max-w-[860px]">
        {onBack && <BackButton onClick={onBack} />}
        <div className="mt-auto a-rise" style={{ animationDelay: '0.14s' }}>
          {eyebrow && (
            <div className="t-eyebrow" style={{ color: eyebrowColor || 'rgba(255,255,255,0.9)', letterSpacing: '0.18em' }}>
              {eyebrow}
            </div>
          )}
          {title && (face === 'display' ? (
            <h1 className="t-display mt-2.5 text-[44px] leading-[0.98] lg:text-[clamp(56px,5vw,80px)]" style={{ letterSpacing: '-0.035em' }}>
              {title}
            </h1>
          ) : (
            <h1 className="t-title mt-2.5 text-[32px] leading-[1.1] lg:text-[44px]">{title}</h1>
          ))}
          {sub && <div className="mt-2.5 text-[13.5px] opacity-90">{sub}</div>}
          {blurb && <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 lg:max-w-[520px] lg:text-[17px]">{blurb}</p>}
        </div>
      </div>
    </header>
  )
}

/* ── From / To ───────────────────────────────────────────────────────── */

function FromToCard({ label, text, grad, panel, ink }) {
  return (
    <div
      className="relative overflow-hidden rounded-[22px] bg-white"
      style={{ border: '1px solid var(--color-hairline)', boxShadow: '0 6px 18px rgba(27,22,32,0.06)' }}
    >
      <div className="absolute inset-0" style={{ backgroundImage: grad, animation: `${panel} 8s ease-in-out infinite` }} />
      <div
        className="relative box-border flex h-[208px] flex-col items-center justify-center gap-2.5 px-[15px] py-5 text-center lg:h-[264px] lg:gap-3.5 lg:px-8"
        style={{ animation: `${ink} 8s ease-in-out infinite` }}
      >
        <span className="t-display text-[25px] lg:text-[32px]" style={{ letterSpacing: '-0.02em' }}>{label}</span>
        <span className="text-[13.5px] leading-[1.42] lg:text-[16px] lg:leading-[1.5]">{text}</span>
      </div>
    </div>
  )
}

/** Two cards whose gradient fills cross-fade against each other. */
export function FromTo({ from, to, grad }) {
  if (!from || !to) return null
  return (
    <div className="grid grid-cols-2 gap-3">
      <FromToCard label="From" text={from} grad={grad} panel="ssPanelA" ink="ssInkA" />
      <FromToCard label="To" text={to} grad={grad} panel="ssPanelB" ink="ssInkB" />
    </div>
  )
}

/** Solid-fill From/To pair used on sub-shift pages (green → pink). */
export function FromToSolid({ from, to }) {
  if (!from || !to) return null
  const card = (label, text, grad) => (
    <div
      className="flex-1 min-w-0 box-border rounded-[18px] p-4 text-white flex flex-col gap-2"
      style={{ backgroundImage: grad }}
    >
      <span className="t-eyebrow text-[11.5px]" style={{ letterSpacing: '0.12em' }}>{label}</span>
      <span className="text-[13.5px] leading-[1.45]">{text}</span>
    </div>
  )
  return <div className="flex gap-2.5 items-stretch">{card('From', from, 'var(--grad-green)')}{card('To', to, 'var(--grad-pink)')}</div>
}

/* ── Stat band ───────────────────────────────────────────────────────── */

export function StatBand({ stat, size = 58 }) {
  if (!stat?.value) return null
  return (
    <div
      className="bleed box-border flex items-center gap-[18px] py-[34px] text-white lg:gap-10 lg:py-14"
      style={{ backgroundImage: "url('/shift/stat-band-gradient.png')", backgroundSize: 'cover', backgroundPosition: 'center' }}
    >
      <span
        className="shrink-0 leading-[0.9]"
        style={{
          fontFamily: 'var(--font-title)',
          // The numeral is the anchor of the band; give it real scale once
          // there's room, but keep the mobile size exactly as designed.
          fontSize: `clamp(${size}px, ${size / 3.9}vw, ${Math.round(size * 1.7)}px)`,
          letterSpacing: '-0.015em',
        }}
      >
        {stat.value}
      </span>
      <span className="flex flex-1 flex-col gap-2">
        <span className="text-[13.5px] leading-[1.45] text-pretty lg:text-[17px] lg:leading-[1.5]">{stat.text}</span>
        {stat.source && <span className="text-[11px] leading-[1.4] opacity-75 lg:text-[12.5px]">{stat.source}</span>}
      </span>
    </div>
  )
}

/* ── "What's changing / Why now" peel tabs ───────────────────────────── */

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
      <div className="rounded-[20px] p-5 text-white" style={{ backgroundImage: 'var(--grad-pink)' }}>
        <div className="t-eyebrow mb-2.5" style={{ letterSpacing: '0.04em' }}>{cards[0].label}</div>
        <div className="text-[14.5px] leading-[1.58] text-pretty">{cards[0].text}</div>
      </div>
    )
  }

  return (
    <div className="relative" style={{ height: (h || 150) + 96 }}>
      {cards.map((c, i) => {
        const front = i === top
        const left = i === 0
        const bg = front ? 'var(--grad-pink)' : 'var(--grad-grey)'
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
                className="text-[14.5px] leading-[1.58] text-pretty"
                style={{ color: fg, opacity: front ? 1 : 0, transition: 'opacity 0.3s ease' }}
              >{c.text}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ── Sub-shift cards ─────────────────────────────────────────────────── */

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
            <span className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundImage: 'var(--grad-pink)' }} />
            <span className="flex items-center gap-2">
              <span
                className="inline-flex items-center h-[22px] px-[9px] rounded-full t-eyebrow"
                style={{ background: 'var(--color-pink-wash)', color: 'var(--color-pink-ink)', fontSize: 10, fontWeight: 800, letterSpacing: '0.14em' }}
              >Sub-shift {b.num}</span>
              <span className="ml-auto text-[11.5px] font-semibold" style={{ color: 'var(--color-pink-ink)' }}>Open</span>
              <span
                className="grid place-items-center w-[22px] h-[22px] rounded-full text-[13px]"
                style={{ background: 'var(--color-pink-wash)', color: 'var(--color-pink-ink)' }}
              >↗</span>
            </span>
            <span className="t-title text-[15px] leading-[1.24]">{b.title}</span>
            <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: '#5C5768' }}>{b.dek}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── Human needs ─────────────────────────────────────────────────────── */

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
        {card('u', 'Unlocked', needs.unlocked, 'var(--grad-green)', '0 12px 26px rgba(16,80,47,0.24)')}
        {card('t', 'Threatened', needs.threatened, 'var(--grad-pink)', '0 12px 26px rgba(94,0,51,0.22)')}
      </div>
    </div>
  )
}

/* ── Tension quote band ──────────────────────────────────────────────── */

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
      <span className="absolute left-0 top-2 bottom-2 w-1 rounded-full" style={{ backgroundImage: 'var(--grad-pink)' }} />
      <blockquote
        className="t-display m-0 text-[21px] leading-[1.3] text-pretty lg:text-[27px]"
        style={{ fontWeight: 600, letterSpacing: '-0.018em', color: 'var(--color-ink)' }}
      >
        “{quote}”
      </blockquote>
    </figure>
  )
}

/* ── Innovations in the wild: real branded examples ──────────────────────── */

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
                <span className="t-eyebrow" style={{ color: 'var(--color-pink-ink)', fontSize: 10, letterSpacing: '0.14em' }}>
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

/* ── Now / next / beyond ─────────────────────────────────────────────── */

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
              style={{ left: -26, top: 18, border: '2.5px solid var(--color-pink)', background: '#fff', animation: `ssDot${i + 1} 12s linear infinite` }}
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

/* ── Implications by industry ────────────────────────────────────────── */

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

/* ── Opportunity territories ─────────────────────────────────────────── */

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
          style={{ scrollSnapAlign: 'center', backgroundImage: 'var(--grad-pink-hot)', boxShadow: '0 12px 26px rgba(94,0,51,0.24)', animationDelay: '0.34s' }}
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

/* ── Signals / counter-signals ───────────────────────────────────────── */

function NumberedCard({ title, items, grad, shadow }) {
  if (!items?.length) return null
  return (
    <div className="rounded-[22px] overflow-hidden flex flex-col" style={{ backgroundImage: grad, boxShadow: shadow }}>
      <div className="t-eyebrow px-5 pt-5 pb-3.5 text-white" style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.16em' }}>{title}</div>
      <div className="max-h-[300px] overflow-y-auto px-4 pb-[18px] flex flex-col gap-3">
        {items.map((t, i) => (
          <div
            key={i}
            className="shrink-0 rounded-2xl bg-white pl-3 pr-4 py-4 flex items-center gap-3"
            style={{ boxShadow: '0 4px 14px rgba(27,22,32,0.12)' }}
          >
            <span className="shrink-0 w-10 text-center t-display text-[34px] leading-none" style={{ fontWeight: 800 }}>{i + 1}.</span>
            <span className="flex-1 text-[13.5px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{t}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export const SignalsCard = ({ items }) => (
  <NumberedCard title="Signals" items={items} grad="var(--grad-pink-hot)" shadow="0 12px 28px rgba(94,0,51,0.22)" />
)
export const CounterSignalsCard = ({ items }) => (
  <NumberedCard title="Counter-signals" items={items} grad="var(--grad-green-lit)" shadow="0 12px 28px rgba(16,80,47,0.22)" />
)

/* ── Voices: who backs the shift and who disputes it ─────────────────────── */

function VoiceColumn({ title, people, grad, shadow }) {
  if (!people?.length) return null
  return (
    <div className="flex-1 min-w-0 rounded-[22px] overflow-hidden flex flex-col" style={{ backgroundImage: grad, boxShadow: shadow }}>
      <div className="t-eyebrow px-5 pt-5 pb-3.5 text-white" style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.16em' }}>{title}</div>
      <div className="flex flex-col gap-3 px-4 pb-[18px]">
        {people.map((p, i) => (
          <div key={`${p.name}-${i}`} className="rounded-2xl bg-white px-4 py-4 flex flex-col gap-2" style={{ boxShadow: '0 4px 14px rgba(27,22,32,0.12)' }}>
            <span className="t-display text-[14px]" style={{ letterSpacing: '-0.01em' }}>{p.name}</span>
            <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-strong)' }}>“{p.quote}”</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Real attributed positions from the thinker-attribution phase. */
export function Voices({ proponents, skeptics }) {
  if (!proponents?.length && !skeptics?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Who is saying this" aside={`${(proponents?.length || 0) + (skeptics?.length || 0)} voices`} />
      <div className="flex flex-col gap-3 lg:flex-row lg:gap-4 lg:items-start">
        <VoiceColumn title="Argue for" people={proponents} grad="var(--grad-green-lit)" shadow="0 12px 28px rgba(16,80,47,0.22)" />
        <VoiceColumn title="Push back" people={skeptics} grad="var(--grad-pink-hot)" shadow="0 12px 28px rgba(94,0,51,0.22)" />
      </div>
    </div>
  )
}

/* ── Evidence: the sourced claims behind a sub-shift ─────────────────────── */

const STRENGTH_LABEL = {
  strong_signal: 'Strong signal',
  signal: 'Signal',
  background: 'Background',
  noise: 'Noise',
}

export function Evidence({ items }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="The evidence" aside={`${items.length} sourced`} />
      <div className="flex flex-col gap-2.5">
        {items.map((c, i) => (
          <div key={i} className="card flex flex-col gap-2.5 p-4 lg:p-5">
            <span className="flex flex-wrap items-center gap-2">
              <span className="t-display text-[13.5px]" style={{ letterSpacing: '-0.01em' }}>{c.thinker}</span>
              {c.strength && (
                <span
                  className="t-eyebrow inline-flex h-[20px] items-center rounded-full px-2"
                  style={{ background: 'var(--color-pink-wash)', color: 'var(--color-pink-ink)', fontSize: 9.5, fontWeight: 800, letterSpacing: '0.12em' }}
                >{STRENGTH_LABEL[c.strength] || c.strength}</span>
              )}
              {c.date && <span className="ml-auto font-mono text-[11px]" style={{ color: 'var(--color-ink-dim)' }}>{c.date}</span>}
            </span>
            <span className="text-[14px] leading-[1.55] text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{c.text}</span>
            {c.implication && (
              <span className="text-[13px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-mid)' }}>
                <span className="font-semibold">So what — </span>{c.implication}
              </span>
            )}
            {c.source && <span className="text-[11.5px]" style={{ color: 'var(--color-ink-dim)' }}>{c.source}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Related shifts: typed edges from the interrelatedness phase ─────────── */

export function RelatedShifts({ items, onOpen }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Connected shifts" aside={`${items.length}`} />
      <div className="flex flex-col">
        {items.map((r, i) => (
          <button
            key={`${r.href}-${i}`} type="button" onClick={() => onOpen?.(r)}
            className="flex gap-4 border-b py-4 text-left transition-colors hover:bg-[var(--color-paper)]"
            style={{ borderColor: 'var(--color-hairline-soft)' }}
          >
            <span className="flex flex-1 flex-col gap-1.5">
              <span className="t-eyebrow" style={{ color: 'var(--color-pink-ink)', fontSize: 10, letterSpacing: '0.14em' }}>{r.relationship}</span>
              <span className="t-title text-[16px] leading-[1.2] lg:text-[18px]">{r.title}</span>
              {r.reasoning && (
                <span className="text-[13px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{r.reasoning}</span>
              )}
            </span>
            <span className="pt-1 text-[15px]" style={{ color: 'var(--color-ink-dim)' }}>›</span>
          </button>
        ))}
      </div>
    </div>
  )
}
