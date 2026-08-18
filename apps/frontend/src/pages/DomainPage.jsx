import { Link, useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { isSphere, quoted } from '../lib/theme'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Loading, Missing, Unavailable } from './states'

// Design's photographic set from the "Serious Shift Homepage Animation"
// export — the later delivered variants, replacing the 12 Aug illustrations
// (which broke the brief's "no copy in images" rule). The variant lives in the
// filename: it records what shipped and stops a cached copy of the old art
// surviving a deploy, since public/ is served unhashed. Provenance in
// docs/sphere-image-prompts.md; scripts/generate-sphere-bg.mjs stays retired.
const HERO_IMAGE = {
  society: '/shift/domain-society-bg-v2.jpg',
  economy: '/shift/domain-economy-bg-v3.jpg',
  organizations: '/shift/domain-organizations-bg-v4.jpg',
  consumers: '/shift/domain-consumers-bg-v2.jpg',
}

export default function DomainPage() {
  const { domainSlug } = useParams()
  // Not a sphere — `/:domainSlug` matches any single segment now, so this is
  // an unknown path and has to 404 rather than render a sphere.
  if (!isSphere(domainSlug)) return <Missing />
  const { domain, loading, unavailable, error, retry } = useResolved({ domainSlug })
  useDocumentMeta(domain?.name, domain?.blurb)

  // Not `!domain`. A sphere is assembled from TWO requests — the index, which
  // carries every sphere's name and blurb, and the per-sphere fragment, which
  // carries its key shifts. The index lands first, so `domain` was truthy while
  // `keyShifts` was still empty: the sheet painted at its 520px minimum with the
  // footer sitting at y=500, in view, and then five rows arrived and shoved it
  // 1100px down the page. That was 0.39 of layout shift — the worst on the site,
  // and the one thing here a reader would actually describe as a stutter.
  //
  // Once loading ends this guard opens regardless, so a sphere that genuinely
  // has no key shifts still renders rather than hanging on the skeleton.
  if (loading && !domain?.keyShifts?.length) return <Loading hero="hero-short" sheet />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain) return <Missing what="domain" />

  const photo = HERO_IMAGE[domain.id]

  return (
    <article className="a-expand relative min-h-dvh" data-domain={domain.id} style={{ backgroundImage: domain.grad }}>
      {/* Floats over the hero rather than docking under the bar — that
          placement is the design's, and it is what lets the hero keep its
          full height. */}
      <div className="crumb-float z-[48]">
        <Breadcrumb crumb={domain.crumb} items={[{ label: 'Home', to: '/' }, { label: domain.name }]} />
      </div>

      <header
        className="hero-short relative box-border flex flex-col overflow-hidden text-white"
        style={{ padding: 'calc(var(--topbar) + 68px) 0 74px' }}
      >
        {photo && (
          /* Position lives on .sphere-art, not inline — the desktop layer
             re-aims the letterbox at the figures mid-frame, and an inline
             value would win that fight and pin every width to `top`. */
          <span
            aria-hidden="true" className="sphere-art absolute z-0"
            style={{ inset: -2, backgroundImage: cssUrl(photo), backgroundSize: 'cover' }}
          />
        )}
        {/* Deepened and started higher on the 18 Aug 2026 art swap. Against the
            illustrations, 34%→0.34 was enough; against the photographs it was
            not — the olive boardroom put the H1 at 2.9:1 and the storefront put
            the blurb at 3.8:1, both under WCAG AA. Measured across all four
            images at the H1's and the blurb's real y-bands, 10%→0.55 is the
            shallowest wash that clears 3:1 large / 4.5:1 normal on every
            sphere, which is why one value serves all four rather than each
            carrying its own — Organizations alone takes a deeper `--hero-scrim`
            on desktop, where its letterbox lands on the pale table. */}
        <span
          aria-hidden="true" className="absolute inset-0 z-[1]"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(27,22,32,0) 10%, rgba(27,22,32,var(--hero-scrim, 0.55)) 100%)' }}
        />
        <div className="canvas gutter relative z-[2] mt-auto">
          {/* Uppercase in the DOM, not by CSS — the breadcrumb directly above
              this already carries its caps as characters, and a page whose
              title copy-pastes differently from its own trail is the bug this
              whole pass is about. */}
          <h1 className="t-display" style={{ fontSize: 'var(--t-hero)', fontWeight: 700, lineHeight: 0.98, letterSpacing: '-0.03em' }}>
            {String(domain.name ?? '').toUpperCase()}
          </h1>
          <p className="measure" style={{ '--measure': '290px', marginTop: 14, fontSize: 15, lineHeight: 1.5, opacity: 0.94 }}>{domain.blurb}</p>
        </div>
      </header>

      {/* The sheet rides up over the gradient, which is what makes it read as
          a card lifted off the hero rather than the next band down. */}
      <div
        className="relative z-[2] bg-white"
        style={{ marginTop: -34, minHeight: 520, borderRadius: '28px 28px 0 0', padding: '8px 0 0' }}
      >
        <div className="canvas gutter">
          <h2 className="sr-only">Key shifts</h2>
          {domain.keyShifts.map((s, i) => (
            <Link
              key={s.id}
              to={`/${domain.slug}/${s.slug}`}
              className="flex"
              style={{
                gap: 16, padding: '22px 0', borderBottom: '1px solid var(--color-line-row)',
                animation: `ssRise 0.7s var(--ease-out) ${(0.06 + i * 0.07).toFixed(2)}s`,
              }}
            >
              <span className="t-mono" style={{ fontSize: 12, color: 'var(--color-ink-num)', paddingTop: 4 }}>{s.num}</span>
              <span className="flex flex-1 flex-col" style={{ gap: 6 }}>
                <span className="t-title" style={{ fontSize: 24, lineHeight: 1.15, letterSpacing: '0.005em' }}>{quoted(s.title)}</span>
                <span style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-row)' }}>{s.dek}</span>
                {/* Caps as characters, not text-transform — house rule, see theme.js. */}
                <span style={{ fontSize: 12, color: 'var(--color-ink-meta)' }}>KEY SHIFT · {s.read}</span>
              </span>
            </Link>
          ))}
        </div>

        {/* Inside the sheet — the design's own placement — but outside the
            gutter, so the bands reach the sheet's edges on their own. */}
        <div style={{ marginTop: 26 }}><Footer /></div>
      </div>
    </article>
  )
}
