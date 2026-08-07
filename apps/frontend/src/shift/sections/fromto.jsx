/** From / To: the shift stated as a before-and-after pair. */

function FromToCard({ label, text, grad, panel, ink }) {
  return (
    <div
      className="relative overflow-hidden rounded-[22px] bg-white"
      style={{ border: '1px solid var(--color-hairline)', boxShadow: '0 6px 18px rgba(27,22,32,0.06)' }}
    >
      <div className="absolute inset-0" style={{ backgroundImage: `linear-gradient(rgba(13,11,16,0.38), rgba(13,11,16,0.38)), ${grad}`, animation: `${panel} 8s ease-in-out infinite` }} />
      <div
        className="relative box-border flex h-[208px] flex-col items-center justify-center gap-2.5 px-[15px] py-5 text-center md:h-[240px] md:px-6 lg:h-[264px] lg:gap-3.5 lg:px-8"
        style={{ animation: `${ink} 8s ease-in-out infinite` }}
      >
        <span className="t-display text-[25px] md:text-[28px] lg:text-[32px]" style={{ letterSpacing: '-0.02em' }}>{label}</span>
        <span className="text-[13.5px] leading-[1.42] md:text-[15px] md:leading-[1.48] lg:text-[16px] lg:leading-[1.5]">{text}</span>
      </div>
    </div>
  )
}

/** Two cards whose gradient fills cross-fade against each other. */
export function FromTo({ from, to, grad }) {
  if (!from || !to) return null
  return (
    <section className="grid grid-cols-2 gap-3" aria-label="From and to">
      <h2 className="sr-only">From and to</h2>
      <FromToCard label="From" text={from} grad={grad} panel="ssPanelA" ink="ssInkA" />
      <FromToCard label="To" text={to} grad={grad} panel="ssPanelB" ink="ssInkB" />
    </section>
  )
}

/**
 * Solid-fill From/To pair, sub-shift only: green "from", sunset "to".
 *
 * The "to" card takes the sunset gradient rather than the domain accent, and
 * that is the point of it. A sub-shift's whole visual argument is that you have
 * moved a level down; colouring its spine in the parent's pink would make the
 * two pages read as the same page twice, which is the confusion the design
 * brief opened with.
 */
export function FromToSolid({ from, to }) {
  if (!from || !to) return null
  const card = (label, text, grad) => (
    <div
      className="flex-1 min-w-0 box-border rounded-[18px] p-4 text-white flex flex-col gap-2 md:p-5 lg:gap-3 lg:p-6"
      style={{ backgroundImage: grad }}
    >
      <span className="t-eyebrow text-[11.5px]" style={{ letterSpacing: '0.12em' }}>{label}</span>
      <span className="t-body">{text}</span>
    </div>
  )
  return <section className="flex gap-2.5 items-stretch lg:gap-4" aria-label="From and to"><h2 className="sr-only">From and to</h2>{card('From', from, 'var(--pos-grad)')}{card('To', to, 'var(--grad-sunset)')}</section>
}
