/**
 * SubTrendDetail — the Sub-shift page (/map/:domainSlug/:ktSlug/:subTrendSlug).
 *
 * The tangible leaf: what the sub-shift is, what it's about, a supporting stat,
 * and the evidence (claims with full thinker attribution).
 */
import { useParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMapLookup, slugify } from './MapDataContext'
import Breadcrumbs from './components/Breadcrumbs'
import StatCallout from './components/StatCallout'
import { ThinkerAvatar } from './ThinkerIndex'
import { paletteFor, pad } from './palette'
import { pageIn, fadeUp, fadeInView } from './atmosphere'

const SIGNAL_LABEL = {
  strong_signal: 'Strong', signal: 'Signal', background: 'Background', noise: 'Noise',
}

export default function SubTrendDetail() {
  const { domainSlug, ktSlug, subTrendSlug } = useParams()
  const {
    isV2, domainMap, thinkerByName, ktBySlug, subTrendBySlug, claimsForSubTrend,
  } = useMapLookup()

  const domain  = domainMap[domainSlug]
  const kt      = ktBySlug(domainSlug, ktSlug)
  const sub     = subTrendBySlug(domainSlug, ktSlug, subTrendSlug)
  const palette = paletteFor(domainSlug)

  if (!isV2 || !domain || !kt || !sub) {
    return <NotFound to={`/map/${domainSlug}/${ktSlug || ''}`} label="sub-shift" />
  }

  const claims = claimsForSubTrend(sub.id)
  const uniqueThinkers = new Set(claims.map((c) => c.thinker).filter(Boolean))
  const uniqueSources  = new Set(claims.map((c) => c.source_title).filter(Boolean))
  const strongCount = claims.filter((c) => c.signal_strength === 'strong_signal').length

  return (
    <motion.div
      {...pageIn}
      style={{ background: `radial-gradient(120% 45% at 50% 0%, ${palette.soft} 0%, transparent 55%)` }}
    >
      <Breadcrumbs
        tint={palette.color}
        crumbs={[
          { label: 'Home', to: '/map' },
          { label: domain.name, to: `/map/${domainSlug}` },
          { label: kt.name, to: `/map/${domainSlug}/${ktSlug}` },
          { label: sub.name },
        ]}
      />

      <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-8 sm:pt-10 pb-16">
        {/* ── Hero ── */}
        <header className="mb-10">
          <motion.p {...fadeUp(0.05)} className="font-mono text-[11px] uppercase tracking-[0.2em] mb-3" style={{ color: palette.color }}>
            Sub-shift
          </motion.p>
          <motion.h1 {...fadeUp(0.1)} className="font-display font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-[1.06] text-ink">
            &ldquo;{sub.name}&rdquo;
          </motion.h1>
          {sub.description && (
            <motion.p {...fadeUp(0.16)} className="mt-5 text-ink-soft text-base sm:text-lg leading-relaxed">
              {sub.description}
            </motion.p>
          )}
          <motion.div {...fadeUp(0.22)} className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-1.5">
            <Stat value={pad(claims.length, 2)} label="Claims" />
            <Sep />
            <Stat value={pad(uniqueThinkers.size, 2)} label="Thinkers" />
            <Sep />
            <Stat value={pad(uniqueSources.size, 2)} label="Sources" />
          </motion.div>
        </header>

        {/* ── Supporting signal stat ── */}
        {claims.length > 0 && (
          <div className="border-y border-hairline my-8">
            <StatCallout
              value={pad(strongCount || claims.length, 2)}
              context={strongCount
                ? `strong signals corroborate this sub-shift`
                : `claims tracked from top thinkers and sources`}
              source={`${uniqueThinkers.size} thinkers · ${uniqueSources.size} sources`}
            />
          </div>
        )}

        {/* ── Evidence ── */}
        <motion.h2 {...fadeInView()}
          className="font-display font-bold text-2xl text-ink mb-1">
          What &ldquo;{sub.name}&rdquo; is about
        </motion.h2>
        <p className="text-ink-soft text-sm mb-6">
          Evidence · {pad(claims.length, 2)} {claims.length === 1 ? 'claim' : 'claims'}
        </p>

        {claims.length === 0 ? (
          <p className="text-ink-faint text-sm">No claims recorded for this sub-shift.</p>
        ) : (
          <ul className="space-y-4">
            {claims.map((claim, i) => (
              <ClaimRow
                key={claim.id}
                claim={claim}
                accent={palette.color}
                thinkerSlug={claim.thinker ? slugify(claim.thinker) : null}
                thinkerKnown={!!thinkerByName[claim.thinker]}
                delay={Math.min(i * 0.03, 0.24)}
              />
            ))}
          </ul>
        )}
      </div>
    </motion.div>
  )
}

function ClaimRow({ claim, accent, thinkerSlug, thinkerKnown, delay = 0 }) {
  const credibility = claim.thinker_credibility
  const showCred = typeof credibility === 'number' && !Number.isNaN(credibility)
  const signalLabel = SIGNAL_LABEL[claim.signal_strength]

  return (
    <motion.li {...fadeInView(delay)} className="rounded-2xl border border-hairline bg-paper p-4 sm:p-5 shadow-sm">
      <div className="flex items-start gap-4">
        {claim.thinker && <div className="shrink-0"><ThinkerAvatar name={claim.thinker} size={44} /></div>}
        <div className="flex-1 min-w-0">
          <p className="text-[15px] sm:text-base leading-relaxed text-ink">{claim.text}</p>
          <div className="mt-3 flex items-baseline flex-wrap gap-x-2 gap-y-1 text-[11px] text-ink-faint">
            {claim.thinker && (
              thinkerKnown && thinkerSlug ? (
                <Link to={`/map/thinkers/${thinkerSlug}`} className="text-ink font-medium hover:opacity-70 transition-opacity"
                  style={{ borderBottom: `1px dashed color-mix(in oklab, ${accent} 45%, transparent)` }}>
                  {claim.thinker}
                </Link>
              ) : <span className="text-ink font-medium">{claim.thinker}</span>
            )}
            {showCred && (
              <span className="font-mono tabular-nums" style={{ color: accent }} title={`Credibility: ${credibility.toFixed(1)}`}>
                {credibility.toFixed(1)}
              </span>
            )}
            {(claim.thinker || showCred) && claim.source_title && <Dot />}
            {claim.source_title && <span className="text-ink-soft italic truncate max-w-[40ch]">{claim.source_title}</span>}
            {claim.source_date && (<><Dot /><span className="font-mono text-[10px] text-ink-faint">{formatDate(claim.source_date)}</span></>)}
            {signalLabel && (
              <><Dot /><span className="font-mono uppercase tracking-widest text-[9px]"
                style={{ color: claim.signal_strength === 'strong_signal' ? accent : 'var(--color-ink-faint)' }}>{signalLabel}</span></>
            )}
          </div>
          {claim.consumer_implication && (
            <div className="mt-3 pt-3 border-t border-hairline text-[12.5px] text-ink-soft leading-relaxed">
              <span className="font-mono text-[9px] uppercase tracking-widest text-ink-faint mr-1.5">Consumer impact</span>
              {claim.consumer_implication}
            </div>
          )}
        </div>
      </div>
    </motion.li>
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
function Sep() { return <span className="text-ink-faint/50 select-none font-mono text-xs" aria-hidden="true">·</span> }
function Dot() { return <span className="text-ink-faint/60 select-none" aria-hidden="true">·</span> }

function formatDate(s) {
  if (!s) return ''
  const m = String(s).match(/^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/)
  if (!m) return s
  const [, y, mm, dd] = m
  if (dd) return `${y}-${mm}-${dd}`
  if (mm) return `${y}-${mm}`
  return y
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
