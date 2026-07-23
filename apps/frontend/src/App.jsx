import { Routes, Route, Navigate } from 'react-router-dom'
import { useTheme } from './hooks/useTheme'
import ScrollToTop from './components/ScrollToTop'
import NavBar from './components/shell/NavBar'
import IdeateSection from './components/shell/IdeateSection'
import TrustedBy from './components/shell/TrustedBy'
import SiteFooter from './components/shell/SiteFooter'
import Map from './views/Map'
import About from './views/About'
import ThinkerProfile from './views/ThinkerProfile'
import Daily from './views/Daily'

// Map child routes
import MapLanding     from './views/map/MapLanding'
import MacroDetail    from './views/map/MacroDetail'
import DomainDetail   from './views/map/DomainDetail'
import KtDetail       from './views/map/KtDetail'
import SubTrendDetail from './views/map/SubTrendDetail'
import SynthesisIndex from './views/map/SynthesisIndex'
import ThinkerIndex   from './views/map/ThinkerIndex'
import ThinkerDetail  from './views/map/ThinkerDetail'

// ─── Soft-launch: secondary views intentionally hidden ──────────────────────
// Keynote, Leaderboard, Predictions, and Explore pages remain on disk under
// src/views/ and can be restored by re-adding imports + routes below.

export default function App() {
  const { theme, toggle } = useTheme()
  return (
    <div className="min-h-screen flex flex-col page-canvas text-ink">
      <ScrollToTop />
      <NavBar theme={theme} onToggleTheme={toggle} />

      <main className="flex-1">
        <Routes>
          {/* Home = the map, served directly at the clean root ("/") with no
             redirect. Detail pages still live under /map/... (see below). */}
          <Route path="/" element={<Map />}>
            <Route index element={<MapLanding />} />
          </Route>

          {/* Map — nested routes share data context via layout.
             Static segments (synthesis/thinkers/macros/domains) take
             precedence over the :domainSlug param by route ranking. */}
          <Route path="/map" element={<Map />}>
            <Route index element={<MapLanding />} />
            <Route path="macros/:slug" element={<MacroDetail />} />
            <Route path="domains/:domainId" element={<DomainDetail />} />
            <Route path="synthesis" element={<SynthesisIndex />} />
            <Route path="thinkers" element={<ThinkerIndex />} />
            <Route path="thinkers/:slug" element={<ThinkerDetail />} />
            {/* Deep hierarchy: sphere → key shift → sub-shift. */}
            <Route path=":domainSlug" element={<DomainDetail />} />
            <Route path=":domainSlug/:ktSlug" element={<KtDetail />} />
            <Route
              path=":domainSlug/:ktSlug/:subTrendSlug"
              element={<SubTrendDetail />}
            />
          </Route>

          <Route path="/about" element={<About />} />
          <Route path="/thinker/:name" element={<ThinkerProfile />} />
          <Route path="/daily" element={<Daily />} />

          {/* Anything else falls back to the home map at the clean root. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* Shared page chrome — present at the foot of every page. */}
      <IdeateSection />
      <TrustedBy />
      <SiteFooter />
    </div>
  )
}
