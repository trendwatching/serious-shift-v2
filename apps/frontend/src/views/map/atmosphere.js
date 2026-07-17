/**
 * atmosphere.js — motion vocabulary for the redesigned "smoke & comet" look.
 *
 * Replaces the old cinematic warp system. Everything here is transform/opacity
 * only and respects prefers-reduced-motion (Framer's MotionConfig in Map.jsx
 * handles the global reduced-motion switch).
 *
 * IMPORTANT: these helpers return EXPLICIT prop objects (initial/animate/
 * whileInView as value objects, not variant labels). We deliberately avoid
 * variant-label propagation — a parent animating to a named label bleeds that
 * label onto descendants and clobbers their own reveal, which is fragile.
 */

export const EASE_OUT    = [0.22, 0.61, 0.36, 1]
export const EASE_GENTLE = [0.33, 0.0, 0.2, 1]

// Page mount fade — spread onto a page's outer wrapper.
export const pageIn = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, ease: EASE_OUT },
}

// Immediate fade-up (above-the-fold hero elements). `delay` staggers siblings.
export function fadeUp(delay = 0) {
  return {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.55, ease: EASE_OUT, delay },
  }
}

// Fade-up on scroll into view (below-the-fold sections/cards).
export function fadeInView(delay = 0) {
  return {
    initial: { opacity: 0, y: 18 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, margin: '-60px' },
    transition: { duration: 0.55, ease: EASE_OUT, delay },
  }
}

// Comet streak sweeps in from its tail (left) on scroll into view.
export function cometInView(delay = 0) {
  return {
    initial: { opacity: 0, x: -36 },
    whileInView: { opacity: 1, x: 0 },
    viewport: { once: true, margin: '-60px' },
    transition: { duration: 0.6, ease: EASE_OUT, delay },
  }
}

// A slow, looping 0-G drift for smoke-blobs. Index varies phase/amplitude.
export function driftFor(index = 0) {
  const a = ((index * 13) % 7) - 3
  const b = ((index * 17) % 5) - 2
  const dur = 9 + (index % 4) * 1.6
  return {
    animate: { x: [0, 6 + a, -5 + b, 0], y: [0, -7 + b, 6 + a, 0] },
    transition: {
      duration: dur,
      ease: 'easeInOut',
      repeat: Infinity,
      repeatType: 'mirror',
      delay: (index % 4) * 0.5,
    },
  }
}
