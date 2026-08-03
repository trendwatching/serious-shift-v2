/** Evidence: the sourced claims behind a sub-shift. */
import { SectionHead } from './primitives'

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
      {/* The tallest module on the site by a distance — a stack of 5-6 short
          cards. As a grid it is a third of the height for the same copy. */}
      <div className="grid gap-2.5 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
        {items.map((c, i) => (
          <div key={i} className="card flex flex-col gap-2.5 p-4 lg:p-5">
            <span className="flex flex-wrap items-center gap-2">
              <h3 className="t-display text-[13.5px]" style={{ letterSpacing: '-0.01em' }}>{c.thinker}</h3>
              {c.strength && (
                <span
                  className="t-eyebrow inline-flex h-[20px] items-center rounded-full px-2"
                  style={{ background: 'var(--a-wash)', color: 'var(--a-ink)', fontSize: 9.5, fontWeight: 800, letterSpacing: '0.12em' }}
                >{STRENGTH_LABEL[c.strength] || c.strength}</span>
              )}
              {c.date && <span className="ml-auto font-mono text-[11px]" style={{ color: 'var(--color-ink-dim)' }}>{c.date}</span>}
            </span>
            <p className="t-body text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{c.text}</p>
            {c.implication && (
              <p className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>
                <span className="font-semibold">So what — </span>{c.implication}
              </p>
            )}
            {c.url && (
              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center self-start text-[11.5px] underline underline-offset-2"
                style={{ color: 'var(--color-link)' }}
                aria-label={`Read source: ${c.source || 'external evidence'}`}
              >{c.source || 'Source'}</a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
