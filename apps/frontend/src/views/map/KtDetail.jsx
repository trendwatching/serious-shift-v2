/**
 * KtDetail — the Key Shift page (/map/:domainSlug/:ktSlug).
 *
 * One key shift: quoted title + description, a headline stat, optional
 * proponents/skeptics, then the sub-shifts beneath it as cards.
 */
import { useParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMapLookup } from './MapDataContext'
import Breadcrumbs from './components/Breadcrumbs'
import StatCallout from './components/StatCallout'
import { paletteFor, VELOCITY_LABEL, pad } from './palette'
import { pageIn, fadeUp, fadeInView } from './atmosphere'

// Pull a leading figure ("50%", "$2.3B", "10x") off a stat sentence so it can
// render as the oversized numeral; the remainder becomes the context line.
function splitStat(text) {
  if (!text) return { value: null, context: null }
  const m = String(text).match(/^\s*(~?\$?\d[\d,.]*\s?(?:%|x|bn|b|m|k|×)?)\s*(.*)$/i)
  if (m && /\d/.test(m[1])) return { value: m[1].trim(), context: m[2].trim() || null }
  return { value: null, context: String(text) }
}

export default function KtDetail() {
  const { domainSlug, ktSlug: kSlug } = useParams()
  const {
    isV2, domainMap, subTrendsByKtId, claimsBySubTrendId, ktBySlug, subSlug,
  } = useMapLookup()

  const domain  = domainMap[domainSlug]
  const kt      = ktBySlug(domainSlug, kSlug)
  const palette = paletteFor(domainSlug)
  const subs    = kt ? (subTrendsByKtId[kt.id] || []) : []

  if (!isV2 || !domain || !kt) return <NotFound to={`/map/${domainSlug}`} label="key shift" />

  const velocityLabel = VELOCITY_LABEL[kt.velocity] || kt.velocity || ''
  const totalClaims = subs.reduce((n, st) => n + (claimsBySubTrendId[st.id] || []).length, 0)
  const stat = splitStat(kt.hero_stat?.value)
  const statSource = [kt.hero_stat?.thinker, kt.hero_stat?.source, kt.hero_stat?.year].filter(Boolean).join(' · ')

  return (
    <motion.div
      {...pageIn}
      style={{ background: `radial-gradient(120% 50% at 50% 0%, ${palette.soft} 0%, transparent 55%)` }}
    >
      <Breadcrumbs
        tint={palette.color}
        crumbs={[
          { label: 'Home', to: '/map' },
          { label: domain.name, to: `/map/${domainSlug}` },
          { label: kt.name },
        ]}
      />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 pt-8 sm:pt-10 pb-12">
        {/* ── Hero ── */}
        <header className="mb-10 sm:mb-14">
          <motion.div {...fadeUp(0.05)} className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="font-mono text-[11px] uppercase tracking-[0.2em]" style={{ color: palette.color }}>Key Shift</span>
            {velocityLabel && (
              <span className="font-mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full border"
                style={{ color: palette.color, borderColor: `color-mix(in oklab, ${palette.color} 35%, transparent)` }}>
                {velocityLabel}
              </span>
            )}
          </motion.div>

          <motion.h1 {...fadeUp(0.1)} className="font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl leading-[1.03] text-ink max-w-4xl">
            &ldquo;{kt.name}&rdquo;
          </motion.h1>

          {kt.description && (
            <motion.p {...fadeUp(0.16)} className="mt-5 text-ink-soft text-lg leading-relaxed max-w-3xl">
              {kt.description}
            </motion.p>
          )}

          {(kt.proponents?.length > 0 || kt.skeptics?.length > 0) && (
            <motion.div {...fadeUp(0.22)} className="mt-6 flex gap-x-8 gap-y-3 flex-wrap">
              {kt.proponents?.length > 0 && <ThinkerList label="Proponents" names={kt.proponents} accent={palette.color} />}
              {kt.skeptics?.length > 0 && <ThinkerList label="Skeptics" names={kt.skeptics} accent="var(--color-ink-faint)" />}
            </motion.div>
          )}
        </header>

        {/* ── Headline stat ── */}
        {stat.value ? (
          <div className="border-y border-hairline my-10">
            <StatCallout value={stat.value} context={stat.context} source={statSource || undefined} />
          </div>
        ) : stat.context ? (
          <motion.blockquote {...fadeInView()}
            className="border-y border-hairline my-10 py-8">
            <p className="font-display font-medium text-xl sm:text-2xl text-ink leading-snug max-w-3xl">{stat.context}</p>
            {statSource && <p className="mt-2 font-mono text-[11px] uppercase tracking-widest text-ink-faint">{statSource}</p>}
          </motion.blockquote>
        ) : null}

        {/* ── Sub-shifts ── */}
        <motion.h2 {...fadeInView()}
          className="font-display font-bold text-2xl sm:text-3xl text-ink mb-1">
          The {subs.length} Sub-shift{subs.length === 1 ? '' : 's'}
        </motion.h2>
        <p className="text-ink-soft text-sm mb-6">The concrete ways this shift shows up.</p>

        {subs.length === 0 ? (
          <p className="text-ink-faint text-sm">No sub-shifts yet.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
            {subs.map((st, i) => (
              <SubShiftCard
                key={st.id}
                index={i + 1}
                sub={st}
                color={palette.color}
                claimCount={(claimsBySubTrendId[st.id] || []).length}
                href={`/map/${domainSlug}/${kSlug}/${subSlug(st)}`}
                delay={Math.min(i * 0.04, 0.28)}
              />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

function SubShiftCard({ index, sub, color, claimCount, href, delay = 0 }) {
  return (
    <motion.div {...fadeInView(delay)}>
      <Link
        to={href}
        className="group relative block h-full overflow-hidden rounded-2xl border border-hairline bg-paper p-5 sm:p-6 shadow-sm transition-shadow hover:shadow-lg"
        style={{ '--streak': color }}
      >
        <span className="absolute left-0 top-0 h-full w-1" style={{ background: color }} />
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono text-[11px] tabular-nums font-semibold" style={{ color }}>{pad(index, 2)}</span>
          <span aria-hidden="true" className="text-ink-faint transition-transform group-hover:translate-x-1" style={{ color }}>→</span>
        </div>
        <h3 className="font-display font-bold text-lg sm:text-xl text-ink leading-snug mb-2">
          &ldquo;{sub.name}&rdquo;
        </h3>
        {sub.description && <p className="text-sm text-ink-soft leading-relaxed line-clamp-3">{sub.description}</p>}
        <p className="mt-4 pt-3 border-t border-hairline font-mono text-[10px] uppercase tracking-widest text-ink-faint">
          {pad(claimCount, 2)} {claimCount === 1 ? 'claim' : 'claims'}
        </p>
      </Link>
    </motion.div>
  )
}

function ThinkerList({ label, names, accent }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-widest text-ink-faint mb-1">{label}</p>
      <p className="text-sm" style={{ color: accent }}>{names.join(' · ')}</p>
    </div>
  )
}

function NotFound({ to, label }) {
  const navigate = useNavigate()
  return (
    <div className="max-w-2xl mx-auto px-4 pt-16 pb-24 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-ink-faint mb-3">Not found</p>
      <h1 className="font-display font-bold text-3xl text-ink mb-6">Couldn&rsquo;t find that {label}.</h1>
      <button type="button" onClick={() => navigate(to)} className="font-mono text-[11px] uppercase tracking-widest text-accent hover:opacity-70">← Back</button>
    </div>
  )
}
