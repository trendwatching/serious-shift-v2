/** From / To: the shift stated as a before-and-after pair. */
import { PAD } from './primitives'

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
  return <div className="flex gap-2.5 items-stretch">{card('From', from, 'var(--pos-grad)')}{card('To', to, 'var(--a-grad)')}</div>
}
