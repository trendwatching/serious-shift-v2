import { Outlet } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'
import { useData } from '../hooks/useData'

import './map/map.css'
import { MapDataContext } from './map/MapDataContext'

/**
 * Map — /map layout shell.
 *
 * Loads map.json once, provides MapDataContext to all child routes,
 * and renders the persistent sub-nav (Overview / Synthesis / Thinkers).
 * Child routes are rendered via <Outlet />.
 */
export default function Map() {
  const { data, loading } = useData('map.json')

  if (loading) return <MapLoading />
  if (!data)   return <MapError />

  const isV2 = data.architecture === 'domain-first-v2'
  const { macros, key_trends, sub_trends, claims } = data
  if (isV2) {
    if (
      !Array.isArray(data.domains) ||
      !Array.isArray(key_trends)   ||
      !Array.isArray(sub_trends)   ||
      !Array.isArray(claims)
    ) {
      return <MapError />
    }
  } else {
    if (
      !Array.isArray(macros)     ||
      !Array.isArray(key_trends) ||
      !Array.isArray(sub_trends) ||
      !Array.isArray(claims)
    ) {
      return <MapError />
    }
  }

  return (
    <MapDataContext.Provider value={data}>
      <MotionConfig reducedMotion="user">
        <div className="map-root">
          <Outlet />
        </div>
      </MotionConfig>
    </MapDataContext.Provider>
  )
}

export function MapLoading() {
  return (
    <div className="flex items-center justify-center py-24 text-neutral-600 text-xs tracking-widest uppercase">
      Loading trend map…
    </div>
  )
}

export function MapError() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-24 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-neutral-500 mb-3">
        Map unavailable
      </p>
      <h1 className="font-editorial text-3xl text-cream">
        Couldn&rsquo;t load the map.
      </h1>
      <p className="mt-4 text-neutral-400 text-sm">
        The app couldn&rsquo;t reach <code>/api/map</code>. Check that the
        frontend&rsquo;s <code>BACKEND_ORIGIN</code> points at the backend (the
        Next.js proxy target) and that the database has a <code>map</code>{' '}
        document. See the browser console for the exact error.
      </p>
    </div>
  )
}
