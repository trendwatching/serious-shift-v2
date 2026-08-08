/** Loading, missing and unavailable — the three states a static design has no
 *  opinion about, kept deliberately plain so they never read as content. */
import { Link } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { useDeferred } from '../lib/useDeferred'
import { failureState } from '../lib/failure'

const Shell = ({ children }) => (
  <div className="screen text-center">
    <div className="flex max-w-[400px] flex-col items-center gap-4">{children}</div>
  </div>
)

/**
 * The page's own shape, and only once there is a wait worth showing.
 *
 * Two separate things were making the reader's screen jump.
 *
 * The first is that a skeleton which does not match what replaces it IS the
 * stutter: this was a `100dvh` centred block becoming a page with a 660px hero,
 * and the document moved by 0.099 the moment the map arrived. `hero` names the
 * height class the real page uses, and `sheet` draws the white panel the sphere
 * page overlaps its hero with, so the bands are already the right size and only
 * their contents change.
 *
 * The second is that matching the shape is not enough when nobody is waiting.
 * The map answers in about 30ms, so the skeleton was on screen for two frames
 * and gone — a flash, and then a swap, which measured 0.39 on the sphere page.
 * Mounting this component IS the moment loading starts, so it holds itself back
 * for a quarter second: under that the page simply appears, and over it the
 * skeleton has something real to say.
 */
export function Loading({ hero = 'hero-short', sheet = false }) {
  const worthShowing = useDeferred(true)
  if (!worthShowing) return null

  return (
    <div aria-busy="true" aria-label="Loading">
      {/* No top margin: the bar is absolute and OVERLAPS the article, so a real
          hero starts at y=0. Pushing the skeleton down by `--topbar` offset the
          band by the height of the bar and shifted the page anyway. Neutral, so
          a sphere's colour arrives with its content rather than flashing. */}
      <div className={`${hero} animate-pulse`} style={{ background: 'var(--color-line)' }} aria-hidden="true" />
      <div
        className="canvas gutter animate-pulse"
        style={sheet
          ? { marginTop: -34, minHeight: 520, borderRadius: '28px 28px 0 0', background: '#fff', paddingTop: 34 }
          : { paddingTop: 26 }}
        aria-hidden="true"
      >
        <div className="h-24 rounded-2xl bg-black/10" />
      </div>
    </div>
  )
}

export function Missing({ what }) {
  useDocumentMeta('Page not found', undefined, { notFound: true })
  return (
    <Shell>
      <p className="t-eyebrow" style={{ color: 'var(--color-ink-meta)' }}>Not found</p>
      <h1 className="t-display text-[26px] font-bold" style={{ letterSpacing: '-0.03em' }}>We couldn’t find that {what}.</h1>
      <Link to="/" className="pill-yellow">Back to the domains</Link>
    </Shell>
  )
}

export function Unavailable({ error, onRetry }) {
  const failure = failureState(error)
  return (
    <Shell>
      <p className="t-eyebrow" style={{ color: 'var(--color-ink-meta)' }}>{failure.eyebrow}</p>
      <h1 className="t-display text-[26px] font-bold" style={{ letterSpacing: '-0.03em' }}>{failure.title}</h1>
      <p style={{ color: 'var(--color-ink-row)' }}>{failure.body}</p>
      {onRetry && <button type="button" className="pill-yellow" onClick={onRetry}>Retry</button>}
    </Shell>
  )
}
