/** The non-interactive modules. Every value here is the design's. */
import { Link } from '../lib/router'

export const Eyebrow = ({ children, right }) => (
  <div className="flex items-baseline" style={{ gap: 10 }}>
    <h2 className="t-eyebrow">{children}</h2>
    {right && <span className="ml-auto" style={{ fontSize: 11.5, color: 'var(--color-ink-meta)' }}>{right}</span>}
  </div>
)

export const Dek = ({ data }) => (
  <p className="t-display text-pretty" style={{ fontSize: 19, fontWeight: 600, lineHeight: 1.35, letterSpacing: '-0.01em' }}>
    {data.text}
  </p>
)

export const Lede = ({ data }) => (
  <p className="text-pretty" style={{ fontSize: 16.5, lineHeight: 1.55, color: 'var(--color-ink-strong)' }}>{data.text}</p>
)

export const RichText = ({ data }) => (
  <div className="flex flex-col" style={{ gap: 10 }}>
    {data.heading && <h2 className="t-eyebrow">{data.heading}</h2>}
    <p className="text-pretty" style={{ fontSize: 16.5, lineHeight: 1.55, color: 'var(--color-ink-strong)' }}>{data.body}</p>
  </div>
)

/**
 * From / To — two cards whose gradient fills cross-fade past each other on one
 * 8s clock while the ink inverts with them.
 *
 * No scrim over the gradient. The previous build laid 38% black on both cards,
 * which is why the pair read muddy instead of luminous.
 */
export const FromTo = ({ data, ctx }) => {
  if (!data.from || !data.to) return null
  const card = (label, text, panel, ink) => (
    <div
      className="relative overflow-hidden bg-white"
      style={{ borderRadius: 22, border: '1px solid var(--color-line)', minHeight: 208, boxShadow: '0 6px 18px rgba(27,22,32,0.06)' }}
    >
      <div className="absolute inset-0" style={{ backgroundImage: ctx.domain.grad, animation: `${panel} 8s ease-in-out infinite` }} />
      <div
        className="relative box-border flex flex-col items-center justify-center text-center"
        style={{ height: 208, padding: '20px 15px', gap: 10, animation: `${ink} 8s ease-in-out infinite` }}
      >
        <span className="t-display" style={{ fontSize: 'var(--t-stat)', fontWeight: 700, letterSpacing: '-0.02em' }}>{label}</span>
        <span style={{ fontSize: 13.5, lineHeight: 1.42 }}>{text}</span>
      </div>
    </div>
  )
  return (
    <section className="grid grid-cols-2" style={{ gap: 12, margin: '2px 0 4px' }} aria-label="From and to">
      {card('From', data.from, 'ssPanelA', 'ssInkA')}
      {card('To', data.to, 'ssPanelB', 'ssInkB')}
    </section>
  )
}

/** The sub-shift variant: green "from", sunset "to", solid fills, tiny labels. */
export const FromToSolid = ({ data }) => {
  if (!data.from || !data.to) return null
  const card = (label, text, grad) => (
    <div className="box-border flex min-w-0 flex-1 flex-col text-white" style={{ borderRadius: 18, padding: 16, gap: 8, backgroundImage: grad }}>
      <span className="t-eyebrow" style={{ fontSize: 11.5, fontWeight: 800, letterSpacing: '0.12em' }}>{label}</span>
      <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.45 }}>{text}</span>
    </div>
  )
  return (
    <section className="flex items-stretch" style={{ gap: 10 }} aria-label="From and to">
      {card('From', data.from, 'var(--pos-grad)')}
      {/* Sunset, not the domain accent: a sub-shift is a level down, and
          tinting its spine with the parent's colour is what made the two
          levels indistinguishable. */}
      {card('To', data.to, 'var(--grad-sunset)')}
    </section>
  )
}

/** Full-bleed statistic. The background is the design's own artwork. */
export const StatBand = ({ data, ctx }) => {
  if (!data.value) return null
  const big = ctx.scope === 'sub_shift' ? 52 : 58
  return (
    <section
      className="bleed stat-surface box-border flex items-center text-white"
      style={{
        gap: 18,
        marginBlock: ctx.scope === 'sub_shift' ? 0 : 10,
        paddingBlock: ctx.scope === 'sub_shift' ? 32 : 34,
      }}
      aria-label="Key statistic"
    >
      {/* `flex: 0 0 auto` is right for the figure the design draws — "72%",
          "3.4×" — and catastrophic for one the pipeline let through long, such
          as "$54.2 million": at 52px that is 353px of unshrinkable content in a
          349px band, and the whole PAGE scrolls sideways. Capped and allowed to
          wrap, so a long value costs a line rather than the layout. The real
          repair is upstream, in _short_figure; this is the floor under it. */}
      <span
        className="t-title"
        style={{
          flex: '0 1 auto', minWidth: 0, maxWidth: '58%',
          fontSize: big, lineHeight: 0.9, letterSpacing: '-0.015em',
          overflowWrap: 'anywhere',
        }}
      >
        {data.value}
      </span>
      {/* `min-w-0` is load-bearing: a flex item defaults to `min-width: auto`,
          so this column refuses to shrink below its longest word and pushes the
          band past the viewport. */}
      <span className="flex min-w-0 flex-1 flex-col" style={{ gap: 8 }}>
        <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.45 }}>{data.text}</span>
        {data.source && <span style={{ fontSize: 11, lineHeight: 1.4, opacity: 0.75 }}>{data.source}</span>}
      </span>
    </section>
  )
}

/** Full-bleed dark band carrying the tension, in the reader's own voice. */
export const TensionBand = ({ data, ctx }) => {
  if (!data.quote) return null
  return (
    <section
      className="bleed flex flex-col text-white"
      style={{
        gap: 12, paddingBlock: 30, background: 'var(--color-ink)',
        // On a sub-shift the band butts straight onto the stat band below it —
        // but only when there IS one. Applied unconditionally it pulled the
        // peel-tab stack up into the band on every sub-shift without a
        // statistic, which is 19 of the 51 shifts' children.
        marginBottom: ctx.scope === 'sub_shift' && ctx.next === 'stat_band' ? -30 : undefined,
      }}
    >
      <h2 className="t-eyebrow" style={{ color: 'var(--color-yellow)' }}>{data.label || 'The tension'}</h2>
      <p className="t-display text-pretty" style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.3, letterSpacing: '-0.018em' }}>
        “{data.quote}”
      </p>
    </section>
  )
}

export const PullQuote = ({ data }) => (
  <figure className="relative m-0" style={{ paddingLeft: 20 }}>
    <span className="absolute inset-y-0 left-0" style={{ width: 4, background: 'var(--a)' }} />
    <blockquote className="t-display m-0 text-pretty" style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.3, letterSpacing: '-0.018em' }}>
      “{data.quote}”
    </blockquote>
  </figure>
)

/** Today / next / beyond, on a rail that lights each card in turn. */
export const Timeline = ({ data, ctx }) => {
  const steps = data.steps || []
  if (!steps.length) return null
  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      {/* A fixed label, not the steps joined. The design writes "Today / next /
          beyond" above cards whose own labels are Today / Next / Beyond — and
          deriving it meant a document published with the older "Now" wording put
          "Now / Next / Beyond" over the section on every page. */}
      <Eyebrow>Today / next / beyond</Eyebrow>
      <div
        className="horizon relative"
        /* A sub-shift's rail is lit by the hot end of the sphere's ramp, a key
           shift's by the accent itself. On Society that hot end is #F5007F —
           the #FF007A the mockup drew — and every other sphere now lights its
           own rather than inheriting Society's pink. */
        style={{ paddingLeft: 26, gap: 12, '--dot-lit': ctx.scope === 'sub_shift' ? 'var(--a-hot)' : 'var(--a)' }}
      >
        <span className="horizon-rail" />
        {steps.map((s, i) => (
          <div
            key={s.label ?? i}
            className="relative box-border flex flex-col"
            style={{
              borderRadius: 16, padding: '15px 16px', gap: 6,
              background: 'var(--color-card)', color: 'var(--color-ink-strong)',
              animation: i < 3 ? `ssFill${i + 1} 12s linear infinite` : undefined,
            }}
          >
            <span
              className="horizon-dot"
              style={{
                border: `2.5px solid ${ctx.scope === 'sub_shift' ? 'var(--a-hot)' : 'var(--a)'}`,
                animation: i < 3 ? `ssDot${i + 1} 12s linear infinite` : undefined,
              }}
            />
            <span className="flex items-baseline" style={{ gap: 10 }}>
              <span className="t-display" style={{ fontSize: 14.5, fontWeight: 700, letterSpacing: '-0.005em' }}>{s.label}</span>
              <span className="t-mono ml-auto" style={{ fontSize: 11, opacity: 0.75 }}>
                {['0–12 months', '1–3 years', '3–10 years'][i] || ''}
              </span>
            </span>
            <span className="text-pretty" style={{ fontSize: 13.5, lineHeight: 1.5 }}>{s.text}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

/** Typed links out to sibling shifts. */
export const RelatedShifts = ({ data }) => {
  const items = (data.items || []).filter((r) => r?.title && r?.href)
  if (!items.length) return null
  return (
    <section className="widen flex flex-col" style={{ gap: 10 }}>
      <Eyebrow right={String(items.length)}>Connected shifts</Eyebrow>
      <div className="sub-stack" style={{ gap: 0 }}>
        {items.map((r) => (
          <Link key={r.href} to={r.href} className="flex flex-col" style={{ gap: 6, padding: '14px 0', borderBottom: '1px solid var(--color-line)' }}>
            <span className="t-eyebrow" style={{ fontSize: 10, letterSpacing: '0.12em', color: 'var(--a-ink)' }}>{r.relationship}</span>
            <span className="t-title" style={{ fontSize: 16, lineHeight: 1.2, letterSpacing: '0.005em', color: '#3D1152' }}>{r.title}</span>
            {r.reasoning && <span style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--color-ink-mid)' }}>{r.reasoning}</span>}
          </Link>
        ))}
      </div>
    </section>
  )
}
