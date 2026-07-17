/**
 * MapLanding — the homepage ("The sky of AI").
 *
 * A bright editorial hero over four drifting domain smoke-blobs. Each blob is
 * a doorway into a Sphere (domain) page. Replaces the old dark starfield +
 * cinematic-warp landing.
 */
import { motion } from 'framer-motion'
import { useMapLookup } from './MapDataContext'
import SmokeBlob from './components/SmokeBlob'
import { paletteFor, pad } from './palette'
import { pageIn, fadeUp } from './atmosphere'

// Display order + fallback copy (mirrors the Figma 2×2 arrangement).
const ORDER = ['society', 'economy', 'consumers', 'organisations']

const STATIC_DOMAINS = {
  society:       { name: 'Society',       short: 'How AI rewrites the social contract — governance, culture and what it means to be human.' },
  economy:       { name: 'Economy',       short: 'How AI restructures who creates value, who captures it, and what happens to the rest.' },
  consumers:     { name: 'Consumers',     short: 'How AI transforms the way people decide, seek fulfilment, and relate to brands.' },
  organisations: { name: 'Organisations', short: 'How firms adapt — or fail to — when AI can perform, plan and decide faster than any hierarchy.' },
}

export default function MapLanding() {
  const { isV2, domainsArr, key_trends, sub_trends, claims, ktsByDomain } = useMapLookup()

  const liveById = {}
  if (isV2) for (const d of domainsArr) liveById[d.id] = d

  const domains = ORDER.map((id) => {
    const live = liveById[id]
    const fallback = STATIC_DOMAINS[id]
    return {
      id,
      name: live?.name || fallback.name,
      label: (live?.label || `AI × ${fallback.name}`).replace(/\s*\/\s*World$/, ''),
      short: live?.short_description || fallback.short,
      hasData: isV2 && (ktsByDomain[id]?.length > 0),
      ...paletteFor(id),
    }
  })

  return (
    <motion.div {...pageIn} className="relative">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-8">

        {/* ── Hero ── */}
        <div className="text-center max-w-3xl mx-auto mb-14 sm:mb-20">
          <motion.h1
            {...fadeUp(0.05)}
            className="font-display font-bold text-4xl sm:text-5xl lg:text-6xl leading-[1.05] text-ink"
          >
            Tasked With Mapping<br className="hidden sm:block" /> Out The Future of AI?
          </motion.h1>
          <motion.p {...fadeUp(0.13)} className="mt-5 text-ink-soft text-base sm:text-lg leading-relaxed max-w-2xl mx-auto">
            Learn from top experts and their thinking on how AI will transform
            society, the economy, consumers and organisations — then turn those
            shifts into your own daring new opportunities and futures.
          </motion.p>
          <motion.div {...fadeUp(0.2)} className="mt-7 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5">
            <Stat value={pad(4, 2)} label="Spheres" />
            <Sep />
            <Stat value={pad(key_trends.length, 2)} label="Key Shifts" />
            <Sep />
            <Stat value={pad(sub_trends.length, 2)} label="Sub-shifts" />
            <Sep />
            <Stat value={pad(claims.length, 3)} label="Claims" />
          </motion.div>
        </div>

        {/* ── Domain blobs ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-10 sm:gap-y-4 max-w-4xl mx-auto">
          {domains.map((d, i) => (
            <div key={d.id} className={i % 2 === 1 ? 'sm:mt-16' : ''}>
              <SmokeBlob
                color={d.color}
                image={d.image}
                name={d.name}
                eyebrow={d.label}
                href={`/map/${d.id}`}
                index={i}
              />
            </div>
          ))}
        </div>
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
