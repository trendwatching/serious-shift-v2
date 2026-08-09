import { useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Modules } from '../modules'
import { Loading, Missing, Unavailable } from './states'
import { quoted, trendTitle, unquote } from '../lib/theme'

/**
 * A sub-shift has no sibling rail, no related shifts and no next pager, so the
 * breadcrumb is the entire way out — which is why it is the design's trail and
 * not the collapsed menu this page used to render.
 *
 * The trail is `Home › {key shift} › {sub-shift}`: it names the parent and
 * makes going up one level a single visible tap. The menu variant hid that
 * behind a pill a reader had to guess was a dropdown, and named the sub-shift
 * they were already reading. Note the middle rung is the KEY SHIFT, not the
 * sphere — the sphere is one more tap from there, and this is the trail the
 * delivered build renders.
 */
export default function SubShiftPage() {
  const { domainSlug, ktSlug, subSlug } = useParams()
  const { domain, shift, sub, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug, subSlug })
  // See the note in ShiftPage — CSS casing never reaches the tab or the unfurl.
  useDocumentMeta(trendTitle(sub?.title), sub?.dek)

  // Gated on the modules — see the note in DomainPage. The index can satisfy
  // `!sub` before the body arrives.
  if (loading && !sub?.modules?.length) return <Loading hero="hero-sub" />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift || !sub) return <Missing what="sub-shift" />

  const image = sub.heroImage

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      <div className="crumb-float z-[52]" style={{ '--crumb-max': '320px' }}>
        <Breadcrumb
          crumb={domain.crumb}
          items={[
            { label: 'Home', to: '/' },
            { label: unquote(shift.title), to: `/map/${domain.slug}/${shift.slug}` },
            { label: unquote(sub.title) },
          ]}
        />
      </div>

      {/* Sunset, and a title in Urbanist rather than the key shift's serif.
          Both say the same thing: you are a level down. */}
      <header
        className="hero-sub relative box-border flex flex-col overflow-hidden text-white"
        style={{ padding: '226px 0 30px', backgroundImage: 'var(--grad-sunset)' }}
      >
        {image && (
          <span
            aria-hidden="true" className="hero-art hero-art-sub absolute inset-0 z-0"
            style={{ '--art': cssUrl(image), '--art-wide': cssUrl(sub.heroImageWide) }}
          />
        )}
        <span
          aria-hidden="true" className="absolute inset-0 z-[2]"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(27,22,32,0) 42%, color-mix(in srgb, var(--a-deep) 74%, transparent) 100%)' }}
        />
        <div className="canvas gutter relative z-[3] mt-auto" style={{ animation: 'ssRise 0.6s var(--ease-out) 0.14s' }}>
          <h1
            className="t-display uppercase"
            style={{ margin: 0, fontSize: 'var(--t-sub)', fontWeight: 800, lineHeight: 1.06, letterSpacing: '-0.015em' }}
          >
            {quoted(sub.title)}
          </h1>
        </div>
      </header>

      <div className="canvas gutter flex flex-col" style={{ paddingTop: 26, gap: 'var(--module-gap)' }}>
        <Modules modules={sub.modules} ctx={{ scope: 'sub_shift', domain, subs: [] }} />
      </div>

      <div style={{ marginTop: 10 }}><Footer /></div>
    </article>
  )
}
