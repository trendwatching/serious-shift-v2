/**
 * The editorial blocks shared by the shift and sub-shift pages.
 *
 * Ported style-for-style from the approved design. Each block returns null when
 * its data is absent, so a page composed of these renders exactly the sections
 * the content supports. Motion is CSS (see index.css keyframes) rather than a JS
 * animation loop — the ambient animations run on the compositor and cost no
 * main-thread work, which keeps long detail pages smooth while scrolling.
 *
 * Re-exported from one place so consumers (modules.jsx, pages.jsx) import from
 * './sections' regardless of which file a block lives in.
 */
export { Eyebrow, SectionHead, BackButton, NumberedCard, PAD } from './primitives'
export { GradientHero } from './hero'
export { FromTo, FromToSolid } from './fromto'
export { StatBand } from './stats'
export { PeelTabs, TensionBand, PullQuote } from './narrative'
export {
  SubShiftList, HumanNeeds, Innovations, Timeline, Industries, Territories,
} from './lists'
export { SignalsCard, CounterSignalsCard } from './signals'
export { Voices } from './people'
export { Evidence } from './evidence'
export { RelatedShifts } from './related'
