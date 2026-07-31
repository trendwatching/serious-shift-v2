import { useEffect, useState } from 'react'

/**
 * useData — read a JSON document from the API, once.
 *
 * Same-origin only: the browser fetches /api/<name> from the frontend's own
 * origin and Next proxies it to the backend server-side (see next.config.mjs
 * rewrites), so there is no CORS and no backend URL in the client bundle.
 *
 * Requests are de-duplicated across components. Several components subscribe to
 * the map document, and without this every one of them would open its own
 * connection for the same bytes; instead the first caller starts the request and
 * the rest await the same promise. The settled result (success *or* failure) is
 * cached, so a failing endpoint is not retried on every re-render.
 */
const cache = new Map()     // url → { data } | { error }
const inflight = new Map()  // url → Promise<{ data } | { error }>

function load(url) {
  if (cache.has(url)) return Promise.resolve(cache.get(url))

  let pending = inflight.get(url)
  if (!pending) {
    pending = fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${url} → ${r.status}`)
        return r.json()
      })
      .then((data) => ({ data }))
      .catch((error) => ({ error }))
      .then((result) => {
        cache.set(url, result)
        inflight.delete(url)
        return result
      })
    inflight.set(url, pending)
  }
  return pending
}

export function useData(file) {
  const url = `/api/${String(file).replace(/\.json$/, '')}`
  const [result, setResult] = useState(() => cache.get(url))

  useEffect(() => {
    if (cache.has(url)) {
      setResult(cache.get(url))
      return
    }
    let alive = true
    load(url).then((r) => { if (alive) setResult(r) })
    return () => { alive = false }
  }, [url])

  return {
    data: result?.data ?? null,
    error: result?.error ?? null,
    loading: !result,
  }
}
