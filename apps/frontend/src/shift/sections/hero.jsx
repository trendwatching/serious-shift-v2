/** The gradient header every reading view opens on. */
import { BackButton, Eyebrow, PAD } from './primitives'
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
      className="relative flex flex-col text-white box-border"
      style={{ minHeight, paddingTop: 62, paddingBottom: PAD, backgroundImage: layers.join(', ') }}
    >
      {/* Content shares the reading column's exact measure and padding so the
          hero lines up with the body copy instead of hugging the edge. */}
      <div className="mx-auto flex w-full flex-1 flex-col px-[22px] lg:max-w-[860px]">
        {onBack && <BackButton onClick={onBack} />}
        <div className="mt-auto a-rise" style={{ animationDelay: '0.14s' }}>
          {eyebrow && (
            <div className="t-eyebrow" style={{ color: eyebrowColor || 'rgba(255,255,255,0.9)', letterSpacing: '0.18em' }}>
              {eyebrow}
            </div>
          )}
          {title && (face === 'display' ? (
            <h1 className="t-display mt-2.5 text-[44px] leading-[0.98] lg:text-[clamp(56px,5vw,80px)]" style={{ letterSpacing: '-0.035em' }}>
              {title}
            </h1>
          ) : (
            <h1 className="t-title mt-2.5 text-[32px] leading-[1.1] lg:text-[44px]">{quoteTitle(title)}</h1>
          ))}
          {sub && <div className="mt-2.5 text-[13.5px] opacity-90">{sub}</div>}
          {blurb && <p className="mt-3.5 max-w-[290px] text-[15px] leading-[1.5] opacity-95 lg:max-w-[520px] lg:text-[17px]">{blurb}</p>}
        </div>
      </div>
    </header>
  )
}
