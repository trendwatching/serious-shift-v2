/** Loading, missing and unavailable — the three states a static design has no
 *  opinion about, kept deliberately plain so they never read as content. */
import { Link } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { failureState } from '../lib/failure'

const Shell = ({ children }) => (
  <div className="grid min-h-dvh place-items-center px-6 text-center" style={{ paddingTop: 'var(--topbar)' }}>
    <div className="flex max-w-[400px] flex-col items-center gap-4">{children}</div>
  </div>
)

export const Loading = () => (
  <div className="grid min-h-dvh place-items-center px-6" style={{ paddingTop: 'var(--topbar)' }} aria-busy="true" aria-label="Loading">
    <div className="w-full max-w-[420px] animate-pulse space-y-4" aria-hidden="true">
      <div className="h-10 w-2/3 rounded-lg bg-black/10" />
      <div className="h-24 rounded-2xl bg-black/10" />
      <div className="h-40 rounded-2xl bg-black/10" />
    </div>
  </div>
)

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
