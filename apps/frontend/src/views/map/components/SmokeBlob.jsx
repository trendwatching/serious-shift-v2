/**
 * SmokeBlob — the signature organic "smoke cloud" for a domain.
 *
 * A tinted, feathered cloud with an optional photographic fill and a comet
 * tail, gently drifting in place. Used as the four domain doorways on the
 * homepage. Clicking navigates to the domain (Sphere) page.
 *
 * The cloud edge is feathered (radial gradient fading to transparent + blur)
 * rather than a hard-clipped circle, so it reads as smoke rather than a ball.
 *
 * Props: color, image, name, eyebrow, href, index
 */
import { motion, useReducedMotion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { driftFor, EASE_GENTLE } from '../atmosphere'

// Off-centre focal points so the four clouds don't look identical.
const FOCI = ['42% 38%', '56% 44%', '46% 52%', '52% 40%']
// Elliptical organic silhouettes (used for the soft mask + subtle rotation).
const SKEW = [-4, 5, -2, 3]

export default function SmokeBlob({ color, image, name, eyebrow, href, index = 0 }) {
  const prefersReduced = useReducedMotion()
  const drift = prefersReduced ? {} : driftFor(index)
  const focus = FOCI[index % FOCI.length]
  const skew = SKEW[index % SKEW.length]

  const cloud = `radial-gradient(60% 58% at ${focus},
    color-mix(in oklab, ${color} 92%, white 8%) 0%,
    color-mix(in oklab, ${color} 82%, transparent) 42%,
    color-mix(in oklab, ${color} 40%, transparent) 66%,
    transparent 80%)`

  return (
    <motion.div
      className="relative"
      animate={drift.animate}
      transition={drift.transition}
      whileHover={{ scale: 1.03, transition: { duration: 0.3, ease: EASE_GENTLE } }}
    >
      <Link
        to={href}
        aria-label={`Explore ${name}`}
        className="group relative block aspect-[5/4] w-full"
        style={{ transform: `rotate(${skew}deg)` }}
      >
        {/* comet tail */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 -left-1/4 h-2/5 w-3/4 -translate-y-1/2 rounded-full blur-3xl opacity-80"
          style={{ background: `linear-gradient(90deg, transparent, color-mix(in oklab, ${color} 60%, transparent))` }}
        />

        {/* photographic fill, feathered to the cloud shape */}
        {image && (
          <img
            src={image}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 h-full w-full object-cover opacity-60 transition-transform duration-700 group-hover:scale-105"
            style={{
              WebkitMaskImage: `radial-gradient(58% 56% at ${focus}, #000 55%, transparent 78%)`,
              maskImage: `radial-gradient(58% 56% at ${focus}, #000 55%, transparent 78%)`,
            }}
            draggable="false"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
        )}

        {/* the soft colored cloud */}
        <div
          className="absolute inset-0"
          style={{ background: cloud, filter: 'blur(4px) saturate(1.05)', mixBlendMode: image ? 'multiply' : 'normal' }}
        />
        {/* inner highlight for volume */}
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{ background: `radial-gradient(30% 28% at ${focus}, rgba(255,255,255,0.5), transparent 60%)`, filter: 'blur(6px)' }}
        />

        {/* content */}
        <div className="relative z-10 flex h-full flex-col items-center justify-center text-center px-6" style={{ transform: `rotate(${-skew}deg)` }}>
          {eyebrow && (
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/85 mb-1.5 drop-shadow">
              {eyebrow}
            </span>
          )}
          <h2 className="font-display font-extrabold text-white text-3xl sm:text-4xl lg:text-5xl drop-shadow-[0_2px_10px_rgba(0,0,0,0.25)]">
            {name}
          </h2>
          <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-4 py-1.5 text-xs font-semibold uppercase tracking-widest text-ink shadow-md transition-transform group-hover:-translate-y-0.5">
            Explore <span aria-hidden="true">✦</span>
          </span>
        </div>
      </Link>
    </motion.div>
  )
}
