/**
 * DomainDetail — the Sphere page (/map/:domainSlug).
 *
 * A domain's Key Shifts rendered as staggered comet streaks. Clicking a streak
 * opens that Key Shift. Also matches the legacy /map/domains/:domainId route.
 */
import { useParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMapLookup } from './MapDataContext'
import Breadcrumbs from './components/Breadcrumbs'
import CometStreak from './components/CometStreak'
import { paletteFor, pad } from './palette'
import { pageIn, fadeUp, fadeInView } from './atmosphere'

export default function DomainDetail() {
  const params = useParams()
  const domainId = params.domainSlug || params.domainId
  const {
    isV2, domainMap, ktsByDomain, ktsByDomainId,
    subTrendsByKtId, insightsByDomain, ktSlug,
  } = useMapLookup()

  const domain  = domainMap[domainId]
  const palette = paletteFor(domainId)
  const kts = (ktsByDomainId[domainId]?.length ? ktsByDomainId[domainId] : ktsByDomain[domainId]) || []
  const insights = insightsByDomain[domainId] || []

  if (!isV2 || !domain) {
    return (
      <div className="max-w-2xl mx-auto px-4 pt-16 pb-24 text-center">
        <p className="font-mono text-[10px] uppercase tracking-widest text-ink-faint mb-3">
          AI × {domainId || 'sphere'}
        </p>
        <h1 className="font-display font-bold text-3xl text-ink mb-4">Key Shifts generating…</h1>
        <p className="text-ink-soft text-sm leading-relaxed mb-8">The generator hasn&rsquo;t run for this sphere yet.</p>
        <Link to="/map" className="font-mono text-[11px] uppercase tracking-widest text-accent hover:opacity-70">← Back to overview</Link>
      </div>
    )
  }

  const totalSubs = kts.reduce((n, kt) => n + (subTrendsByKtId[kt.id] || []).length, 0)

  return (
    <motion.div
      {...pageIn}
      style={{ background: `radial-gradient(120% 55% at 50% 0%, ${palette.soft} 0%, transparent 60%)` }}
    >
      <Breadcrumbs
        tint={palette.color}
        crumbs={[{ label: 'Home', to: '/map' }, { label: domain.name }]}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-8 sm:pt-10 pb-12">
        {/* ── Sphere hero ── */}
        <header className="mb-12 sm:mb-16 max-w-3xl">
          <motion.p {...fadeUp(0.05)} className="font-mono text-[11px] uppercase tracking-[0.2em] mb-3" style={{ color: palette.color }}>
            {(domain.label || `AI × ${domain.name}`).replace(/\s*\/\s*World$/, '')}
          </motion.p>
          <motion.h1 {...fadeUp(0.1)} className="font-display font-extrabold text-5xl sm:text-6xl lg:text-7xl uppercase leading-none" style={{ color: palette.color }}>
            {domain.name}
          </motion.h1>
          <motion.p {...fadeUp(0.16)} className="mt-5 text-ink-soft text-base sm:text-lg leading-relaxed">
            {domain.short_description || domain.description}
          </motion.p>
          <motion.div {...fadeUp(0.22)} className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1.5">
            <Stat value={pad(kts.length, 2)} label="Key Shifts" />
            <Sep />
            <Stat value={pad(totalSubs, 2)} label="Sub-shifts" />
          </motion.div>
        </header>

        {/* ── Key Shift comet streaks ── */}
        {kts.length === 0 ? (
          <p className="font-mono text-[11px] uppercase tracking-widest text-ink-faint py-12">No key shifts yet.</p>
        ) : (
          <div className="flex flex-col gap-5 sm:gap-6">
            {kts.map((kt, i) => (
              <CometStreak
                key={kt.id}
                index={i + 1}
                name={kt.name}
                subtitle={kt.subtitle || kt.description}
                color={palette.color}
                href={`/map/${domainId}/${ktSlug(kt)}`}
                align={i % 2 === 0 ? 'left' : 'right'}
                delay={Math.min(i * 0.05, 0.3)}
              />
            ))}
          </div>
        )}

        {/* ── AI-synthesised patterns (optional closing section) ── */}
        {insights.length > 0 && (
          <motion.section {...fadeInView()} className="mt-16 sm:mt-20">
            <div className="flex items-center gap-3 mb-6">
              <div className="h-px flex-1 bg-hairline" />
              <span className="font-mono text-[10px] uppercase tracking-widest shrink-0 px-1" style={{ color: palette.color }}>
                AI-Synthesised Patterns · {pad(insights.length, 2)}
              </span>
              <div className="h-px flex-1 bg-hairline" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {insights.map((ins) => (
                <article key={ins.id} className="rounded-2xl border border-hairline bg-paper p-5 sm:p-6 shadow-sm">
                  <h3 className="font-display font-semibold text-lg leading-snug text-ink mb-2">{ins.name}</h3>
                  <p className="text-sm text-ink-soft leading-relaxed">{ins.description}</p>
                </article>
              ))}
            </div>
          </motion.section>
        )}
      </div>
    </motion.div>
  )
}

function Stat({ value, label }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-mono text-sm text-ink">{value}</span>
      <span className="font-mono text-[10px] uppercase tracking-widest text-ink-faint">{label}</span>
    </div>
  )
}
function Sep() {
  return <span className="text-ink-faint/50 select-none font-mono text-xs" aria-hidden="true">·</span>
}
