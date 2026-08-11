import { Link, useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { isSphere, quoted } from '../lib/theme'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Loading, Missing, Unavailable } from './states'

const HERO_IMAGE = { society: '/shift/domain-society-bg.jpg' }

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
          <span
            aria-hidden="true" className="absolute z-0"
            style={{ inset: -2, backgroundImage: cssUrl(photo), backgroundSize: 'cover', backgroundPosition: 'center top' }}
          />
        )}
        <span
          aria-hidden="true" className="absolute inset-0 z-[1]"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.34) 100%)' }}
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
                <span className="t-title" style={{ fontSize: 19, lineHeight: 1.2, letterSpacing: '0.005em' }}>{quoted(s.title)}</span>
                <span style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-row)' }}>{s.dek}</span>
                <span style={{ fontSize: 12, color: 'var(--color-ink-meta)' }}>Key shift · {s.read}</span>
              </span>
            </Link>
          ))}
        </div>

        {/* Inside the sheet — the design's own placement — but outside the
            gutter, so the bands reach the sheet's edges on their own. */}
        <div style={{ marginTop: 26 }}><Footer social={false} /></div>
      </div>
    </article>
  )
}
