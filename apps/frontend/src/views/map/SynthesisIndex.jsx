import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useMapLookup } from './MapDataContext'
import StickyBreadcrumb from './components/Breadcrumbs'
import {
  EASE_WARP, EASE_GENTLE,
  DUR_CONTENT, STAGGER_CARD,
  fadeUp, staggerContainer,
} from './motion'

/**
 * SynthesisIndex — /map/synthesis
 *
 * Insight cards grouped by domain (scenario layer removed), each expandable
 * with an animated height reveal. A domain filter narrows the set.
 * Entrance: staggered fade-up per group then per card within each group.
 */
export default function SynthesisIndex() {
  const { synthesis_insights, domainsArr, domainMap } = useMapLookup()
  const [selectedDomains, setSelectedDomains] = useState([])

  const toggleDomain = (id) => {
    setSelectedDomains(prev =>
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    )
  }

  // Domain sort order, for stable grouping.
  const domainOrder = Object.fromEntries(domainsArr.map((d, i) => [d.id, i]))

  // Sort: by domain order then alphabetical within.
  const sorted = [...(synthesis_insights || [])].sort((a, b) => {
    const da = domainOrder[a.domain_id] ?? 99
    const db = domainOrder[b.domain_id] ?? 99
    if (da !== db) return da - db
    return a.name.localeCompare(b.name)
  })

  // Filter
  const filtered = selectedDomains.length === 0
    ? sorted
    : sorted.filter(ins => selectedDomains.includes(ins.domain_id))

  // Group by domain (preserving order from filtered list)
  const groups = []
  const seen = new Set()
  for (const ins of filtered) {
    if (!seen.has(ins.domain_id)) {
      seen.add(ins.domain_id)
      groups.push({
        domainId: ins.domain_id,
        domain: domainMap[ins.domain_id] || null,
        insights: filtered.filter(i => i.domain_id === ins.domain_id),
      })
    }
  }

  const hasFilter = selectedDomains.length > 0

  return (
    <>
    <StickyBreadcrumb crumbs={[
      { label: 'Home', to: '/map' },
      { label: 'AI-Synthesised Patterns' },
    ]} />
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-14">

      {/* ── Header ── */}
      <motion.div
        className="mb-10"
        initial="hidden"
        animate="visible"
        variants={staggerContainer(0.07, 0.05)}
      >
        <motion.div variants={fadeUp} className="flex items-center gap-3 mb-3">
          <h1 className="font-editorial text-3xl sm:text-4xl text-cream">
            AI-Synthesised Patterns
          </h1>
          <span className="font-mono text-[9px] uppercase tracking-widest border border-violet-800/50 text-violet-400 rounded px-1.5 py-0.5 shrink-0">
            AI-generated
          </span>
        </motion.div>
        <motion.p variants={fadeUp} className="text-neutral-400 text-sm leading-relaxed max-w-2xl">
          Insights that emerge from combining claims across thinkers, but that no single
          thinker has named explicitly. Synthesised by AI from the full evidence base.
        </motion.p>
      </motion.div>

      {/* ── Domain filter ── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DUR_CONTENT, ease: EASE_GENTLE, delay: 0.18 }}
        className="flex flex-wrap gap-2 mb-10 items-center"
      >
        <span className="font-mono text-[9px] uppercase tracking-widest text-neutral-600 mr-1">
          Filter by domain
        </span>
        {domainsArr.map(d => {
          const active = selectedDomains.includes(d.id)
          return (
            <motion.button
              key={d.id}
              type="button"
              onClick={() => toggleDomain(d.id)}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              className={`px-2.5 py-1 rounded border text-[10px] font-mono uppercase tracking-widest transition-colors max-w-[160px] truncate ${
                active
                  ? 'border-[var(--map-macro)] text-[var(--map-macro)] bg-[var(--map-macro-soft)]'
                  : 'border-neutral-800 text-neutral-500 hover:border-neutral-700 hover:text-neutral-300'
              }`}
              title={d.name}
            >
              {d.name.length > 18 ? d.name.slice(0, 17) + '…' : d.name}
            </motion.button>
          )
        })}
        {hasFilter && (
          <button
            type="button"
            onClick={() => setSelectedDomains([])}
            className="text-[10px] font-mono uppercase tracking-widest text-neutral-500 hover:text-cream transition-colors ml-2"
          >
            Clear
          </button>
        )}
        <span className="font-mono text-[10px] text-neutral-600 ml-auto">
          {filtered.length}/{sorted.length} insights
        </span>
      </motion.div>

      {/* ── Grouped insight cards ── */}
      <AnimatePresence mode="wait">
        {filtered.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="py-12 text-center"
          >
            <p className="text-neutral-500 font-mono text-xs uppercase tracking-widest mb-4">
              No insights match these filters.
            </p>
            <button
              type="button"
              onClick={() => setSelectedDomains([])}
              className="text-[11px] font-mono uppercase tracking-widest text-neutral-500 hover:text-cream border border-neutral-800 rounded px-3 py-1.5 transition-colors"
            >
              Clear filters
            </button>
          </motion.div>
        ) : (
          <motion.div
            key="content"
            initial="hidden"
            animate="visible"
            variants={staggerContainer(0.05, 0.1)}
            className="space-y-12"
          >
            {groups.map(({ domainId, domain, insights }) => (
              <InsightGroup
                key={domainId}
                domain={domain}
                insights={insights}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </>
  )
}

// ── InsightGroup ──────────────────────────────────────────────────────────────

function InsightGroup({ domain, insights }) {
  return (
    <motion.section variants={fadeUp}>
      {/* Domain section divider */}
      {domain && (
        <div className="flex items-center gap-3 mb-5">
          <div className="h-px flex-1 bg-neutral-800/80" />
          <Link
            to={`/map/domains/${domain.id}`}
            className="font-mono text-[9px] uppercase tracking-widest text-[var(--map-macro)] hover:text-cream transition-colors shrink-0 px-1"
            onClick={e => e.stopPropagation()}
          >
            {domain.name}
          </Link>
          <div className="h-px flex-1 bg-neutral-800/80" />
        </div>
      )}

      {/* Cards in a 2-col grid */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 gap-4"
        variants={staggerContainer(STAGGER_CARD, 0)}
      >
        {insights.map(ins => (
          <InsightCard key={ins.id} insight={ins} domain={domain} />
        ))}
      </motion.div>
    </motion.section>
  )
}

// ── InsightCard ───────────────────────────────────────────────────────────────

function InsightCard({ insight: ins, domain }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <motion.article
      variants={fadeUp}
      layout
      whileHover={{ y: -3, transition: { duration: 0.18, ease: EASE_GENTLE } }}
      className="bg-neutral-900/30 border border-neutral-800 rounded-lg overflow-hidden hover:border-neutral-700 transition-colors cursor-pointer"
      onClick={() => setExpanded(e => !e)}
    >
      {/* Always-visible header */}
      <div className="p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3 mb-3">
          <h3 className="font-editorial text-lg sm:text-xl leading-snug text-cream">
            {ins.name}
          </h3>
          <div className="flex items-center gap-2 shrink-0 pt-1">
            <span className="font-mono text-[8px] uppercase tracking-widest border border-violet-900/60 text-violet-500 rounded px-1.5 py-0.5">
              AI
            </span>
            <motion.span
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.22 }}
              className="text-neutral-600 text-[9px] select-none"
              aria-hidden="true"
            >
              ▼
            </motion.span>
          </div>
        </div>

        {/* Collapsed preview */}
        {!expanded && (
          <p className="text-sm text-neutral-500 leading-relaxed line-clamp-2">
            {ins.description}
          </p>
        )}
      </div>

      {/* Expanded body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: EASE_WARP }}
            className="overflow-hidden"
          >
            <div className="px-5 sm:px-6 pb-5 sm:pb-6 border-t border-neutral-800">
              <p className="text-sm text-neutral-400 leading-relaxed mt-4">
                {ins.description}
              </p>
              {ins.contributing_claim_ids?.length > 0 && (
                <div className="flex items-center gap-3 pt-4 mt-4 border-t border-neutral-800/60">
                  <span className="font-mono text-[9px] uppercase tracking-widest text-neutral-600">
                    {ins.contributing_claim_ids.length} supporting claim{ins.contributing_claim_ids.length !== 1 ? 's' : ''}
                  </span>
                  {domain && (
                    <Link
                      to={`/map/domains/${domain.id}`}
                      className="ml-auto font-mono text-[9px] uppercase tracking-widest text-[var(--map-macro)] hover:text-cream transition-colors"
                      onClick={e => e.stopPropagation()}
                    >
                      View domain →
                    </Link>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}
