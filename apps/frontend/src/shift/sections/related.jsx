/** Related shifts: typed edges from the interrelatedness phase. */
import { Eyebrow, SectionHead } from './primitives'
import { quoteTitle } from '../theme'

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
              <span className="t-eyebrow" style={{ color: 'var(--a-ink)', fontSize: 10, letterSpacing: '0.14em' }}>{r.relationship}</span>
              <span className="t-title text-[16px] leading-[1.2] lg:text-[18px]">{quoteTitle(r.title)}</span>
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
