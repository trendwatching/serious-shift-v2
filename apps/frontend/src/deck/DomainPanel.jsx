import { Link } from '../lib/router'
import { pad2 } from '../lib/theme'

/**
 * Society is the only panel with photography behind it; the other three are
 * their gradient, unmodified.
 *
 * No scrim on those three. The previous build added a flat 30% black over
 * every gradient, which is the single reason the whole deck read darker than
 * the design.
 */
const PANEL_IMAGE = { society: '/shift/domain-society-bg.jpg' }

const background = (domain) => (PANEL_IMAGE[domain.id]
  ? `linear-gradient(180deg, rgba(27,22,32,0.12) 0%, rgba(27,22,32,0.42) 100%), url('${PANEL_IMAGE[domain.id]}')`
  : domain.grad)

export default function DomainPanel({ domain, width, active, position, count, total }) {
  return (
    <div
      className="box-border flex h-full shrink-0 flex-col text-white"
      style={{
        width, padding: '30px 24px 74px',
        backgroundImage: background(domain), backgroundSize: 'cover', backgroundPosition: 'center',
      }}
      role="group" aria-roledescription="slide" aria-label={`${domain.name}, ${position} of ${count}`}
      aria-hidden={!active} inert={!active ? '' : undefined}
    >
      <div className="canvas flex h-full flex-col">
        <div className="t-mono" style={{ fontSize: 11, letterSpacing: '0.08em', opacity: 0.9 }}>
          {domain.num} / {pad2(total)}
        </div>

        <h2
          className="t-display uppercase"
          style={{ marginTop: 30, fontSize: 46, fontWeight: 700, lineHeight: 0.98, letterSpacing: '-0.03em' }}
        >
          {domain.name}
        </h2>

        <p style={{ marginTop: 14, maxWidth: 290, fontSize: 15, lineHeight: 1.5, opacity: 0.94 }}>{domain.blurb}</p>

        {/* Pinned to the bottom: what is moving in this domain right now, as
            opposed to the evergreen line above. */}
        <div className="mt-auto flex flex-col" style={{ gap: 8 }}>
          <span className="t-eyebrow" style={{ fontWeight: 800, color: domain.eyebrow }}>What’s shifting right now</span>
          <span className="text-pretty" style={{ maxWidth: 300, fontSize: 14, lineHeight: 1.5, opacity: 0.94 }}>
            {domain.intro}
          </span>
        </div>

        <div
          className="flex flex-col"
          style={{ marginTop: 26, marginBottom: 34, paddingBottom: 24, borderBottom: '1px solid rgba(255,255,255,0.3)' }}
        >
          {/* The arrow points DOWN. The shift list is the next thing on this
              journey; a right arrow read as "a different site over there". */}
          <Link
            to={`/map/${domain.slug}`}
            onClick={(e) => { if (!active) e.preventDefault() }}
            tabIndex={active ? 0 : -1}
            className="pill-yellow self-start"
          >
            All {domain.count} key shifts
            <span aria-hidden="true" className="inline-block rotate-90" style={{ fontSize: 16, lineHeight: 1 }}>→</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
