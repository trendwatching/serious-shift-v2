/** Small shared pieces: labels, headings, the back affordance, numbered cards. */
import { quoteTitle } from '../theme'

export const PAD = 22

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

export function NumberedCard({ title, items, grad, shadow }) {
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
            <span className="flex-1 text-[13.5px] leading-[1.5] lg:text-[16.5px] lg:leading-[1.62] text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{t}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
