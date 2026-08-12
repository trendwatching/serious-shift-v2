import { Link } from '../lib/router'
import { pad2 } from '../lib/theme'

/**
 * Every panel carries its sphere's artwork since the 11 Aug 2026 review asked
 * for imagery behind all four ("the spheres on the homepage don't have the
 * images in the background"). All four are design's own human-made
 * illustrations since the 12 Aug 2026 review (the "Serious Shift Homepage
 * Animation" export), replacing the interim generated set — provenance in
 * docs/sphere-image-prompts.md.
 *
 * All four therefore get the 0.12→0.42 scrim below. The earlier build kept
 * the three imageless panels scrim-free because a flat black over a bare
 * gradient read darker than the design; with artwork behind the type the
 * scrim is what keeps the panel text legible.
 */
const PANEL_IMAGE = {
  society: '/shift/domain-society-bg.jpg',
  economy: '/shift/domain-economy-bg.jpg',
  organizations: '/shift/domain-organizations-bg.jpg',
  consumers: '/shift/domain-consumers-bg.jpg',
}

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
      {/* `panel-canvas` is the desktop hook: a full-height desktop panel
          centers this copy instead of stretching it top-and-bottom — the
          same fix .intro-panel got, from the other direction. */}
      <div className="panel-canvas canvas flex h-full flex-col">
        <div className="t-mono" style={{ fontSize: 11, letterSpacing: '0.08em', opacity: 0.9 }}>
          {domain.num} / {pad2(total)}
        </div>

        <h2
          className="t-display uppercase"
          style={{ marginTop: 30, fontSize: 'var(--t-hero)', fontWeight: 700, lineHeight: 0.98, letterSpacing: '-0.03em' }}
        >
          {domain.name}
        </h2>

        <p className="measure" style={{ '--measure': '290px', marginTop: 14, fontSize: 15, lineHeight: 1.5, opacity: 0.94 }}>{domain.blurb}</p>

        {/* Pinned to the bottom on a phone: what is moving in this domain
            right now, as opposed to the evergreen line above. The desktop
            layer swaps the auto margin for a fixed gap so the copy sits as
            one centered group instead of splitting to the panel's edges. */}
        <div className="panel-shifting mt-auto flex flex-col" style={{ gap: 8 }}>
          <span className="t-eyebrow" style={{ fontWeight: 800, color: domain.eyebrow }}>What’s shifting right now</span>
          <span className="measure text-pretty" style={{ fontSize: 14, lineHeight: 1.5, opacity: 0.94 }}>
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
            to={`/${domain.slug}`}
            onClick={(e) => { if (!active) e.preventDefault() }}
            tabIndex={active ? 0 : -1}
            className="pill-yellow self-start"
          >
            ALL {domain.count} KEY SHIFTS
            <span aria-hidden="true" className="inline-block rotate-90" style={{ fontSize: 16, lineHeight: 1 }}>→</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
