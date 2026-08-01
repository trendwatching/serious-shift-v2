/** Signals and counter-signals, as numbered cards. */
import { NumberedCard } from './primitives'

export const SignalsCard = ({ items }) => (
  <NumberedCard title="Signals" items={items} grad="var(--a-grad-hot)" shadow="0 12px 28px var(--a-shadow)" />
)
export const CounterSignalsCard = ({ items }) => (
  <NumberedCard title="Counter-signals" items={items} grad="var(--pos-grad-lit)" shadow="0 12px 28px var(--pos-shadow)" />
)
