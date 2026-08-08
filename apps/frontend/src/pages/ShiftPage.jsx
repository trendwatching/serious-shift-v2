import { useEffect, useRef } from 'react'
import { useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Modules } from '../modules'
import { Loading, Missing, Unavailable } from './states'
import { unquote } from '../lib/theme'

/**
 * Shrink the hero as the page scrolls: 660 → 360px, and the title 46 → 29px.
 *
 * Written straight to the node through a ref rather than held in state — this
 * fires on every scroll frame, and re-rendering a route's header sixty times a
 * second to change two numbers is the difference between smooth and janky.
 * Skipped under reduced motion, where a header resizing under you is exactly
 * the movement the setting is for.
 */
function useHeroShrink(ref, enabled) {
  useEffect(() => {
    const node = ref.current
    if (!node || !enabled) return undefined
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined
    let frame = 0
    const paint = () => {
      frame = 0
      const y = window.scrollY
      node.style.height = `${Math.max(360, 660 - y * 0.85).toFixed(0)}px`
      node.style.setProperty('--hero-fs', `${Math.max(29, 46 - y * 0.055).toFixed(1)}px`)
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(paint) }
    paint()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => { window.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame) }
  }, [ref, enabled])
}

export default function ShiftPage() {
  const { domainSlug, ktSlug } = useParams()
  const { domain, shift, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug })
  useDocumentMeta(shift?.title, shift?.dek)
  const heroRef = useRef(null)
  useHeroShrink(heroRef, Boolean(shift?.heroImage))

  if (loading && !shift) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift) return <Missing what="shift" />

  const image = shift.heroImage

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      <div className="absolute z-[48]" style={{ top: 156, left: 22, maxWidth: 300 }}>
        <Breadcrumb
          crumb={domain.crumb}
          items={[
            { label: 'Home', to: '/' },
            { label: domain.name, to: `/map/${domain.slug}` },
            { label: unquote(shift.title) },
          ]}
        />
      </div>

      <header
        ref={heroRef}
        className="relative box-border flex flex-col overflow-hidden text-white"
        style={{
          height: image ? 660 : 340,
          padding: '152px 22px 22px',
          backgroundImage: [
            'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.58) 100%)',
            'repeating-linear-gradient(115deg, rgba(255,255,255,0.1) 0 10px, rgba(255,255,255,0) 10px 26px)',
            domain.grad,
          ].join(', '),
        }}
      >
        {image && (
          <>
            <span
              aria-hidden="true" className="absolute inset-0 z-0"
              style={{ backgroundImage: cssUrl(image), backgroundSize: 'cover', backgroundPosition: 'center 30%' }}
            />
            <span
              aria-hidden="true" className="absolute inset-0 z-[1]"
              /* Legibility for the white H1, and nothing more. The design's
                 grade over the hand-made photograph was a literal Society ramp,
                 which both washed the art out and repainted an Economy or
                 Consumers hero pink. The generated posters are already lit by
                 their own sphere, so this only needs to darken the foot of the
                 frame — in that sphere's deep ink, not Society's. */
              style={{
                backgroundImage: [
                  'linear-gradient(180deg,',
                  'transparent 24%,',
                  'color-mix(in srgb, var(--a-deep) 26%, transparent) 56%,',
                  'color-mix(in srgb, var(--a-deep) 88%, transparent) 100%)',
                ].join(' '),
              }}
            />
          </>
        )}
        <div className="canvas relative z-[2] mt-auto" style={{ animation: 'ssRise 0.6s var(--ease-out) 0.16s' }}>
          <h1
            className="t-title"
            style={{ margin: 0, fontSize: `var(--hero-fs, ${image ? 46 : 32}px)`, lineHeight: 1.1, letterSpacing: '0.005em' }}
          >
            {shift.title}
          </h1>
        </div>
      </header>

      <div
        className="canvas gutter flex flex-col"
        style={{ paddingTop: 26, gap: 'var(--module-gap)', animation: 'ssRise 0.6s var(--ease-out) 0.24s' }}
      >
        <Modules
          modules={shift.modules}
          ctx={{
            scope: 'shift',
            domain,
            subs: shift.subshifts,
            subCardStyle: 'tile',
            basePath: `/map/${domain.slug}/${shift.slug}`,
          }}
        />
        <div style={{ margin: '22px -22px 0' }}><Footer /></div>
      </div>
    </article>
  )
}
