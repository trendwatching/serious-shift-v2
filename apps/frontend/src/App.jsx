import { Routes, Route, Navigate } from 'react-router-dom'
import ScrollToTop from './components/ScrollToTop'
import { TopBar } from './shift/chrome'
import Home from './shift/Home'
import { DomainSheet, ShiftDetail, SubShiftDetail } from './shift/pages'

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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
