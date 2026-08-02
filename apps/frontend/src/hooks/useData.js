import { useCallback, useEffect, useMemo, useState } from 'react'

const cache = new Map()     // url → successful data only
const inflight = new Map()  // url → Promise<data>

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export class ApiError extends Error {
  constructor(url, status = 0, code = '', kind = '') {
    super(status ? `${url} → ${status}` : `${url} → network error`)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.kind = kind || (status === 503 || code === 'unavailable'
      ? 'unavailable'
      : status === 408 || status === 504
        ? 'timeout'
        : status >= 500
        ? 'server'
          : status === 0
            ? 'offline'
            : 'request')
  }
}

function normaliseUrl(resource) {
  const value = String(resource || '')
  if (value.startsWith('/api/')) return value
  return `/api/${value.replace(/^\/+/, '').replace(/\.json$/, '')}`
}

function transient(error) {
  return !error?.status || error.status === 408 || error.status === 429 || error.status >= 500
}

async function fetchJson(url) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  let response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' }, signal: controller.signal })
  } catch (cause) {
    const timedOut = cause?.name === 'AbortError'
    throw new ApiError(url, 0, timedOut ? 'timeout' : 'network_error', timedOut ? 'timeout' : 'offline')
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) {
    let code = ''
    try { code = (await response.json())?.error?.code || '' } catch { /* non-JSON error */ }
    throw new ApiError(url, response.status, code)
  }
  return response.json()
}

/** Load once, retrying only transient failures. Rejections are never cached. */
export function load(resource, { force = false } = {}) {
  const url = normaliseUrl(resource)
  if (!force && cache.has(url)) return Promise.resolve(cache.get(url))

  let pending = inflight.get(url)
  if (!pending) {
    pending = (async () => {
      let lastError
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const data = await fetchJson(url)
          cache.set(url, data)
          return data
        } catch (error) {
          lastError = error
          if (!transient(error) || attempt === 2) throw error
          await wait(150 * (2 ** attempt))
        }
      }
      throw lastError
    })().finally(() => inflight.delete(url))
    inflight.set(url, pending)
  }
  return pending
}

export function useData(resource, { enabled = true } = {}) {
  const url = useMemo(() => normaliseUrl(resource), [resource])
  const [result, setResult] = useState(() => (
    enabled && cache.has(url) ? { data: cache.get(url), error: null } : null
  ))
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!enabled) {
      setResult(null)
      return undefined
    }
    let alive = true
    const cached = cache.get(url)
    setResult(cached ? { data: cached, error: null } : null)
    load(url, { force: revision > 0 })
      .then((data) => { if (alive) setResult({ data, error: null }) })
      .catch((error) => { if (alive) setResult((current) => ({ data: current?.data || cached || null, error })) })
    return () => { alive = false }
  }, [enabled, revision, url])

  const retry = useCallback(() => setRevision((value) => value + 1), [])

  return {
    data: result?.data ?? null,
    error: result?.error ?? null,
    loading: enabled && !result,
    retry,
  }
}

export function __resetDataCacheForTests() {
  cache.clear()
  inflight.clear()
}
