import { useEffect } from 'react'
import { useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { useResolved } from '../lib/useDomains'
import { BreadcrumbMenu } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Modules } from '../modules'
import { Loading, Missing, Unavailable } from './states'
import { unquote } from '../lib/theme'

/**
 * A sub-shift is navigationally terminal by design — no sibling rail, no
 * related shifts, no next pager. The breadcrumb MENU is what replaces all of
 * them: it lists the whole domain, so the only way onward is also the way
 * back up.
 */
export default function SubShiftPage() {
  const { domainSlug, ktSlug, subSlug } = useParams()
  const { domain, shift, sub, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug, subSlug })
  useDocumentMeta(sub?.title, sub?.dek)

  useEffect(() => { window.scrollTo(0, 0) }, [subSlug])

  if (loading && !sub) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift || !sub) return <Missing what="sub-shift" />

  const image = sub.heroImage

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      <div className="absolute z-[52]" style={{ top: 156, left: 22, maxWidth: 320 }}>
        <BreadcrumbMenu
          label={unquote(sub.title)}
          domainLabel={domain.name}
          domainTo={`/map/${domain.slug}`}
          crumb={domain.crumb}
          dot={domain.dot}
          activeShift={shift.slug}
          activeSub={shift.subshifts.findIndex((s) => s.slug === sub.slug)}
          groups={domain.keyShifts.map((k) => ({
            slug: k.slug,
            title: unquote(k.title),
            to: `/map/${domain.slug}/${k.slug}`,
            subs: k.subshifts.map((s) => ({
              slug: s.slug, title: unquote(s.title), to: `/map/${domain.slug}/${k.slug}/${s.slug}`,
            })),
          }))}
        />
      </div>

      {/* Sunset, and a title in Urbanist rather than the key shift's serif.
          Both say the same thing: you are a level down. */}
      <header
        className="relative box-border flex flex-col overflow-hidden text-white"
        style={{ minHeight: 400, padding: '226px 22px 30px', backgroundImage: 'var(--grad-sunset)' }}
      >
        {image && (
          <span
            aria-hidden="true" className="absolute inset-0 z-0"
            style={{ backgroundImage: `url('${image}')`, backgroundSize: 'cover', backgroundPosition: 'center 22%' }}
          />
        )}
        <span
          aria-hidden="true" className="absolute inset-0 z-[2]"
          style={{ backgroundImage: 'linear-gradient(180deg, rgba(27,22,32,0) 42%, rgba(74,0,39,0.72) 100%)' }}
        />
        <div className="canvas relative z-[3] mt-auto" style={{ animation: 'ssRise 0.6s var(--ease-out) 0.14s' }}>
          <h1
            className="t-display uppercase"
            style={{ margin: 0, fontSize: 32, fontWeight: 800, lineHeight: 1.06, letterSpacing: '-0.015em' }}
          >
            {sub.title}
          </h1>
        </div>
      </header>

      <div className="canvas gutter flex flex-col" style={{ paddingTop: 26, gap: 'var(--module-gap)' }}>
        <Modules modules={sub.modules} ctx={{ scope: 'sub_shift', domain, subs: [] }} />
        <div style={{ margin: '10px -22px 0' }}><Footer /></div>
      </div>
    </article>
  )
}
