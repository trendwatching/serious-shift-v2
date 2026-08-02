import { Link, Routes, Route } from 'react-router-dom'
import ScrollToTop from './components/ScrollToTop'
import { TopBar } from './shift/chrome'
import Home from './shift/Home'
import { DomainSheet, ShiftDetail, SubShiftDetail } from './shift/pages'

export function NotFound() {
  return (
    <section className="grid min-h-[70dvh] place-items-center px-6 text-center" aria-labelledby="not-found-title">
      <div className="flex max-w-[420px] flex-col items-center gap-4">
        <p className="t-eyebrow" style={{ color: 'var(--color-ink-dim)' }}>404 · Not found</p>
        <h1 id="not-found-title" className="t-display text-4xl">This shift has moved.</h1>
        <p className="t-body" style={{ color: 'var(--color-ink-mid)' }}>
          The address does not match anything in this week’s map.
        </p>
        <Link to="/" className="pill-yellow">Back to the shifts</Link>
      </div>
    </section>
  )
}

/**
 * The whole site: a swipe deck of domains, and the reading views beneath it.
 *
 * The black top bar is the only shared chrome — the footer belongs to the
 * reading views, because the deck is a full-viewport surface with none.
 */
export default function App() {
  return (
    <div className="flex min-h-dvh flex-col">
      <ScrollToTop />
      <TopBar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/map/:domainSlug" element={<DomainSheet />} />
          <Route path="/map/:domainSlug/:ktSlug" element={<ShiftDetail />} />
          <Route path="/map/:domainSlug/:ktSlug/:subSlug" element={<SubShiftDetail />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
