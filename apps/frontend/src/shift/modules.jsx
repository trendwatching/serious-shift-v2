/**
 * modules.jsx — the module registry and renderer.
 *
 * A shift page is an ordered list of `{ type, data }` modules supplied by the
 * backend, so page composition is data rather than code: reordering, dropping or
 * adding a section is a change to the map document, not a deploy.
 *
 * Three properties this file has to guarantee:
 *
 *  • Unknown types are SKIPPED, not fatal — so the pipeline can start emitting a
 *    new module type before the front end knows about it.
 *  • `data` is untrusted. It originates from an LLM and may be partial, so every
 *    module validates its own inputs and renders nothing rather than an empty box.
 *  • One bad module can't take the page down — an error boundary isolates each.
 *
 * Canonical type list + data shapes: packages/contracts/shift_modules.json
 * (guarded by apps/pipeline/tests/test_shift_modules_contract.py).
 */
import { Component } from 'react'
import {
  FromTo, FromToSolid, StatBand, PeelTabs, SubShiftList, HumanNeeds,
  TensionBand, Timeline, Industries, Territories,
  SignalsCard, CounterSignalsCard, Eyebrow,
  Voices, Evidence, RelatedShifts,
} from './sections'

const str = (v) => (typeof v === 'string' ? v.trim() : '')
const list = (v) => (Array.isArray(v) ? v : [])

/* ── Module bodies ───────────────────────────────────────────────────────
   Thin adapters: validate, then hand off to the shared section components. */

const Dek = ({ data }) => {
  const text = str(data?.text)
  if (!text) return null
  return (
    <p
      className="t-display text-[19px] leading-[1.35] text-pretty lg:text-[23px]"
      style={{ fontWeight: 600, letterSpacing: '-0.01em' }}
    >{text}</p>
  )
}

const Lede = ({ data }) => {
  const text = str(data?.text)
  if (!text) return null
  return (
    <p className="text-[16.5px] leading-[1.55] text-pretty lg:text-[19px]" style={{ color: 'var(--color-ink-strong)' }}>
      {text}
    </p>
  )
}

const RichText = ({ data }) => {
  const body = str(data?.body)
  if (!body) return null
  const heading = str(data?.heading)
  return (
    <div className="flex flex-col gap-2.5">
      {heading && <Eyebrow>{heading}</Eyebrow>}
      <p className="text-[15px] leading-[1.6] text-pretty lg:text-[17px]" style={{ color: 'var(--color-ink-strong)' }}>
        {body}
      </p>
    </div>
  )
}

/**
 * The registry. Keys are the `type` strings from the contract; the two-space
 * indentation of each key is what the contract test greps for, so keep it flat.
 */
export const SHIFT_MODULES = {
  dek: Dek,
  lede: Lede,
  rich_text: RichText,
  from_to: ({ data, ctx }) => <FromTo from={str(data?.from)} to={str(data?.to)} grad={ctx.domain?.grad} />,
  from_to_solid: ({ data }) => <FromToSolid from={str(data?.from)} to={str(data?.to)} />,
  stat_band: ({ data, ctx }) => (
    <StatBand
      stat={{ value: str(data?.value), text: str(data?.text), source: str(data?.source) }}
      size={ctx.scope === 'sub_shift' ? 52 : 58}
    />
  ),
  peel_tabs: ({ data }) => <PeelTabs whatChanging={str(data?.whats_changing)} whyNow={str(data?.why_now)} />,
  sub_shift_list: ({ ctx }) => <SubShiftList subs={ctx.subs} onOpen={ctx.onOpenSub} />,
  human_needs: ({ data }) => (
    <HumanNeeds needs={{ unlocked: str(data?.unlocked), threatened: str(data?.threatened) }} />
  ),
  tension_band: ({ data }) => <TensionBand quote={str(data?.quote)} label={str(data?.label) || undefined} />,
  timeline: ({ data }) => (
    <Timeline steps={list(data?.steps).filter((s) => s && str(s.text))} />
  ),
  industries: ({ data }) => <Industries items={list(data?.items).filter((i) => i && str(i.name))} />,
  territories: ({ data }) => <Territories items={list(data?.items).filter((i) => i && str(i.name))} />,
  signals: ({ data }) => <SignalsCard items={list(data?.items).filter((s) => str(s))} />,
  counter_signals: ({ data }) => <CounterSignalsCard items={list(data?.items).filter((s) => str(s))} />,
  voices: ({ data }) => (
    <Voices
      proponents={list(data?.proponents).filter((p) => p && str(p.name) && str(p.quote))}
      skeptics={list(data?.skeptics).filter((p) => p && str(p.name) && str(p.quote))}
    />
  ),
  evidence: ({ data }) => <Evidence items={list(data?.items).filter((c) => c && str(c.text))} />,
  related_shifts: ({ data, ctx }) => (
    <RelatedShifts
      items={list(data?.items).filter((r) => r && str(r.title) && str(r.href))}
      onOpen={ctx.onNavigate}
    />
  ),
}

/* ── Isolation ───────────────────────────────────────────────────────────── */

class ModuleBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    // A module is one section of a long page; losing it is survivable, so log
    // and drop it rather than letting the throw unmount the whole route.
    console.error(`[modules] "${this.props.type}" failed to render:`, error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

/**
 * Render an ordered module list.
 *
 * @param modules  [{ type, data }] — as served in the map document
 * @param ctx      narrow render context: { domain, subs, onOpenSub, scope }
 */
export function Modules({ modules, ctx }) {
  return list(modules).map((m, i) => {
    const type = str(m?.type)
    const Body = SHIFT_MODULES[type]
    if (!Body) {
      if (process.env.NODE_ENV !== 'production' && type) {
        console.warn(`[modules] no component for type "${type}" — skipping. ` +
          'Add it to SHIFT_MODULES and packages/contracts/shift_modules.json.')
      }
      return null
    }
    // A type may legitimately repeat (two rich_text blocks), so the key pairs it
    // with its position rather than assuming uniqueness.
    return (
      <ModuleBoundary key={`${type}-${i}`} type={type}>
        <Body data={m.data || {}} ctx={ctx} />
      </ModuleBoundary>
    )
  })
}
