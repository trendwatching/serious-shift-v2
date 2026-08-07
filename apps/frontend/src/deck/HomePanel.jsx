import { DOMAIN_ORDER, DOMAIN_THEME } from '../lib/theme'
import Orbs from './Orbs'

/**
 * Slide 1. Headline, standfirst, four gradient badges — and nothing else.
 *
 * There is deliberately no eyebrow. The previous build added a "Week N · four
 * domains" line here, which pushed the H1 down and cost it its size; the
 * design opens on the sentence.
 */
export default function HomePanel({ width, active, count, domains, onJump }) {
  const nameOf = (id) => domains.find((d) => d.id === id)?.name
    ?? id.charAt(0).toUpperCase() + id.slice(1)

  return (
    <div
      className="relative box-border flex h-full shrink-0 flex-col overflow-hidden bg-white"
      style={{ width, padding: '30px 24px 74px' }}
      role="group" aria-roledescription="slide" aria-label={`Introduction, 1 of ${count}`}
      aria-hidden={!active} inert={!active ? '' : undefined}
    >
      <Orbs />

      <div className="canvas relative">
        <h1
          className="t-display"
          style={{ margin: '6px 0 0', fontSize: 58, lineHeight: 0.94, fontWeight: 700, letterSpacing: '-0.04em' }}
        >
          {['Everything', 'that is about'].map((line, i) => (
            <span key={line} className="block" style={{ animation: `ssWord 0.75s var(--ease-out) ${0.05 + i * 0.09}s both` }}>{line}</span>
          ))}
          <span className="block italic" style={{ animation: 'ssWord 0.75s var(--ease-out) 0.23s both' }}>to change</span>
        </h1>

        <p
          style={{
            margin: '24px 0 0', maxWidth: 320, fontSize: 18.5, lineHeight: 1.45,
            color: 'var(--color-ink-soft)', animation: 'ssRise 0.7s var(--ease-out) 0.4s both',
          }}
        >
          Understand how AI will transform society, the economy, consumers and organizations — then turn those shifts into your own daring new opportunities and futures.
        </p>

        <div className="flex flex-wrap items-center" style={{ marginTop: 24, gap: 9 }}>
          {DOMAIN_ORDER.map((id, i) => (
            <button
              key={id} type="button" onClick={() => onJump(i + 1)} tabIndex={active ? 0 : -1}
              className="ss-badge box-border inline-flex items-center text-white"
              style={{
                height: 40, padding: '0 16px', borderRadius: 999, gap: 10,
                backgroundImage: DOMAIN_THEME[id].grad,
                boxShadow: '0 6px 14px rgba(27,22,32,0.2), inset 0 1px 0 rgba(255,255,255,0.26)',
                animation: `ssRise 0.7s var(--ease-out) ${(0.5 + i * 0.07).toFixed(2)}s both`,
                transition: 'transform 0.25s var(--ease-out), box-shadow 0.25s ease',
              }}
            >
              <span className="t-display" style={{ fontSize: 13.5, fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                {nameOf(id)}
              </span>
              <span aria-hidden="true" style={{ fontSize: 16, lineHeight: 1 }}>→</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
