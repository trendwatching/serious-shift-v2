import { Link, useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Loading, Missing, Unavailable } from './states'

const HERO_IMAGE = { society: '/shift/domain-society-bg.jpg' }

export default function DomainPage() {
  const { domainSlug } = useParams()
  const { domain, loading, unavailable, error, retry } = useResolved({ domainSlug })
  useDocumentMeta(domain?.name, domain?.blurb)

  if (loading && !domain) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain) return <Missing what="domain" />

  const photo = HERO_IMAGE[domain.id]

  return (
    <article className="a-expand relative min-h-dvh" data-domain={domain.id} style={{ backgroundImage: domain.grad }}>
      {/* Floats over the hero rather than docking under the bar — that
          placement is the design's, and it is what lets the hero keep its
          full height. */}
      <div className="absolute z-[48]" style={{ top: 156, left: 22, maxWidth: 300 }}>
        <Breadcrumb crumb={domain.crumb} items={[{ label: 'Home', to: '/' }, { label: domain.name }]} />
      </div>

      <header
        className="relative box-border flex flex-col overflow-hidden text-white"
        style={{ minHeight: 500, padding: '152px 22px 74px' }}
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
        <div className="canvas relative z-[2] mt-auto">
          <h1 className="t-display uppercase" style={{ fontSize: 46, fontWeight: 700, lineHeight: 0.98, letterSpacing: '-0.03em' }}>
            {domain.name}
          </h1>
          <p style={{ marginTop: 14, maxWidth: 290, fontSize: 15, lineHeight: 1.5, opacity: 0.94 }}>{domain.blurb}</p>
        </div>
      </header>

      {/* The sheet rides up over the gradient, which is what makes it read as
          a card lifted off the hero rather than the next band down. */}
      <div
        className="relative z-[2] bg-white"
        style={{ marginTop: -34, minHeight: 520, borderRadius: '28px 28px 0 0', padding: '8px 22px 0' }}
      >
        <div className="canvas">
          <h2 className="sr-only">Key shifts</h2>
          {domain.keyShifts.map((s, i) => (
            <Link
              key={s.id}
              to={`/map/${domain.slug}/${s.slug}`}
              className="flex"
              style={{
                gap: 16, padding: '22px 0', borderBottom: '1px solid var(--color-line-row)',
                animation: `ssRise 0.7s var(--ease-out) ${(0.06 + i * 0.07).toFixed(2)}s`,
              }}
            >
              <span className="t-mono" style={{ fontSize: 12, color: 'var(--color-ink-num)', paddingTop: 4 }}>{s.num}</span>
              <span className="flex flex-1 flex-col" style={{ gap: 6 }}>
                <span className="t-title" style={{ fontSize: 19, lineHeight: 1.2, letterSpacing: '0.005em' }}>{s.title}</span>
                <span style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-row)' }}>{s.dek}</span>
                <span style={{ fontSize: 12, color: 'var(--color-ink-meta)' }}>Key shift · {s.read}</span>
              </span>
            </Link>
          ))}
        </div>

        {/* Inside the sheet, breaking its gutter — the design's own placement. */}
        <div style={{ margin: '26px -22px 0' }}><Footer /></div>
      </div>
    </article>
  )
}
