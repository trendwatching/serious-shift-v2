/** The gradient header every reading view opens on. */
import { BackButton, Eyebrow, Frame } from './primitives'
import { quoteTitle } from '../theme'

export function GradientHero({ grad, onBack, eyebrow, eyebrowColor, title, sub, blurb, minHeight = 300, stripes, face = 'title' }) {
  // The darkening wash + diagonal texture belong to the shift hero only; the
  // domain and sub-shift heroes are a clean gradient in the design.
  const layers = [
    stripes && 'linear-gradient(180deg, rgba(27,22,32,0) 34%, rgba(27,22,32,0.58) 100%)',
    stripes && 'repeating-linear-gradient(115deg, rgba(255,255,255,0.1) 0 10px, rgba(255,255,255,0) 10px 26px)',
    grad,
  ].filter(Boolean)

  return (
    <header
      className="relative flex flex-col box-border pb-[22px] text-white md:pb-8 lg:pb-10"
      style={{
        // At least the height the design gives it, and at least a third of the
        // window — so a tall desktop viewport doesn't open on a thin strip.
        minHeight: minHeight ? `max(${minHeight}px, 32vh)` : 0,
        // Clears the sticky top bar. This used to be a literal 62 that happened
        // to equal --topbar; naming it means the hero can't drift out from
        // under the bar, and it picks up the iOS safe-area inset for free.
        paddingTop: 'calc(var(--topbar) + 0.75rem)',
        backgroundImage: layers.join(', '),
      }}
    >
      {/* The title sits in the same `--measure` track as the article below it.
          It used to be 860px against the body's 660px, which put the hero's
          left edge 94px out from every line of copy under it. */}
      <Frame className="flex flex-1 flex-col">
        <div className="w-prose flex flex-1 flex-col">
          {onBack && <BackButton onClick={onBack} />}
          <div className="mt-auto a-rise" style={{ animationDelay: '0.14s' }}>
            {eyebrow && (
              <div className="t-eyebrow" style={{ color: eyebrowColor || 'rgba(255,255,255,0.9)', letterSpacing: '0.18em' }}>
                {eyebrow}
              </div>
            )}
            {title && (face === 'display' ? (
              <h1 className="t-display mt-2.5 text-[44px] leading-[0.98] md:text-[52px] lg:text-[clamp(56px,5vw,80px)]" style={{ letterSpacing: '-0.035em' }}>
                {title}
              </h1>
            ) : (
              // Shift titles run 16 characters on average and 28 at the longest,
              // so at the measure this sets as a two-line block rather than a
              // single stretched line.
              <h1 className="t-title mt-2.5 text-[32px] leading-[1.1] md:text-[40px] lg:text-[52px] lg:leading-[1.05]">{quoteTitle(title)}</h1>
            ))}
            {sub && <div className="t-body mt-2.5 opacity-90">{sub}</div>}
            {blurb && <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 md:max-w-none md:text-[16px] lg:text-[17px]">{blurb}</p>}
          </div>
        </div>
      </Frame>
    </header>
  )
}
