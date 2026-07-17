/**
 * CometStreak — a single Key Shift on the Sphere (domain) page.
 *
 * A numbered, quoted shift title trailing a colored comet streak, with a
 * punchy one-line subtitle. Staggered left/right for a zig-zag rhythm.
 *
 * Props: index, name, subtitle, color, href, align ('left' | 'right')
 */
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { cometInView } from '../atmosphere'
import { pad } from '../palette'

export default function CometStreak({ index, name, subtitle, color, href, align = 'left', delay = 0 }) {
  const right = align === 'right'
  return (
    <motion.div
      {...cometInView(delay)}
      className={right ? 'md:ml-auto md:mr-0 md:pl-16' : 'md:mr-auto md:pr-16'}
      style={{ maxWidth: '46rem' }}
    >
      <Link
        to={href}
        className="comet-streak group flex items-center gap-4 rounded-full py-4 pl-5 pr-6 transition-colors"
        style={{ '--streak': color }}
      >
        <span
          className="font-mono text-sm tabular-nums shrink-0 font-semibold"
          style={{ color }}
        >
          {pad(index, 2)}
        </span>
        <div className="min-w-0">
          <h3 className="font-display font-bold text-xl sm:text-2xl text-ink leading-tight truncate">
            &ldquo;{name}&rdquo;
          </h3>
          {subtitle && (
            <p className="text-ink-soft text-sm leading-snug mt-0.5 line-clamp-1">
              {subtitle}
            </p>
          )}
        </div>
        <span
          aria-hidden="true"
          className="ml-auto shrink-0 text-lg opacity-0 -translate-x-2 transition-all group-hover:opacity-100 group-hover:translate-x-0"
          style={{ color }}
        >
          →
        </span>
      </Link>
    </motion.div>
  )
}
