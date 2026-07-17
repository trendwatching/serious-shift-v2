/**
 * StatCallout — the oversized numeral + sourced context sentence.
 *
 * Props:
 *   value   — the headline figure (e.g. "50%")
 *   context — the sentence around it (e.g. "chance of high-level AI …")
 *   source  — optional attribution ("AI Impacts · 2024")
 */
import { motion } from 'framer-motion'
import { fadeInView } from '../atmosphere'

export default function StatCallout({ value, context, source }) {
  if (!value) return null
  return (
    <motion.div
      {...fadeInView()}
      className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-8 py-8"
    >
      <span className="stat-numeral text-6xl sm:text-7xl lg:text-8xl shrink-0">
        {value}
      </span>
      <div className="max-w-md">
        {context && (
          <p className="text-ink text-lg sm:text-xl leading-snug font-display font-medium">
            {context}
          </p>
        )}
        {source && (
          <p className="mt-2 font-mono text-[11px] uppercase tracking-widest text-ink-faint">
            {source}
          </p>
        )}
      </div>
    </motion.div>
  )
}
