/** Voices: who backs the shift and who disputes it. */
import { SectionHead } from './primitives'

function VoiceColumn({ title, people, grad, shadow }) {
  if (!people?.length) return null
  return (
    <div className="flex-1 min-w-0 rounded-[22px] overflow-hidden flex flex-col" style={{ backgroundImage: grad, boxShadow: shadow }}>
      <div className="t-eyebrow px-5 pt-5 pb-3.5 text-white lg:px-6 lg:pt-6" style={{ fontSize: 13, fontWeight: 800, letterSpacing: '0.16em' }}>{title}</div>
      <div className="flex flex-col gap-3 px-4 pb-[18px] lg:px-6 lg:pb-6">
        {people.map((p, i) => (
          <div key={`${p.name}-${i}`} className="rounded-2xl bg-white px-4 py-4 flex flex-col gap-2 lg:px-5 lg:py-5" style={{ boxShadow: '0 4px 14px rgba(27,22,32,0.12)' }}>
            <span className="t-display text-[14px] lg:text-[16px]" style={{ letterSpacing: '-0.01em' }}>{p.name}</span>
            <span className="t-body text-pretty" style={{ color: 'var(--color-ink-strong)' }}>“{p.quote}”</span>
            {p.url && (
              <a
                href={p.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11.5px] underline underline-offset-2"
                aria-label={`Read source: ${p.source || p.name}`}
              >{p.source || 'Source'}{p.date ? ` · ${p.date}` : ''}</a>
            )}
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
        <VoiceColumn title="Argue for" people={proponents} grad="var(--pos-grad-lit)" shadow="0 12px 28px var(--pos-shadow)" />
        <VoiceColumn title="Push back" people={skeptics} grad="var(--a-grad-hot)" shadow="0 12px 28px var(--a-shadow)" />
      </div>
    </div>
  )
}
