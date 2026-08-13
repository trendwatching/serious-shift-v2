import { DOMAIN_ORDER, DOMAIN_THEME } from '../lib/theme'
import { DECK } from '../lib/site'
import Orbs from './Orbs'

/**
 * Slide 1. Headline, standfirst, four gradient badges — and nothing else.
 *
 * There is deliberately no eyebrow. The previous build added a "Week N · four
 * domains" line here, which pushed the H1 down and cost it its size; the
 * design opens on the sentence.
 */
export default function HomePanel({ width, active, count, domains, onJump }) {
  // Falls back to DECK, not to a capitalised id: the id is the database
  // spelling ("organizations") and the badge would render "Organisations" until
  // the map arrived and then reflow to "Organizations". One letter, but it is a
  // visible twitch on the first screen anyone sees.
  const nameOf = (id) => domains.find((d) => d.id === id)?.name
    ?? DECK.find((d) => d.id === id)?.name
    ?? id

  return (
    <div
      // Bottom padding lives on the class, not inline — the desktop layer
      // overrides it (74 → 110px) and an inline shorthand silently won that
      // fight for as long as it existed, leaving the rule inert.
      className="intro-panel relative box-border flex h-full shrink-0 flex-col overflow-hidden bg-white"
      style={{ width, paddingTop: 24, paddingInline: 24 }}
      role="group" aria-roledescription="slide" aria-label={`Introduction, 1 of ${count}`}
      aria-hidden={!active} inert={!active ? '' : undefined}
    >
      <Orbs />

      <div className="canvas relative">
        <h1
          className="t-display"
          style={{ margin: '6px 0 0', fontSize: 'var(--t-deck)', lineHeight: 0.94, fontWeight: 700, letterSpacing: '-0.04em' }}
        >
          {['Everything', 'that is about'].map((line, i) => (
            <span key={line} className="block" style={{ animation: `ssWord 0.75s var(--ease-out) ${0.05 + i * 0.09}s` }}>{line}</span>
          ))}
          <span className="block italic" style={{ animation: 'ssWord 0.75s var(--ease-out) 0.23s' }}>to change</span>
        </h1>

        <p
          className="measure"
          style={{
            '--measure': '320px',
            margin: '18px 0 0', fontSize: 'var(--t-standfirst)', lineHeight: 1.45,
            color: 'var(--color-ink-soft)', animation: 'ssRise 0.7s var(--ease-out) 0.4s',
          }}
        >
          Understand how AI will transform society, the economy, consumers and organizations — then turn those shifts into your own daring new opportunities and futures.
        </p>

        <div className="badge-row flex flex-wrap items-center" style={{ marginTop: 18, gap: 9 }}>
          {DOMAIN_ORDER.map((id, i) => (
            <button
              key={id} type="button" onClick={() => onJump(i + 1)} tabIndex={active ? 0 : -1}
              className="ss-badge box-border inline-flex items-center text-white"
              style={{
                height: 'var(--badge-h)', padding: '0 calc(var(--badge-h) * 0.4)', borderRadius: 999, gap: 10,
                backgroundImage: DOMAIN_THEME[id].grad,
                boxShadow: '0 6px 14px rgba(27,22,32,0.2), inset 0 1px 0 rgba(255,255,255,0.26)',
                animation: `ssRise 0.7s var(--ease-out) ${(0.5 + i * 0.07).toFixed(2)}s`,
                transition: 'transform 0.25s var(--ease-out), box-shadow 0.25s ease',
              }}
            >
              <span className="t-display" style={{ fontSize: 'var(--t-badge)', fontWeight: 800, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
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
