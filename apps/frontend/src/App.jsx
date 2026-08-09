import { Routes, Route } from './lib/router'
import { Header } from './chrome/Header'
import Deck from './deck/Deck'
import DomainPage from './pages/DomainPage'
import ShiftPage from './pages/ShiftPage'
import SubShiftPage from './pages/SubShiftPage'
import AboutPage from './pages/AboutPage'
import { Missing } from './pages/states'

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
        <Route path="/:domainSlug" element={<DomainPage />} />
        <Route path="/:domainSlug/:ktSlug" element={<ShiftPage />} />
        <Route path="/:domainSlug/:ktSlug/:subSlug" element={<SubShiftPage />} />
        <Route path="*" element={<Missing />} />
      </Routes>
    </>
  )
}
