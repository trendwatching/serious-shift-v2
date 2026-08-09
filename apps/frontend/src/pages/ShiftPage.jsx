import { useEffect, useRef } from 'react'
import { useParams } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { cssUrl } from '../lib/safeUrl'
import { useResolved } from '../lib/useDomains'
import { Breadcrumb } from '../chrome/Breadcrumb'
import { Footer } from '../chrome/Footer'
import { Modules } from '../modules'
import { Loading, Missing, Unavailable } from './states'
import { isSphere, quoted, trendTitle, unquote } from '../lib/theme'

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
    // Bounds come from the stylesheet, not from here: this writes an inline
    // height, which beats every rule, so a constant would drag the desktop hero
    // back to the phone's 660px on the first scroll event.
    const bound = (name, fallback) => {
      const value = Number.parseFloat(getComputedStyle(node).getPropertyValue(name))
      return Number.isFinite(value) ? value : fallback
    }
    const paint = () => {
      frame = 0
      const y = window.scrollY
      const tall = bound('--hero-h', 660)
      const short = bound('--hero-h-min', 360)
      node.style.height = `${Math.max(short, tall - y * 0.85).toFixed(0)}px`
      // The title shrinks 46 → 29 on the design canvas. Both ends and the rate
      // are now taken from `--t-hero` rather than written out, for the same
      // reason the height is: this writes an inline size that beats every rule,
      // so a literal 46 would yank a 68px desktop title down to the phone's on
      // the first scroll event — and then shrink it at the phone's pace.
      const base = bound('--t-hero', 46)
      node.style.setProperty(
        '--hero-fs',
        `${Math.max(base * 0.63, base - y * 0.055 * (base / 46)).toFixed(1)}px`,
      )
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(paint) }
    paint()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => { window.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame) }
  }, [ref, enabled])
}

export default function ShiftPage() {
  const { domainSlug, ktSlug } = useParams()
  // Not a sphere — `/:domainSlug` matches any single segment now, so this is
  // an unknown path and has to 404 rather than render a sphere.
  if (!isSphere(domainSlug)) return <Missing />
  const { domain, shift, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug })
  // `trendTitle`, not the raw name: CSS uppercases the heading on the page but
  // `text-transform` never reaches the tab, the unfurl or a copy-paste, so a
  // shift shared into WhatsApp read `Delegated Discovery` while the page it
  // opened said `DELEGATED DISCOVERY`. Matches `trend_title` in seo.rs, or the
  // title would visibly change a beat after load.
  useDocumentMeta(trendTitle(shift?.title), shift?.dek)
  const heroRef = useRef(null)
  useHeroShrink(heroRef, Boolean(shift?.heroImage))

  // Gated on the modules, not on `shift`: the index carries enough of a shift
  // to satisfy `!shift` while its body is still in flight, so the page would
  // paint a hero with nothing under it and then grow. Same failure the sphere
  // page had at 0.39 — see the note in DomainPage.
  if (loading && !shift?.modules?.length) return <Loading hero="hero-tall" />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift) return <Missing what="shift" />

  const image = shift.heroImage

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      <div className="crumb-float z-[48]">
        <Breadcrumb
          crumb={domain.crumb}
          items={[
            { label: 'Home', to: '/' },
            { label: domain.name, to: `/${domain.slug}` },
            { label: unquote(shift.title) },
          ]}
        />
      </div>

      <header
        ref={heroRef}
        className={`${image ? 'hero-tall' : 'hero-flat'} relative box-border flex flex-col overflow-hidden text-white`}
        style={{
          padding: 'calc(var(--topbar) + 68px) 0 22px',
          backgroundImage: [
            'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.58) 100%)',
            'repeating-linear-gradient(115deg, rgba(255,255,255,0.1) 0 10px, rgba(255,255,255,0) 10px 26px)',
            domain.grad,
          ].join(', '),
        }}
      >
        {image && (
          <>
            {/* The URLs are custom properties, not `backgroundImage`. An inline
                style beats every layer, so painting it here would silently
                discard the desktop rule that swaps in the landscape cut —
                `.hero-art` in components.css owns the painting. */}
            <span
              aria-hidden="true" className="hero-art absolute inset-0 z-0"
              style={{ '--art': cssUrl(image), '--art-wide': cssUrl(shift.heroImageWide) }}
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
        <div className="canvas gutter relative z-[2] mt-auto" style={{ animation: 'ssRise 0.6s var(--ease-out) 0.16s' }}>
          <h1
            className="t-title"
            style={{ margin: 0, fontSize: `var(--hero-fs, var(${image ? '--t-hero' : '--t-sub'}))`, lineHeight: 1.1, letterSpacing: '0.005em' }}
          >
            {quoted(shift.title)}
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
            basePath: `/${domain.slug}/${shift.slug}`,
          }}
        />
      </div>

      {/* Outside the canvas, not inside it with the gutter cancelled: a footer
          band spans the page at every width, and nesting it was the only reason
          it ever needed a width of its own. */}
      <div style={{ marginTop: 22 }}><Footer /></div>
    </article>
  )
}
