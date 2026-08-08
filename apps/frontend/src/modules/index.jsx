/**
 * The module registry.
 *
 * A shift page is an ordered list of `{type, data}` the backend supplies, so
 * adding, removing or reordering a section is a data change. Which types a
 * sphere actually shows is decided server-side by the visibility matrix; the
 * client renders whatever arrives, in the order it arrives.
 */
import { Component } from 'react'
import * as B from './blocks'
import * as I from './interactive'

const SHIFT_MODULES = {
  dek: B.Dek,
  lede: B.Lede,
  rich_text: B.RichText,
  from_to: B.FromTo,
  from_to_solid: B.FromToSolid,
  stat_band: B.StatBand,
  tension_band: B.TensionBand,
  pull_quote: B.PullQuote,
  timeline: B.Timeline,
  related_shifts: B.RelatedShifts,
  peel_tabs: I.PeelTabs,
  human_needs: I.HumanNeeds,
  industries: I.Industries,
  territories: I.Territories,
  sub_shift_list: I.SubShiftList,
  innovations: I.Innovations,
  voices: I.Voices,
  evidence: I.Evidence,
  signals: (props) => <I.SignalList {...props} tone="signals" />,
  counter_signals: (props) => <I.SignalList {...props} tone="counter" />,
}

const Unavailable = ({ type }) => (
  <p role="status" style={{ borderRadius: 12, background: 'var(--color-paper)', padding: 16, fontSize: 14, color: 'var(--color-ink-soft)' }}>
    This section is temporarily unavailable<span className="sr-only"> ({type})</span>.
  </p>
)

/** One bad module is one section, not the whole page. */
class ModuleBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error) {
    console.error(`[modules] "${this.props.type}" failed to render:`, error)
  }
  render() {
    return this.state.failed ? <Unavailable type={this.props.type} /> : this.props.children
  }
}

export function Modules({ modules, ctx }) {
  const list = modules || []
  return list.map((m, i) => {
    const type = String(m?.type || '')
    // A module occasionally needs to know what follows it — the tension band
    // butts onto a stat band and has to stop doing that when there isn't one.
    const next = String(list[i + 1]?.type || '')
    const Body = SHIFT_MODULES[type]
    if (!Body) {
      if (type) console.error(`[modules] unsupported module type "${type}"`)
      return type ? <Unavailable key={`x-${i}`} type={type} /> : null
    }
    return (
      <ModuleBoundary key={`${type}-${i}`} type={type}>
        <Body data={m.data || {}} ctx={{ ...ctx, next }} />
      </ModuleBoundary>
    )
  })
}
