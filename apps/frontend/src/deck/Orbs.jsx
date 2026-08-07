/**
 * The drifting colour field behind the homepage headline.
 *
 * One orb per domain plus the brand yellow, so the whole palette is present
 * before a word about it is read. Five paths on five different periods
 * (29–41s) mean the composition never repeats within a visit.
 *
 * Decorative and transform-only, so it stays on the compositor; the
 * reduced-motion guard removes it entirely.
 */
const ORBS = [
  { w: 300, h: 300, bottom: 60, left: -80, at: '42% 38%', rgb: '237,2,107', a: 0.6, b: 0.26, blur: 24, anim: 'ssFloat 34s ease-in-out infinite' },
  { w: 280, h: 280, top: 150, right: -90, at: '44% 40%', rgb: '15,145,238', a: 0.52, b: 0.22, blur: 26, anim: 'ssOrb1 29s ease-in-out infinite' },
  { w: 260, h: 260, bottom: -50, right: 10, at: '46% 42%', rgb: '173,176,58', a: 0.52, b: 0.22, blur: 24, anim: 'ssOrb2 37s ease-in-out infinite' },
  { w: 250, h: 250, top: 60, left: 30, at: '44% 40%', rgb: '246,85,16', a: 0.46, b: 0.2, blur: 28, anim: 'ssOrb3 32s ease-in-out infinite' },
  { w: 220, h: 220, bottom: 170, left: 140, at: '44% 40%', rgb: '253,255,133', a: 0.85, b: 0.36, blur: 22, anim: 'ssFloat 41s ease-in-out infinite reverse' },
]

export default function Orbs() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {ORBS.map((o, i) => {
        const { w, h, at, rgb, a, b, blur, anim, ...pos } = o
        return (
          <div
            key={i}
            className="absolute rounded-full"
            style={{
              ...pos, width: w, height: h,
              background: `radial-gradient(circle at ${at}, rgba(${rgb},${a}), rgba(${rgb},${b}) 48%, rgba(${rgb},0) 72%)`,
              filter: `blur(${blur}px)`,
              animation: anim,
              willChange: 'transform',
            }}
          />
        )
      })}
    </div>
  )
}
