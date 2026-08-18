import { Link } from '../lib/router'
import { pad2 } from '../lib/theme'

/**
 * Every panel carries its sphere's artwork since the 11 Aug 2026 review asked
 * for imagery behind all four ("the spheres on the homepage don't have the
 * images in the background"). The set below is design's photographic direction
 * from the "Serious Shift Homepage Animation" export — the later variants that
 * had never been pulled in, replacing the 12 Aug illustrations. The filename
 * carries the delivered variant so the docs ledger stays checkable, and so a
 * cached copy of the old art cannot survive a deploy: public/ is served
 * unhashed. Provenance in docs/sphere-image-prompts.md.
 *
 * These are raw duotone photographs with NO copy baked in — the brief's rule,
 * which the illustrations they replace broke (Society carried TRUST/BELONGING/
 * TRUTH, Economy carried PRODUCING WORK / PROVING A HUMAN JUDGED IT).
 *
 * All four therefore get the 0.12→0.42 scrim below. The earlier build kept
 * the three imageless panels scrim-free because a flat black over a bare
 * gradient read darker than the design; with artwork behind the type the
 * scrim is what keeps the panel text legible.
 */
const PANEL_IMAGE = {
  society: '/shift/domain-society-bg-v2.jpg',
  economy: '/shift/domain-economy-bg-v3.jpg',
  organizations: '/shift/domain-organizations-bg-v4.jpg',
  consumers: '/shift/domain-consumers-bg-v2.jpg',
}

/**
 * Dark at both ends, lightest at 35% — the panel's type sits in two clusters
 * (counter/name/blurb up top, intro pinned at the bottom) with the picture
 * showing between them, so a shaped scrim buys legibility exactly where it is
 * needed instead of flattening the whole photograph.
 *
 * The old flat 0.12→0.42 was tuned against the illustrations. The photographs
 * are brighter: it left the Economy counter at 2.8:1 and the Organizations
 * blurb at 3.0:1. A flat ramp deep enough to fix those (0.30→0.60) still could
 * not clear 4.5:1 on Organizations while turning every sphere to mud. Measured
 * across all four images at each text band's real y, this shape clears 3:1
 * large / 4.5:1 normal on every band, with the Organizations blurb and intro
 * the closest calls at ~4.8:1 mean.
 */
const PANEL_SCRIM = 'linear-gradient(180deg, rgba(27,22,32,0.62) 0%, rgba(27,22,32,0.38) 35%, rgba(27,22,32,0.66) 100%)'

const background = (domain) => (PANEL_IMAGE[domain.id]
  ? `${PANEL_SCRIM}, url('${PANEL_IMAGE[domain.id]}')`
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
            right now, as opposed to the evergreen line above. It used to carry
            a "What's shifting right now" eyebrow, dropped on the 18 Aug 2026
            review — the paragraph says it. The wrapper stays: .panel-shifting
            is the desktop hook and mt-auto is what does the pinning. */}
        <div className="panel-shifting mt-auto flex flex-col">
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
