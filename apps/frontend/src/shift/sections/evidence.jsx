/** Evidence: the sourced claims behind a sub-shift. */
import { Eyebrow, SectionHead } from './primitives'

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
                  style={{ background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 9.5, fontWeight: 800, letterSpacing: '0.12em' }}
                >{STRENGTH_LABEL[c.strength] || c.strength}</span>
              )}
              {c.date && <span className="ml-auto font-mono text-[11px]" style={{ color: 'var(--color-ink-dim)' }}>{c.date}</span>}
            </span>
            <span className="text-[14px] leading-[1.55] lg:text-[16.5px] lg:leading-[1.62] text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{c.text}</span>
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
