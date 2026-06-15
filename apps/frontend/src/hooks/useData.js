import { useState, useEffect } from 'react'

const cache = {}

// Same-origin only. The browser fetches /api/<name> from the frontend's own
// origin; Next.js (see next.config.mjs `rewrites`) proxies that to the backend
// server-side. So there is no cross-origin request and no CORS — and no public
// backend URL is baked into the client bundle.
export function useData(file) {
  const [data, setData] = useState(cache[file] || null)
  const [loading, setLoading] = useState(!cache[file])

  useEffect(() => {
    if (cache[file]) return
    const url = `/api/${file.replace(/\.json$/, '')}`
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`${url} → ${r.status}`); return r.json() })
      .then(d => { cache[file] = d; setData(d); setLoading(false) })
      .catch(err => { console.error('useData fetch failed:', err); setLoading(false) })
  }, [file])

  return { data, loading }
}
