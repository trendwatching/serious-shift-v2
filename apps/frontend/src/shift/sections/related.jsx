/** Related shifts: typed edges from the interrelatedness phase. */
import { SectionHead } from './primitives'
import { quoteTitle } from '../theme'
import { Link } from '../../router'

export function RelatedShifts({ items }) {
  if (!items?.length) return null
  return (
    <div className="flex flex-col gap-2.5">
      <SectionHead title="Connected shifts" aside={`${items.length}`} />
      <div className="grid md:grid-cols-2 md:gap-x-8">
        {items.map((r, i) => (
          <Link
            key={`${r.href}-${i}`} to={r.href}
            className="flex gap-4 border-b py-4 text-left transition-colors hover:bg-[var(--color-paper)]"
            style={{ borderColor: 'var(--color-hairline-soft)' }}
          >
            <span className="flex flex-1 flex-col gap-1.5">
              <span className="t-eyebrow" style={{ color: 'var(--a-ink)', fontSize: 10, letterSpacing: '0.14em' }}>{r.relationship}</span>
              <span className="t-title text-[16px] leading-[1.2] lg:text-[18px]">{quoteTitle(r.title)}</span>
              {r.reasoning && (
                <span className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{r.reasoning}</span>
              )}
            </span>
            <span className="pt-1 text-[15px]" style={{ color: 'var(--color-ink-dim)' }}>›</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
