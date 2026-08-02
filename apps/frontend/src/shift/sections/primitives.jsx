/** Small shared pieces: labels, headings, the back affordance, numbered cards. */

/**
 * The outer container every reading view shares: `--frame` wide with the
 * responsive gutter, both defined in index.css.
 *
 * It is the *wide* track. Prose inside it is pulled back to `--measure` by a
 * `.w-prose` wrapper, so a page reads as a narrow article with card grids
 * breaking out symmetrically either side of it. Below 1024px `--frame`
 * collapses to `--measure` and the two are the same thing.
 */
export const Frame = ({ className = '', children }) => (
  <div
    className={`mx-auto w-full ${className}`}
    style={{ maxWidth: 'calc(var(--frame) + 2 * var(--gutter))', paddingInline: 'var(--gutter)' }}
  >
    {children}
  </div>
)

export function Eyebrow({ children, color = 'var(--color-ink)', className = '', as: Tag = 'div', id }) {
  return <Tag id={id} className={`t-eyebrow ${className}`} style={{ color }}>{children}</Tag>
}

export function SectionHead({ title, aside, color }) {
  return (
    <div className="flex items-baseline gap-2.5">
      <Eyebrow as="h2" color={color}>{title}</Eyebrow>
      {aside && <div className="ml-auto text-[11.5px]" style={{ color: 'var(--color-ink-dim)' }}>{aside}</div>}
    </div>
  )
}

export function BackButton({ onClick, label = 'Back' }) {
  return (
    <button
      type="button" onClick={onClick} aria-label={label}
      className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-[17px] font-semibold text-white transition-colors hover:bg-white/40"
      style={{ fontFamily: 'var(--font-display)' }}
    ><span className="grid h-[34px] w-[34px] place-items-center rounded-full" style={{ background: 'rgba(13,11,16,0.42)' }}>‹</span></button>
  )
}

/**
 * Numbered list on a gradient — signals and counter-signals.
 *
 * The list used to be `max-h-[300px] overflow-y-auto`, which was the design's
 * phone-frame height carried over literally. Scrollbars are suppressed globally
 * (index.css), so at 3.8 signals averaging ~90px each, anything past the third
 * was invisible with nothing to say it was there. No cap now: the list is 3-5
 * items and it goes two-up on desktop instead of scrolling.
 */
export function NumberedCard({ title, items, grad, shadow }) {
  if (!items?.length) return null
  return (
    <div className="rounded-[22px] overflow-hidden flex flex-col" style={{ backgroundImage: `linear-gradient(rgba(13,11,16,0.34), rgba(13,11,16,0.34)), ${grad}`, boxShadow: shadow }}>
      <h2 className="t-eyebrow px-5 pt-5 pb-3.5 text-white lg:px-6 lg:pt-6" style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.16em' }}>{title}</h2>
      <div className="flex flex-col gap-3 px-4 pb-[18px] lg:grid lg:grid-cols-2 lg:gap-4 lg:px-6 lg:pb-6">
        {items.map((t, i) => (
          <div
            key={i}
            className="rounded-2xl bg-white pl-3 pr-4 py-4 flex items-center gap-3"
            style={{ boxShadow: '0 4px 14px rgba(27,22,32,0.12)' }}
          >
            <span className="shrink-0 w-10 text-center t-display text-[34px] leading-none" style={{ fontWeight: 800 }}>{i + 1}.</span>
            <span className="t-body flex-1 text-pretty" style={{ color: 'var(--color-ink-strong)' }}>{t}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
