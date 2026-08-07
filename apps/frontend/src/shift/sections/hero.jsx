/** The gradient header every reading view opens on. */
import { useEffect, useRef } from 'react'
import { Eyebrow, Frame } from './primitives'
import { quoteTitle } from '../theme'

/**
 * Shrink the hero as the page scrolls, the way the design build does.
 *
 * The build interpolates height 660→360 and the title 46→29px against its own
 * scroller. Here the window is the scroller, and the values are written straight
 * to the node through a ref rather than held in state: this fires on every
 * scroll frame, and re-rendering a route's whole header sixty times a second to
 * change two numbers is the difference between a smooth page and a janky one.
 *
 * Skipped entirely when the reader has asked for reduced motion — a header that
 * resizes under you is exactly the kind of movement that setting is for.
 */
function useHeroShrink(ref, { from, to, fontFrom, fontTo, rate, fontRate } = {}) {
  useEffect(() => {
    const node = ref.current
    if (!node) return undefined
    // Most heroes do not shrink. Without this guard the arithmetic below runs on
    // undefined, writes `NaNpx` into --hero-fs, and the title silently collapses
    // to the inherited 16px — which is exactly what it did.
    if (![from, to, fontFrom, fontTo, rate, fontRate].every(Number.isFinite)) return undefined
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined

    let frame = 0
    const paint = () => {
      frame = 0
      const y = window.scrollY
      node.style.minHeight = `${Math.max(to, from - y * rate).toFixed(0)}px`
      node.style.setProperty('--hero-fs', `${Math.max(fontTo, fontFrom - y * fontRate).toFixed(1)}px`)
    }
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(paint) }

    paint()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [ref, from, to, fontFrom, fontTo, rate, fontRate])
}

export function GradientHero({
  grad, eyebrow, eyebrowColor, title, sub, blurb, minHeight = 300,
  stripes, face = 'title', image, imageWash, shrink, children, bottomPad,
}) {
  const ref = useRef(null)
  useHeroShrink(ref, shrink || {})

  // The darkening wash + diagonal texture belong to the shift hero only; the
  // domain and sub-shift heroes are a clean gradient in the design.
  const layers = [
    stripes && 'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.58) 100%)',
    stripes && 'repeating-linear-gradient(115deg, rgba(255,255,255,0.1) 0 10px, rgba(255,255,255,0) 10px 26px)',
    !image && 'linear-gradient(rgba(13,11,16,0.38), rgba(13,11,16,0.38))',
    grad,
  ].filter(Boolean)

  return (
    <header
      ref={ref}
      className="relative box-border flex flex-col overflow-hidden pb-[22px] text-white md:pb-8 lg:pb-10"
      style={{
        // The domain sheet rides 34px up over its hero, so that hero has to
        // reserve the space or the overlap crops the last line of the blurb.
        ...(bottomPad ? { paddingBottom: bottomPad } : null),
        // At least the height the design gives it, and at least a third of the
        // window — so a tall desktop viewport doesn't open on a thin strip.
        minHeight: minHeight ? `max(${minHeight}px, 32vh)` : 0,
        // Clears the sticky top bar. This used to be a literal 62 that happened
        // to equal --topbar; naming it means the hero can't drift out from
        // under the bar, and it picks up the iOS safe-area inset for free.
        paddingTop: 'calc(var(--topbar) + 0.75rem)',
        backgroundImage: layers.join(', '),
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      {/* A commissioned hero sits under a heavy accent wash rather than a neutral
          scrim: the photograph is there to give the page a register, and the
          wash is what keeps it unmistakably this domain's page. */}
      {image && (
        <>
          <span
            aria-hidden="true"
            className="absolute inset-0 z-0"
            style={{ backgroundImage: `url('${image}')`, backgroundSize: 'cover', backgroundPosition: 'center 30%' }}
          />
          <span aria-hidden="true" className="absolute inset-0 z-[1]" style={{ backgroundImage: imageWash }} />
        </>
      )}

      {/* The title sits in the same `--measure` track as the article below it. */}
      <Frame className="relative z-[2] flex flex-1 flex-col">
        <div className="w-prose flex flex-1 flex-col">
          {children}
          <div className="mt-auto a-rise" style={{ animationDelay: '0.14s' }}>
            {eyebrow && (
              <div className="t-eyebrow" style={{ color: eyebrowColor || 'rgba(255,255,255,0.9)', letterSpacing: '0.18em' }}>
                {eyebrow}
              </div>
            )}
            {title && (face === 'display' ? (
              <h1
                className="t-display mt-2.5 uppercase leading-[0.98]"
                style={{ letterSpacing: '-0.03em', fontSize: 'var(--hero-fs, clamp(40px, 12vw, 46px))' }}
              >
                {title}
              </h1>
            ) : (
              // Shift titles run 16 characters on average and 28 at the longest,
              // so at the measure this sets as a two-line block rather than a
              // single stretched line.
              <h1
                className="t-title mt-2.5 leading-[1.1]"
                style={{ fontSize: 'var(--hero-fs, clamp(32px, 9vw, 46px))' }}
              >
                {quoteTitle(title)}
              </h1>
            ))}
            {sub && <p className="t-body mt-2.5 text-white">{sub}</p>}
            {blurb && <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 md:max-w-none md:text-[16px] lg:text-[17px]">{blurb}</p>}
          </div>
        </div>
      </Frame>
    </header>
  )
}

export { Eyebrow }
