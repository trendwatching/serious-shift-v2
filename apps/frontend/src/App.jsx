import { Routes, Route, Link } from './lib/router'
import { useDocumentMeta } from './lib/useDocumentMeta'
import { Header } from './chrome/Header'
import Deck from './deck/Deck'
import DomainPage from './pages/DomainPage'
import ShiftPage from './pages/ShiftPage'
import SubShiftPage from './pages/SubShiftPage'
import AboutPage from './pages/AboutPage'

function NotFound() {
  useDocumentMeta('Page not found', undefined, { notFound: true })
  return (
    <div className="grid min-h-dvh place-items-center px-6 text-center" style={{ paddingTop: 'var(--topbar)' }}>
      <div className="flex max-w-[420px] flex-col items-center gap-4">
        <p className="t-eyebrow" style={{ color: 'var(--color-ink-meta)' }}>404 · Not found</p>
        <h1 className="t-display text-[32px] font-bold" style={{ letterSpacing: '-0.03em' }}>This shift has moved.</h1>
        <p style={{ color: 'var(--color-ink-row)' }}>
          The address does not match anything in the current weekly map.
        </p>
        <Link to="/" className="pill-yellow">Back to the shifts</Link>
      </div>
    </div>
  )
}

/**
 * The header is absolutely positioned and overlaps whatever is beneath it, so
 * it is a sibling of the routes rather than a wrapper — every page reserves
 * its own `--topbar` of space.
 */
export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Deck />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/map/:domainSlug" element={<DomainPage />} />
        <Route path="/map/:domainSlug/:ktSlug" element={<ShiftPage />} />
        <Route path="/map/:domainSlug/:ktSlug/:subSlug" element={<SubShiftPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  )
}
